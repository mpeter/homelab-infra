"""Configuration preservation, native membership and forwarding regressions."""

from dataclasses import replace
import re

import pytest

import bond_vlan_membership as membership
import native_trunk_observation as observer
import native_trunk_plan as plan
import port_description as evidence
from test_bond_vlan_membership import AFTER1, AFTER132
from test_standby_native_observation import BASELINE, EXISTING, brief
from test_standby_native_membership import SYNTHETIC10


def running(state: plan.State, baseline: tuple[str, ...]) -> tuple[str, ...]:
    lines = list(baseline)
    for port in state.native:
        header = f"interface ethernet {port}"
        if header in lines:
            lines.insert(lines.index(header) + 1, " dual-mode")
        else:
            index = lines.index("ip route 0.0.0.0/0 192.168.0.1")
            lines[index:index] = [header, " dual-mode", "!"]
    additions = [
        line
        for vlan, ports in state.vlans
        for line in (
            f"vlan {vlan} name {dict(plan.VLANS)[vlan]} by port",
            *(f" tagged ethe {port}" for port in ports),
            "!",
        )
    ]
    lines[9:9] = additions
    return tuple(lines)


def classify(
    state: plan.State, baseline: tuple[str, ...] = BASELINE
) -> observer.Observation:
    return observer._classify_observation(
        baseline,
        running(state, baseline),
        baseline,
        baseline_sha256=evidence.configuration_hash(baseline),
    )


def r8_probe_running(state: plan.State, baseline: tuple[str, ...]) -> tuple[str, ...]:
    lines = list(baseline)
    if 60 in dict(state.vlans):
        index = lines.index("end")
        stanza = ["vlan 60 name M7-QUALIFY by port"]
        if state.tagged(60):
            stanza.append(" tagged ethe 1/2/2")
        stanza.append("!")
        lines[index:index] = stanza
    return tuple(lines)


def operational(state: plan.State) -> str:
    text = brief()
    rows = []
    for line in text.splitlines():
        words = line.split()
        if words and words[0] in plan.PORTS:
            words[6] = (
                "Yes" if any(words[0] in ports for _, ports in state.vlans) else "No"
            )
            words[7] = "1"
            line = " ".join(words)
        rows.append(line)
    return "\n".join(rows)


def tables(state: plan.State) -> dict[int, str]:
    total = 2 + sum(bool(ports) for _, ports in state.vlans)
    one = observer.parse_vlan(AFTER1, 1, total=2)
    tagged = {observer._port(port) for port in state.tagged(10)}
    one = replace(
        one,
        untagged=tuple(p for p in one.untagged if p not in tagged),
        dual_mode=tuple(observer._port(p) for p in state.native),
    )
    legacy = observer.parse_vlan(AFTER132, 132, total=2)

    def render(facts: membership.VlanMembership) -> str:
        result = [
            f"Total PORT-VLAN entries: {total}",
            "Maximum PORT-VLAN entries: 64",
            "Legend: [Stk=Stack-Id, S=Slot]",
            f"PORT-VLAN {facts.vlan}, Name {facts.name}, Priority level0, Spanning tree {facts.spanning_tree}",
        ]
        for label, ports in zip(
            membership.LABELS,
            (
                facts.untagged,
                facts.tagged,
                facts.uplink,
                facts.dual_mode,
                facts.mac_vlan,
            ),
            strict=True,
        ):
            if not ports:
                result.append(f"{label} Ports: None")
            else:
                for slot in (1, 2, 3):
                    numbers = [str(p[2]) for p in ports if p[1] == slot]
                    if numbers:
                        result.append(
                            f"{label} Ports: (U1/M{slot}) " + " ".join(numbers)
                        )
        return "\n".join([*result, "Monitoring: Disabled"])

    result = {1: render(one), 132: render(legacy)}
    for vlan, name in plan.VLANS:
        ports = state.tagged(vlan)
        result[vlan] = (
            render(
                membership.VlanMembership(
                    vlan,
                    name,
                    (),
                    tuple(observer._port(p) for p in ports),
                    (),
                    (),
                    (),
                    spanning_tree="Off",
                )
            )
            if ports
            else f"Port-vlan {vlan} does not have any members."
            if vlan in dict(state.vlans)
            else f"Error - port-vlan {vlan} does not exist."
        )
    return result


