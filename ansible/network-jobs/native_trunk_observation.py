"""Pure native trunk configuration/table guards; no execution or traffic proof."""

from collections.abc import Mapping
from dataclasses import dataclass, replace
import math
import re
from typing import Any

import bond_vlan_membership as membership
import native_trunk_plan as plan
import port_description as evidence
import standby_native_membership as established
import trunk_link_admission
import trunk_observation
import trunk_plan

NAMES = {1: "DEFAULT-VLAN", 132: "DEFAULT-DECKPIN", **dict(plan.VLANS)}
NATIVE_LEAF = " dual-mode"
R8_VLAN_IDS = (1, 10, 20, 30, 40, 132)
R8_VLAN_COMMANDS = tuple(f"show vlan {vlan}" for vlan in R8_VLAN_IDS)


@dataclass(frozen=True)
class Observation:
    state: plan.State
    baseline_sha256: str
    running_sha256: str
    startup_sha256: str
    execution_qualified: bool = False
    live_admission: bool = False


@dataclass(frozen=True)
class R8ProbeObservation:
    state: plan.State
    baseline_sha256: str
    running_sha256: str
    startup_sha256: str
    execution_qualified: bool = False
    live_admission: bool = False


@dataclass(frozen=True)
class R8FullTrunkObservation:
    state: plan.State
    baseline_sha256: str
    running_sha256: str
    startup_sha256: str
    execution_qualified: bool = False
    live_admission: bool = False


def require_r8_vlan_capture(payload: Any) -> dict[str, str]:
    if not isinstance(payload, Mapping):
        raise evidence.Rejected("R8 VLAN evidence object required")
    tables = payload.get("r8_vlan_tables")
    captures = payload.get("r8_vlan_capture_sha256")
    if (
        payload.get("r8_vlan_commands") != list(R8_VLAN_COMMANDS)
        or not isinstance(tables, Mapping)
        or set(tables) != {str(vlan) for vlan in R8_VLAN_IDS}
        or any(
            not isinstance(value, str) or not value.strip() for value in tables.values()
        )
        or not isinstance(captures, Mapping)
        or set(captures) != set(R8_VLAN_COMMANDS)
        or any(not evidence.valid_digest(value) for value in captures.values())
    ):
        raise evidence.Rejected("complete source-bound R8 VLAN readbacks required")
    return dict(tables)


