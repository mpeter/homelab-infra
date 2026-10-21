"""Fixed unsaved native trunk transports; serial residency and admission are caller-owned.

Prompt and acknowledgement candidates require actual device qualification. Unknown
responses retain raw capture and permanently stop; no retry or save is provided.
"""

import hashlib
from pathlib import Path
import re
from typing import Any

import empty_vlan_transport as base
import native_trunk_plan as plan
import port_writer

Rejected = port_writer.Rejected
EXECUTION_QUALIFIED = False
_INTERFACE_MODES = {
    "1/2/6": r"(?:SSH@)?headwater\(config-if-e40000-1/2/6\)#",
    "1/2/2": r"(?:SSH@)?headwater\(config-if-e10000-1/2/2\)#",
    "1/3/1": r"(?:SSH@)?headwater\(config-if-e10000-1/3/1\)#",
}


def _modes(
    commands: tuple[str, ...], initial: plan.State = plan.State()
) -> tuple[str, ...]:
    modes = [base._syntax.EXEC]
    states = plan._states(commands, initial)
    for command in commands:
        if command == "configure terminal" or command.startswith("no vlan "):
            mode = base._syntax.CONFIG
        elif command.startswith("vlan "):
            mode = rf"(?:SSH@)?headwater\(config-vlan-{command.split()[1]}\)#"
        elif command.startswith("interface ethernet "):
            mode = _INTERFACE_MODES[command.split()[2]]
        elif command == "exit":
            mode = (
                base._syntax.EXEC
                if modes[-1] == base._syntax.CONFIG
                else base._syntax.CONFIG
            )
        elif command.startswith("no tagged ethernet "):
            vlan = re.search(r"config-vlan-(\d+)", modes[-1])
            if vlan is None:
                raise Rejected("native trunk VLAN context missing")
            mode = (
                modes[-1]
                if states[len(modes)].tagged(int(vlan[1]))
                else base._syntax.CONFIG
            )
        elif command.startswith("tagged ethernet ") or command in (
            "dual-mode 1",
            "no dual-mode 1",
        ):
            mode = modes[-1]
        else:
            raise Rejected("unsupported fixed native trunk command")
        modes.append(mode)
    return tuple(modes)


FORWARD_MODES = _modes(plan.FORWARD_COMMANDS)
INVERSE_MODES = _modes(plan.INVERSE_COMMANDS, plan.FINAL_STATE)
_BASE = Path(__file__).resolve().parent
SOURCE_PATHS = {
    name: _BASE / (name + ".py")
    for name in (
        "native_trunk_transport",
        "native_trunk_plan",
        "empty_vlan_transport",
        "empty_vlan_cycle",
        "trunk_writer",
        "trunk_plan",
    )
}
SOURCE_PATHS.update(
    {f"base_{index}": path for index, path in enumerate(port_writer._SOURCES)}
)
SOURCE_SHA256 = {
    name: hashlib.sha256(path.read_bytes()).hexdigest()
    for name, path in SOURCE_PATHS.items()
}


def unchanged_sources() -> None:
    port_writer.unchanged_sources()
    if any(
        hashlib.sha256(path.read_bytes()).hexdigest() != SOURCE_SHA256[name]
        for name, path in SOURCE_PATHS.items()
    ):
        raise Rejected("native trunk transport source drift")