def r8_tables(state: plan.State) -> dict[str, str]:
    result = {str(vlan): text for vlan, text in tables(state).items()}
    rows = []
    for line in result["1"].splitlines():
        if line.startswith("Untagged Ports: (U1/M2) "):
            ports = [
                port
                for port in line.removeprefix("Untagged Ports: (U1/M2) ").split()
                if port != "2"
            ]
            primary_tagged = any("1/2/2" in members for _, members in state.vlans)
            if "1/2/2" not in state.native and not primary_tagged:
                ports.append("2")
                ports.sort(key=int)
            line = (
                "Untagged Ports: (U1/M2) " + " ".join(ports)
                if ports
                else "Untagged Ports: None"
            )
        rows.append(line)
    result["1"] = "\n".join(rows)
    return result


def r8_operational(state: plan.State) -> str:
    rows = []
    for line in operational(state).splitlines():
        words = line.split()
        if words and words[0] == plan.R8_PRIMARY_PORT:
            words[1:6] = ["Down", "None", "None", "None", "None"]
            words[7] = (
                "N/A"
                if "1/2/2" not in state.native
                and any("1/2/2" in members for _, members in state.vlans)
                else "1"
            )
            line = " ".join(words)
        rows.append(line)
    return "\n".join(rows)


def r8_fixture() -> tuple[str, ...]:
    vlans = tuple(
        line
        for vlan, name in plan.VLANS
        for line in (
            f"vlan {vlan} name {name} by port",
            " tagged ethe 1/2/6 1/2/2 1/3/1",
            "!",
        )
    )
    lines = list(EXISTING)
    for port in ("1/2/2", "1/2/6"):
        header = f"interface ethernet {port}"
        lines.insert(lines.index(header) + 1, " dual-mode")
    route = lines.index("ip route 0.0.0.0/0 192.168.0.1")
    return (
        *lines[:9],
        *vlans,
        *lines[9:route],
        "interface ethernet 1/3/1",
        " dual-mode",
        "!",
        *lines[route:],
    )


def r8_running(state: plan.State, baseline: tuple[str, ...]) -> tuple[str, ...]:
    result: list[str] = []
    index = 0
    targets = dict(plan.VLANS)
    while index < len(baseline):
        match = re.fullmatch(
            r"vlan ([0-9]+) name ([A-Za-z0-9_-]+) by port", baseline[index]
        )
        if match is None or int(match[1]) not in targets:
            result.append(baseline[index])
            index += 1
            continue
        vlan = int(match[1])
        result.append(baseline[index])
        stanza_start = index
        index += 1
        while index < len(baseline) and baseline[index].startswith(" "):
            index += 1
        ports = dict(state.vlans)[vlan]
        original_ports = tuple(
            baseline[stanza_start + 1].removeprefix(" tagged ethe ").split()
        )
        if set(ports) == set(original_ports):
            result.extend(baseline[stanza_start + 1 : index])
        elif ports:
            result.append(" tagged ethe " + " ".join(ports))
        continue
    for port in plan.PORTS:
        header = f"interface ethernet {port}"
        if port == plan.R8_PRIMARY_PORT and port not in state.native:
            start = result.index(header)
            end = next(
                (
                    index
                    for index in range(start + 1, len(result))
                    if result[index] == "!"
                ),
                len(result),
            )
            del result[start : min(end + 1, len(result))]
            continue
        start = result.index(header) + 1
        end = next(
            (index for index in range(start, len(result)) if result[index] == "!"),
            len(result),
        )
        result[start:end] = [
            line
            for line in result[start:end]
            if not line.lstrip().startswith("dual-mode")
        ]
        if port in state.native:
            result.insert(start, " dual-mode")
    return tuple(result)