def classify_r8_full_trunk_observation(
    baseline: tuple[str, ...], running: tuple[str, ...], startup: tuple[str, ...]
) -> R8FullTrunkObservation:
    plan.build_r8_full_trunk_plan(baseline, startup)
    before = trunk_plan._configuration(baseline)
    current = trunk_plan._configuration(running)
    saved = trunk_plan._configuration(startup)
    if saved != before:
        raise evidence.Rejected("startup must remain exact R8 baseline")

    original = trunk_observation._target_stanzas(before)
    observed = trunk_observation._target_stanzas(current)
    targets = {vlan for vlan, _ in plan.VLANS}
    if {int(block[0].split()[1]) for _, block, _ in original.values()} != targets or {
        int(block[0].split()[1]) for _, block, _ in observed.values()
    } != targets:
        raise evidence.Rejected("complete R8 routed VLAN set required")

    def without_targets(
        lines: tuple[str, ...],
        stanzas: dict[int, tuple[int, tuple[str, ...], tuple[str, ...]]],
    ) -> tuple[str, ...]:
        excluded = {
            index
            for start, (end, _, _) in stanzas.items()
            for index in range(start, end)
        }
        primary_header = f"interface ethernet {plan.R8_PRIMARY_PORT}"
        primary_headers = [
            index for index, line in enumerate(lines) if line == primary_header
        ]
        if len(primary_headers) > 1:
            raise evidence.Rejected("duplicate R8 primary interface stanza")
        if primary_headers:
            start = primary_headers[0]
            end = next(
                (
                    index
                    for index in range(start + 1, len(lines))
                    if lines[index] == "!"
                ),
                len(lines),
            )
            leaves = lines[start + 1 : end]
            if leaves in ((" dual-mode",), (" dual-mode", " port-name primary")):
                excluded.update(range(start, min(end + 1, len(lines))))
        result = []
        interface: str | None = None
        for index, line in enumerate(lines):
            if index in excluded:
                continue
            match = re.fullmatch(r"interface ethernet (.+)", line)
            if match:
                interface = match[1]
            elif not line.startswith(" ") and line != "!":
                interface = None
            if interface in plan.PORTS and line.lstrip().startswith("dual-mode"):
                continue
            result.append(line)
        return tuple(result)

    if without_targets(before, original) != without_targets(current, observed):
        raise evidence.Rejected("unrelated configuration drift during R8 trunk cycle")

    native = set()
    for port in plan.PORTS:
        headers = [
            index
            for index, line in enumerate(current)
            if line == f"interface ethernet {port}"
        ]
        if port == plan.R8_PRIMARY_PORT and not headers:
            continue
        if len(headers) != 1:
            raise evidence.Rejected("R8 native interface identity")
        start = headers[0] + 1
        end = next(
            (index for index in range(start, len(current)) if current[index] == "!"),
            len(current),
        )
        leaves = [
            line for line in current[start:end] if line.lstrip().startswith("dual-mode")
        ]
        if leaves not in ([], [" dual-mode"]):
            raise evidence.Rejected("R8 native VLAN leaf")
        if leaves:
            native.add(port)

    state = plan.State(
        tuple(
            sorted(
                (
                    int(block[0].split()[1]),
                    tuple(sorted(members)),
                )
                for _, block, members in observed.values()
            )
        ),
        tuple(sorted(native)),
    )
    if any(
        set(members) not in (set(plan.PORTS), set(plan.PORTS) - {plan.R8_PRIMARY_PORT})
        for _, members in state.vlans
    ):
        raise evidence.Rejected("unrecognized R8 trunk membership delta")
    return R8FullTrunkObservation(
        state,
        evidence.configuration_hash(before),
        evidence.configuration_hash(current),
        evidence.configuration_hash(saved),
    )


def require_r8_full_trunk_state(
    observed: R8FullTrunkObservation,
    *,
    completed: int,
    inverse: bool = False,
    initial_state: plan.State,
) -> None:
    commands = plan.R8_FULL_INVERSE if inverse else plan.R8_FULL_FORWARD
    initial = (
        plan._states(plan.R8_FULL_FORWARD, initial_state)[-1]
        if inverse
        else initial_state
    )
    expected = plan._states(commands, initial)
    if type(completed) is not int or not 0 <= completed < len(expected):
        raise evidence.Rejected("invalid R8 full trunk command count")
    if observed.state != expected[completed]:
        raise evidence.Rejected("R8 full trunk per-command configuration drift")


def require_r8_full_trunk_restored(
    observed: R8FullTrunkObservation, baseline_sha256: str
) -> None:
    if (
        observed.baseline_sha256 != baseline_sha256
        or observed.running_sha256 != baseline_sha256
        or observed.startup_sha256 != baseline_sha256
    ):
        raise evidence.Rejected(
            "R8 full trunk exact configuration restoration required"
        )


