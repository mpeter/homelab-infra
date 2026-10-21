"""Offline tests of fixed commands, real prompt parsing, and failure latching."""

from collections.abc import Callable
import hashlib
from pathlib import Path
import tempfile
from types import CoroutineType
from typing import Any
from unittest.mock import Mock

import pytest

import empty_vlan_transport as transport
import port_writer

EXEC = "SSH@headwater#"
CONFIG = "SSH@headwater(config)#"
VLAN = "SSH@headwater(config-vlan-10)#"
MODES = (EXEC, CONFIG, VLAN, CONFIG, CONFIG, EXEC)


class Channel:
    def __init__(self, replies: list[str]):
        self.replies = replies.copy()
        self.chunks: list[bytes] = []
        self.sent: list[str] = []
        self.closed = False
        self.partial_at: str | None = None

    def sendall(self, command: str) -> None:
        self.sent.append(command)
        if command == self.partial_at:
            raise OSError("partial delivery")
        raw = self.replies.pop(0).encode("ascii")
        self.chunks = [raw[i : i + 1] for i in range(len(raw))]
        self.closed = False

    def recv_ready(self) -> bool:
        return bool(self.chunks)

    def recv(self, size: int) -> bytes:
        data = self.chunks.pop(0)
        self.closed = not self.chunks
        return data


class Console:
    def __init__(self, replies: list[str]):
        self._temporary = tempfile.TemporaryDirectory()
        self.runtime = Path(self._temporary.name)
        self.channel = Channel(replies)
        self.saved: list[str] = []

    def save(self, raw: str) -> None:
        self.saved.append(raw)


def replies() -> list[str]:
    return [
        response
        for index, command in enumerate(transport.COMMANDS)
        for response in (
            "\r\n" + MODES[index],
            command + "\r\nInformational acknowledgement\r\n" + MODES[index + 1],
        )
    ]


def attempt(
    console: Console, callback: Callable[[], object] = lambda: None
) -> transport.EmptyVlanTransport:
    instance = transport.EmptyVlanTransport(console)
    instance.send(0, transport.COMMANDS[0], callback)
    return instance


def test_full_cycle_returns_raw_diagnostics_and_refuses_reuse() -> None:
    console = Console(replies())
    instance = transport.EmptyVlanTransport(console)
    for index, command in enumerate(transport.COMMANDS):
        callback = Mock(return_value=None)
        result = instance.send(index, command, callback)
        callback.assert_called_once_with()
        raw = console.saved[-1]
        assert result == {
            "response_body": raw,
            "response_sha256": hashlib.sha256(raw.encode()).hexdigest(),
        }
        assert "\r\nInformational acknowledgement\r\n" in raw
    assert console.channel.sent == [
        value for command in transport.COMMANDS for value in ("\r", command + "\r")
    ]
    with pytest.raises(transport.Rejected):
        instance.send(0, transport.COMMANDS[0], lambda: None)
    assert len(console.channel.sent) == 10


@pytest.mark.parametrize("index", range(5))
@pytest.mark.parametrize("phase", (0, 1))
def test_wrong_prompt_stops_at_each_boundary(index: int, phase: int) -> None:
    responses = replies()
    bad = "\r\nSSH@headwater(config-if-e1000-1/1/47)#"
    responses[index * 2 + phase] = bad
    console = Console(responses)
    instance = transport.EmptyVlanTransport(console)
    for prior in range(index):
        instance.send(prior, transport.COMMANDS[prior], lambda: None)
    callback = Mock(return_value=None)
    with pytest.raises(transport._syntax.Rejected):
        instance.send(index, transport.COMMANDS[index], callback)
    assert callback.call_count == phase
    assert console.saved[-1] == bad
    sent = console.channel.sent.copy()
    with pytest.raises(transport.Rejected):
        instance.send(index, transport.COMMANDS[index], lambda: None)
    assert console.channel.sent == sent


@pytest.mark.parametrize(
    "raw",
    (
        "\r\n" + EXEC + "retained",
        "other\r\n" + EXEC,
        "\r\n" + CONFIG,
        "\r\nheadwater>",
    ),
)
def test_current_prompt_must_be_fresh_empty_exec(raw: str) -> None:
    console = Console([raw])
    callback = Mock(return_value=None)
    with pytest.raises((transport.Rejected, transport._syntax.Rejected)):
        attempt(console, callback)
    callback.assert_not_called()
    assert console.channel.sent == ["\r"]
    assert len(console.saved) == 1
    assert raw.startswith(console.saved[0])
    assert console.saved[0]