def test_r8_full_trunk_observes_every_primary_tag_inverse(monkeypatch) -> None:
    baseline = r8_fixture()
    monkeypatch.setattr(
        plan, "R8_BASELINE_SHA256", evidence.configuration_hash(baseline)
    )
    selected = plan.build_r8_full_trunk_plan(baseline, baseline)
    forward = plan._states(plan.R8_FULL_FORWARD, selected.initial_state)
    inverse = plan._states(plan.R8_FULL_INVERSE, forward[-1])

    for completed, state in enumerate(forward):
        observed = observer.classify_r8_full_trunk_observation(
            baseline, r8_running(state, baseline), baseline
        )
        observer.require_r8_full_trunk_state(
            observed,
            completed=completed,
            initial_state=selected.initial_state,
        )
        observer.require_r8_full_trunk_membership(
            r8_tables(state),
            r8_tables(selected.initial_state),
            state,
            selected.initial_state,
        )
        observer.require_r8_full_trunk_operational_state(r8_operational(state), state)
    for completed, state in enumerate(inverse):
        observed = observer.classify_r8_full_trunk_observation(
            baseline, r8_running(state, baseline), baseline
        )
        observer.require_r8_full_trunk_state(
            observed,
            completed=completed,
            inverse=True,
            initial_state=selected.initial_state,
        )
    restored = observer.classify_r8_full_trunk_observation(
        baseline, r8_running(inverse[-1], baseline), baseline
    )
    observer.require_r8_full_trunk_restored(
        restored, evidence.configuration_hash(baseline)
    )

    for state in forward[1:]:
        if state == selected.initial_state:
            continue
        inverse_commands = plan.r8_full_inverse_commands(state)
        restored_state = plan._states(inverse_commands, state)[-1]
        assert restored_state == selected.initial_state

    reordered = list(baseline)
    vlan_index = reordered.index("vlan 10 name LAB-MGMT by port")
    tagged = next(
        i
        for i in range(vlan_index + 1, len(reordered))
        if reordered[i].startswith(" tagged ethe ")
    )
    reordered[tagged] = " tagged ethe 1/2/2 1/2/6 1/3/1"
    membership_equivalent = observer.classify_r8_full_trunk_observation(
        baseline, tuple(reordered), baseline
    )
    with pytest.raises(evidence.Rejected, match="exact configuration restoration"):
        observer.require_r8_full_trunk_restored(
            membership_equivalent, evidence.configuration_hash(baseline)
        )

    drifted = tuple(
        " port-name drift" if line == " port-name standby" else line
        for line in r8_running(forward[-1], baseline)
    )
    with pytest.raises(evidence.Rejected, match="unrelated configuration drift"):
        observer.classify_r8_full_trunk_observation(baseline, drifted, baseline)
    with pytest.raises(evidence.Rejected, match="running and startup differ"):
        observer.classify_r8_full_trunk_observation(
            baseline,
            r8_running(forward[-1], baseline),
            r8_running(forward[-1], baseline),
        )


@pytest.mark.parametrize("inverse,count", [(False, 36), (True, 22)])
@pytest.mark.parametrize("baseline", [BASELINE, EXISTING])
def test_every_command_cumulative_state_preserves_baseline(
    inverse: bool, count: int, baseline: tuple[str, ...]
) -> None:
    for completed in range(count):
        state = plan.expected_state(completed, inverse=inverse)
        result = classify(state, baseline)
        observer.require_state(result, completed=completed, inverse=inverse)
        observer.require_operational_state(
            operational(state), completed=completed, inverse=inverse
        )
        observer.require_membership(
            tables(state),
            baseline_vlan1=AFTER1,
            baseline_vlan132=AFTER132,
            completed=completed,
            inverse=inverse,
        )
        assert result.execution_qualified is False and result.live_admission is False


@pytest.mark.parametrize("completed", [7, 13, 19])
def test_settled_phase_requires_native_not_tag_only(completed: int) -> None:
    state = plan.expected_state(completed)
    observer.require_settled_native_phase(
        classify(state), operational(state), completed=completed, elapsed_seconds=35
    )
    tagged_only = replace(
        state,
        native=tuple(
            port for port in state.native if port != plan.NATIVE_PHASE_ENDS[completed]
        ),
    )
    with pytest.raises(evidence.Rejected):
        observer.require_settled_native_phase(
            classify(tagged_only),
            operational(tagged_only),
            completed=completed,
            elapsed_seconds=35,
        )


@pytest.mark.parametrize("elapsed", [0, 34.9, 90.1, float("nan"), float("inf")])
def test_hold_is_bounded(elapsed: float) -> None:
    state = plan.expected_state(7)
    with pytest.raises(evidence.Rejected):
        observer.require_settled_native_phase(
            classify(state), operational(state), completed=7, elapsed_seconds=elapsed
        )


