"""Fixed native-aware unsaved trunk preparation; no transport or live admission."""

from dataclasses import dataclass
from enum import Enum
import re

import port_description as evidence
import trunk_plan

PORTS = ("1/2/6", "1/2/2", "1/3/1")
VLANS = trunk_plan.TARGET_VLANS
BASELINE_SHA256 = trunk_plan.BASELINE_SHA256
R8_BASELINE_SHA256 = "01b4a646e764f2874a2310b7e0efd1622f779f230d1d77a41a176b720a327eff"
R8_PROBE_VLAN = (60, "M7-QUALIFY")
R8_PROBE_PORT = "1/2/2"
R8_PROBE_FORWARD = (
    "configure terminal",
    "vlan 60 name M7-QUALIFY by port",
    "tagged ethernet 1/2/2",
    "exit",
    "exit",
)
R8_PROBE_INVERSE = (
    "configure terminal",
    "vlan 60",
    "no tagged ethernet 1/2/2",
    "no vlan 60",
    "exit",
)
R8_PRIMARY_PORT = "1/2/2"
R8_FULL_FORWARD = (
    "configure terminal",
    f"interface ethernet {R8_PRIMARY_PORT}",
    "no dual-mode 1",
    "exit",
    "vlan 40",
    f"no tagged ethernet {R8_PRIMARY_PORT}",
    "exit",
    *(
        command
        for vlan, _ in VLANS[:-1]
        for command in (
            f"vlan {vlan}",
            f"no tagged ethernet {R8_PRIMARY_PORT}",
            "exit",
        )
    ),
    "exit",
)
R8_FULL_INVERSE = (
    "configure terminal",
    *(
        command
        for vlan, _ in VLANS
        for command in (
            f"vlan {vlan}",
            f"tagged ethernet {R8_PRIMARY_PORT}",
            "exit",
        )
    ),
    f"interface ethernet {R8_PRIMARY_PORT}",
    "dual-mode 1",
    "exit",
    "exit",
)
EXECUTION_QUALIFIED = False
FORWARD_COMMANDS = (
    "configure terminal",
    *(
        command
        for index, port in enumerate(PORTS)
        for command in (
            "vlan 10 name LAB-MGMT by port" if index == 0 else "vlan 10",
            f"tagged ethernet {port}",
            "exit",
            f"interface ethernet {port}",
            "dual-mode 1",
            "exit",
        )
    ),
    *(
        command
        for vlan, name in VLANS[1:]
        for command in (
            f"vlan {vlan} name {name} by port",
            *(f"tagged ethernet {port}" for port in PORTS),
            "exit",
        )
    ),
    "exit",
)
NATIVE_PHASE_ENDS = {7: PORTS[0], 13: PORTS[1], 19: PORTS[2]}
NATIVE_SET_COMPLETED = (6, 12, 18)
MIN_SETTLE_SECONDS = 35
MAX_FORWARD_SECONDS = 90


class QualificationMode(Enum):
    ALL_UP = "all-up"
    PRIMARY_DOWN = "primary-down"


def require_qualification_mode(mode: QualificationMode) -> None:
    if not isinstance(mode, QualificationMode):
        raise evidence.Rejected("explicit fixed native qualification mode required")


@dataclass(frozen=True)
class Qualification:
    """Select before observation; a carrier failure never changes the contract.

    This is a pure switch evidence contract, not guest-proof admission. Degraded
    acceptance still needs a read-only helper proving nic5 remains active and
    primary carrier stays down throughout the bounded cycle.
    """

    mode: QualificationMode

    def __post_init__(self) -> None:
        require_qualification_mode(self.mode)

    @property
    def accepted_outcome(self) -> str:
        return (
            "all-up-native-trunk-qualified"
            if self.mode is QualificationMode.ALL_UP
            else "primary-down-active40g-native-trunk-qualified"
        )

    @property
    def forwarding_ports(self) -> tuple[str, ...]:
        return PORTS if self.mode is QualificationMode.ALL_UP else ("1/2/6", "1/3/1")


@dataclass(frozen=True)
class State:
    """Declared target VLANs, their complete tag sets, and implicit native leaves."""

    vlans: tuple[tuple[int, tuple[str, ...]], ...] = ()
    native: tuple[str, ...] = ()

    def tagged(self, vlan: int) -> tuple[str, ...]:
        return dict(self.vlans).get(vlan, ())