@pytest.mark.parametrize(
    "index, command",
    (
        (1, "exit"),
        (-1, "exit"),
        (True, "configure terminal"),
        (0, "reload"),
        (0, "configure terminal\rreload"),
    ),
)
def test_arbitrary_commands_and_indices_never_send(index: int, command: str) -> None:
    console = Console([])
    instance = transport.EmptyVlanTransport(console)
    with pytest.raises(transport.Rejected):
        instance.send(index, command, lambda: None)
    with pytest.raises(transport.Rejected):
        instance.send(0, transport.COMMANDS[0], lambda: None)
    assert console.channel.sent == []


@pytest.mark.parametrize("value", (False, 0, "", object()))
def test_callback_must_return_none(value: object) -> None:
    console = Console(replies())
    callback = Mock(return_value=value)
    with pytest.raises(transport.Rejected):
        attempt(console, callback)
    callback.assert_called_once_with()
    assert console.channel.sent == ["\r"]


def test_callback_exception_and_async_result_never_send() -> None:
    console = Console(replies())
    with pytest.raises(OSError):
        attempt(console, Mock(side_effect=OSError("intent failure")))
    assert console.channel.sent == ["\r"]
    body = Mock()

    async def callback() -> None:
        body()

    coroutine = callback()
    console = Console(replies())
    with pytest.raises(transport.Rejected):
        attempt(console, lambda: coroutine)
    body.assert_not_called()
    assert isinstance(coroutine, CoroutineType)
    assert coroutine.cr_frame is None
    assert console.channel.sent == ["\r"]


@pytest.mark.parametrize("failure", (1, 2, 3))
def test_source_checks_surround_callback(
    monkeypatch: pytest.MonkeyPatch, failure: int
) -> None:
    events: list[str] = []

    def check() -> None:
        events.append("check")
        if events.count("check") == failure:
            raise transport.Rejected("source drift")

    def callback() -> None:
        assert console.channel.sent == ["\r"]
        events.append("intent")

    console = Console(replies())
    instance = transport.EmptyVlanTransport(console)
    monkeypatch.setattr(port_writer, "unchanged_sources", check)
    with pytest.raises(transport.Rejected):
        instance.send(0, transport.COMMANDS[0], callback)
    assert console.channel.sent == ([] if failure == 1 else ["\r"])
    assert events == (
        ["check"]
        if failure == 1
        else ["check", "check"]
        if failure == 2
        else ["check", "check", "intent", "check"]
    )


@pytest.mark.parametrize("raw", ("partial response", "bad\x7f", "% Error: denied"))
def test_response_failures_preserve_capture_without_unwind(raw: str) -> None:
    console = Console(["\r\n" + EXEC, raw])
    instance = transport.EmptyVlanTransport(console)
    with pytest.raises(transport._syntax.Rejected):
        instance.send(0, transport.COMMANDS[0], lambda: None)
    assert console.saved[-1]
    assert raw.startswith(console.saved[-1])
    assert console.channel.sent == ["\r", "configure terminal\r"]
    with pytest.raises(transport.Rejected):
        instance.send(0, transport.COMMANDS[0], lambda: None)


def test_partial_delivery_never_retries() -> None:
    console = Console(replies())
    console.channel.partial_at = "configure terminal\r"
    instance = transport.EmptyVlanTransport(console)
    with pytest.raises(OSError):
        instance.send(0, transport.COMMANDS[0], lambda: None)
    with pytest.raises(transport.Rejected):
        instance.send(0, transport.COMMANDS[0], lambda: None)
    assert console.channel.sent == ["\r", "configure terminal\r"]


def test_reentrant_callback_latches_even_if_caller_swallows_failure() -> None:
    console = Console(replies())
    instance = transport.EmptyVlanTransport(console)

    def callback() -> None:
        with pytest.raises(transport.Rejected):
            instance.send(0, transport.COMMANDS[0], lambda: None)

    with pytest.raises(transport.Rejected):
        instance.send(0, transport.COMMANDS[0], callback)
    assert console.channel.sent == ["\r"]