def require_r8_full_trunk_operational_state(brief: str, state: plan.State) -> None:
    if (
        not isinstance(brief, str)
        or not brief.isascii()
        or re.search(r"[^\x20-\x7e\r\n\t]", brief)
        or re.search(r"\r(?!\n)", brief)
    ):
        raise evidence.Rejected("R8 full trunk interface brief required")
    rows = [line.split() for line in brief.splitlines() if line.split()]
    primary = [row for row in rows if row[0] == plan.R8_PRIMARY_PORT]
    if (
        len(primary) != 1
        or len(primary[0]) != 10
        or primary[0][1:6] != ["Down", "None", "None", "None", "None"]
    ):
        raise evidence.Rejected("R8 full trunk requires primary link down")
    normalized = []
    for row in rows:
        if row[0] == plan.R8_PRIMARY_PORT:
            row = [*row[:1], "Up", "Forward", "Full", "10G", *row[5:]]
        normalized.append(" ".join(row))
    trunk_link_admission.require_links("\n".join(normalized))
    by_port = {row[0]: row for row in rows if row[0] in plan.PORTS}
    primary_tagged = any(plan.R8_PRIMARY_PORT in ports for _, ports in state.vlans)
    for port in plan.PORTS:
        row = by_port[port]
        expected_tagged = any(port in ports for _, ports in state.vlans)
        expected_pvid = (
            "N/A"
            if port == plan.R8_PRIMARY_PORT
            and port not in state.native
            and primary_tagged
            else "1"
        )
        if row[6] != ("Yes" if expected_tagged else "No") or row[7] != expected_pvid:
            raise evidence.Rejected("R8 full trunk PVID or tag state drift")
        if port != plan.R8_PRIMARY_PORT and row[2] != "Forward":
            raise evidence.Rejected("R8 active trunk path is not forwarding")


class R8PrimaryListening(evidence.Rejected):
    """Only the primary carrier is still settling after restoration."""


def require_r8_full_trunk_restoration_operational_state(
    brief: str, state: plan.State
) -> None:
    if (
        not isinstance(brief, str)
        or not brief.isascii()
        or re.search(r"[^\x20-\x7e\r\n\t]", brief)
        or re.search(r"\r(?!\n)", brief)
    ):
        raise evidence.Rejected("R8 full trunk interface brief required")
    rows = [line.split() for line in brief.splitlines() if line.split()]
    primary = [row for row in rows if row[0] == plan.R8_PRIMARY_PORT]
    if len(primary) != 1 or len(primary[0]) != 10:
        raise evidence.Rejected("R8 restoration primary interface required")
    carrier = primary[0][1:6]
    if carrier not in (
        ["Down", "None", "None", "None", "None"],
        ["Up", "Forward", "Full", "10G", "None"],
        ["Up", "Listen", "Full", "10G", "None"],
    ):
        raise evidence.Rejected("R8 restoration primary carrier drift")
    normalized = []
    for row in rows:
        if row[0] == plan.R8_PRIMARY_PORT:
            row = [*row[:1], "Down", "None", "None", "None", "None", *row[6:]]
        normalized.append(" ".join(row))
    require_r8_full_trunk_operational_state("\n".join(normalized), state)
    if carrier[1] == "Listen":
        raise R8PrimaryListening("R8 restoration primary is still listening")


def require_r8_full_trunk_membership(
    observed: Mapping[str, str],
    baseline: Mapping[str, str],
    state: plan.State,
    initial_state: plan.State,
) -> None:
    """Require complete VLAN table readbacks against the captured R8 baseline."""
    vlan_ids = {1, 132, *(vlan for vlan, _ in plan.VLANS)}
    expected_keys = {str(vlan) for vlan in vlan_ids}
    if (
        not isinstance(observed, Mapping)
        or not isinstance(baseline, Mapping)
        or set(observed) != expected_keys
        or set(baseline) != expected_keys
        or any(
            not isinstance(text, str) or not text.strip() for text in observed.values()
        )
        or any(
            not isinstance(text, str) or not text.strip() for text in baseline.values()
        )
    ):
        raise evidence.Rejected("complete R8 VLAN table readbacks required")

    total = len(vlan_ids)
    before = {
        vlan: parse_vlan(baseline[str(vlan)], vlan, total=total) for vlan in vlan_ids
    }
    current = {
        vlan: parse_vlan(observed[str(vlan)], vlan, total=total) for vlan in vlan_ids
    }
    native_ports = {_port(port) for port in state.native}
    primary = _port(plan.R8_PRIMARY_PORT)
    primary_tagged = any(plan.R8_PRIMARY_PORT in ports for _, ports in state.vlans)
    expected_vlan1 = replace(
        before[1],
        untagged=(
            before[1].untagged
            if primary in native_ports or primary_tagged
            else tuple(sorted((*before[1].untagged, primary)))
        ),
        dual_mode=tuple(port for port in before[1].dual_mode if port in native_ports),
    )
    if expected_vlan1 != current[1] or before[132] != current[132]:
        raise evidence.Rejected("R8 VLAN1 or VLAN132 membership drift")

    initial_tagged = dict(initial_state.vlans)
    expected_tagged = dict(state.vlans)
    for vlan, _ in plan.VLANS:
        expected_initial = tuple(_port(port) for port in initial_tagged[vlan])
        if before[vlan].tagged != expected_initial:
            raise evidence.Rejected("R8 baseline VLAN table differs from configuration")
        expected = replace(
            before[vlan], tagged=tuple(_port(port) for port in expected_tagged[vlan])
        )
        if current[vlan] != expected:
            raise evidence.Rejected("R8 VLAN table membership drift")