@dataclass(frozen=True)
class R8ProbePlan:
    baseline_sha256: str
    model: str
    release: str
    forward_commands: tuple[str, ...] = R8_PROBE_FORWARD
    inverse_commands: tuple[str, ...] = R8_PROBE_INVERSE
    execution_qualified: bool = False
    live_admission: bool = False


@dataclass(frozen=True)
class R8FullTrunkPlan:
    baseline_sha256: str
    model: str
    release: str
    initial_state: "State"
    forward_commands: tuple[str, ...] = R8_FULL_FORWARD
    inverse_commands: tuple[str, ...] = R8_FULL_INVERSE
    execution_qualified: bool = False
    live_admission: bool = False


def _r8_full_initial_state(configuration: tuple[str, ...]) -> "State":
    targets = dict(VLANS)
    found: dict[int, set[str]] = {}
    native: set[str] = set()
    index = 0
    while index < len(configuration):
        line = configuration[index]
        vlan_match = re.fullmatch(
            r"vlan ([1-9][0-9]*) name ([A-Za-z0-9_-]+) by port", line
        )
        interface_match = re.fullmatch(r"interface ethernet (.+)", line)
        if vlan_match and int(vlan_match[1]) in targets:
            vlan = int(vlan_match[1])
            if vlan in found or vlan_match[2] != targets[vlan]:
                raise evidence.Rejected("R8 trunk target VLAN identity")
            members: set[str] = set()
            index += 1
            while index < len(configuration) and configuration[index].startswith(" "):
                leaf = re.fullmatch(
                    r" tagged (?:ethernet|ethe) ([0-9/ ]+)", configuration[index]
                )
                if leaf is not None:
                    for port in leaf[1].split():
                        if port not in PORTS or port in members:
                            raise evidence.Rejected("R8 trunk target VLAN membership")
                        members.add(port)
                else:
                    repeated = re.fullmatch(
                        r" tagged ethe ([0-9/]+(?: ethe [0-9/]+)+)",
                        configuration[index],
                    )
                    if repeated is None:
                        raise evidence.Rejected("R8 trunk target VLAN leaf")
                    for port in repeated[1].split(" ethe "):
                        if port not in PORTS or port in members:
                            raise evidence.Rejected("R8 trunk target VLAN membership")
                        members.add(port)
                index += 1
            found[vlan] = members
            continue
        if interface_match and interface_match[1] in PORTS:
            port = interface_match[1]
            index += 1
            leaves = []
            while index < len(configuration) and configuration[index].startswith(" "):
                if configuration[index].lstrip().startswith("dual-mode"):
                    leaves.append(configuration[index])
                index += 1
            if leaves not in ([], [" dual-mode"]):
                raise evidence.Rejected("R8 native VLAN leaf")
            if leaves:
                native.add(port)
            continue
        index += 1
    if set(found) != set(targets) or any(
        members != set(PORTS) for members in found.values()
    ):
        raise evidence.Rejected("R8 full trunk target membership required")
    if native != set(PORTS):
        raise evidence.Rejected("R8 native VLAN 1 membership required")
    return State(
        tuple((vlan, tuple(sorted(PORTS))) for vlan, _ in VLANS),
        tuple(sorted(PORTS)),
    )


def r8_full_inverse_commands(observed: State) -> tuple[str, ...]:
    """Restore primary tags and native membership absent at a forward boundary."""
    targets = {vlan for vlan, _ in VLANS}
    tagged = dict(observed.vlans)
    full = set(PORTS)
    without_primary = full - {R8_PRIMARY_PORT}
    if (
        set(tagged) != targets
        or set(observed.native) not in (full, full - {R8_PRIMARY_PORT})
        or any(set(ports) not in (full, without_primary) for ports in tagged.values())
        or not (
            any(R8_PRIMARY_PORT not in ports for ports in tagged.values())
            or R8_PRIMARY_PORT not in observed.native
        )
    ):
        raise evidence.Rejected("unrecognized R8 full trunk inverse boundary")
    commands = ["configure terminal"]
    for vlan, _ in VLANS:
        if R8_PRIMARY_PORT not in tagged[vlan]:
            commands.extend(
                (f"vlan {vlan}", f"tagged ethernet {R8_PRIMARY_PORT}", "exit")
            )
    if R8_PRIMARY_PORT not in observed.native:
        commands.extend(
            (
                f"interface ethernet {R8_PRIMARY_PORT}",
                "dual-mode 1",
                "exit",
            )
        )
    commands.append("exit")
    return tuple(commands)