class NativeTrunkTransport(base.EmptyVlanTransport):
    """Fixed 35-command forward on a caller-owned privileged console."""

    _commands = plan.FORWARD_COMMANDS
    _modes = FORWARD_MODES
    _capture_filename = "native-trunk-forward-received.raw"

    def _unchanged_sources(self) -> None:
        unchanged_sources()

    def _validate_response(self, index: int, response: str) -> None:
        self._unchanged_sources()
        command = self._commands[index]
        acknowledgement = None
        if command.startswith("tagged ethernet "):
            vlan = re.search(r"config-vlan-(\d+)", self._modes[index])
            if vlan is None:
                raise Rejected("native trunk VLAN context missing")
            acknowledgement = f"Added tagged port(s) ethe {command.split()[2]} to port-vlan {vlan[1]}."
        elif command.startswith("no tagged ethernet "):
            vlan = re.search(r"config-vlan-(\d+)", self._modes[index])
            if vlan is None:
                raise Rejected("native trunk VLAN context missing")
            acknowledgement = f"Deleted tagged port(s) to port-vlan {vlan[1]}."
        body = (
            r"(?:" + re.escape(acknowledgement + "\n") + r")?"
            if acknowledgement is not None
            else ""
        )
        pattern = re.escape(command + "\n") + body + self._modes[index + 1] + r" *"
        if re.fullmatch(pattern, response) is None:
            raise Rejected("native trunk unknown command response")
        if acknowledgement is not None and acknowledgement + "\n" in response:
            if re.fullmatch(pattern, self._console.raw.replace("\r\n", "\n")) is None:
                raise Rejected("native trunk raw acknowledgement boundary")


class NativeTrunkInverseTransport(NativeTrunkTransport):
    """Fixed inverse; caller must first prove exact owned full state."""

    _commands = plan.INVERSE_COMMANDS
    _modes = INVERSE_MODES
    _capture_filename = "native-trunk-inverse-received.raw"


class R8ProbeTransport(NativeTrunkTransport):
    """Fixed R8 VLAN 60 probe or its inverse from one observed probe state."""

    def __init__(
        self, console: Any, *, inverse_state: plan.State | None = None
    ) -> None:
        if inverse_state is None:
            self._commands = plan.R8_PROBE_FORWARD
            initial = plan.State()
            self._capture_filename = "r8-probe-forward-received.raw"
        else:
            if inverse_state not in plan.R8_PROBE_FORWARD_STATES:
                raise Rejected("unrecognized R8 probe inverse state")
            self._commands = plan.r8_probe_inverse_commands(inverse_state)
            initial = inverse_state
            self._capture_filename = "r8-probe-inverse-received.raw"
        self._modes = _modes(self._commands, initial)
        super().__init__(console)


class R8ProbeCycleTransport(NativeTrunkTransport):
    """One strict transport for the fixed R8 probe and its exact inverse."""

    _commands = (
        *plan.R8_PROBE_FORWARD,
        *plan.r8_probe_inverse_commands(plan.R8_PROBE_FINAL_STATE),
    )
    _modes = _modes(_commands)
    _capture_filename = "r8-probe-cycle-received.raw"


class R8FullTrunkCycleTransport(NativeTrunkTransport):
    """Strict R8 forward cycle with an inverse selected from observed state."""

    _capture_filename = "r8-full-trunk-cycle-received.raw"

    def __init__(self, console: Any, initial_state: plan.State) -> None:
        self._initial_state = initial_state
        self._forward_count = len(plan.R8_FULL_FORWARD)
        self._commands = (*plan.R8_FULL_FORWARD, *plan.R8_FULL_INVERSE)
        self._modes = _modes(self._commands, initial_state)
        super().__init__(console)

    def set_inverse_state(self, observed: plan.State) -> None:
        if self._active or self._failed or self._index != self._forward_count:
            raise Rejected("R8 inverse can only be selected at the forward boundary")
        inverse = plan.r8_full_inverse_commands(observed)
        self._commands = (*plan.R8_FULL_FORWARD, *inverse)
        self._modes = _modes(self._commands, self._initial_state)


class R8FullTrunkRecoveryTransport(NativeTrunkTransport):
    """Strict inverse transport selected from an independently observed state."""

    _capture_filename = "r8-full-trunk-recovery-received.raw"

    def __init__(self, console: Any, observed_state: plan.State) -> None:
        self._commands = plan.r8_full_inverse_commands(observed_state)
        self._modes = _modes(self._commands, observed_state)
        super().__init__(console)