def test_timeout_keeps_partial_raw(monkeypatch: pytest.MonkeyPatch) -> None:
    console = Console(["\r\n" + EXEC, "partial"])
    real_reader = transport._syntax.read_mode

    def reader(captured: Any, prompt: str) -> str:
        if prompt == transport._syntax.EXEC:
            return str(real_reader(captured, prompt))
        ticks = iter([0.0, 0.0, 21.0])
        monkeypatch.setattr(transport._syntax.time, "monotonic", lambda: next(ticks))
        monkeypatch.setattr(console.channel, "recv", lambda size: b"partial")
        return str(real_reader(captured, prompt))

    monkeypatch.setattr(transport._syntax, "read_mode", reader)
    with pytest.raises(transport._syntax.Rejected, match="incomplete mode response"):
        attempt(console)
    assert console.saved[-1] == "partial"


def test_post_prompt_accepts_diagnostic_body_without_exact_echo() -> None:
    raw = "notice\r\n" + CONFIG
    console = Console(["\r\n" + EXEC, raw])
    instance = transport.EmptyVlanTransport(console)
    assert instance.send(0, transport.COMMANDS[0], lambda: None)["response_body"] == raw


def test_invalid_ascii_retains_offending_wire_bytes() -> None:
    console = Console(["\r\n" + EXEC, "ignored"])
    original_send = console.channel.sendall

    def send(command: str) -> None:
        original_send(command)
        if command == "configure terminal\r":
            console.channel.chunks = [b"diagnostic\r\n", b"\xffbad"]

    setattr(console.channel, "sendall", send)
    instance = transport.EmptyVlanTransport(console)
    with pytest.raises(UnicodeError):
        instance.send(0, transport.COMMANDS[0], lambda: None)
    wire = console.runtime / "empty-vlan-received.raw"
    assert wire.read_bytes() == ("\r\n" + EXEC).encode() + b"diagnostic\r\n\xffbad"
    assert wire.stat().st_mode & 0o777 == 0o600
    assert instance._console.capture.closed
    with pytest.raises(transport.Rejected):
        instance.send(0, transport.COMMANDS[0], lambda: None)
    assert console.channel.sent == ["\r", "configure terminal\r"]


def test_context_exit_closes_capture_without_closing_root_channel() -> None:
    console = Console(replies())
    with transport.EmptyVlanTransport(console) as instance:
        instance.send(0, transport.COMMANDS[0], lambda: None)
        assert not instance._console.capture.closed
    assert instance._console.capture.closed
    assert console.channel.sent == ["\r", "configure terminal\r"]
    with pytest.raises(transport.Rejected):
        instance.send(1, transport.COMMANDS[1], lambda: None)


def test_existing_wire_capture_is_never_overwritten() -> None:
    console = Console([])
    wire = console.runtime / "empty-vlan-received.raw"
    wire.write_bytes(b"previous evidence")
    with pytest.raises(FileExistsError):
        transport.EmptyVlanTransport(console)
    assert wire.read_bytes() == b"previous evidence"
    assert console.channel.sent == []


TAGGED_MODES = (EXEC, CONFIG, VLAN, VLAN, CONFIG, CONFIG, EXEC)


def tagged_replies() -> list[str]:
    return [
        response
        for index, command in enumerate(transport.STANDBY_TAGGED_COMMANDS)
        for response in (
            "\r\n" + TAGGED_MODES[index],
            command
            + "\r\n"
            + (
                "Deleted tagged port(s) to port-vlan 10."
                if index == 3
                else "Diagnostic"
            )
            + "\r\n"
            + TAGGED_MODES[index + 1],
        )
    ]