def _classify_r8_probe_observation(
    baseline: tuple[str, ...],
    running: tuple[str, ...],
    startup: tuple[str, ...],
    *,
    baseline_sha256: str = plan.R8_BASELINE_SHA256,
) -> R8ProbeObservation:
    plan._build_r8_probe_plan(
        baseline,
        baseline,
        baseline_sha256=baseline_sha256,
        model=trunk_plan.MODEL,
        release=trunk_plan.RELEASE,
    )
    before = trunk_plan._configuration(baseline)
    current = trunk_plan._configuration(running)
    saved = trunk_plan._configuration(startup)
    if saved != before:
        raise evidence.Rejected("startup must remain exact R8 baseline")

    matches = [
        index
        for index, line in enumerate(current)
        if re.fullmatch(r"vlan 60(?: .*)?", line)
    ]
    if len(matches) > 1:
        raise evidence.Rejected("duplicate R8 probe VLAN stanza")
    stanzas: dict[int, tuple[int, tuple[str, ...], tuple[str, ...]]] = {}
    state = plan.State()
    if matches:
        start = matches[0]
        if current[start] != "vlan 60 name M7-QUALIFY by port":
            raise evidence.Rejected("unrecognized R8 probe VLAN header")
        end = start + 1
        members: list[str] = []
        while end < len(current) and current[end].startswith(" "):
            leaf = re.fullmatch(r" tagged (?:ethernet|ethe) (.+)", current[end])
            if leaf is None or leaf[1] != "1/2/2":
                raise evidence.Rejected("unrecognized R8 probe VLAN leaf")
            members.append("1/2/2")
            end += 1
        if len(members) > 1:
            raise evidence.Rejected("duplicate R8 probe tag")
        block = current[start:end]
        stanzas[start] = (end, block, tuple(members))
        state = plan.State(((60, tuple(members)),))

    trunk_observation._require_exact_remainder(before, current, stanzas)
    return R8ProbeObservation(
        state,
        evidence.configuration_hash(before),
        evidence.configuration_hash(current),
        evidence.configuration_hash(saved),
    )


def classify_r8_probe_observation(
    baseline: tuple[str, ...], running: tuple[str, ...], startup: tuple[str, ...]
) -> R8ProbeObservation:
    return _classify_r8_probe_observation(
        baseline,
        running,
        startup,
        baseline_sha256=plan.R8_BASELINE_SHA256,
    )


def require_r8_probe_state(
    observed: R8ProbeObservation,
    *,
    completed: int,
    inverse: bool = False,
    inverse_initial: plan.State = plan.R8_PROBE_FINAL_STATE,
) -> None:
    expected = plan.expected_r8_probe_state(
        completed, inverse=inverse, inverse_initial=inverse_initial
    )
    if observed.state != expected:
        raise evidence.Rejected("R8 probe per-command configuration state drift")