def build_r8_full_trunk_plan(
    baseline: tuple[str, ...] | list[str],
    startup: tuple[str, ...] | list[str],
    *,
    model: str = trunk_plan.MODEL,
    release: str = trunk_plan.RELEASE,
) -> R8FullTrunkPlan:
    """Plan a reversible primary-down tag cycle from the accepted R8 target."""
    if model != trunk_plan.MODEL or release != trunk_plan.RELEASE:
        raise evidence.Rejected("unsupported fixed target")
    running = trunk_plan._configuration(baseline)
    saved = trunk_plan._configuration(startup)
    if running != saved:
        raise evidence.Rejected("running and startup differ")
    actual_sha256 = evidence.configuration_hash(running)
    if actual_sha256 != R8_BASELINE_SHA256:
        raise evidence.Rejected("R8 qualification baseline drift")
    initial = _r8_full_initial_state(running)
    final = _states(R8_FULL_FORWARD, initial)[-1]
    if (
        final.vlans
        != tuple(
            (vlan, tuple(port for port in PORTS if port != R8_PRIMARY_PORT))
            for vlan, _ in VLANS
        )
        or final.native != tuple(
            sorted(set(initial.native) - {R8_PRIMARY_PORT})
        )
    ):
        raise evidence.Rejected("R8 full trunk delta model")
    return R8FullTrunkPlan(actual_sha256, model, release, initial)


def _build_r8_probe_plan(
    baseline: tuple[str, ...] | list[str],
    startup: tuple[str, ...] | list[str],
    *,
    baseline_sha256: str,
    model: str,
    release: str,
) -> R8ProbePlan:
    if model != trunk_plan.MODEL or release != trunk_plan.RELEASE:
        raise evidence.Rejected("unsupported fixed target")
    running = trunk_plan._configuration(baseline)
    saved = trunk_plan._configuration(startup)
    if running != saved:
        raise evidence.Rejected("running and startup differ")
    actual_sha256 = evidence.configuration_hash(running)
    if actual_sha256 != baseline_sha256:
        raise evidence.Rejected("R8 qualification baseline drift")
    vlan_ids: set[int] = set()
    for line in running:
        if not line.startswith("vlan"):
            continue
        match = re.fullmatch(
            r"vlan ([1-9][0-9]*)(?: name [A-Za-z0-9_-]+)? by port", line
        )
        if match is None:
            raise evidence.Rejected("ambiguous VLAN stanza")
        vlan_id = int(match.group(1))
        if vlan_id in vlan_ids:
            raise evidence.Rejected("duplicate VLAN stanza")
        vlan_ids.add(vlan_id)
    if R8_PROBE_VLAN[0] in vlan_ids:
        raise evidence.Rejected("R8 probe VLAN already exists")
    return R8ProbePlan(actual_sha256, model, release)


def build_r8_probe_plan(
    baseline: tuple[str, ...] | list[str],
    startup: tuple[str, ...] | list[str],
    *,
    model: str = trunk_plan.MODEL,
    release: str = trunk_plan.RELEASE,
) -> R8ProbePlan:
    """Plan a reversible VLAN 60 tag on the down primary from accepted R8."""
    return _build_r8_probe_plan(
        baseline,
        startup,
        baseline_sha256=R8_BASELINE_SHA256,
        model=model,
        release=release,
    )


def _states(commands: tuple[str, ...], initial: State) -> tuple[State, ...]:
    vlans = {vlan: set(ports) for vlan, ports in initial.vlans}
    native = set(initial.native)
    context: int | str | None = None
    states = [initial]
    for command in commands:
        if command.startswith("no vlan "):
            vlan = int(command.split()[2])
            del vlans[vlan]
            context = None
        elif command.startswith("vlan "):
            context = int(command.split()[1])
            vlans.setdefault(context, set())
        elif command.startswith("interface ethernet "):
            context = command.split()[2]
        elif command.startswith("tagged ethernet "):
            assert isinstance(context, int)
            vlans[context].add(command.split()[2])
        elif command.startswith("no tagged ethernet "):
            assert isinstance(context, int)
            port = command.split()[3]
            if port in native and sum(port in ports for ports in vlans.values()) == 1:
                raise evidence.Rejected("cannot remove the last tag from a dual-mode port")
            vlans[context].remove(port)
            if not vlans[context]:
                context = None
        elif command == "dual-mode 1":
            assert isinstance(context, str)
            if not any(context in ports for ports in vlans.values()):
                raise evidence.Rejected("dual-mode requires a tagged VLAN membership")
            native.add(context)
        elif command == "no dual-mode 1":
            assert isinstance(context, str)
            native.remove(context)
        elif command in ("exit", "configure terminal"):
            context = None
        else:
            raise evidence.Rejected("unsupported fixed native command")
        states.append(
            State(
                tuple(
                    (vlan, tuple(sorted(ports)))
                    for vlan, ports in sorted(vlans.items())
                ),
                tuple(sorted(native)),
            )
        )
    return tuple(states)