def test_standby_tagged_commands_prompts_and_received_bytes() -> None:
    responses = tagged_replies()
    console = Console(responses)
    instance = transport.StandbyTaggedTransport(console)
    for index, command in enumerate(transport.STANDBY_TAGGED_COMMANDS):
        callback = Mock(return_value=None)
        result = instance.send(index, command, callback)
        callback.assert_called_once_with()
        assert result["response_body"] == responses[2 * index + 1]
    assert "Deleted tagged port(s) to port-vlan 10.\r\n" + CONFIG in responses[7]
    assert console.channel.sent == [
        value
        for command in transport.STANDBY_TAGGED_COMMANDS
        for value in ("\r", command + "\r")
    ]
    wire = console.runtime / "standby-tagged-vlan-received.raw"
    assert wire.read_bytes() == "".join(responses).encode()
    assert wire.stat().st_mode & 0o777 == 0o600
    assert instance._console.capture.closed
    with pytest.raises(transport.Rejected):
        instance.send(0, transport.STANDBY_TAGGED_COMMANDS[0], lambda: None)


@pytest.mark.parametrize("index", range(6))
@pytest.mark.parametrize("phase", (0, 1))
def test_standby_wrong_prompt_latches_at_every_boundary(index: int, phase: int) -> None:
    responses = tagged_replies()
    bad = "\r\nSSH@headwater(config-if-e1000-1/1/47)#"
    responses[index * 2 + phase] = bad
    console = Console(responses)
    instance = transport.StandbyTaggedTransport(console)
    for prior in range(index):
        instance.send(prior, transport.STANDBY_TAGGED_COMMANDS[prior], lambda: None)
    callback = Mock(return_value=None)
    with pytest.raises(transport._syntax.Rejected):
        instance.send(index, transport.STANDBY_TAGGED_COMMANDS[index], callback)
    assert callback.call_count == phase
    assert (
        (console.runtime / "standby-tagged-vlan-received.raw")
        .read_bytes()
        .endswith(bad.encode())
    )
    sent = console.channel.sent.copy()
    with pytest.raises(transport.Rejected):
        instance.send(index, transport.STANDBY_TAGGED_COMMANDS[index], lambda: None)
    assert console.channel.sent == sent


@pytest.mark.parametrize(
    "command",
    ["tagged ethernet 1/2/2", "exit", "write memory", "tagged ethernet 1/2/6\rreload"],
)
def test_standby_rejects_altered_sequence(command: str) -> None:
    console = Console(tagged_replies())
    instance = transport.StandbyTaggedTransport(console)
    for index in range(2):
        instance.send(index, transport.STANDBY_TAGGED_COMMANDS[index], lambda: None)
    sent = console.channel.sent.copy()
    with pytest.raises(transport.Rejected):
        instance.send(2, command, lambda: None)
    assert console.channel.sent == sent


def test_standby_inverse_must_autoexit_to_config() -> None:
    responses = tagged_replies()
    responses[7] = (
        "no tagged ethernet 1/2/6\r\nDeleted tagged port(s) to port-vlan 10.\r\n" + VLAN
    )
    console = Console(responses)
    instance = transport.StandbyTaggedTransport(console)
    for index in range(3):
        instance.send(index, transport.STANDBY_TAGGED_COMMANDS[index], lambda: None)
    with pytest.raises(transport._syntax.Rejected):
        instance.send(3, transport.STANDBY_TAGGED_COMMANDS[3], lambda: None)
    sent = console.channel.sent.copy()
    with pytest.raises(transport.Rejected):
        instance.send(3, transport.STANDBY_TAGGED_COMMANDS[3], lambda: None)
    assert console.channel.sent == sent
    assert sent.count("no tagged ethernet 1/2/6\r") == 1


@pytest.fixture
def full_fast_reads(monkeypatch: pytest.MonkeyPatch) -> None:
    # Fragmented offline replies are already ready; no real transport polling delay.
    monkeypatch.setattr(transport._syntax.time, "sleep", lambda seconds: None)


def full_modes() -> tuple[str, ...]:
    return (
        EXEC,
        CONFIG,
        *(
            prompt
            for vlan_id in (10, 20, 30, 40)
            for prompt in (
                *(f"SSH@headwater(config-vlan-{vlan_id})#" for _ in range(4)),
                CONFIG,
            )
        ),
        EXEC,
        *(CONFIG for _ in range(5)),
        EXEC,
    )