def test_startup_and_unrelated_config_drift_rejected() -> None:
    current = running(plan.FINAL_STATE, EXISTING)
    for changed, startup in [
        (current, current),
        (current[:-1] + ("ip route 10.0.0.0/8 192.168.0.1", "end"), EXISTING),
        (tuple(x.replace(" mtu 9000", " mtu 1500") for x in current), EXISTING),
        (
            tuple(
                x.replace(" tagged ethe 1/1/48", " tagged ethe 1/1/47") for x in current
            ),
            EXISTING,
        ),
    ]:
        with pytest.raises(evidence.Rejected):
            observer._classify_observation(
                EXISTING,
                changed,
                startup,
                baseline_sha256=evidence.configuration_hash(EXISTING),
            )


@pytest.mark.parametrize(
    "leaf", [" dual-mode 2", " dual-mode\n dual-mode", " shutdown"]
)
def test_unsupported_native_serialization_rejected(leaf: str) -> None:
    current = tuple(
        x
        for line in running(plan.expected_state(7), BASELINE)
        for x in line.replace(" dual-mode", leaf).splitlines()
    )
    with pytest.raises(evidence.Rejected):
        observer._classify_observation(
            BASELINE,
            current,
            BASELINE,
            baseline_sha256=evidence.configuration_hash(BASELINE),
        )


@pytest.mark.parametrize("port", plan.PORTS)
@pytest.mark.parametrize("mutation", ["pvid", "stp", "speed", "duplicate"])
def test_each_port_guard(port: str, mutation: str) -> None:
    state = plan.FINAL_STATE
    text = operational(state)
    rows = text.splitlines()
    row = next(line for line in rows if line.split() and line.split()[0] == port)
    words = row.split()
    if mutation == "duplicate":
        changed = text + "\n" + row
    else:
        words[{"pvid": 7, "stp": 2, "speed": 4}[mutation]] = {
            "pvid": "10",
            "stp": "Blocked",
            "speed": "1G",
        }[mutation]
        changed = text.replace(row, " ".join(words))
    with pytest.raises(evidence.Rejected):
        observer.require_operational_state(changed, completed=35)


@pytest.mark.parametrize(
    "mutation", ["native", "legacy", "foreign", "missing", "count", "stp"]
)
def test_complete_vlan_guards(mutation: str) -> None:
    current = tables(plan.FINAL_STATE)
    if mutation == "native":
        current[1] = current[1].replace(
            "DualMode Ports: (U1/M3) 1", "DualMode Ports: None"
        )
    elif mutation == "legacy":
        current[132] = current[132].replace("(U1/M1) 48", "(U1/M1) 47")
    elif mutation == "foreign":
        current[999] = SYNTHETIC10
    elif mutation == "missing":
        del current[30]
    elif mutation == "count":
        current[40] = current[40].replace("entries: 6", "entries: 5")
    else:
        current[20] = current[20].replace("Spanning tree Off", "Spanning tree On")
    with pytest.raises(evidence.Rejected):
        observer.require_membership(
            current, baseline_vlan1=AFTER1, baseline_vlan132=AFTER132, completed=35
        )


def test_public_classifier_rejects_fixture_baseline() -> None:
    with pytest.raises(evidence.Rejected, match="fixed baseline drift"):
        observer.classify_observation(BASELINE, BASELINE, BASELINE)


@pytest.mark.parametrize("inverse", [False, True])
def test_r8_probe_observes_each_forward_and_inverse_state(inverse: bool) -> None:
    baseline = EXISTING
    baseline_hash = evidence.configuration_hash(baseline)
    origins = plan.R8_PROBE_FORWARD_STATES if inverse else (None,)
    for origin in origins:
        initial = plan.R8_PROBE_FINAL_STATE if origin is None else origin
        states = (
            plan._states(plan.r8_probe_inverse_commands(initial), initial)
            if inverse
            else plan.R8_PROBE_FORWARD_STATES
        )
        for completed, state in enumerate(states):
            observed = observer._classify_r8_probe_observation(
                baseline,
                r8_probe_running(state, baseline),
                baseline,
                baseline_sha256=baseline_hash,
            )
            observer.require_r8_probe_state(
                observed,
                completed=completed,
                inverse=inverse,
                inverse_initial=initial,
            )
            assert observed.execution_qualified is False
            assert observed.live_admission is False