def require_r8_probe_operational_state(
    brief: str, baseline: tuple[str, ...], state: plan.State
) -> None:
    if (
        not isinstance(brief, str)
        or not brief.isascii()
        or re.search(r"[^\x20-\x7e\r\n\t]", brief)
        or re.search(r"\r(?!\n)", brief)
    ):
        raise evidence.Rejected("R8 probe interface brief required")
    rows = [line.split() for line in brief.splitlines() if line.split()]
    primary = [row for row in rows if row[0] == "1/2/2"]
    if len(primary) != 1 or len(primary[0]) != 10:
        raise evidence.Rejected("one complete primary-down row required")
    row = primary[0]
    if row[1:6] != ["Down", "None", "None", "None", "None"]:
        raise evidence.Rejected("R8 qualification requires primary link down")
    baseline_tagged = any(
        line.lstrip().startswith("tagged ") and "1/2/2" in line.split()
        for line in baseline
    )
    probe_tagged = "1/2/2" in state.tagged(60)
    if row[6:8] != ["Yes" if baseline_tagged or probe_tagged else "No", "1"]:
        raise evidence.Rejected("R8 probe primary VLAN tag or PVID drift")
    normalized = [
        " ".join([*row[:1], "Up", "Forward", "Full", "10G", *row[5:]])
        if row[0] == "1/2/2"
        else " ".join(row)
        for row in rows
    ]
    trunk_link_admission.require_links("\n".join(normalized))


def _interfaces(lines: tuple[str, ...]) -> dict[str, tuple[int, int]]:
    blocks: dict[str, tuple[int, int]] = {}
    for start, line in enumerate(lines):
        match = re.fullmatch(r"interface ethernet (1/[23]/[126])", line)
        if match is None or match[1] not in plan.PORTS:
            continue
        port = match[1]
        if port in blocks:
            raise evidence.Rejected("duplicate target interface stanza")
        end = start + 1
        while end < len(lines) and lines[end].startswith(" "):
            end += 1
        blocks[port] = (start, end)
    return blocks


def _classify_observation(
    baseline: tuple[str, ...],
    running: tuple[str, ...],
    startup: tuple[str, ...],
    *,
    baseline_sha256: str,
) -> Observation:
    trunk_plan._build_plan(
        baseline,
        baseline,
        baseline_sha256=baseline_sha256,
        model=trunk_plan.MODEL,
        release=trunk_plan.RELEASE,
    )
    before = trunk_plan._configuration(baseline)
    current = trunk_plan._configuration(running)
    if trunk_plan._configuration(startup) != before:
        raise evidence.Rejected("startup must remain exact baseline")
    original = _interfaces(before)
    for start, end in original.values():
        if any(
            line.lstrip().startswith("dual-mode") for line in before[start + 1 : end]
        ):
            raise evidence.Rejected("baseline native mode already configured")
    native: list[str] = []
    removed: set[int] = set()
    inserted: set[str] = set()
    for port, (start, end) in _interfaces(current).items():
        leaves = current[start + 1 : end]
        native_leaves = [
            line for line in leaves if line.lstrip().startswith("dual-mode")
        ]
        if native_leaves not in ([], [NATIVE_LEAF]):
            raise evidence.Rejected("unknown or duplicate native leaf")
        if native_leaves:
            native.append(port)
        if port in original:
            removed.update(
                i for i in range(start + 1, end) if current[i] == NATIVE_LEAF
            )
        else:
            if leaves != (NATIVE_LEAF,):
                raise evidence.Rejected("inserted interface requires only native leaf")
            inserted.add(port)
    remainder = tuple(
        line for index, line in enumerate(current) if index not in removed
    )
    stanzas = trunk_observation._target_stanzas(remainder)
    vlans = tuple(
        sorted(
            (int(block[0].split()[1]), tuple(sorted(ports)))
            for _, block, ports in stanzas.values()
        )
    )
    for port, (start, end) in _interfaces(remainder).items():
        if port in inserted:
            stanzas[start] = (end, remainder[start:end], ())
    trunk_observation._require_exact_remainder(before, remainder, stanzas)
    state = plan.State(vlans, tuple(sorted(native)))
    if state not in (*plan.FORWARD_STATES, *plan.INVERSE_STATES):
        raise evidence.Rejected("unreachable fixed native trunk state")
    return Observation(
        state,
        evidence.configuration_hash(before),
        evidence.configuration_hash(current),
        evidence.configuration_hash(startup),
    )


