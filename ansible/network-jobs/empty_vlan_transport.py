"""Fixed unsaved VLAN 10 transport on a caller-owned privileged root console."""

from collections.abc import Callable
import hashlib
from inspect import iscoroutine
import os
import re
from types import TracebackType
from typing import Any

import empty_vlan_cycle as cycle
import port_writer
import trunk_writer

COMMANDS = cycle.COMMANDS
STANDBY_TAGGED_COMMANDS = cycle.STANDBY_TAGGED_COMMANDS
FULL_TRUNK_COMMANDS = cycle.FULL_TRUNK_COMMANDS
_syntax = port_writer._syntax
_MODES = (
    _syntax.EXEC,
    _syntax.CONFIG,
    r"(?:SSH@)?headwater\(config-vlan-10\)#",
    _syntax.CONFIG,
    _syntax.CONFIG,
    _syntax.EXEC,
)
_STANDBY_TAGGED_MODES = (*_MODES[:3], _MODES[2], *_MODES[3:])
Rejected = port_writer.Rejected


class _Capture:
    def __init__(self, console: Any, filename: str):
        self._console = console
        port_writer.unchanged_sources()
        port_writer._private_path(console.runtime, directory=True)
        fd = os.open(
            console.runtime / filename,
            os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
        )
        self.capture = os.fdopen(fd, "wb")
        self.channel = port_writer._CaptureChannel(console.channel, self.capture)
        self.raw = ""

    def save(self, raw: str) -> None:
        self.raw = raw
        self._console.save(raw)


class EmptyVlanTransport:
    """One ordered cycle; any failure leaves reconciliation to the caller.

    The caller supplies the console from the pinned bootstrap root session.
    Acknowledgements are raw diagnostics; whole-config evidence accepts changes.
    Use a context manager or close() if abandoning the cycle before completion.
    Received bytes are flushed before decoding to the private runtime wire file.
    """

    _commands: tuple[str, ...] = COMMANDS
    _modes: tuple[str, ...] = _MODES
    _capture_filename = "empty-vlan-received.raw"

    def __init__(self, console: Any):
        self._console = _Capture(console, self._capture_filename)
        self._index = 0
        self._failed = False
        self._active = False

    def __enter__(self) -> "EmptyVlanTransport":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        """Close byte capture without closing the caller's root session."""
        self._failed = True
        self._console.capture.close()

    def _unchanged_sources(self) -> None:
        port_writer.unchanged_sources()

    def _validate_response(self, index: int, response: str) -> None:
        pass

    def send(
        self, index: int, command: str, before_send: Callable[[], object]
    ) -> dict[str, str]:
        if self._failed:
            raise Rejected("empty VLAN transport failed")
        try:
            if (
                self._active
                or type(index) is not int
                or index != self._index
                or index >= len(self._commands)
                or command != self._commands[index]
                or not callable(before_send)
            ):
                raise Rejected("fixed empty VLAN command sequence required")
            self._active = True
            self._unchanged_sources()
            self._console.channel.sendall("\r")
            prompt = _syntax.read_mode(self._console, self._modes[index])
            if re.fullmatch(r"\n" + self._modes[index] + r" *", prompt) is None:
                raise Rejected("fresh empty current prompt required")
            self._unchanged_sources()
            result = before_send()
            if result is not None:
                if iscoroutine(result):
                    result.close()
                raise Rejected("durable intent must return None synchronously")
            self._unchanged_sources()
            if self._failed:
                raise Rejected("empty VLAN transport failed during intent")
            self._console.channel.sendall(self._commands[index] + "\r")
            response = _syntax.read_mode(self._console, self._modes[index + 1])
            self._validate_response(index, response)
            raw = self._console.raw
            self._index += 1
            return {
                "response_body": raw,
                "response_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
            }
        except BaseException:
            self._failed = True
            raise
        finally:
            self._active = False
            if self._failed or self._index == len(self._commands):
                self._console.capture.close()


class StandbyTaggedTransport(EmptyVlanTransport):
    """Fixed six-command standby tag and reversal on the caller's console."""

    _commands = STANDBY_TAGGED_COMMANDS
    _modes = _STANDBY_TAGGED_MODES
    _capture_filename = "standby-tagged-vlan-received.raw"


class FullTrunkTransport(EmptyVlanTransport):
    """Fixed trunk and inverse; unrecognized acknowledgements stop with raw capture."""

    _commands = FULL_TRUNK_COMMANDS
    _modes = (
        _syntax.EXEC,
        *trunk_writer.PROMPTS,
        *(_syntax.CONFIG for _ in range(5)),
        _syntax.EXEC,
    )
    _capture_filename = "full-trunk-received.raw"

    def _unchanged_sources(self) -> None:
        try:
            trunk_writer.unchanged_sources()
        except trunk_writer.Rejected as error:
            raise Rejected(str(error)) from error

    def _validate_response(self, index: int, response: str) -> None:
        self._unchanged_sources()
        if index < len(trunk_writer.COMMANDS):
            try:
                trunk_writer.validate_response(index + 1, response)
            except trunk_writer.Rejected as error:
                raise Rejected(str(error)) from error
        elif (
            re.fullmatch(
                re.escape(self._commands[index] + "\n")
                + self._modes[index + 1]
                + r" *",
                response,
            )
            is None
        ):
            raise Rejected("full trunk inverse echo or body boundary")