def full_replies() -> list[str]:
    modes = full_modes()
    responses: list[str] = []
    for index, command in enumerate(transport.FULL_TRUNK_COMMANDS):
        body = command + "\r\n"
        if command.startswith("tagged ethernet "):
            port = command.removeprefix("tagged ethernet ")
            vlan_id = (10, 20, 30, 40)[(index - 2) // 5]
            body += f"Added tagged port(s) ethe {port} to port-vlan {vlan_id}.\r\n"
        responses.extend(["\r\n" + modes[index], body + modes[index + 1]])
    return responses


def test_full_trunk_exact_acknowledgements_and_capture(full_fast_reads: None) -> None:
    responses = full_replies()
    console = Console(responses)
    instance = transport.FullTrunkTransport(console)
    for index, command in enumerate(transport.FULL_TRUNK_COMMANDS):
        callback = Mock(return_value=None)
        result = instance.send(index, command, callback)
        callback.assert_called_once_with()
        assert result["response_body"] == responses[2 * index + 1]
    assert console.channel.sent == [
        value
        for command in transport.FULL_TRUNK_COMMANDS
        for value in ("\r", command + "\r")
    ]
    assert (console.runtime / "full-trunk-received.raw").read_bytes() == (
        "".join(responses).encode()
    )
    assert instance._console.capture.closed
    sent = console.channel.sent.copy()
    with pytest.raises(transport.Rejected):
        instance.send(0, transport.FULL_TRUNK_COMMANDS[0], lambda: None)
    assert console.channel.sent == sent


@pytest.mark.parametrize("index", range(28))
@pytest.mark.parametrize("phase", [0, 1])
def test_full_trunk_wrong_prompt_latches_at_every_boundary(
    full_fast_reads: None, index: int, phase: int
) -> None:
    responses = full_replies()
    responses[2 * index + phase] = "\r\nSSH@headwater(config-if-e1000-1/1/47)#"
    console = Console(responses)
    instance = transport.FullTrunkTransport(console)
    for prior in range(index):
        instance.send(prior, transport.FULL_TRUNK_COMMANDS[prior], lambda: None)
    callback = Mock(return_value=None)
    with pytest.raises(transport._syntax.Rejected):
        instance.send(index, transport.FULL_TRUNK_COMMANDS[index], callback)
    assert callback.call_count == phase
    assert (
        (console.runtime / "full-trunk-received.raw")
        .read_bytes()
        .endswith(responses[2 * index + phase].encode())
    )
    sent = console.channel.sent.copy()
    with pytest.raises(transport.Rejected):
        instance.send(index, transport.FULL_TRUNK_COMMANDS[index], lambda: None)
    assert console.channel.sent == sent


@pytest.mark.parametrize(
    "index", [2, 3, 4, 7, 8, 9, 12, 13, 14, 17, 18, 19, 23, 24, 25, 26]
)
@pytest.mark.parametrize("kind", ["missing", "extra", "wrong_port", "wrong_vlan"])
def test_full_trunk_unknown_ack_stops_with_raw_capture(
    full_fast_reads: None,
    index: int,
    kind: str,
) -> None:
    responses = full_replies()
    response = responses[2 * index + 1]
    if kind == "missing":
        response = "\r\n" + full_modes()[index + 1]
    elif kind == "extra":
        response = response.replace("\r\n", "\r\nUnexpected deletion notice\r\n", 1)
    elif kind == "wrong_port":
        response = response.replace(
            "Added tagged port(s) ethe", "Added tagged port(s) ethe 1/1/48"
        )
    else:
        response = response.replace("to port-vlan", "to port-vlan 50")
    # Deletion responses carry only an echo; any additional acknowledgement is unqualified.
    if response == responses[2 * index + 1]:
        response = response.replace(
            "\r\n", "\r\nDeleted tagged port(s) to port-vlan 40.\r\n", 1
        )
    responses[2 * index + 1] = response
    console = Console(responses)
    instance = transport.FullTrunkTransport(console)
    for prior in range(index):
        instance.send(prior, transport.FULL_TRUNK_COMMANDS[prior], lambda: None)
    with pytest.raises(transport.Rejected):
        instance.send(index, transport.FULL_TRUNK_COMMANDS[index], lambda: None)
    assert (
        (console.runtime / "full-trunk-received.raw")
        .read_bytes()
        .endswith(response.encode())
    )
    sent = console.channel.sent.copy()
    with pytest.raises(transport.Rejected):
        instance.send(index, transport.FULL_TRUNK_COMMANDS[index], lambda: None)
    assert console.channel.sent == sent