def classify_observation(
    baseline: tuple[str, ...],
    running: tuple[str, ...],
    startup: tuple[str, ...],
) -> Observation:
    return _classify_observation(
        baseline,
        running,
        startup,
        baseline_sha256=plan.BASELINE_SHA256,
    )


def require_state(
    observed: Observation, *, completed: int, inverse: bool = False
) -> None:
    if observed.state != plan.expected_state(completed, inverse=inverse):
        raise evidence.Rejected("native per-command configuration state drift")


def parse_vlan(text: str, vlan: int, *, total: int) -> membership.VlanMembership:
    if (
        type(vlan) is not int
        or vlan not in NAMES
        or type(total) is not int
        or not 2 <= total <= 6
    ):
        raise evidence.Rejected("invalid native VLAN identity or count")
    stp = "On" if vlan in (1, 132) else "Off"
    header = (
        f"PORT-VLAN {vlan}, Name {NAMES[vlan]}, Priority level0, Spanning tree {stp}"
    )
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if (
        len(lines) < 4
        or lines[0] != f"Total PORT-VLAN entries: {total}"
        or lines[3] != header
    ):
        raise evidence.Rejected("native VLAN identity or count drift")
    canonical = text.replace(
        f"Total PORT-VLAN entries: {total}", "Total PORT-VLAN entries: 2", 1
    ).replace(
        header, "PORT-VLAN 1, Name DEFAULT-VLAN, Priority level0, Spanning tree On", 1
    )
    try:
        facts = membership.parse_vlan(canonical, 1)
    except membership.Rejected as error:
        raise evidence.Rejected(str(error)) from error
    return replace(facts, vlan=vlan, name=NAMES[vlan], spanning_tree=stp)


def _port(port: str) -> membership.Port:
    unit, slot, number = (int(value) for value in port.split("/"))
    return unit, slot, number


def require_membership(
    responses: Mapping[int, str],
    *,
    baseline_vlan1: str,
    baseline_vlan132: str,
    completed: int,
    inverse: bool = False,
) -> None:
    state = plan.expected_state(completed, inverse=inverse)
    try:
        established.check_membership(
            {1: baseline_vlan1, 132: baseline_vlan132},
            baseline_vlan1=baseline_vlan1,
            baseline_vlan132=baseline_vlan132,
            phase="baseline",
        )
    except established.Rejected as error:
        raise evidence.Rejected(str(error)) from error
    if any(type(vlan) is not int for vlan in responses) or set(responses) != set(NAMES):
        raise evidence.Rejected("complete VLAN1/10/20/30/40/132 observations required")
    total = 2 + sum(bool(ports) for _, ports in state.vlans)
    original1 = parse_vlan(baseline_vlan1, 1, total=2)
    tagged10 = {_port(port) for port in state.tagged(10)}
    expected1 = replace(
        original1,
        untagged=tuple(port for port in original1.untagged if port not in tagged10),
        dual_mode=tuple(_port(port) for port in state.native),
    )
    if parse_vlan(responses[1], 1, total=total) != expected1 or parse_vlan(
        responses[132], 132, total=total
    ) != parse_vlan(baseline_vlan132, 132, total=2):
        raise evidence.Rejected("native VLAN1 or legacy VLAN132 drift")
    present = dict(state.vlans)
    for vlan, name in plan.VLANS:
        ports = state.tagged(vlan)
        if not ports:
            expected = (
                f"Port-vlan {vlan} does not have any members."
                if vlan in present
                else f"Error - port-vlan {vlan} does not exist."
            )
            if responses[vlan] != expected:
                raise evidence.Rejected("absent or empty target VLAN drift")
        elif parse_vlan(
            responses[vlan], vlan, total=total
        ) != membership.VlanMembership(
            vlan,
            name,
            (),
            tuple(_port(port) for port in ports),
            (),
            (),
            (),
            spanning_tree="Off",
        ):
            raise evidence.Rejected("target VLAN membership drift")


