"""Synthetic exact-delta and PVID regressions; no live qualification."""

from typing import Any

import pytest

import port_description as evidence
import standby_native_observation as engine
import trunk_link_admission
import trunk_observation
import trunk_plan

BASELINE = (
    f"ver {trunk_plan.RELEASE}",
    "!",
    "vlan 1 name DEFAULT-VLAN by port",
    " untagged ethe 1/2/2 1/2/6 1/3/1",
    "!",
    "vlan 132 name DEFAULT-DECKPIN by port",
    " tagged ethe 1/1/48",
    " spanning-tree",
    "!",
    "interface ethernet 1/2/2",
    " port-name primary",
    "!",
    "ip route 0.0.0.0/0 192.168.0.1",
    "end",
)
EXISTING = (
    *BASELINE[:12],
    engine.INTERFACE,
    " port-name standby",
    " mtu 9000",
    "!",
    *BASELINE[12:],
)
VLAN = ("vlan 10 name LAB-MGMT by port", " tagged ethe 1/2/6", "!")
INTERFACE = (engine.INTERFACE, engine.NATIVE_LEAF, "!")


def insert(baseline: tuple[str, ...], *lines: str, index: int = 9) -> tuple[str, ...]:
    return (*baseline[:index], *lines, *baseline[index:])


