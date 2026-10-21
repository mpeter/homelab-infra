"""Offline native trunk receive boundaries through the established real parser."""

import hashlib
from pathlib import Path
from unittest.mock import Mock

import pytest

import empty_vlan_transport as base
import native_trunk_plan as plan
import native_trunk_serial_plan as serial
import native_trunk_transport as transport
from test_empty_vlan_transport import CONFIG, EXEC, Console

V10 = "SSH@headwater(config-vlan-10)#"
I6 = "SSH@headwater(config-if-e40000-1/2/6)#"
I2 = "SSH@headwater(config-if-e10000-1/2/2)#"
I1 = "SSH@headwater(config-if-e10000-1/3/1)#"
FORWARD = (
    EXEC,
    CONFIG,
    V10,
    V10,
    CONFIG,
    I6,
    I6,
    CONFIG,
    V10,
    V10,
    CONFIG,
    I2,
    I2,
    CONFIG,
    V10,
    V10,
    CONFIG,
    I1,
    I1,
    CONFIG,
    *(["SSH@headwater(config-vlan-20)#"] * 4),
    CONFIG,
    *(["SSH@headwater(config-vlan-30)#"] * 4),
    CONFIG,
    *(["SSH@headwater(config-vlan-40)#"] * 4),
    CONFIG,
    EXEC,
)
INVERSE = (
    EXEC,
    CONFIG,
    CONFIG,
    CONFIG,
    CONFIG,
    I1,
    I1,
    CONFIG,
    V10,
    V10,
    CONFIG,
    I2,
    I2,
    CONFIG,
    V10,
    V10,
    CONFIG,
    I6,
    I6,
    CONFIG,
    V10,
    CONFIG,
    CONFIG,
    EXEC,
)
CASES = (
    (transport.NativeTrunkTransport, plan.FORWARD_COMMANDS, FORWARD),
    (transport.NativeTrunkInverseTransport, plan.INVERSE_COMMANDS, INVERSE),
)


