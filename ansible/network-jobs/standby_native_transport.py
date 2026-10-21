"""Fixed unsaved standby native candidate; execution qualification is pending.

The caller owns admission, durable intent, observations and recovery. Cancelled
help queries establish syntax only. Unknown acknowledgements stop the sequence
with received bytes retained; no save, retry or automatic recovery is supplied.
"""

import hashlib
from pathlib import Path
import re

import empty_vlan_transport as base
import port_writer

Rejected = port_writer.Rejected
EXECUTION_QUALIFIED = False
COMMANDS = (
    "configure terminal",
    "vlan 10 name LAB-MGMT by port",
    "tagged ethernet 1/2/6",
    "exit",
    "interface ethernet 1/2/6",
    "dual-mode 1",
    "exit",
    "exit",
    "configure terminal",
    "interface ethernet 1/2/6",
    "no dual-mode 1",
    "exit",
    "vlan 10",
    "no tagged ethernet 1/2/6",
    "no vlan 10",
    "exit",
)
_VLAN = r"(?:SSH@)?headwater\(config-vlan-10\)#"
_INTERFACE = r"SSH@headwater\(config-if-e40000-1/2/6\)#"
MODES = (
    base._syntax.EXEC,
    base._syntax.CONFIG,
    _VLAN,
    _VLAN,
    base._syntax.CONFIG,
    _INTERFACE,
    _INTERFACE,
    base._syntax.CONFIG,
    base._syntax.EXEC,
    base._syntax.CONFIG,
    _INTERFACE,
    _INTERFACE,
    base._syntax.CONFIG,
    _VLAN,
    base._syntax.CONFIG,
    base._syntax.CONFIG,
    base._syntax.EXEC,
)
_BASE = Path(__file__).resolve().parent
SOURCE_PATHS = {
    "standby_native_transport": Path(__file__).resolve(),
    "empty_vlan_transport": _BASE / "empty_vlan_transport.py",
    "empty_vlan_cycle": _BASE / "empty_vlan_cycle.py",
    "trunk_writer": _BASE / "trunk_writer.py",
    "trunk_plan": _BASE / "trunk_plan.py",
    **{f"base_{index}": path for index, path in enumerate(port_writer._SOURCES)},
}
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
        raise Rejected("standby native transport source drift")


class StandbyNativeTransport(base.EmptyVlanTransport):
    """One fixed forward/inverse candidate on a caller-owned root console."""

    _commands = COMMANDS
    _modes = MODES
    _capture_filename = "standby-native-received.raw"

    def _unchanged_sources(self) -> None:
        unchanged_sources()

    def _validate_response(self, index: int, response: str) -> None:
        self._unchanged_sources()
        acknowledgement = {
            2: "Added tagged port(s) ethe 1/2/6 to port-vlan 10.",
            13: "Deleted tagged port(s) to port-vlan 10.",
        }.get(index)
        body = (
            r"(?:" + re.escape(acknowledgement + "\n") + r")?"
            if acknowledgement is not None
            else ""
        )
        pattern = re.escape(COMMANDS[index] + "\n") + body + MODES[index + 1] + r" *"
        if (
            re.fullmatch(
                pattern,
                response,
            )
            is None
        ):
            raise Rejected("standby native command echo or body boundary")
        if acknowledgement is not None and acknowledgement + "\n" in response:
            if re.fullmatch(pattern, self._console.raw.replace("\r\n", "\n")) is None:
                raise Rejected("standby native raw acknowledgement boundary")
