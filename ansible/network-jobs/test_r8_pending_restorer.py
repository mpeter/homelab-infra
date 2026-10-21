"""Offline checks for the bounded pending R8 restore transport."""

import pytest
import time
from pathlib import Path
from typing import Any

import r8_pending_restorer as restorer
import native_trunk_plan as plan
import native_trunk_transport
import native_trunk_observation as trunk_observation
import port_description as evidence
import test_native_trunk_observation as trunk_fixtures


@pytest.mark.parametrize(
    ("count", "last", "accepted"),
    (
        (23, "empty-vlan-phase-22-command_11_intent.json", True),
        (29, "empty-vlan-phase-28-command_14_intent.json", True),
        (35, "empty-vlan-phase-34-command_17_intent.json", True),
        (29, "empty-vlan-phase-27-command_13_observed.json", False),
    ),
)
def test_recognizes_interrupted_forward_intent_shape(
    count: int, last: str, accepted: bool
) -> None:
    phases = [
        (Path(f"empty-vlan-phase-{index:02d}-unused.json"), b"", (1, 1))
        for index in range(count)
    ]
    phases[-1] = (Path(last), b"", (1, 1))

    assert restorer._recognized_phase_shape(phases) is accepted


def test_restore_accepts_brocade_default_vlan_transition_after_no_dual_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline = trunk_fixtures.r8_fixture()
    monkeypatch.setattr(
        plan, "R8_BASELINE_SHA256", evidence.configuration_hash(baseline)
    )
    initial = plan.build_r8_full_trunk_plan(baseline, baseline).initial_state
    state = plan._states(plan.R8_FULL_FORWARD, initial)[15]
    tables = trunk_fixtures.r8_tables(state)
    restorer._validate_vlan_membership(
        tables, trunk_fixtures.r8_tables(initial), state, initial
    )
    operational_state = plan.State(
        state.vlans, tuple(sorted((*state.native, plan.R8_PRIMARY_PORT)))
    )
    trunk_observation.require_r8_full_trunk_operational_state(
        trunk_fixtures.r8_operational(state), operational_state
    )
    inverse = plan.r8_full_inverse_commands(state)
    tagged_state = plan._states(inverse, state)[3]
    restorer._validate_vlan_membership(
        trunk_fixtures.r8_tables(tagged_state),
        trunk_fixtures.r8_tables(initial),
        tagged_state,
        initial,
    )
    trunk_observation.require_r8_full_trunk_operational_state(
        trunk_fixtures.r8_operational(tagged_state), tagged_state
    )


def test_restore_resumes_only_from_an_exact_inverse_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline = trunk_fixtures.r8_fixture()
    monkeypatch.setattr(
        plan, "R8_BASELINE_SHA256", evidence.configuration_hash(baseline)
    )
    initial = plan.build_r8_full_trunk_plan(baseline, baseline).initial_state
    original = plan._states(plan.R8_FULL_FORWARD, initial)[15]
    original_inverse = plan.r8_full_inverse_commands(original)
    context = {"inverse": original_inverse, "recorded_state": original}
    partial = plan._states(original_inverse, original)[3]

    commands = restorer._remaining_inverse(partial, context)

    assert commands == plan.r8_full_inverse_commands(partial)
    assert commands[0] == "configure terminal"
    assert "vlan 10" not in commands
    with pytest.raises(restorer.Rejected, match="outside the recorded restore path"):
        restorer._remaining_inverse(plan.State(), context)


def transport() -> restorer.RecoveryTransport:
    writer = object.__new__(restorer.RecoveryTransport)
    state = plan.State(
        tuple(
            (
                vlan,
                tuple(
                    port
                    for port in plan.PORTS
                    if vlan not in (10, 20, 30) or port != plan.R8_PRIMARY_PORT
                ),
            )
            for vlan, _ in plan.VLANS
        ),
        tuple(sorted(plan.PORTS)),
    )
    writer._commands = plan.r8_full_inverse_commands(state)
    writer._modes = native_trunk_transport._modes(writer._commands, state)
    writer._console = type("Console", (), {"raw": ""})()
    return writer