@pytest.fixture(autouse=True)
def fast_reads(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(base._syntax.time, "sleep", lambda seconds: None)


def replies(commands: tuple[str, ...], modes: tuple[str, ...]) -> list[str]:
    modes = tuple(
        mode.replace("(?:SSH@)?", "SSH@")
        .replace(r"\(", "(")
        .replace(r"\)", ")")
        .replace(" *", "")
        for mode in modes
    )
    return [
        response
        for index, command in enumerate(commands)
        for response in (
            "\r\n" + modes[index],
            command + "\r\n" + modes[index + 1],
        )
    ]


@pytest.mark.parametrize("cls,commands,modes", CASES)
def test_complete_fixed_sequences(
    cls: type[transport.NativeTrunkTransport],
    commands: tuple[str, ...],
    modes: tuple[str, ...],
) -> None:
    responses = replies(commands, modes)
    console = Console(responses)
    writer = cls(console)
    for index, command in enumerate(commands):

        def intent() -> None:
            assert len(console.channel.sent) == 2 * index + 1
            assert console.channel.sent[-1] == "\r"

        callback = Mock(side_effect=intent)
        receipt = writer.send(index, command, callback)
        callback.assert_called_once_with()
        raw = responses[2 * index + 1]
        assert receipt == {
            "response_body": raw,
            "response_sha256": hashlib.sha256(raw.encode()).hexdigest(),
        }
    assert console.channel.sent == [
        value for command in commands for value in ("\r", command + "\r")
    ]
    assert (console.runtime / writer._capture_filename).read_bytes() == "".join(
        responses
    ).encode()
    assert writer._console.capture.closed
    assert transport.EXECUTION_QUALIFIED is False
    with pytest.raises(transport.Rejected):
        writer.send(len(commands), "write memory", lambda: None)
    assert len(console.channel.sent) == 2 * len(commands)


def test_r8_full_trunk_transport_selects_partial_inverse_at_forward_boundary() -> None:
    initial = plan.State(
        tuple((vlan, tuple(sorted(plan.PORTS))) for vlan, _ in plan.VLANS),
        tuple(sorted(plan.PORTS)),
    )
    partial = plan._states(plan.R8_FULL_FORWARD[:5], initial)[-1]
    inverse = plan.r8_full_inverse_commands(partial)
    modes = transport._modes(inverse, partial)
    responses = replies(inverse, modes)
    console = Console(responses)
    writer = transport.R8FullTrunkRecoveryTransport(console, partial)

    for index, command in enumerate(inverse):
        writer.send(index, command, lambda: None)

    assert writer._index == len(inverse)
    assert console.channel.sent == [
        value for command in inverse for value in ("\r", command + "\r")
    ]


STEPS = [
    (cls, commands, modes, index)
    for cls, commands, modes in CASES
    for index in range(len(commands))
]


@pytest.mark.parametrize("cls,commands,modes,index", STEPS)
@pytest.mark.parametrize("phase", [0, 1])
def test_wrong_prompt_at_every_boundary_stops_permanently(
    cls: type[transport.NativeTrunkTransport],
    commands: tuple[str, ...],
    modes: tuple[str, ...],
    index: int,
    phase: int,
) -> None:
    responses = replies(commands, modes)
    responses[2 * index + phase] = (
        "\r\n" if phase == 0 else commands[index] + "\r\n"
    ) + "SSH@headwater(config-if-e1000-1/1/47)#"
    console = Console(responses)
    writer = cls(console)
    for previous in range(index):
        writer.send(previous, commands[previous], lambda: None)
    callback = Mock(return_value=None)
    with pytest.raises(base._syntax.Rejected):
        writer.send(index, commands[index], callback)
    assert callback.call_count == phase
    assert console.channel.sent[2 * index :] == (
        ["\r", commands[index] + "\r"] if phase else ["\r"]
    )
    sent = console.channel.sent.copy()
    with pytest.raises(transport.Rejected):
        writer.send(index, commands[index], callback)
    assert console.channel.sent == sent
    assert writer._console.capture.closed


@pytest.mark.parametrize("cls,commands,modes", CASES)
def test_unknown_ack_retains_raw_and_does_not_retry(
    cls: type[transport.NativeTrunkTransport],
    commands: tuple[str, ...],
    modes: tuple[str, ...],
) -> None:
    responses = replies(commands, modes)
    responses[1] = commands[0] + "\r\nUnexpected response\r\n" + modes[1]
    console = Console(responses)
    writer = cls(console)
    with pytest.raises(transport.Rejected, match="unknown command response"):
        writer.send(0, commands[0], lambda: None)
    assert (console.runtime / writer._capture_filename).read_bytes() == "".join(
        responses[:2]
    ).encode()
    with pytest.raises(transport.Rejected):
        writer.send(0, commands[0], lambda: None)
    assert console.channel.sent == ["\r", commands[0] + "\r"]


@pytest.mark.parametrize("cls,commands,modes", CASES)
def test_intent_failure_and_partial_dispatch_latch(
    cls: type[transport.NativeTrunkTransport],
    commands: tuple[str, ...],
    modes: tuple[str, ...],
) -> None:
    for partial in (False, True):
        console = Console(replies(commands, modes))
        writer = cls(console)
        if partial:
            console.channel.partial_at = commands[0] + "\r"
            callback = Mock(return_value=None)
        else:
            callback = Mock(side_effect=OSError("intent fsync failed"))
        with pytest.raises(OSError):
            writer.send(0, commands[0], callback)
        callback.assert_called_once_with()
        assert (
            console.channel.sent == ["\r", commands[0] + "\r"]
            if partial
            else console.channel.sent == ["\r"]
        )
        sent = console.channel.sent.copy()
        with pytest.raises(transport.Rejected):
            writer.send(0, commands[0], lambda: None)
        assert console.channel.sent == sent


def test_source_drift_precedes_any_input(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(transport.SOURCE_SHA256, "native_trunk_plan", "0" * 64)
    console = Console(replies(plan.FORWARD_COMMANDS, FORWARD))
    writer = transport.NativeTrunkTransport(console)
    with pytest.raises(transport.Rejected, match="source drift"):
        writer.send(0, plan.FORWARD_COMMANDS[0], lambda: None)
    assert console.channel.sent == []


def test_only_new_source_paths_are_bound() -> None:
    assert transport.SOURCE_PATHS["native_trunk_plan"] == Path(plan.__file__).resolve()
    assert "write memory" not in (*plan.FORWARD_COMMANDS, *plan.INVERSE_COMMANDS)
    assert len(plan.FORWARD_COMMANDS) == 35
    assert len(plan.INVERSE_COMMANDS) == 23


@pytest.mark.parametrize("cls,commands,modes", CASES)
def test_known_tag_acknowledgements_are_exact(
    cls: type[transport.NativeTrunkTransport],
    commands: tuple[str, ...],
    modes: tuple[str, ...],
) -> None:
    responses = replies(commands, modes)
    vlan = 0
    for index, command in enumerate(commands):
        if command.startswith("vlan "):
            vlan = int(command.split()[1])
        ack = None
        if command.startswith("tagged ethernet "):
            ack = f"Added tagged port(s) ethe {command.split()[2]} to port-vlan {vlan}."
        elif command.startswith("no tagged ethernet "):
            ack = f"Deleted tagged port(s) to port-vlan {vlan}."
        if ack:
            responses[2 * index + 1] = (
                command + "\r\n" + ack + "\r\n" + modes[index + 1]
            )
    console = Console(responses)
    with cls(console) as writer:
        for index, command in enumerate(commands):
            writer.send(index, command, lambda: None)


@pytest.mark.parametrize(
    "index,wrong", [(2, "write memory"), (1, plan.FORWARD_COMMANDS[0])]
)
def test_arbitrary_or_out_of_order_command_never_dispatches(
    index: int, wrong: str
) -> None:
    console = Console(replies(plan.FORWARD_COMMANDS, FORWARD))
    writer = transport.NativeTrunkTransport(console)
    callback = Mock(return_value=None)
    with pytest.raises(transport.Rejected):
        writer.send(index, wrong, callback)
    callback.assert_not_called()
    assert console.channel.sent == []


def test_r8_probe_forward_and_partial_inverse_use_strict_transport() -> None:
    cases: list[tuple[plan.State | None, tuple[str, ...]]] = [
        (None, plan.R8_PROBE_FORWARD)
    ]
    cases.extend(
        (
            plan.expected_r8_probe_state(completed),
            plan.r8_probe_inverse_commands(plan.expected_r8_probe_state(completed)),
        )
        for completed in range(2, len(plan.R8_PROBE_FORWARD) + 1)
    )
    for state, commands in cases:
        initial = plan.State() if state is None else state
        modes = transport._modes(commands, initial)
        responses = replies(commands, modes)
        console = Console(responses)
        writer = transport.R8ProbeTransport(console, inverse_state=state)
        for index, command in enumerate(commands):
            writer.send(index, command, lambda: None)
        assert writer._console.capture.closed
        assert console.channel.sent == [
            value for command in commands for value in ("\r", command + "\r")
        ]


def test_r8_probe_cycle_transport_matches_semantic_cycle_sequence() -> None:
    commands = (
        *plan.R8_PROBE_FORWARD,
        *plan.r8_probe_inverse_commands(plan.R8_PROBE_FINAL_STATE),
    )
    assert commands == base.cycle.R8_PROBE_CYCLE_COMMANDS
    modes = transport._modes(commands)
    console = Console(replies(commands, modes))
    writer = transport.R8ProbeCycleTransport(console)
    for index, command in enumerate(commands):
        writer.send(index, command, lambda: None)
    assert writer._console.capture.closed
    assert console.channel.sent == [
        value for command in commands for value in ("\r", command + "\r")
    ]


def test_r8_probe_serial_plan_accepts_only_fixed_reachable_sequences() -> None:
    forward = serial.r8_probe_forward()
    assert serial.fixed_sequence(forward)
    for completed in range(2, len(plan.R8_PROBE_FORWARD) + 1):
        inverse = serial.r8_probe_inverse(plan.expected_r8_probe_state(completed))
        assert inverse and serial.fixed_sequence(inverse)
    with pytest.raises(transport.Rejected):
        serial.r8_probe_inverse(plan.State(((60, ("1/2/6",)),)))