def test_r8_probe_observation_rejects_unrelated_or_foreign_changes() -> None:
    baseline = EXISTING
    baseline_hash = evidence.configuration_hash(baseline)
    tagged = r8_probe_running(plan.R8_PROBE_FINAL_STATE, baseline)
    for running, startup in (
        (tagged[:-2] + ("ip route 10.0.0.0/8 192.168.0.1", *tagged[-1:]), baseline),
        (tagged, tagged),
        (
            tuple(
                line.replace("tagged ethe 1/2/2", "tagged ethe 1/2/6")
                for line in tagged
            ),
            baseline,
        ),
        (
            tagged[:-2] + ("vlan 60 name M7-QUALIFY by port", *tagged[-2:]),
            baseline,
        ),
    ):
        with pytest.raises(evidence.Rejected):
            observer._classify_r8_probe_observation(
                baseline, running, startup, baseline_sha256=baseline_hash
            )


@pytest.mark.parametrize("completed,inverse", ((13, False), (0, False), (23, True)))
def test_primary_down_restoration_keeps_full_trunk_qualification_closed(
    completed: int, inverse: bool
) -> None:
    state = plan.expected_state(completed, inverse=inverse)
    text = operational(state)
    rows = []
    for line in text.splitlines():
        words = line.split()
        if words and words[0] == "1/2/2":
            words[1:5] = ["Down", "None", "None", "None"]
            line = " ".join(words)
        rows.append(line)
    down = "\n".join(rows)
    observer.require_recovery_operational_state(
        down, completed=completed, inverse=inverse
    )
    with pytest.raises(evidence.Rejected):
        observer.require_recovery_operational_state(
            down.replace("1/2/2 Down", "1/2/2\u00a0Down"),
            completed=completed,
            inverse=inverse,
        )
    with pytest.raises(evidence.Rejected):
        observer.require_operational_state(down, completed=completed, inverse=inverse)
    for port in ("1/2/6", "1/3/1"):
        damaged = down.replace(port + " Up", port + " Down")
        with pytest.raises(evidence.Rejected):
            observer.require_recovery_operational_state(
                damaged, completed=completed, inverse=inverse
            )
    with pytest.raises(evidence.Rejected):
        observer.require_recovery_operational_state(
            down.replace("Down None None None", "Down Blocked None None"),
            completed=completed,
            inverse=inverse,
        )


def primary_down(state: plan.State) -> str:
    return operational(state).replace(
        "1/2/2 Up Forward Full 10G None", "1/2/2 Down None None None None"
    )


@pytest.mark.parametrize("inverse", [False, True])
def test_primary_down_mode_all_partial_states_preserve_membership(
    inverse: bool,
) -> None:
    qualification = plan.Qualification(plan.QualificationMode.PRIMARY_DOWN)
    states = plan.INVERSE_STATES if inverse else plan.FORWARD_STATES
    for completed, state in enumerate(states):
        observed = observer._classify_observation(
            EXISTING,
            running(state, EXISTING),
            EXISTING,
            baseline_sha256=evidence.configuration_hash(EXISTING),
        )
        observer.require_state(observed, completed=completed, inverse=inverse)
        observer.require_operational_state(
            primary_down(state),
            completed=completed,
            inverse=inverse,
            qualification=qualification,
        )
        observer.require_membership(
            tables(state),
            baseline_vlan1=AFTER1,
            baseline_vlan132=AFTER132,
            completed=completed,
            inverse=inverse,
        )
        assert not observed.execution_qualified and not observed.live_admission


@pytest.mark.parametrize("completed", [7, 13, 19])
def test_primary_down_settled_phase_uses_preselected_mode(completed: int) -> None:
    state = plan.expected_state(completed)
    observed = classify(state)
    observer.require_settled_native_phase(
        observed,
        primary_down(state),
        completed=completed,
        elapsed_seconds=35,
        qualification=plan.Qualification(plan.QualificationMode.PRIMARY_DOWN),
    )
    with pytest.raises(evidence.Rejected):
        observer.require_settled_native_phase(
            classify(state),
            primary_down(state),
            completed=completed,
            elapsed_seconds=35,
        )


