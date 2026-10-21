"""Fixed serial EXEC block boundaries; no implicit mode navigation or admission."""

from dataclasses import dataclass
from enum import Enum

import empty_vlan_transport as base
import native_trunk_plan as native
import native_trunk_transport as transport

EXECUTION_QUALIFIED = False
LIVE_ADMISSION = False


class Phase(Enum):
    STANDBY_QUALIFICATION = "standbyQualification"
    REMAINING_TRUNK = "remainingTrunk"


@dataclass(frozen=True)
class Step:
    command: str
    before: str
    after: str
    completed: int
    observe: bool = False
    hold: bool = False


def _blocks(
    commands: tuple[str, ...], modes: tuple[str, ...], ends: tuple[int, ...]
) -> tuple[Step, ...]:
    result = []
    for index, command in enumerate(commands):
        completed = index + 1
        result.append(Step(command, modes[index], modes[completed], completed))
        if completed in ends:
            result.append(
                Step(
                    "exit",
                    modes[completed],
                    base._syntax.EXEC,
                    completed,
                    True,
                    True,
                )
            )
            result.append(
                Step(
                    "configure terminal",
                    base._syntax.EXEC,
                    base._syntax.CONFIG,
                    completed,
                )
            )
    last = result[-1]
    result[-1] = Step(last.command, last.before, last.after, last.completed, True)
    return tuple(result)


FORWARD = _blocks(native.FORWARD_COMMANDS, transport.FORWARD_MODES, (7, 13, 19))
INVERSE_ENDS = tuple(
    index + (2 if native.INVERSE_COMMANDS[index + 1] == "exit" else 1)
    for index, command in enumerate(native.INVERSE_COMMANDS)
    if command.startswith("no tagged ethernet ")
)
INVERSE = _blocks(native.INVERSE_COMMANDS, transport.INVERSE_MODES, INVERSE_ENDS)
STANDBY_END = next(index + 1 for index, step in enumerate(FORWARD) if step.observe)
# The hold is needed when introducing native forwarding, not when restoring baseline.
INVERSE = tuple(
    Step(s.command, s.before, s.after, s.completed, s.observe) for s in INVERSE
)


def r8_probe_forward() -> tuple[Step, ...]:
    return _blocks(
        native.R8_PROBE_FORWARD,
        transport._modes(native.R8_PROBE_FORWARD),
        (),
    )


def r8_probe_inverse(state: native.State) -> tuple[Step, ...]:
    if state not in native.R8_PROBE_FORWARD_STATES:
        raise transport.Rejected("no fixed R8 probe inverse for observed state")
    if state == native.State():
        return ()
    commands = native.r8_probe_inverse_commands(state)
    modes = transport._modes(commands, state)
    return _blocks(commands, modes, ())


def inverse_for(completed: int) -> tuple[Step, ...]:
    state = native.expected_state(completed)
    commands = native.inverse_commands(state)
    modes = transport._modes(commands, state)
    # Native hold boundaries have only the exact modeled VLAN10 membership.
    if completed in native.NATIVE_PHASE_ENDS:
        return _blocks(commands, modes, ())
    if completed == len(native.FORWARD_COMMANDS):
        return INVERSE
    raise transport.Rejected("no fixed serial inverse for this boundary")


ROLLBACK_BOUNDARIES = (*native.NATIVE_PHASE_ENDS, len(native.FORWARD_COMMANDS))


def fixed_sequence(steps: tuple[Step, ...]) -> bool:
    return (
        steps == FORWARD
        or any(steps == inverse_for(n) for n in ROLLBACK_BOUNDARIES)
        or steps == r8_probe_forward()
        or any(
            steps == r8_probe_inverse(native.expected_r8_probe_state(completed))
            for completed in range(2, len(native.R8_PROBE_FORWARD) + 1)
        )
    )
