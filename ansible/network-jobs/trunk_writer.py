"""Fixed 22-command transport on a caller-supplied, verified headwater Console.

This library grants no admission and opens no connection. The caller owns
identity, exclusion, durable intent, observations and recovery. No credentials,
save, inverse or retry operation is supplied. Tagged commands require the exact
firmware acknowledgement captured for standby 1/2/6 in VLAN 10. Other commands
require echo-only responses; whole-writer execution qualification is pending.
"""

from collections.abc import Callable
import hashlib
from inspect import isawaitable, iscoroutine, iscoroutinefunction
from pathlib import Path
import re
from types import ModuleType
from typing import Any

import port_description as evidence
import trunk_plan

TRANSPORT_SHA256 = "892dab2b7ab444a69f3858ac2a166661c5695f126a07a55e126d159c568fa503"
_TRANSPORT_PATH = Path(__file__).resolve().with_name("port_writer.py")
_TRANSPORT_BYTES = _TRANSPORT_PATH.read_bytes()
if hashlib.sha256(_TRANSPORT_BYTES).hexdigest() != TRANSPORT_SHA256:
    raise RuntimeError("trunk transport dependency drift")
transport = ModuleType("trunk_fixed_transport")
transport.__file__ = str(_TRANSPORT_PATH)
exec(compile(_TRANSPORT_BYTES, str(_TRANSPORT_PATH), "exec"), transport.__dict__)
Rejected = transport.Rejected
COMMANDS = trunk_plan.FORWARD_COMMANDS
EXECUTION_QUALIFIED = False
SOURCE_PATHS = {
    **evidence.SOURCE_PATHS,
    **{
        f"transport_dependency_{index}": path
        for index, path in enumerate(transport._SOURCES)
    },
    "trunk_plan": Path(trunk_plan.__file__).resolve(),
    "trunk_writer": Path(__file__).resolve(),
    "transport": _TRANSPORT_PATH,
}
SOURCE_SHA256 = {
    name: hashlib.sha256(path.read_bytes()).hexdigest()
    for name, path in SOURCE_PATHS.items()
}

# VLAN member leaves remain in the current VLAN mode; exits return to config.
PROMPTS = (
    transport._syntax.CONFIG,
    *(
        prompt
        for vlan_id, _ in trunk_plan.TARGET_VLANS
        for prompt in (
            *(rf"(?:SSH@)?headwater\(config-vlan-{vlan_id}\)#" for _ in range(4)),
            transport._syntax.CONFIG,
        )
    ),
    transport._syntax.EXEC,
)


def unchanged_sources() -> None:
    transport.unchanged_sources()
    if any(
        hashlib.sha256(path.read_bytes()).hexdigest() != SOURCE_SHA256[name]
        for name, path in SOURCE_PATHS.items()
    ):
        raise Rejected("trunk writer source drift")


def validate_response(index: int, response: str) -> None:
    """Check a normalized read_mode body against its fixed command and mode."""
    if type(index) is not int or not 1 <= index <= len(COMMANDS):
        raise Rejected("fixed trunk command index required")
    command = COMMANDS[index - 1]
    body = command + "\n"
    if command.startswith("tagged ethernet "):
        port = command.removeprefix("tagged ethernet ")
        vlan_id, _ = trunk_plan.TARGET_VLANS[(index - 2) // 5]
        body += f"Added tagged port(s) ethe {port} to port-vlan {vlan_id}.\n"
    if re.fullmatch(re.escape(body) + PROMPTS[index - 1] + r" *", response) is None:
        raise Rejected("trunk command echo or body boundary")


class TrunkWriter:
    """Ordered indexed sends; any failed attempt permanently latches uncertainty.

    Each send calls its caller-supplied before_send exactly once synchronously
    immediately before transport send. Only a None result permits that send.
    Success means the command response and prompt matched, not live admission or
    proven configuration. Initial EXEC mode must already be verified by the caller.
    """

    def __init__(self, console: Any):
        self._console = console
        self._next_index = 1
        self._uncertain = False
        self._sending = False

    @property
    def next_index(self) -> int:
        return self._next_index

    @property
    def uncertain(self) -> bool:
        return self._uncertain

    @property
    def complete(self) -> bool:
        return self._next_index == len(COMMANDS) + 1 and not self._uncertain

    def send(self, index: int, before_send: Callable[[], object]) -> None:
        if self._uncertain or self._sending:
            self._uncertain = True
            raise Rejected("trunk writer state uncertain; retry forbidden")
        self._sending = True
        try:
            if (
                type(index) is not int
                or index != self._next_index
                or not 1 <= index <= len(COMMANDS)
            ):
                raise Rejected("fixed trunk command index order required")
            if not callable(before_send) or iscoroutinefunction(before_send):
                raise Rejected("synchronous durable intent callback required")
            unchanged_sources()
            result = before_send()
            if isawaitable(result):
                if iscoroutine(result):
                    result.close()
                raise Rejected("durable intent must return None synchronously")
            if result is not None:
                raise Rejected("durable intent must return None synchronously")
            if self._uncertain:
                raise Rejected("trunk writer callback reentered send")
            unchanged_sources()
            command = COMMANDS[index - 1]
            self._console.channel.sendall(command + "\r")
            try:
                response = transport._syntax.read_mode(
                    self._console, PROMPTS[index - 1]
                )
            except transport._syntax.Rejected as error:
                raise Rejected(str(error)) from error
            validate_response(index, response)
            unchanged_sources()
            self._next_index += 1
        except BaseException:
            self._uncertain = True
            raise
        finally:
            self._sending = False