@pytest.mark.parametrize(
    "before,after",
    [
        ("1/2/2 Down None None None None", "1/2/2 Up Forward Full 10G None"),
        ("1/2/2 Down None None None None", "1/2/2 Down Blocked None None None"),
        ("1/2/2 Down None None None None", "1/2/2 Down None Full None None"),
        ("1/2/2 Down None None None None", "1/2/2 Down None None 10G None"),
        ("1/2/2 Down None None None None", "1/2/2 Down None None None 1"),
        ("1/2/2 Down None None None None Yes 1", "1/2/2 Down None None None None No 1"),
        (
            "1/2/2 Down None None None None Yes 1",
            "1/2/2 Down None None None None Yes 10",
        ),
        ("1/2/6 Up Forward Full 40G", "1/2/6 Up Blocked Full 40G"),
        ("1/2/6 Up Forward Full 40G", "1/2/6 Up Forward Full 10G"),
        ("1/3/1 Up Forward Full 10G", "1/3/1 Down None None None"),
        ("1/3/1 Up Forward Full 10G", "1/3/1 Up Blocked Full 10G"),
    ],
)
def test_primary_down_mode_never_adopts_carrier_or_healthy_port_drift(
    before: str,
    after: str,
) -> None:
    text = primary_down(plan.FINAL_STATE)
    assert before in text
    with pytest.raises(evidence.Rejected):
        observer.require_operational_state(
            text.replace(before, after),
            completed=35,
            qualification=plan.Qualification(plan.QualificationMode.PRIMARY_DOWN),
        )


def test_primary_down_mode_keeps_complete_table_guard() -> None:
    text = primary_down(plan.FINAL_STATE)
    primary = next(line for line in text.splitlines() if line.startswith("1/2/2 "))
    for changed in (text + "\n" + primary, text.replace(primary, "")):
        with pytest.raises(evidence.Rejected):
            observer.require_operational_state(
                changed,
                completed=35,
                qualification=plan.Qualification(plan.QualificationMode.PRIMARY_DOWN),
            )


@pytest.mark.parametrize("character", ["\r", "\u00a0", "\v", "\f", "\x1c", "\x00"])
@pytest.mark.parametrize("location", ["primary", "table"])
def test_primary_down_mode_rejects_raw_text_before_normalization(
    character: str,
    location: str,
) -> None:
    text = primary_down(plan.FINAL_STATE)
    changed = (
        text.replace("1/2/2 Down", "1/2/2" + character + "Down")
        if location == "primary"
        else text.replace("\n", character, 1)
    )
    with pytest.raises(evidence.Rejected, match="trunk interface brief table required"):
        observer.require_operational_state(
            changed,
            completed=35,
            qualification=plan.Qualification(plan.QualificationMode.PRIMARY_DOWN),
        )


def test_primary_down_mode_preserves_valid_crlf_and_tabs() -> None:
    observer.require_operational_state(
        primary_down(plan.FINAL_STATE).replace("\n", "\r\n").replace(" ", "\t"),
        completed=35,
        qualification=plan.Qualification(plan.QualificationMode.PRIMARY_DOWN),
    )


def test_r8_vlan_capture_requires_all_fixed_readbacks_and_raw_capture_digests() -> None:
    payload = {
        "r8_vlan_commands": list(observer.R8_VLAN_COMMANDS),
        "r8_vlan_tables": {str(vlan): f"table {vlan}" for vlan in observer.R8_VLAN_IDS},
        "r8_vlan_capture_sha256": {
            command: "a" * 64 for command in observer.R8_VLAN_COMMANDS
        },
    }
    assert observer.require_r8_vlan_capture(payload) == payload["r8_vlan_tables"]
    for mutate in (
        lambda value: value["r8_vlan_tables"].pop("40"),
        lambda value: value["r8_vlan_capture_sha256"].pop("show vlan 132"),
        lambda value: value["r8_vlan_capture_sha256"].update({"show vlan 132": "bad"}),
        lambda value: value.update({"r8_vlan_commands": ["show vlan 1; write memory"]}),
    ):
        changed = {
            **payload,
            "r8_vlan_tables": dict(payload["r8_vlan_tables"]),
            "r8_vlan_capture_sha256": dict(payload["r8_vlan_capture_sha256"]),
        }
        mutate(changed)
        with pytest.raises(evidence.Rejected):
            observer.require_r8_vlan_capture(changed)