def classify(
    running: tuple[str, ...],
    *,
    baseline: tuple[str, ...] = BASELINE,
    startup: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    return engine._classify_observation(
        baseline,
        running,
        baseline if startup is None else startup,
        baseline_sha256=evidence.configuration_hash(baseline),
    )


def test_public_api_cannot_substitute_synthetic_baseline() -> None:
    with pytest.raises(evidence.Rejected, match="fixed baseline drift"):
        engine.classify_observation(BASELINE, BASELINE, BASELINE)


@pytest.mark.parametrize("baseline", [BASELINE, EXISTING])
def test_unchanged_and_exact_hashes(baseline: tuple[str, ...]) -> None:
    result = classify(baseline, baseline=baseline)
    assert result["classification"] == "unchanged"
    assert result["tagged_standby"] is False
    assert result["native_mode"] is False
    assert result["execution_qualified"] is False
    assert result["live_admission"] is False
    for name in ("baseline_sha256", "running_sha256", "startup_sha256"):
        assert result[name] == evidence.configuration_hash(baseline)


@pytest.mark.parametrize(
    "leaves", [(), (" tagged ethernet 1/2/6",), (" tagged ethe 1/2/6",)]
)
def test_created_and_tagged_phases(leaves: tuple[str, ...]) -> None:
    running = insert(BASELINE, VLAN[0], *leaves, "!")
    result = classify(running)
    assert result["vlan_present"] is True
    assert result["tagged_standby"] is bool(leaves)
    assert result["native_mode"] is False
    assert result["classification"] == (
        "tagged_candidate" if leaves else "partial_candidate"
    )


@pytest.mark.parametrize("index", [2, 4, 5, 8, 9, 11, 12, 13])
@pytest.mark.parametrize("separator", [False, True])
def test_inserted_native_stanza_preserves_every_baseline_line(
    index: int, separator: bool
) -> None:
    running = insert(
        BASELINE, *(INTERFACE if separator else INTERFACE[:-1]), index=index
    )
    result = classify(running)
    assert result["native_mode"] is True
    assert result["tagged_standby"] is False
    assert result["running_sha256"] == evidence.configuration_hash(running)


@pytest.mark.parametrize("leaf_index", [13, 14, 15])
def test_native_leaf_in_existing_stanza_retains_other_leaves(leaf_index: int) -> None:
    native = insert(EXISTING, engine.NATIVE_LEAF, index=leaf_index)
    running = insert(native, *VLAN)
    result = classify(running, baseline=EXISTING)
    assert result["native_mode"] is True
    assert result["tagged_standby"] is True
    assert result["running_sha256"] == evidence.configuration_hash(running)


def test_inserted_vlan_and_native_stanza() -> None:
    result = classify(insert(BASELINE, *VLAN, *INTERFACE))
    assert result["classification"] == "native_candidate"
    assert result["tagged_standby"] is True
    assert result["native_mode"] is True
    assert result["live_admission"] is False


@pytest.mark.parametrize(
    "lines",
    [
        (VLAN[0], " tagged ethe 1/2/2", "!"),
        (VLAN[0], " tagged ethe 1/3/1", "!"),
        (VLAN[0], " tagged ethe 1/2/6 ethe 1/2/2", "!"),
        (VLAN[0], " tagged ethe 1/2/6 1/2/6", "!"),
        (VLAN[0], " tagged ethe 1/2/6", " tagged ethernet 1/2/6", "!"),
        (VLAN[0], " untagged ethe 1/2/6", "!"),
        (VLAN[0], " tagged ethe 1/2/6", " spanning-tree", "!"),
        ("vlan 20 name LAB-DEV by port", "!"),
        ("vlan 10 name WRONG by port", "!"),
        (*VLAN, *VLAN),
        (engine.INTERFACE, "!"),
        (engine.INTERFACE, " dual-mode 1", "!"),
        (engine.INTERFACE, " dual-mode 10", "!"),
        (engine.INTERFACE, engine.NATIVE_LEAF, " dual-mode 1", "!"),
        (engine.INTERFACE, " dual-mode 1", engine.NATIVE_LEAF, "!"),
        (engine.INTERFACE, engine.NATIVE_LEAF, " mtu 9000", "!"),
        (engine.INTERFACE, engine.NATIVE_LEAF, engine.NATIVE_LEAF, "!"),
        (*INTERFACE, *INTERFACE),
        ("interface ethernet 1/2/2", engine.NATIVE_LEAF, "!"),
        ("interface ethernet 1/3/1", engine.NATIVE_LEAF, "!"),
        ("interface ethe 1/2/6", engine.NATIVE_LEAF, "!"),
        (engine.NATIVE_LEAF,),
    ],
)
def test_unowned_delta_rejects(lines: tuple[str, ...]) -> None:
    with pytest.raises(evidence.Rejected):
        classify(insert(BASELINE, *lines))


@pytest.mark.parametrize(
    "leaf",
    [
        " dual-mode 1",
        " dual-mode 10",
        "  dual-mode",
        " dual-mode ",
        "  dual-mode 1",
        " dual-mode 1 ",
        " dual-mode 1 vlan 10",
        " no dual-mode 1",
        " disable",
        " mtu 1500",
    ],
)
def test_extra_or_mutated_existing_interface_leaf_rejects(leaf: str) -> None:
    running = insert(EXISTING, engine.NATIVE_LEAF, leaf, index=14)
    with pytest.raises(evidence.Rejected):
        classify(running, baseline=EXISTING)


@pytest.mark.parametrize("index", [0, 3, 6, 7, 10])
def test_native_stanza_insertion_inside_baseline_block_rejects(index: int) -> None:
    with pytest.raises(evidence.Rejected):
        classify(insert(BASELINE, *INTERFACE, index=index))


def test_native_leaf_in_unrelated_existing_interface_rejects() -> None:
    with pytest.raises(evidence.Rejected):
        classify(insert(EXISTING, engine.NATIVE_LEAF, index=11), baseline=EXISTING)


def test_ambiguous_separator_ownership_across_two_owned_insertions_rejects() -> None:
    running = (*BASELINE[:8], *VLAN, *INTERFACE, *BASELINE[9:])
    with pytest.raises(evidence.Rejected, match="ambiguous insertion"):
        classify(running)


@pytest.mark.parametrize(
    "old,new",
    [
        ("vlan 1 name DEFAULT-VLAN by port", "vlan 1 name CHANGED by port"),
        (" untagged ethe 1/2/2 1/2/6 1/3/1", " untagged ethe 1/2/2 1/3/1"),
        (" tagged ethe 1/1/48", " tagged ethe 1/1/47"),
        (" spanning-tree", " spanning-tree 802-1w"),
        (" port-name standby", " port-name changed"),
        (" mtu 9000", " mtu 1500"),
        ("ip route 0.0.0.0/0 192.168.0.1", "ip route 0.0.0.0/0 192.168.0.2"),
    ],
)
def test_unrelated_baseline_mutation_rejects(old: str, new: str) -> None:
    running = insert(insert(EXISTING, engine.NATIVE_LEAF, index=14), *VLAN)
    changed = tuple(new if line == old else line for line in running)
    with pytest.raises(evidence.Rejected):
        classify(changed, baseline=EXISTING)


def test_reordered_baseline_and_saved_candidate_reject() -> None:
    running = insert(BASELINE, *VLAN, *INTERFACE)
    with pytest.raises(evidence.Rejected, match="startup"):
        classify(running, startup=running)
    reordered = list(running)
    reordered[6], reordered[7] = reordered[7], reordered[6]
    with pytest.raises(evidence.Rejected):
        classify(tuple(reordered))


@pytest.mark.parametrize(
    "bad",
    [
        ("end",),
        BASELINE[:-1],
        (*BASELINE, "end"),
        (*BASELINE[:-1], "", "end"),
        (*BASELINE[:-1], "end "),
    ],
)
def test_full_canonical_configuration_required(bad: tuple[str, ...]) -> None:
    for running, startup in ((bad, BASELINE), (BASELINE, bad)):
        with pytest.raises(evidence.Rejected):
            classify(running, startup=startup)


def test_existing_full_trunk_profile_does_not_accept_native_delta() -> None:
    with pytest.raises(evidence.Rejected):
        trunk_observation._classify_observation(
            BASELINE,
            insert(BASELINE, *VLAN, *INTERFACE),
            BASELINE,
            baseline_sha256=evidence.configuration_hash(BASELINE),
        )


def brief(*, tag: str = "No", pvid: str = "1") -> str:
    return "\n".join(
        (
            trunk_link_admission.HEADER,
            *(
                f"{port} Up Forward Full {trunk_link_admission.EXPECTED_SPEEDS[port]} None {tag if port == engine.STANDBY_PORT else 'No'} {pvid if port == engine.STANDBY_PORT else '1'} 0 748e.f8e7.8d50"
                if port in trunk_link_admission.EXPECTED_SPEEDS
                else f"{port} Down None None None None No 1 0 748e.f8e7.8d50"
                for port in sorted(trunk_link_admission.PHYSICAL_PORTS)
            ),
            "mgmt1 Down None None None None No None 0 748e.f8e7.8d50",
        )
    )


@pytest.mark.parametrize(
    "phase,tag,pvid",
    [
        ("baseline", "No", "1"),
        ("standby", "Yes", "N/A"),
        ("standby", "Yes", "1"),
        ("native", "Yes", "1"),
    ],
)
def test_operational_exact_phase_states(phase: str, tag: str, pvid: str) -> None:
    engine.require_operational_state(brief(tag=tag, pvid=pvid), phase=phase)


@pytest.mark.parametrize("phase", ["standby", "native"])
@pytest.mark.parametrize("pvid", ["0", "2", "10", "132", "4095", "01", "unknown"])
def test_arbitrary_numeric_or_noncanonical_pvid_rejects(phase: str, pvid: str) -> None:
    with pytest.raises(evidence.Rejected):
        engine.require_operational_state(brief(tag="Yes", pvid=pvid), phase=phase)


@pytest.mark.parametrize(
    "phase,tag,pvid",
    [
        ("native", "Yes", "N/A"),
        ("native", "No", "1"),
        ("standby", "No", "1"),
        ("baseline", "Yes", "1"),
    ],
)
def test_wrong_phase_state_rejects(phase: str, tag: str, pvid: str) -> None:
    with pytest.raises(evidence.Rejected):
        engine.require_operational_state(brief(tag=tag, pvid=pvid), phase=phase)


@pytest.mark.parametrize("port", ["1/2/2", "1/3/1", "1/2/6"])
@pytest.mark.parametrize(
    "mutation", ["blocked", "listen", "down", "speed", "missing", "duplicate"]
)
def test_operational_paths_require_complete_up_forward_table(
    port: str, mutation: str
) -> None:
    lines = brief(tag="Yes").splitlines()
    index = next(i for i, line in enumerate(lines) if line.startswith(port + " "))
    if mutation == "blocked":
        lines[index] = lines[index].replace("Up Forward", "Up Blocked")
    elif mutation == "listen":
        lines[index] = lines[index].replace("Up Forward", "Up Listen")
    elif mutation == "down":
        lines[index] = lines[index].replace("Up Forward Full", "Down None None")
    elif mutation == "speed":
        lines[index] = lines[index].replace(
            trunk_link_admission.EXPECTED_SPEEDS[port], "1G"
        )
    elif mutation == "missing":
        lines.pop(index)
    else:
        lines.append(lines[index])
    with pytest.raises(evidence.Rejected):
        engine.require_operational_state("\n".join(lines), phase="native")


@pytest.mark.parametrize("port", ["1/2/2", "1/3/1"])
@pytest.mark.parametrize("membership", ["Yes 1", "No N/A", "No 10", "Yes N/A"])
def test_primary_gateway_native_membership_required(port: str, membership: str) -> None:
    lines = brief(tag="Yes").splitlines()
    index = next(i for i, line in enumerate(lines) if line.startswith(port + " "))
    lines[index] = lines[index].replace("No 1", membership)
    with pytest.raises(evidence.Rejected, match="primary and gateway"):
        engine.require_operational_state("\n".join(lines), phase="native")


def test_complete_table_and_known_phase_required() -> None:
    with pytest.raises(evidence.Rejected):
        engine.require_operational_state(
            brief().replace("mgmt1 Down", "mgmt2 Down"), phase="baseline"
        )
    with pytest.raises(evidence.Rejected, match="unknown"):
        engine.require_operational_state(brief(), phase="arbitrary")


def test_actual_implicit_serialization_is_configuration_only() -> None:
    # ICX6610-48P 08.0.30uT7f3: native-observe-q7fujhtt configuration capture.
    assert engine.NATIVE_LEAF == " dual-mode"
    running = insert(BASELINE, *VLAN, engine.INTERFACE, " dual-mode", "!")
    result = classify(running)
    assert result["classification"] == "native_candidate"
    assert result["running_sha256"] == evidence.configuration_hash(running)
    assert result["startup_sha256"] == evidence.configuration_hash(BASELINE)
    assert result["execution_qualified"] is False
    assert result["live_admission"] is False
    assert (
        "configuration observations do not prove native membership or PVID"
        in result["limitations"]
    )


@pytest.mark.parametrize("leaf", [" dual-mode 1", " dual-mode 10", " dual-mode 132"])
def test_numeric_serialization_alone_in_existing_stanza_is_unsupported(
    leaf: str,
) -> None:
    running = insert(EXISTING, leaf, index=14)
    with pytest.raises(evidence.Rejected):
        classify(running, baseline=EXISTING)