@pytest.mark.parametrize(
    "response",
    (
        "configure terminal\nSSH@headwater(config)#",
        "configure terminal\nWarning: 1 user(s) already in config mode.\n"
        "SSH@headwater(config)#",
    ),
)
def test_first_command_accepts_only_exact_config_mode_warning(
    monkeypatch: pytest.MonkeyPatch, response: str
) -> None:
    monkeypatch.setattr(native_trunk_transport, "unchanged_sources", lambda: None)
    transport()._validate_response(0, response)


@pytest.mark.parametrize(
    "response",
    (
        "configure terminal\nWarning: 2 users already in config mode.\n"
        "SSH@headwater(config)#",
        "configure terminal\nWarning: 1 user(s) already in config mode.\n"
        "extra output\nSSH@headwater(config)#",
        "configure terminal\nSSH@headwater(config-if-e10000-1/2/2)#",
        "wrong command\nSSH@headwater(config)#",
    ),
)
def test_first_command_rejects_unrecognized_response(
    monkeypatch: pytest.MonkeyPatch, response: str
) -> None:
    monkeypatch.setattr(native_trunk_transport, "unchanged_sources", lambda: None)
    with pytest.raises(native_trunk_transport.Rejected):
        transport()._validate_response(0, response)


def test_later_inverse_commands_keep_the_pinned_strict_parser(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(native_trunk_transport, "unchanged_sources", lambda: None)
    writer: Any = transport()
    writer._failed = False
    writer._active = False
    writer._index = 0
    response = f"{writer._commands[1]}\nSSH@headwater(config-vlan-10)#"
    writer._validate_response(1, response)
    with pytest.raises(native_trunk_transport.Rejected):
        writer._validate_response(
            1, response.replace("config-vlan-10", "config-vlan-20")
        )


def test_expired_deadline_stops_before_intent_or_any_console_write() -> None:
    writer = object.__new__(restorer.RecoveryTransport)
    writer._failed = False
    writer._active = False
    writer._index = 0
    writer._commands = ("configure terminal",)
    writer.deadline = time.monotonic() - 1
    writer._console = type(
        "Capture", (), {"capture": type("File", (), {"close": lambda self: None})()}
    )()
    sent: list[str] = []

    with pytest.raises(native_trunk_transport.Rejected):
        writer.send(0, "configure terminal", lambda: sent.append("intent"))

    assert sent == []


class Channel:
    def __init__(self, chunks: list[bytes]) -> None:
        self.chunks = chunks
        self.sent: list[str] = []

    @property
    def closed(self) -> bool:
        return False

    def recv_ready(self) -> bool:
        return bool(self.chunks)

    def recv(self, size: int) -> bytes:
        return self.chunks.pop(0)

    def sendall(self, value: str) -> None:
        self.sent.append(value)


class Capture:
    def __init__(self, channel: Channel) -> None:
        self.channel = channel
        self.raw = ""
        self.capture = type("File", (), {"close": lambda self: None})()

    def save(self, raw: str) -> None:
        self.raw = raw


def test_mode_reader_preserves_split_crlf() -> None:
    writer: Any = object.__new__(restorer.RecoveryTransport)
    writer.deadline = time.monotonic() + 2
    channel = Channel([b"\r", b"\nSSH@headwater#"])
    writer._console = Capture(channel)

    assert writer._read_mode(r"(?:SSH@)?headwater# *") == "\nSSH@headwater#"
    assert writer._console.raw == "\r\nSSH@headwater#"


def test_source_check_cannot_push_command_send_past_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    writer: Any = transport()
    writer._failed = False
    writer._active = False
    writer._index = 0
    channel = Channel([b"\r\nSSH@headwater#"])
    writer._console = Capture(channel)
    writer.deadline = time.monotonic() + 0.1
    checks = 0

    def source_check() -> None:
        nonlocal checks
        checks += 1
        if checks == 3:
            time.sleep(0.15)

    monkeypatch.setattr(native_trunk_transport, "unchanged_sources", source_check)
    with pytest.raises(TimeoutError):
        writer.send(0, writer._commands[0], lambda: None)

    assert channel.sent == ["\r"]