FORWARD_STATES = _states(FORWARD_COMMANDS, State())
FINAL_STATE = FORWARD_STATES[-1]
R8_PROBE_FORWARD_STATES = _states(R8_PROBE_FORWARD, State())
R8_PROBE_FINAL_STATE = R8_PROBE_FORWARD_STATES[-1]


def r8_probe_inverse_commands(observed: State) -> tuple[str, ...]:
    if observed not in R8_PROBE_FORWARD_STATES:
        raise evidence.Rejected("unrecognized R8 probe state")
    commands = ["configure terminal"]
    if 60 in dict(observed.vlans):
        if observed.tagged(60):
            commands.extend(("vlan 60", "no tagged ethernet 1/2/2"))
        commands.append("no vlan 60")
    commands.append("exit")
    return tuple(commands)


R8_PROBE_INVERSE_STATES = _states(
    r8_probe_inverse_commands(R8_PROBE_FINAL_STATE), R8_PROBE_FINAL_STATE
)


def expected_state(completed: int, *, inverse: bool = False) -> State:
    states = INVERSE_STATES if inverse else FORWARD_STATES
    if type(completed) is not int or not 0 <= completed < len(states):
        raise evidence.Rejected("invalid completed native command count")
    return states[completed]


def expected_r8_probe_state(
    completed: int,
    *,
    inverse: bool = False,
    inverse_initial: State = R8_PROBE_FINAL_STATE,
) -> State:
    if inverse:
        if inverse_initial not in R8_PROBE_FORWARD_STATES:
            raise evidence.Rejected("unrecognized R8 probe inverse origin")
        states = _states(r8_probe_inverse_commands(inverse_initial), inverse_initial)
    else:
        states = R8_PROBE_FORWARD_STATES
    if type(completed) is not int or not 0 <= completed < len(states):
        raise evidence.Rejected("invalid R8 probe command count")
    return states[completed]


def inverse_commands(observed: State) -> tuple[str, ...]:
    """Produce only an inverse of a reachable, exactly observed forward state.

    The caller must first compare complete configuration and operational evidence;
    this function cannot establish that a VLAN is task-owned on a live device.
    """
    if observed not in FORWARD_STATES:
        raise evidence.Rejected("unrecognized native state; no VLAN deletion allowed")
    commands = ["configure terminal"]
    present = dict(observed.vlans)
    for vlan in (40, 30, 20):
        if vlan in present:
            commands.append(f"no vlan {vlan}")
    remaining_tags = set(observed.tagged(10))
    for port in reversed(PORTS):
        if port in observed.native:
            commands.extend((f"interface ethernet {port}", "no dual-mode 1", "exit"))
        if port in observed.tagged(10):
            commands.extend(("vlan 10", f"no tagged ethernet {port}"))
            remaining_tags.remove(port)
            if remaining_tags:
                commands.append("exit")
    if 10 in present:
        commands.append("no vlan 10")
    commands.append("exit")
    return tuple(commands)


INVERSE_COMMANDS = inverse_commands(FINAL_STATE)
INVERSE_STATES = _states(INVERSE_COMMANDS, FINAL_STATE)


def build_plan(
    baseline: tuple[str, ...],
    startup: tuple[str, ...],
    *,
    qualification: Qualification = Qualification(QualificationMode.ALL_UP),
) -> dict[str, object]:
    """Require the historical saved baseline; drift is not automatically adopted."""
    require_qualification_mode(qualification.mode)
    trunk_plan.build_plan(baseline, startup)
    return {
        "qualification_mode": qualification.mode.value,
        "accepted_outcome": qualification.accepted_outcome,
        "forwarding_ports": qualification.forwarding_ports,
        "primary_redundancy_qualified": False,
        "requires_read_only_active40g_guest_proof": qualification.mode
        is QualificationMode.PRIMARY_DOWN,
        "forward_commands": FORWARD_COMMANDS,
        "inverse_commands": INVERSE_COMMANDS,
        "baseline_sha256": BASELINE_SHA256,
        "execution_qualified": False,
        "live_admission": False,
        "requires_standby_guest_proof_before_primary": True,
        "requires_resident_pikvm_gateway_writer": True,
        "startup_save_permitted": False,
    }