def require_operational_state(
    brief: str,
    *,
    completed: int,
    inverse: bool = False,
    qualification: plan.Qualification = plan.Qualification(
        plan.QualificationMode.ALL_UP
    ),
) -> None:
    """Require exact tag/PVID and forwarding on the selected mode's healthy ports.

    Transitional tag-only steps can be diagnosed with PVID N/A; they cannot pass
    require_settled_native_phase. The separate serial reader must still capture
    show span vlan 1; this pure guard does not invent a qualified span parser.
    """
    state = plan.expected_state(completed, inverse=inverse)
    plan.require_qualification_mode(qualification.mode)
    validated = brief
    if qualification.mode is plan.QualificationMode.PRIMARY_DOWN:
        # Preserve require_links' raw text grammar before split/join can erase it.
        if (
            not isinstance(brief, str)
            or not brief.isascii()
            or re.search(r"[^\x20-\x7e\r\n\t]", brief)
            or re.search(r"\r(?!\n)", brief)
        ):
            raise evidence.Rejected("trunk interface brief table required")
        # Normalize only for the established complete-table validator. Forwarding
        # on the down primary is never inferred from the normalized row.
        lines = []
        for line in brief.splitlines():
            words = line.split()
            if words and words[0] == "1/2/2":
                if len(words) != 10 or words[1:6] != ["Down", *["None"] * 4]:
                    raise evidence.Rejected(
                        "fixed primary-down qualification row required"
                    )
                words[1:5] = ["Up", "Forward", "Full", "10G"]
                line = " ".join(words)
            lines.append(line)
        validated = "\n".join(lines)
    trunk_link_admission.require_links(validated)
    rows = {
        words[0]: words
        for line in brief.splitlines()
        if (words := line.split()) and words[0] in plan.PORTS
    }
    for port in plan.PORTS:
        row = rows[port]
        tagged = any(port in ports for _, ports in state.vlans)
        forwarding = port not in qualification.forwarding_ports or row[2] == "Forward"
        if not forwarding or row[6] != ("Yes" if tagged else "No"):
            raise evidence.Rejected("native port forwarding or tag drift")
        allowed = ("1", "N/A") if tagged and port not in state.native else ("1",)
        if row[7] not in allowed:
            raise evidence.Rejected("native PVID drift")


def require_settled_native_phase(
    observed: Observation,
    brief: str,
    *,
    completed: int,
    elapsed_seconds: float,
    qualification: plan.Qualification = plan.Qualification(
        plan.QualificationMode.ALL_UP
    ),
) -> None:
    if (
        completed not in plan.NATIVE_PHASE_ENDS
        or not math.isfinite(elapsed_seconds)
        or not (plan.MIN_SETTLE_SECONDS <= elapsed_seconds <= plan.MAX_FORWARD_SECONDS)
    ):
        raise evidence.Rejected("native phase requires bounded settled observation")
    require_state(observed, completed=completed)
    require_operational_state(brief, completed=completed, qualification=qualification)


def require_recovery_operational_state(
    brief: str, *, completed: int, inverse: bool = False
) -> None:
    """Prove restoration safety with standby/gateway healthy; primary may be down.

    Carrier loss is not configuration drift or full-trunk qualification. The only
    additional accepted row is the observed primary Down/None/None/None grammar.
    All table completeness, tag/PVID and healthy-port checks remain mandatory.
    """
    if (
        not isinstance(brief, str)
        or not brief.isascii()
        or re.search(r"[^\x20-\x7e\r\n\t]", brief)
        or re.search(r"\r(?!\n)", brief)
    ):
        raise evidence.Rejected("trunk interface brief table required")
    rows = []
    for line in brief.splitlines():
        words = line.split()
        if words and words[0] == "1/2/2" and words[1:2] == ["Down"]:
            if len(words) != 10 or words[2:6] != ["None"] * 4:
                raise evidence.Rejected("unknown primary carrier-down recovery row")
            words[1:5] = ["Up", "Forward", "Full", "10G"]
            line = " ".join(words)
        rows.append(line)
    require_operational_state("\n".join(rows), completed=completed, inverse=inverse)
