"""Private-ledger qualification of the bounded empty VLAN serialization cycle."""

from collections.abc import Callable
import hashlib
from importlib.util import module_from_spec, spec_from_file_location
from itertools import pairwise
from pathlib import Path
from typing import Any
from unittest.mock import patch

import empty_vlan_cycle as cycle
import native_trunk_transport as native_transport
import r8_probe_admission as admission
import r8_guest_producer as guest_producer
import native_trunk_plan as native_plan
import port_description as evidence
import port_exercise_ledger as storage
import pytest
import standby_native_transport
from test_empty_vlan_transport import Console as StrictConsole
from test_native_trunk_transport import replies as strict_replies
from test_standby_native_observation import (
    EXISTING as R8_BASELINE,
    brief as native_brief,
)
from test_native_trunk_observation import r8_fixture, r8_running
from test_port_exercise import evidence as payload
from test_trunk_step import BASELINE, state
from test_trunk_link_admission import brief
from test_r8_guest_acceptance import (
    receipts as guest_receipts,
    synthetic_evidence,
)

RESIDENT_PATH = (
    Path(__file__).resolve().parents[2]
    / "network/config-backup-preflight/native-trunk-resident.py"
)
resident_spec = spec_from_file_location("r8_probe_test_resident", RESIDENT_PATH)
assert resident_spec is not None and resident_spec.loader is not None
resident = module_from_spec(resident_spec)
resident_spec.loader.exec_module(resident)


def valid_guest_proof(_held: dict[str, Any], binding: dict[str, Any]) -> dict[str, Any]:
    proof, _, _ = synthetic_evidence()
    proof.update(binding)
    guest_receipts(proof)
    return proof


class CallbackProducer(guest_producer.Producer):
    """Bind existing cycle fixtures to the production callback type."""

    def __init__(self, callback):
        object.__setattr__(self, "callback", callback)

    def __call__(self, held, binding):
        return self.callback(held, binding)


class Device:
    def __init__(self, guarded: storage.ExerciseLedger, failure: str = ""):
        self.guarded = guarded
        self.position = 0
        self.failure = failure
        self.sent: list[str] = []
        self.callback: Callable[[], None] | None = None
        self.binding = {
            "baseline_running_sha256": evidence.configuration_hash(BASELINE),
            "baseline_startup_sha256": evidence.configuration_hash(BASELINE),
            "source_binding_sha256": cycle.SOURCE_DIGEST,
            "execution_environment_sha256": evidence.EE_DIGEST,
            "preview_sha256": cycle.preview_digest(BASELINE),
            "native_recovery_proof_sha256": "a" * 64,
        }

    def observe(self) -> dict[str, Any]:
        running = state(2) if self.position in (2, 3) else BASELINE
        startup: tuple[str, ...] = BASELINE
        if self.position == 2:
            if self.failure == "startup":
                startup = running
            elif self.failure == "extra":
                running = (*running[:-1], "vlan 50 name EXTRA by port", "end")
            elif self.failure == "port":
                running = tuple(
                    " port-name changed" if x == " port-name standby" else x
                    for x in running
                )
            elif self.failure == "tagged":
                running = state(3)
            elif self.failure == "binding":
                self.binding["native_recovery_proof_sha256"] = "b" * 64
            elif self.failure == "pending":
                self.guarded.pending.write_text("changed")
        result = payload(running, startup)  # type: ignore[no-untyped-call]
        assert isinstance(result, dict)
        return result

    def admit(self) -> None:
        return None

    def send(
        self, index: int, command: str, before_send: Callable[[], None]
    ) -> dict[str, Any]:
        self.callback = before_send
        assert index == self.position
        assert command == cycle.COMMANDS[index]
        if self.failure == "missing":
            return {}
        before_send()
        path = (
            self.guarded.runtime
            / f"empty-vlan-phase-{2 * index:02d}-command_{index}_intent.json"
        )
        assert path.exists()
        self.sent.append(command)
        self.position += 1
        if self.failure == "timeout":
            raise TimeoutError("unknown send outcome")
        if self.failure == "double":
            try:
                before_send()
            except evidence.Rejected:
                pass
        body = "opaque firmware acknowledgement, extra text\n"
        return {"response_body": body, "response_sha256": storage.digest(body.encode())}

    def run(self) -> dict[str, object]:
        return cycle._run_cycle(
            self.guarded,
            BASELINE,
            self.observe,
            self.send,
            self.admit,
            self.binding,
            baseline_sha256=evidence.configuration_hash(BASELINE),
        )


class R8ProbeDevice(Device):
    def __init__(self, guarded: storage.ExerciseLedger, failure: str = ""):
        self.guarded = guarded
        self.position = 0
        self.failure = failure
        self.sent: list[str] = []
        self.binding = {
            "baseline_running_sha256": evidence.configuration_hash(R8_BASELINE),
            "baseline_startup_sha256": evidence.configuration_hash(R8_BASELINE),
            "source_binding_sha256": cycle.SOURCE_DIGEST,
            "execution_environment_sha256": evidence.EE_DIGEST,
            "preview_sha256": cycle._preview_digest(
                R8_BASELINE, cycle.CycleProfile.R8_PROBE
            ),
            "native_recovery_proof_sha256": "d" * 64,
        }

    def observe(self) -> dict[str, Any]:
        forward = len(native_plan.R8_PROBE_FORWARD)
        if self.position <= forward:
            probe_state = native_plan.expected_r8_probe_state(self.position)
        else:
            probe_state = native_plan.expected_r8_probe_state(
                self.position - forward, inverse=True
            )
        running = list(R8_BASELINE)
        if 60 in dict(probe_state.vlans):
            index = running.index("end")
            stanza = ["vlan 60 name M7-QUALIFY by port"]
            if probe_state.tagged(60):
                stanza.append(" tagged ethe 1/2/2")
            stanza.append("!")
            running[index:index] = stanza
        startup: tuple[str, ...] = R8_BASELINE
        if self.failure == "startup" and self.position == 2:
            startup = tuple(running)
        result = payload(tuple(running), startup)  # type: ignore[no-untyped-call]
        assert isinstance(result, dict)
        rows = []
        expected_tag = any(
            line.lstrip().startswith("tagged ") and "1/2/2" in line.split()
            for line in R8_BASELINE
        ) or "1/2/2" in probe_state.tagged(60)
        for line in brief().splitlines():
            words = line.split()
            if words and words[0] == "1/2/2":
                words[1:6] = ["Down", "None", "None", "None", "None"]
                words[6] = "Yes" if expected_tag else "No"
                words[7] = "1"
                line = " ".join(words)
            rows.append(line)
        result["responses"]["show interfaces brief"] = "\n".join(rows)
        return result

    def send(
        self, index: int, command: str, before_send: Callable[[], None]
    ) -> dict[str, Any]:
        assert index == self.position
        assert command == cycle.R8_PROBE_CYCLE_COMMANDS[index]
        before_send()
        self.sent.append(command)
        self.position += 1
        body = "synthetic command response\n"
        return {"response_body": body, "response_sha256": storage.digest(body.encode())}

    def run(self) -> dict[str, object]:
        return cycle._run_cycle(
            self.guarded,
            R8_BASELINE,
            self.observe,
            self.send,
            self.admit,
            self.binding,
            baseline_sha256=evidence.configuration_hash(R8_BASELINE),
            profile=cycle.CycleProfile.R8_PROBE,
        )


class StrictR8ProbeDevice(R8ProbeDevice):
    def __init__(self, guarded: storage.ExerciseLedger):
        super().__init__(guarded)
        commands = cycle.R8_PROBE_CYCLE_COMMANDS
        self.console = StrictConsole(
            strict_replies(commands, native_transport._modes(commands))
        )
        self.writer = native_transport.R8ProbeCycleTransport(self.console)

    def send(
        self, index: int, command: str, before_send: Callable[[], None]
    ) -> dict[str, Any]:
        assert index == self.position
        assert command == cycle.R8_PROBE_CYCLE_COMMANDS[index]
        acknowledgement = self.writer.send(index, command, before_send)
        self.sent.append(command)
        self.position += 1
        return acknowledgement


class R8FullTrunkDevice:
    def __init__(self, guarded: storage.ExerciseLedger):
        self.guarded = guarded
        self.baseline = r8_fixture()
        self.initial = native_plan._r8_full_initial_state(self.baseline)
        self.forward_states = native_plan._states(
            native_plan.R8_FULL_FORWARD, self.initial
        )
        self.inverse_states = native_plan._states(
            native_plan.R8_FULL_INVERSE, self.forward_states[-1]
        )
        self.position = 0
        self.live_state: native_plan.State | None = None
        self.binding = {
            "baseline_running_sha256": evidence.configuration_hash(self.baseline),
            "baseline_startup_sha256": evidence.configuration_hash(self.baseline),
            "source_binding_sha256": cycle.SOURCE_DIGEST,
            "execution_environment_sha256": evidence.EE_DIGEST,
            "preview_sha256": cycle.r8_full_trunk_preview_digest(self.baseline),
            "native_recovery_proof_sha256": "f" * 64,
        }

    def state(self) -> native_plan.State:
        if self.live_state is not None:
            return self.live_state
        forward_count = len(native_plan.R8_FULL_FORWARD)
        if self.position <= forward_count:
            return self.forward_states[self.position]
        return self.inverse_states[self.position - forward_count]

    def observe(self) -> dict[str, Any]:
        state = self.state()
        running = r8_running(state, self.baseline)
        result = payload(running, self.baseline)  # type: ignore[no-untyped-call]
        assert isinstance(result, dict)
        rows = []
        for line in brief().splitlines():
            words = line.split()
            if words and words[0] in native_plan.PORTS:
                words[6] = (
                    "Yes"
                    if any(words[0] in members for _, members in state.vlans)
                    else "No"
                )
                if words[0] == native_plan.R8_PRIMARY_PORT:
                    words[1:6] = ["Down", "None", "None", "None", "None"]
                    primary_tagged = any(
                        native_plan.R8_PRIMARY_PORT in members
                        for _, members in state.vlans
                    )
                    words[7] = (
                        "N/A"
                        if words[0] not in state.native and primary_tagged
                        else "1"
                    )
                else:
                    words[7] = "1"
                line = " ".join(words)
            rows.append(line)
        result["responses"]["show interfaces brief"] = "\n".join(rows)
        tables = r8_vlan_tables(state)
        result["r8_vlan_tables"] = tables
        result["r8_vlan_baseline_tables"] = r8_vlan_tables(self.initial)
        result["r8_vlan_commands"] = list(admission.observation.R8_VLAN_COMMANDS)
        result["r8_vlan_capture_sha256"] = {
            command: hashlib.sha256(
                f"show vlan {vlan}\n{tables[str(vlan)]}".encode()
            ).hexdigest()
            for command, vlan in zip(
                admission.observation.R8_VLAN_COMMANDS,
                admission.observation.R8_VLAN_IDS,
                strict=True,
            )
        }
        return result

    def admit(self) -> None:
        return None


def open_r8_recovery_session(device: R8FullTrunkDevice):
    held_state = native_plan._states(native_plan.R8_FULL_FORWARD, device.initial)[-1]
    inverse = native_plan.r8_full_inverse_commands(held_state)
    modes = native_transport._modes(inverse, held_state)
    console = StrictConsole(strict_replies(inverse, modes))
    channel_send = console.channel.sendall

    def advance(command: str) -> None:
        channel_send(command)
        if command != "\r":
            device.position += 1

    console.channel.sendall = advance  # type: ignore[method-assign]
    return device.observe, console, lambda: None


def r8_vlan_tables(state: native_plan.State) -> dict[str, str]:
    memberships = {1: (), 132: (), **dict(state.vlans)}
    names = {1: "DEFAULT-VLAN", 132: "DEFAULT-DECKPIN", **dict(native_plan.VLANS)}
    tables = {}
    for vlan, tagged in memberships.items():
        ports = sorted(
            (tuple(int(part) for part in port.split("/")) for port in tagged)
        )
        by_slot: dict[tuple[int, int], list[int]] = {}
        for unit, slot, number in ports:
            by_slot.setdefault((unit, slot), []).append(number)
        row = (
            "\n".join(
                f"Tagged Ports: (U{unit}/M{slot}) " + " ".join(map(str, numbers))
                for (unit, slot), numbers in by_slot.items()
            )
            or "Tagged Ports: None"
        )
        dual_ports = (
            sorted(
                tuple(int(part) for part in port.split("/")) for port in state.native
            )
            if vlan == 1
            else []
        )
        dual_by_slot: dict[tuple[int, int], list[int]] = {}
        for unit, slot, number in dual_ports:
            dual_by_slot.setdefault((unit, slot), []).append(number)
        dual_row = (
            "\n".join(
                f"DualMode Ports: (U{unit}/M{slot}) " + " ".join(map(str, numbers))
                for (unit, slot), numbers in dual_by_slot.items()
            )
            or "DualMode Ports: None"
        )
        spanning = "On" if vlan in (1, 132) else "Off"
        primary = tuple(int(part) for part in native_plan.R8_PRIMARY_PORT.split("/"))
        primary_tagged = any(
            native_plan.R8_PRIMARY_PORT in members for _, members in state.vlans
        )
        untagged = (
            f"Untagged Ports: (U{primary[0]}/M{primary[1]}) {primary[2]}"
            if vlan == 1
            and native_plan.R8_PRIMARY_PORT not in state.native
            and not primary_tagged
            else "Untagged Ports: None"
        )
        tables[str(vlan)] = "\n".join(
            (
                "Total PORT-VLAN entries: 6",
                "Maximum PORT-VLAN entries: 64",
                "Legend: [Stk=Stack-Id, S=Slot]",
                f"PORT-VLAN {vlan}, Name {names[vlan]}, Priority level0, Spanning tree {spanning}",
                untagged,
                row,
                "Uplink Ports: None",
                dual_row,
                "Mac-Vlan Ports: None",
                "Monitoring: Disabled",
            )
        )
    return tables


def test_r8_full_vlan_tables_bind_the_exact_primary_tag_delta() -> None:
    baseline = r8_fixture()
    initial = native_plan._r8_full_initial_state(baseline)
    expected = native_plan.State(
        tuple(
            (vlan, tuple(port for port in ports if port != native_plan.R8_PRIMARY_PORT))
            for vlan, ports in initial.vlans
        ),
        tuple(port for port in initial.native if port != native_plan.R8_PRIMARY_PORT),
    )
    baseline_tables = r8_vlan_tables(initial)
    admission.observation.require_r8_full_trunk_membership(
        r8_vlan_tables(expected), baseline_tables, expected, initial
    )
    with pytest.raises(evidence.Rejected, match="R8 VLAN1 or VLAN132 membership drift"):
        admission.observation.require_r8_full_trunk_membership(
            baseline_tables, baseline_tables, expected, initial
        )
    with pytest.raises(evidence.Rejected, match="complete R8 VLAN table"):
        admission.observation.require_r8_full_trunk_membership(
            {}, baseline_tables, expected, initial
        )


def rechain_r8_cycle(runtime: Path) -> None:
    records = sorted(runtime.glob("empty-vlan-phase-*.json"))
    receipt_path = runtime / "empty-vlan-complete.json"
    receipt = storage.decode(receipt_path.read_bytes())
    previous = storage.digest(storage.canonical(receipt["operation"]))
    for path in records:
        record = storage.decode(path.read_bytes())
        record["prev_digest"] = previous
        raw = storage.canonical(record)
        path.write_bytes(raw)
        previous = storage.digest(raw)
    final = storage.decode(records[-1].read_bytes())
    receipt["final_digest"] = storage.digest(records[-1].read_bytes())
    receipt["final_observation"] = final["evidence"]
    receipt_path.write_bytes(storage.canonical(receipt))


@pytest.fixture
def private_root(tmp_path: Path) -> tuple[Path, Path]:
    tmp_path.chmod(0o700)
    runtime = tmp_path / "runtime"
    runtime.mkdir(mode=0o700)
    return tmp_path, runtime


def test_exact_cycle_receipts_and_late_callback(
    private_root: tuple[Path, Path],
) -> None:
    with storage.locked_exercise(*private_root) as guarded:
        device = Device(guarded)
        result = device.run()
        assert device.sent == list(cycle.COMMANDS)
        assert result["cycle_passed"] is True
        assert result["acknowledgement_parser_qualified"] is False
        assert not guarded.pending.exists()
        records = sorted(guarded.runtime.glob("empty-vlan-phase-*.json"))
        assert len(records) == 11
        for previous, current in pairwise(records):
            assert storage.decode(current.read_bytes())[
                "prev_digest"
            ] == storage.digest(previous.read_bytes())
        observed = storage.decode(records[1].read_bytes())
        assert observed["acknowledgement_parser_qualified"] is False
        ack = observed["acknowledgement"]
        assert isinstance(ack, dict)
        assert ack["response_body"].startswith("opaque")
        assert device.callback is not None
        with pytest.raises(evidence.Rejected, match="callback"):
            device.callback()


def test_r8_probe_cycle_receipts_and_exact_restoration(
    private_root: tuple[Path, Path],
) -> None:
    with storage.locked_exercise(*private_root) as guarded:
        device = StrictR8ProbeDevice(guarded)

        validate = admission.validate_completed_cycle

        def validate_while_held(*args: Any) -> dict[str, object]:
            assert guarded.pending.exists()
            return validate(*args)

        with (
            patch.object(
                admission.plan,
                "R8_BASELINE_SHA256",
                evidence.configuration_hash(R8_BASELINE),
            ),
            patch.object(
                admission, "validate_completed_cycle", side_effect=validate_while_held
            ),
        ):
            result = admission.run_and_admit_cycle(
                guarded,
                R8_BASELINE,
                device.observe,
                device.send,
                device.admit,
                device.binding,
            )
        assert device.sent == list(cycle.R8_PROBE_CYCLE_COMMANDS)
        assert result["cycle"]["scope"] == "unsaved_r8_probe_cycle"
        assert result["cycle"]["cycle_passed"] is True
        assert not guarded.pending.exists()
        records = sorted(guarded.runtime.glob("empty-vlan-phase-*.json"))
        assert len(records) == 2 * len(cycle.R8_PROBE_CYCLE_COMMANDS) + 1
        for previous, current in pairwise(records):
            assert storage.decode(current.read_bytes())[
                "prev_digest"
            ] == storage.digest(previous.read_bytes())
        final = storage.decode(records[-1].read_bytes())
        assert final["phase"] == "final_observed"
        accepted = result["admission"]
        assert accepted["status"] == "semantically_valid_unsaved_r8_cycle"
        assert accepted["task_complete"] is False


def test_current_r8_runner_owns_strict_transport_and_semantic_admission(
    private_root: tuple[Path, Path],
) -> None:
    with storage.locked_exercise(*private_root) as guarded:
        device = R8ProbeDevice(guarded)
        commands = cycle.R8_PROBE_CYCLE_COMMANDS
        console = StrictConsole(
            strict_replies(commands, native_transport._modes(commands))
        )
        channel_send = console.channel.sendall

        def advance(command: str) -> None:
            channel_send(command)
            if command != "\r":
                device.position += 1

        console.channel.sendall = advance  # type: ignore[method-assign]
        with patch.object(
            admission.plan,
            "R8_BASELINE_SHA256",
            evidence.configuration_hash(R8_BASELINE),
        ):
            result = resident.run_r8_probe_candidate(
                guarded,
                R8_BASELINE,
                device.observe,
                console,
                device.admit,
                device.binding,
            )

        assert device.position == len(commands)
        assert result["cycle"]["cycle_passed"] is True
        assert result["admission"]["status"] == "semantically_valid_unsaved_r8_cycle"
        assert not guarded.pending.exists()


def test_r8_large_held_proof_crosses_first_inverse_boundary(
    private_root: tuple[Path, Path],
) -> None:
    with storage.locked_exercise(*private_root) as guarded:
        device = R8FullTrunkDevice(guarded)
        commands = cycle.R8_FULL_TRUNK_CYCLE_COMMANDS
        console = StrictConsole(
            strict_replies(commands, native_transport._modes(commands, device.initial))
        )
        channel_send = console.channel.sendall

        def advance(command: str) -> None:
            channel_send(command)
            if command != "\r":
                device.position += 1

        console.channel.sendall = advance  # type: ignore[method-assign]

        def prove_held_state(
            held: dict[str, Any], binding: dict[str, Any]
        ) -> dict[str, Any]:
            proof = valid_guest_proof(held, binding)
            table = proof["switch"]["responses"]["show mac-address"]
            header, guest, _ = table.splitlines()
            other_rows = [
                f"0200.0001.{index:04x} 1/3/1 Dynamic {index} 1"
                for index in range(2048)
            ]
            proof["switch"]["responses"]["show mac-address"] = "\n".join(
                [
                    header,
                    guest,
                    *other_rows,
                    "Total active entries from all ports = 2049",
                ]
            )
            guest_receipts(proof)
            return proof

        with patch.object(
            admission.plan,
            "R8_BASELINE_SHA256",
            evidence.configuration_hash(device.baseline),
        ):
            result = resident.run_r8_full_trunk_candidate(
                guarded,
                device.baseline,
                device.observe,
                console,
                device.admit,
                device.binding,
                CallbackProducer(prove_held_state),
                synthetic_evidence()[2],
                lambda: open_r8_recovery_session(device),
            )

        intent_path = guarded.runtime / "empty-vlan-phase-34-command_17_intent.json"
        assert 65536 < intent_path.stat().st_size < 1048576
        intent = storage.decode(intent_path.read_bytes())
        assert intent["evidence"]["held_guest_proof"]["status"] == "accepted"
        observed = storage.decode(
            (
                guarded.runtime / "empty-vlan-phase-35-command_17_observed.json"
            ).read_bytes()
        )
        assert observed["acknowledgement"]["response_body"] == (
            "configure terminal\r\nSSH@headwater(config)#"
        )
        assert device.position == 34
        assert device.state() == device.initial
        assert result["admission"]["status"] == (
            "semantically_valid_unsaved_r8_full_trunk_cycle"
        )
        assert not guarded.pending.exists()


def test_current_r8_full_trunk_runner_restores_and_semantically_admits(
    private_root: tuple[Path, Path],
) -> None:
    with storage.locked_exercise(*private_root) as guarded:
        device = R8FullTrunkDevice(guarded)
        commands = cycle.R8_FULL_TRUNK_CYCLE_COMMANDS
        modes = native_transport._modes(commands, device.initial)
        console = StrictConsole(strict_replies(commands, modes))
        channel_send = console.channel.sendall

        def advance(command: str) -> None:
            channel_send(command)
            if command != "\r":
                device.position += 1

        console.channel.sendall = advance  # type: ignore[method-assign]
        proof_positions: list[int] = []

        def prove_held_state(
            held: dict[str, Any], binding: dict[str, Any]
        ) -> dict[str, Any]:
            proof_positions.append(device.position)
            return valid_guest_proof(held, binding)

        with patch.object(
            admission.plan,
            "R8_BASELINE_SHA256",
            evidence.configuration_hash(device.baseline),
        ):
            result = resident.run_r8_full_trunk_candidate(
                guarded,
                device.baseline,
                device.observe,
                console,
                device.admit,
                device.binding,
                CallbackProducer(prove_held_state),
                synthetic_evidence()[2],
                lambda: open_r8_recovery_session(device),
            )

        assert device.position == len(commands)
        assert proof_positions == [
            len(native_plan.R8_FULL_FORWARD),
            len(cycle.R8_FULL_TRUNK_CYCLE_COMMANDS),
        ]
        assert result["cycle"]["cycle_passed"] is True
        assert result["admission"]["status"] == (
            "semantically_valid_unsaved_r8_full_trunk_cycle"
        )
        assert result["admission"][
            "final_running_sha256"
        ] == evidence.configuration_hash(device.baseline)
        assert result["admission"][
            "final_startup_sha256"
        ] == evidence.configuration_hash(device.baseline)
        assert not guarded.pending.exists()

        with patch.object(
            admission.plan,
            "R8_BASELINE_SHA256",
            evidence.configuration_hash(device.baseline),
        ):
            admission.validate_completed_cycle(
                guarded.runtime,
                device.baseline,
                device.binding,
                profile=cycle.CycleProfile.R8_FULL_TRUNK,
            )

            records = sorted(guarded.runtime.glob("empty-vlan-phase-*.json"))
            receipt_path = guarded.runtime / "empty-vlan-complete.json"
            originals = {path: path.read_bytes() for path in (*records, receipt_path)}
            held_index = 2 * len(native_plan.R8_FULL_FORWARD)
            held_record = storage.decode(records[held_index].read_bytes())
            held_payload = held_record["evidence"]
            assert (
                evidence.digest(held_payload["held_boundary_observation"])
                == (held_payload["held_guest_proof"]["boundary_observation_sha256"])
            )
            held_payload["held_boundary_observation"]["observed_at"] = "changed"
            held_record["evidence_sha256"] = evidence.digest(held_payload)
            records[held_index].write_bytes(storage.canonical(held_record))
            rechain_r8_cycle(guarded.runtime)
            with pytest.raises(
                admission.Rejected, match="held-state guest proof binding mismatch"
            ):
                admission.validate_completed_cycle(
                    guarded.runtime,
                    device.baseline,
                    device.binding,
                    profile=cycle.CycleProfile.R8_FULL_TRUNK,
                )
            for path, raw in originals.items():
                path.write_bytes(raw)

            first = storage.decode(records[0].read_bytes())
            vlan_40_removal = native_plan.R8_FULL_FORWARD.index(
                "no tagged ethernet 1/2/2"
            )
            later = storage.decode(records[2 * vlan_40_removal + 1].read_bytes())
            first["evidence"]["r8_vlan_tables"] = later["evidence"]["observation"][
                "r8_vlan_tables"
            ]
            first["evidence_sha256"] = evidence.digest(first["evidence"])
            records[0].write_bytes(storage.canonical(first))
            rechain_r8_cycle(guarded.runtime)
            with pytest.raises(
                (admission.Rejected, evidence.Rejected),
                match="R8 VLAN1 or VLAN132 membership drift",
            ):
                admission.validate_completed_cycle(
                    guarded.runtime,
                    device.baseline,
                    device.binding,
                    profile=cycle.CycleProfile.R8_FULL_TRUNK,
                )
            for path, raw in originals.items():
                path.write_bytes(raw)

            first = storage.decode(records[0].read_bytes())
            later = storage.decode(records[5].read_bytes())
            first["evidence"] = later["evidence"]["observation"]
            first["evidence_sha256"] = evidence.digest(first["evidence"])
            records[0].write_bytes(storage.canonical(first))
            rechain_r8_cycle(guarded.runtime)
            with pytest.raises(
                (admission.Rejected, evidence.Rejected),
                match="per-command configuration drift",
            ):
                admission.validate_completed_cycle(
                    guarded.runtime,
                    device.baseline,
                    device.binding,
                    profile=cycle.CycleProfile.R8_FULL_TRUNK,
                )

            for path, raw in originals.items():
                path.write_bytes(raw)
            held_index = 2 * len(native_plan.R8_FULL_FORWARD)
            held_record = storage.decode(records[held_index].read_bytes())
            held_record["evidence"]["held_guest_proof"]["proof"][
                "guest_observation"
            ] = "tampered"
            held_record["evidence_sha256"] = evidence.digest(held_record["evidence"])
            records[held_index].write_bytes(storage.canonical(held_record))
            rechain_r8_cycle(guarded.runtime)
            with pytest.raises(
                admission.Rejected, match="held-state guest proof binding mismatch"
            ):
                admission.validate_completed_cycle(
                    guarded.runtime,
                    device.baseline,
                    device.binding,
                    profile=cycle.CycleProfile.R8_FULL_TRUNK,
                )
            for path, raw in originals.items():
                path.write_bytes(raw)

            final = storage.decode(records[-1].read_bytes())
            running = final["evidence"]["responses"]["show running-config"]
            assert running.count("tagged ethe 1/2/6 1/2/2 1/3/1") == len(
                native_plan.VLANS
            )
            final["evidence"]["responses"]["show running-config"] = running.replace(
                "tagged ethe 1/2/6 1/2/2 1/3/1",
                "tagged ethe 1/2/2 1/2/6 1/3/1",
            )
            final["evidence_sha256"] = evidence.digest(final["evidence"])
            records[-1].write_bytes(storage.canonical(final))
            rechain_r8_cycle(guarded.runtime)
            with pytest.raises(
                (admission.Rejected, evidence.Rejected),
                match="exact configuration restoration",
            ):
                admission.validate_completed_cycle(
                    guarded.runtime,
                    device.baseline,
                    device.binding,
                    profile=cycle.CycleProfile.R8_FULL_TRUNK,
                )


def test_audited_runner_forwards_fixed_observer_without_parser_overrides(
    tmp_path: Path,
) -> None:
    audit_pin, audit_runtime = tmp_path / "audit-pin", tmp_path / "audit-runtime"
    root_pin, root_runtime = tmp_path / "root-pin", tmp_path / "root-runtime"
    baseline = ("accepted baseline",)

    def audit_provider() -> str:
        return "audit credential"

    observed = {"source": "audit"}
    with (
        patch.object(resident, "verify_sources"),
        patch.object(resident.r8_observation, "observe", return_value=observed) as read,
        patch.object(
            resident,
            "run_r8_full_trunk_session_candidate",
            side_effect=lambda *args: args,
        ),
        patch.object(
            resident.r8_guest_parent.R8GuestParent,
            "prepare",
            return_value=("fixed producer", {"fixed": "policy"}),
        ) as prepare,
    ):
        args = resident.run_r8_full_trunk_audited_candidate(
            guarded=object(),
            baseline=baseline,
            admit=lambda: None,
            binding={},
            audit_pin=audit_pin,
            audit_runtime=audit_runtime,
            audit_credential_provider=audit_provider,
            root_pin=root_pin,
            root_runtime=root_runtime,
            root_credential_provider=lambda: "root credential",
        )

        assert len(args) == 12
        assert args[5] == "fixed producer"
        assert args[6] == {"fixed": "policy"}
        prepare.assert_called_once()
        assert args[2]() == observed
        read.assert_called_once_with(audit_pin, audit_runtime, baseline, audit_provider)
        recovery_observe = args[7]
        assert args[11] is None
        assert recovery_observe(object())() == observed
        assert read.call_count == 2


def test_r8_full_trunk_guest_proof_failure_runs_inverse_and_retains_pending(
    private_root: tuple[Path, Path],
) -> None:
    with storage.locked_exercise(*private_root) as guarded:
        device = R8FullTrunkDevice(guarded)
        commands = cycle.R8_FULL_TRUNK_CYCLE_COMMANDS
        modes = native_transport._modes(commands, device.initial)
        console = StrictConsole(strict_replies(commands, modes))
        channel_send = console.channel.sendall

        def advance(command: str) -> None:
            channel_send(command)
            if command != "\r":
                device.position += 1

        def reject_proof(
            _held: dict[str, Any], _binding: dict[str, Any]
        ) -> dict[str, Any]:
            raise ValueError("synthetic held-state rejection")

        console.channel.sendall = advance  # type: ignore[method-assign]
        with (
            patch.object(
                admission.plan,
                "R8_BASELINE_SHA256",
                evidence.configuration_hash(device.baseline),
            ),
            pytest.raises(evidence.Rejected, match="inverse completed"),
        ):
            resident.run_r8_full_trunk_candidate(
                guarded,
                device.baseline,
                device.observe,
                console,
                device.admit,
                device.binding,
                CallbackProducer(reject_proof),
                synthetic_evidence()[2],
                lambda: open_r8_recovery_session(device),
            )

        assert device.position == len(commands)
        assert device.state() == device.initial
        assert guarded.pending.exists()
        inverse_intent = storage.decode(
            sorted(guarded.runtime.glob("empty-vlan-phase-*.json"))[
                2 * len(native_plan.R8_FULL_FORWARD)
            ].read_bytes()
        )
        proof_record = inverse_intent["evidence"]["held_guest_proof"]
        assert proof_record["status"] == "rejected"
        assert proof_record["reason"] == "ValueError"


def test_r8_restored_guest_proof_failure_retains_pending_after_inverse(
    private_root: tuple[Path, Path],
) -> None:
    with storage.locked_exercise(*private_root) as guarded:
        device = R8FullTrunkDevice(guarded)
        commands = cycle.R8_FULL_TRUNK_CYCLE_COMMANDS
        console = StrictConsole(
            strict_replies(commands, native_transport._modes(commands, device.initial))
        )
        channel_send = console.channel.sendall

        def advance(command: str) -> None:
            channel_send(command)
            if command != "\r":
                device.position += 1

        calls = 0

        def reject_restored(
            held: dict[str, Any], binding: dict[str, Any]
        ) -> dict[str, Any]:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise ValueError("synthetic restored-state rejection")
            return valid_guest_proof(held, binding)

        console.channel.sendall = advance  # type: ignore[method-assign]
        with (
            patch.object(
                admission.plan,
                "R8_BASELINE_SHA256",
                evidence.configuration_hash(device.baseline),
            ),
            pytest.raises(evidence.Rejected, match="custody retained"),
        ):
            resident.run_r8_full_trunk_candidate(
                guarded,
                device.baseline,
                device.observe,
                console,
                device.admit,
                device.binding,
                CallbackProducer(reject_restored),
                synthetic_evidence()[2],
                lambda: open_r8_recovery_session(device),
            )

        assert calls == 2
        assert device.position == len(commands)
        assert device.state() == device.initial
        assert guarded.pending.exists()
        final = storage.decode(
            sorted(guarded.runtime.glob("empty-vlan-phase-*.json"))[-1].read_bytes()
        )
        assert final["phase"] == "final_observed"
        proof = final["evidence"]["restored_guest_proof"]
        assert proof["status"] == "rejected"
        assert proof["reason"] == "ValueError"


@pytest.mark.parametrize(
    ("failed_index", "drift_on_prompt", "late_failure"),
    [(index, False, False) for index in range(len(native_plan.R8_FULL_FORWARD))]
    + [(2, True, False), (2, False, True)],
)
def test_r8_full_trunk_forward_failure_recovers_from_fresh_observed_boundary(
    private_root: tuple[Path, Path],
    failed_index: int,
    drift_on_prompt: bool,
    late_failure: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with storage.locked_exercise(*private_root) as guarded:
        clock = [0.0]
        if late_failure:
            monkeypatch.setattr(resident.time, "monotonic", lambda: clock[0])
        budget = resident.R8OperationBudget()
        device = R8FullTrunkDevice(guarded)
        forward = native_plan.R8_FULL_FORWARD
        cycle_console = StrictConsole(
            strict_replies(
                cycle.R8_FULL_TRUNK_CYCLE_COMMANDS,
                native_transport._modes(
                    cycle.R8_FULL_TRUNK_CYCLE_COMMANDS, device.initial
                ),
            )
        )
        original_sendall = cycle_console.channel.sendall
        forward_index = 0

        def fail_after_command(command: str) -> None:
            nonlocal forward_index
            original_sendall(command)
            if command != "\r" and forward_index < len(forward):
                current = forward_index
                forward_index += 1
                device.position = forward_index
                if current == failed_index:
                    if late_failure:
                        clock[0] = (
                            budget.deadline
                            - resident.INVERSE_RESERVE
                            - resident.R8_PROOF_SECONDS
                            - resident.CLEANUP_RESERVE
                            + 1
                        )
                    raise TimeoutError("injected uncertain forward result")

        cycle_console.channel.sendall = fail_after_command  # type: ignore[method-assign]
        recovery_commands: list[str] = []
        drifted_state = native_plan.State(
            tuple(
                (
                    vlan,
                    tuple(
                        port
                        for port in ports
                        if not (vlan == 40 and port == native_plan.R8_PRIMARY_PORT)
                    ),
                )
                for vlan, ports in device.initial.vlans
            ),
            device.initial.native,
        )

        def fresh_recovery_session() -> tuple[
            Callable[[], dict[str, Any]], Any, Callable[[], None]
        ]:
            observed = device.state()
            inverse = (
                ()
                if observed == device.initial
                else native_plan.r8_full_inverse_commands(observed)
            )
            recovery_console = StrictConsole(
                strict_replies(
                    inverse,
                    native_transport._modes(inverse, observed),
                )
            )
            recovery_sendall = recovery_console.channel.sendall
            recovery_index = 0
            recovery_states = native_plan._states(inverse, observed)
            prompt_seen = False

            def advance_recovery(command: str) -> None:
                nonlocal prompt_seen, recovery_index
                if command == "\r" and drift_on_prompt and not prompt_seen:
                    prompt_seen = True
                    device.live_state = drifted_state
                recovery_sendall(command)
                if command != "\r":
                    recovery_commands.append(command.rstrip("\r"))
                    recovery_index += 1
                    device.live_state = recovery_states[recovery_index]

            recovery_console.channel.sendall = advance_recovery  # type: ignore[method-assign]
            return device.observe, recovery_console, lambda: None

        if drift_on_prompt:
            with (
                patch.object(
                    admission.plan,
                    "R8_BASELINE_SHA256",
                    evidence.configuration_hash(device.baseline),
                ),
                pytest.raises(
                    evidence.Rejected,
                    match="fresh-session recovery incomplete",
                ),
            ):
                resident.run_r8_full_trunk_candidate(
                    guarded,
                    device.baseline,
                    device.observe,
                    cycle_console,
                    device.admit,
                    device.binding,
                    CallbackProducer(valid_guest_proof),
                    synthetic_evidence()[2],
                    fresh_recovery_session,
                    operation_budget=budget if late_failure else None,
                )
            assert device.state() == drifted_state
            assert guarded.pending.exists()
            assert not recovery_commands
            assert not sorted(
                guarded.runtime.glob("empty-vlan-recovery-*-inverse_intent.json")
            )
            return

        with (
            patch.object(
                admission.plan,
                "R8_BASELINE_SHA256",
                evidence.configuration_hash(device.baseline),
            ),
            pytest.raises(evidence.Rejected, match="exact restoration verified"),
        ):
            resident.run_r8_full_trunk_candidate(
                guarded,
                device.baseline,
                device.observe,
                cycle_console,
                device.admit,
                device.binding,
                CallbackProducer(valid_guest_proof),
                synthetic_evidence()[2],
                fresh_recovery_session,
                operation_budget=budget if late_failure else None,
            )

        assert device.state() == device.initial
        assert guarded.pending.exists()
        if late_failure:
            assert budget.phase == "recovery"
        recovery = sorted(guarded.runtime.glob("empty-vlan-recovery-*.json"))
        assert recovery
        assert recovery[-1].name.endswith("-restored.json")
        boundary = native_plan._states(forward, device.initial)[failed_index + 1]
        expected_inverse = (
            ()
            if boundary == device.initial
            else native_plan.r8_full_inverse_commands(boundary)
        )
        assert recovery_commands == list(expected_inverse)


def test_r8_semantic_rejection_retains_pending_custody(
    private_root: tuple[Path, Path],
) -> None:
    with storage.locked_exercise(*private_root) as guarded:
        device = StrictR8ProbeDevice(guarded)
        with (
            patch.object(
                admission.plan,
                "R8_BASELINE_SHA256",
                evidence.configuration_hash(R8_BASELINE),
            ),
            patch.object(
                admission,
                "validate_completed_cycle",
                side_effect=admission.Rejected("semantic receipt rejected"),
            ),
            pytest.raises(admission.Rejected, match="semantic receipt rejected"),
        ):
            admission.run_and_admit_cycle(
                guarded,
                R8_BASELINE,
                device.observe,
                device.send,
                device.admit,
                device.binding,
            )
        assert guarded.pending.exists()


@pytest.mark.parametrize("tamper", ["phase_evidence", "phase_order", "binding"])
def test_r8_admission_rejects_tampered_completed_cycle(
    private_root: tuple[Path, Path], tamper: str
) -> None:
    with storage.locked_exercise(*private_root) as guarded:
        device = R8ProbeDevice(guarded)
        device.run()
        records = sorted(guarded.runtime.glob("empty-vlan-phase-*.json"))
        target = records[1]
        data = storage.decode(target.read_bytes())
        if tamper == "phase_evidence":
            data["evidence"] = {}
        elif tamper == "phase_order":
            data["phase"] = "command_0_intent"
        else:
            receipt_path = guarded.runtime / "empty-vlan-complete.json"
            receipt = storage.decode(receipt_path.read_bytes())
            receipt["operation"]["binding"]["native_recovery_proof_sha256"] = "e" * 64
            receipt_path.write_bytes(storage.canonical(receipt))
        target.write_bytes(storage.canonical(data))
        with (
            patch.object(
                admission.plan,
                "R8_BASELINE_SHA256",
                evidence.configuration_hash(R8_BASELINE),
            ),
            pytest.raises(admission.Rejected),
        ):
            admission.validate_completed_cycle(
                guarded.runtime, R8_BASELINE, device.binding
            )


def test_r8_admission_rejects_source_drift_after_import(
    private_root: tuple[Path, Path],
) -> None:
    with storage.locked_exercise(*private_root) as guarded:
        device = R8ProbeDevice(guarded)
        device.run()
        with (
            patch.object(
                admission.plan,
                "R8_BASELINE_SHA256",
                evidence.configuration_hash(R8_BASELINE),
            ),
            patch.dict(cycle.SOURCE_MANIFEST, {"empty_vlan_cycle": "a" * 64}),
            pytest.raises(admission.Rejected, match="source"),
        ):
            admission.validate_completed_cycle(
                guarded.runtime, R8_BASELINE, device.binding
            )


def test_r8_admission_rejects_semantically_wrong_but_rechained_state(
    private_root: tuple[Path, Path],
) -> None:
    with storage.locked_exercise(*private_root) as guarded:
        device = R8ProbeDevice(guarded)
        device.run()
        records = sorted(guarded.runtime.glob("empty-vlan-phase-*.json"))
        first = storage.decode(records[0].read_bytes())
        later = storage.decode(records[4].read_bytes())
        first["evidence"] = later["evidence"]
        first["evidence_sha256"] = evidence.digest(first["evidence"])
        records[0].write_bytes(storage.canonical(first))

        receipt_path = guarded.runtime / "empty-vlan-complete.json"
        receipt = storage.decode(receipt_path.read_bytes())
        previous = storage.digest(storage.canonical(receipt["operation"]))
        for index, path in enumerate(records):
            record = storage.decode(path.read_bytes())
            record["prev_digest"] = previous
            path.write_bytes(storage.canonical(record))
            previous = storage.digest(path.read_bytes())
        receipt["final_digest"] = previous
        receipt_path.write_bytes(storage.canonical(receipt))

        with (
            patch.object(
                admission.plan,
                "R8_BASELINE_SHA256",
                evidence.configuration_hash(R8_BASELINE),
            ),
            pytest.raises(evidence.Rejected),
        ):
            admission.validate_completed_cycle(
                guarded.runtime, R8_BASELINE, device.binding
            )


def test_r8_probe_startup_drift_retains_pending_and_stops(
    private_root: tuple[Path, Path],
) -> None:
    with storage.locked_exercise(*private_root) as guarded:
        device = R8ProbeDevice(guarded, "startup")
        with pytest.raises(evidence.Rejected):
            device.run()
        assert len(device.sent) == 2
        assert guarded.pending.exists()


@pytest.mark.parametrize(
    "failure,count",
    [
        ("missing", 0),
        ("double", 1),
        ("timeout", 1),
        ("startup", 2),
        ("extra", 2),
        ("port", 2),
        ("tagged", 2),
        ("binding", 2),
        ("pending", 2),
    ],
)
def test_failure_retains_pending_and_stops(
    private_root: tuple[Path, Path], failure: str, count: int
) -> None:
    with storage.locked_exercise(*private_root) as guarded:
        device = Device(guarded, failure)
        with pytest.raises((evidence.Rejected, storage.Rejected, TimeoutError)):
            device.run()
        assert guarded.pending.exists()
        assert len(device.sent) == count


def test_phase_write_failure_has_no_send(private_root: tuple[Path, Path]) -> None:
    with storage.locked_exercise(*private_root) as guarded:
        device = Device(guarded)
        original = storage.exclusive_write

        def fail(path: Path, raw: bytes) -> None:
            if "intent" in path.name:
                raise OSError("fsync failed")
            original(path, raw)

        with (
            patch.object(storage, "exclusive_write", side_effect=fail),
            pytest.raises(storage.Uncertain),
        ):
            device.run()
        assert guarded.pending.exists()
        assert device.sent == []


def test_other_pending_and_incomplete_finish(private_root: tuple[Path, Path]) -> None:
    with storage.locked_exercise(*private_root) as guarded:
        device = Device(guarded)
        ledger = cycle.EmptyVlanLedger(guarded)
        ledger.begin(device.binding)
        with pytest.raises(storage.Rejected, match="incomplete"):
            ledger.finish()
        with pytest.raises(storage.Uncertain, match="pending"):
            device.run()
        assert guarded.pending.exists()
        assert device.sent == []


def test_public_fixed_baseline(private_root: tuple[Path, Path]) -> None:
    with storage.locked_exercise(*private_root) as guarded:
        device = Device(guarded)
        with pytest.raises(evidence.Rejected):
            cycle.run_cycle(
                guarded,
                BASELINE,
                device.observe,
                device.send,
                device.admit,
                device.binding,
            )
        assert device.sent == []
        assert not guarded.pending.exists()


def test_awaitable_admission(private_root: tuple[Path, Path]) -> None:
    with storage.locked_exercise(*private_root) as guarded:
        device = Device(guarded)

        async def later() -> None:
            pass

        with pytest.raises(evidence.Rejected, match="synchronous"):
            cycle._run_cycle(
                guarded,
                BASELINE,
                device.observe,
                device.send,
                later,  # type: ignore[arg-type]
                device.binding,
                baseline_sha256=evidence.configuration_hash(BASELINE),
            )
        assert device.sent == []
        assert not guarded.pending.exists()


@pytest.mark.parametrize("kind", ["existing10", "source", "ee", "closed"])
def test_preflight_rejects_before_begin(
    private_root: tuple[Path, Path], kind: str
) -> None:
    with storage.locked_exercise(*private_root) as guarded:
        device = Device(guarded)
        baseline: tuple[str, ...] = BASELINE
        if kind == "existing10":
            baseline = state(2)
            digest = evidence.configuration_hash(baseline)
            device.binding["baseline_running_sha256"] = digest
            device.binding["baseline_startup_sha256"] = digest
            device.binding["preview_sha256"] = cycle.preview_digest(baseline)
        elif kind == "source":
            device.binding["source_binding_sha256"] = "c" * 64
        elif kind == "ee":
            device.binding["execution_environment_sha256"] = "c" * 64
        else:
            guarded.closed = True
        with pytest.raises((evidence.Rejected, storage.Rejected)):
            cycle._run_cycle(
                guarded,
                baseline,
                device.observe,
                device.send,
                device.admit,
                device.binding,
                baseline_sha256=evidence.configuration_hash(baseline),
            )
        assert not guarded.pending.exists()
        assert device.sent == []


def test_awaitable_send_and_late_callback_preserve_pending(
    private_root: tuple[Path, Path],
) -> None:
    with storage.locked_exercise(*private_root) as guarded:
        device = Device(guarded)
        callback: list[Callable[[], None]] = []

        async def later() -> dict[str, Any]:
            return {}

        def send(index: int, command: str, before: Callable[[], None]) -> Any:
            callback.append(before)
            return later()

        with pytest.raises(evidence.Rejected, match="synchronous"):
            cycle._run_cycle(
                guarded,
                BASELINE,
                device.observe,
                send,
                device.admit,
                device.binding,
                baseline_sha256=evidence.configuration_hash(BASELINE),
            )
        with pytest.raises(evidence.Rejected, match="callback"):
            callback[0]()
        assert guarded.pending.exists()
        assert not list(guarded.runtime.glob("empty-vlan-phase-*.json"))


def test_finish_write_failure_retains_all_receipts(
    private_root: tuple[Path, Path],
) -> None:
    with storage.locked_exercise(*private_root) as guarded:
        device = Device(guarded)
        original = storage.exclusive_write

        def fail(path: Path, raw: bytes) -> None:
            if path.name == "empty-vlan-complete.json":
                raise OSError("receipt fsync failed")
            original(path, raw)

        with (
            patch.object(storage, "exclusive_write", side_effect=fail),
            pytest.raises(storage.Uncertain),
        ):
            device.run()
        assert guarded.pending.exists()
        assert len(list(guarded.runtime.glob("empty-vlan-phase-*.json"))) == 11
        assert len(device.sent) == 5


def test_pending_does_not_claim_transport_identity(
    private_root: tuple[Path, Path],
) -> None:
    with storage.locked_exercise(*private_root) as guarded:
        ledger = cycle.EmptyVlanLedger(guarded)
        ledger.begin(Device(guarded).binding)
        assert ledger.data is not None
        assert ledger.data["writer"] == "caller_supplied_transport"


class StandbyDevice(Device):
    def __init__(
        self,
        guarded: storage.ExerciseLedger,
        failure: str = "",
        *,
        spelling: str = "ethernet",
    ):
        super().__init__(guarded, failure)
        self.spelling = spelling
        self.binding["preview_sha256"] = cycle.standby_tagged_preview_digest(BASELINE)

    def observe(self) -> dict[str, Any]:
        running: tuple[str, ...] = BASELINE
        if self.position in (2, 3, 4):
            leaves = (f" tagged {self.spelling} 1/2/6",) if self.position == 3 else ()
            if self.failure == "wrong_member" and self.position == 3:
                leaves = (f" tagged {self.spelling} 1/2/2",)
            if self.failure == "skipped_reversal" and self.position == 4:
                leaves = (f" tagged {self.spelling} 1/2/6",)
            running = (
                *BASELINE[:9],
                "vlan 10 name LAB-MGMT by port",
                *leaves,
                "!",
                *BASELINE[9:],
            )
        startup: tuple[str, ...] = BASELINE
        if self.position == 3:
            if self.failure == "startup":
                startup = running
            elif self.failure == "port":
                running = tuple(
                    " port-name changed" if x == " port-name standby" else x
                    for x in running
                )
            elif self.failure == "extra":
                running = (*running[:-1], "vlan 20 name LAB-DEV by port", "end")
            elif self.failure == "binding":
                self.binding["native_recovery_proof_sha256"] = "b" * 64
        result = payload(running, startup)  # type: ignore[no-untyped-call]
        assert isinstance(result, dict)
        return result

    def send(
        self, index: int, command: str, before_send: Callable[[], None]
    ) -> dict[str, Any]:
        assert index == self.position
        assert command == cycle.STANDBY_TAGGED_COMMANDS[index]
        before_send()
        intent = (
            self.guarded.runtime
            / f"empty-vlan-phase-{2 * index:02d}-command_{index}_intent.json"
        )
        assert intent.exists()
        self.sent.append(command)
        self.position += 1
        if self.failure == "timeout":
            raise TimeoutError("unknown tagged command outcome")
        body = "raw tagged acknowledgement"
        return {"response_body": body, "response_sha256": storage.digest(body.encode())}

    def run(self) -> dict[str, object]:
        return cycle._run_cycle(
            self.guarded,
            BASELINE,
            self.observe,
            self.send,
            self.admit,
            self.binding,
            baseline_sha256=evidence.configuration_hash(BASELINE),
            profile=cycle.CycleProfile.STANDBY_TAGGED,
        )


@pytest.mark.parametrize("spelling", ["ethernet", "ethe"])
def test_standby_tagged_fixed_commands_and_receipts(
    private_root: tuple[Path, Path], spelling: str
) -> None:
    with storage.locked_exercise(*private_root) as guarded:
        device = StandbyDevice(guarded, spelling=spelling)
        result = device.run()
        assert device.sent == list(cycle.STANDBY_TAGGED_COMMANDS)
        assert device.sent == [
            "configure terminal",
            "vlan 10 name LAB-MGMT by port",
            "tagged ethernet 1/2/6",
            "no tagged ethernet 1/2/6",
            "no vlan 10",
            "exit",
        ]
        assert result["scope"] == "unsaved_standby_tagged_vlan10_cycle"
        assert result["cycle_passed"] is True
        assert not guarded.pending.exists()
        records = sorted(guarded.runtime.glob("empty-vlan-phase-*.json"))
        assert len(records) == 13
        for previous, current in pairwise(records):
            assert storage.decode(current.read_bytes())[
                "prev_digest"
            ] == storage.digest(previous.read_bytes())


@pytest.mark.parametrize(
    "failure,count",
    [
        ("wrong_member", 3),
        ("skipped_reversal", 4),
        ("startup", 3),
        ("port", 3),
        ("extra", 3),
        ("binding", 3),
        ("timeout", 1),
    ],
)
@pytest.mark.parametrize("spelling", ["ethernet", "ethe"])
def test_standby_tagged_rejects_drift_and_retains_pending(
    private_root: tuple[Path, Path], failure: str, count: int, spelling: str
) -> None:
    with storage.locked_exercise(*private_root) as guarded:
        device = StandbyDevice(guarded, failure, spelling=spelling)
        with pytest.raises((evidence.Rejected, storage.Rejected, TimeoutError)):
            device.run()
        assert guarded.pending.exists()
        assert len(device.sent) == count
        pending = storage.decode(guarded.pending.read_bytes())
        assert pending["operation"] == "standby_tagged_vlan10_cycle"
        assert pending["commands"] == list(cycle.STANDBY_TAGGED_COMMANDS)


@pytest.mark.parametrize("boundary", ["intent", "empty-vlan-complete.json"])
def test_standby_tagged_durability_failure_retains_pending(
    private_root: tuple[Path, Path], boundary: str
) -> None:
    with storage.locked_exercise(*private_root) as guarded:
        device = StandbyDevice(guarded)
        original = storage.exclusive_write

        def fail(path: Path, raw: bytes) -> None:
            if boundary in path.name:
                raise OSError("durability failure")
            original(path, raw)

        with (
            patch.object(storage, "exclusive_write", side_effect=fail),
            pytest.raises(storage.Uncertain),
        ):
            device.run()
        assert guarded.pending.exists()
        assert len(device.sent) == (0 if boundary == "intent" else 6)


def test_profiles_cannot_share_preview_binding(private_root: tuple[Path, Path]) -> None:
    with storage.locked_exercise(*private_root) as guarded:
        device = StandbyDevice(guarded)
        device.binding["preview_sha256"] = cycle.preview_digest(BASELINE)
        with pytest.raises(evidence.Rejected, match="binding"):
            device.run()
        assert not guarded.pending.exists()
        assert not device.sent


class FullDevice(Device):
    def __init__(
        self,
        guarded: storage.ExerciseLedger,
        *,
        grouped: bool = False,
        bad_position: int = -1,
        failure: str = "",
    ):
        super().__init__(guarded, failure)
        self.grouped = grouped
        self.bad_position = bad_position
        self.binding["preview_sha256"] = cycle.full_trunk_preview_digest(BASELINE)

    def observe(self) -> dict[str, Any]:
        position = self.position
        if position == self.bad_position and self.failure == "state":
            position = position - 1
        if position <= 22:
            running = state(position, grouped=self.grouped)
        else:
            remaining = max(0, 27 - position)
            running = state(1 + 5 * remaining, grouped=self.grouped)
        startup: tuple[str, ...] = BASELINE
        if self.position == self.bad_position:
            if self.failure == "startup":
                startup = running
            elif self.failure == "member":
                running = tuple(
                    x.replace("1/3/1", "1/3/2")
                    if x.startswith(" tagged ethernet ")
                    else x
                    for x in running
                )
            elif self.failure == "unrelated":
                running = tuple(x.replace("standby", "changed") for x in running)
        result = payload(running, startup)  # type: ignore[no-untyped-call]
        assert isinstance(result, dict)
        result["responses"]["show interfaces brief"] = brief()
        return result

    def send(
        self, index: int, command: str, before_send: Callable[[], None]
    ) -> dict[str, Any]:
        assert index == self.position
        assert command == cycle.FULL_TRUNK_COMMANDS[index]
        before_send()
        intent = self.guarded.runtime / (
            f"empty-vlan-phase-{2 * index:02d}-command_{index}_intent.json"
        )
        assert intent.exists()
        self.sent.append(command)
        self.position += 1
        if self.failure == "timeout" and self.position == self.bad_position:
            raise TimeoutError("unknown outcome")
        body = "raw full trunk acknowledgement"
        return {"response_body": body, "response_sha256": storage.digest(body.encode())}

    def run(self) -> dict[str, object]:
        return cycle._run_cycle(
            self.guarded,
            BASELINE,
            self.observe,
            self.send,
            self.admit,
            self.binding,
            baseline_sha256=evidence.configuration_hash(BASELINE),
            profile=cycle.CycleProfile.FULL_TRUNK,
        )


@pytest.mark.parametrize("grouped", [False, True])
def test_full_trunk_cycle_and_inverse_receipts(
    private_root: tuple[Path, Path],
    grouped: bool,
) -> None:
    with storage.locked_exercise(*private_root) as guarded:
        device = FullDevice(guarded, grouped=grouped)
        result = device.run()
        assert device.sent == list(cycle.FULL_TRUNK_COMMANDS)
        assert len(device.sent) == 28
        assert result["scope"] == "unsaved_full_trunk_cycle"
        assert result["task_complete"] is False
        assert result["live_admission"] is False
        assert result["acknowledgement_parser_qualified"] is False
        assert not guarded.pending.exists()
        records = sorted(guarded.runtime.glob("empty-vlan-phase-*.json"))
        assert len(records) == 57
        for previous, current in pairwise(records):
            assert storage.decode(current.read_bytes())[
                "prev_digest"
            ] == storage.digest(previous.read_bytes())


@pytest.mark.parametrize(
    "position",
    [2, 3, 4, 5, 7, 8, 9, 10, 12, 13, 14, 15, 17, 18, 19, 20, 24, 25, 26, 27],
)
def test_full_trunk_wrong_boundary_stops_with_pending(
    private_root: tuple[Path, Path],
    position: int,
) -> None:
    with storage.locked_exercise(*private_root) as guarded:
        device = FullDevice(guarded, bad_position=position, failure="state")
        with pytest.raises(evidence.Rejected):
            device.run()
        assert len(device.sent) == position
        assert guarded.pending.exists()


@pytest.mark.parametrize("position", [20, 24, 25, 26])
@pytest.mark.parametrize("failure", ["startup", "member", "unrelated", "timeout"])
def test_full_trunk_inverse_drift_and_uncertainty(
    private_root: tuple[Path, Path],
    position: int,
    failure: str,
) -> None:
    with storage.locked_exercise(*private_root) as guarded:
        device = FullDevice(guarded, bad_position=position, failure=failure)
        with pytest.raises((evidence.Rejected, TimeoutError)):
            device.run()
        assert len(device.sent) == position
        assert guarded.pending.exists()


@pytest.mark.parametrize("profile", list(cycle.CycleProfile))
def test_all_profiles_have_distinct_fixed_preview(profile: cycle.CycleProfile) -> None:
    assert len({cycle._preview_digest(BASELINE, p) for p in cycle.CycleProfile}) == len(
        cycle.CycleProfile
    )
    assert len(profile.phases) == 2 * len(profile.commands) + 1


@pytest.mark.parametrize("profile", list(cycle.CycleProfile))
@pytest.mark.parametrize("other", list(cycle.CycleProfile))
def test_all_profiles_reject_another_preview(
    private_root: tuple[Path, Path],
    profile: cycle.CycleProfile,
    other: cycle.CycleProfile,
) -> None:
    if profile is other:
        return
    with storage.locked_exercise(*private_root) as guarded:
        device = Device(guarded)
        device.binding["preview_sha256"] = cycle._preview_digest(BASELINE, other)
        with pytest.raises(evidence.Rejected, match="binding"):
            cycle._run_cycle(
                guarded,
                BASELINE,
                device.observe,
                device.send,
                device.admit,
                device.binding,
                baseline_sha256=evidence.configuration_hash(BASELINE),
                profile=profile,
            )
        assert not guarded.pending.exists()
        assert not device.sent


@pytest.mark.parametrize("boundary", ["intent", "empty-vlan-complete.json"])
def test_full_trunk_durability_failure_retains_pending(
    private_root: tuple[Path, Path],
    boundary: str,
) -> None:
    with storage.locked_exercise(*private_root) as guarded:
        device = FullDevice(guarded)
        original = storage.exclusive_write

        def fail(path: Path, raw: bytes) -> None:
            if boundary in path.name:
                raise OSError("durability failure")
            original(path, raw)

        with (
            patch.object(storage, "exclusive_write", side_effect=fail),
            pytest.raises(storage.Uncertain),
        ):
            device.run()
        assert guarded.pending.exists()
        assert len(device.sent) == (0 if boundary == "intent" else 28)


def test_full_trunk_public_baseline_fixed(private_root: tuple[Path, Path]) -> None:
    with storage.locked_exercise(*private_root) as guarded:
        device = FullDevice(guarded)
        with pytest.raises(evidence.Rejected):
            cycle.run_full_trunk_cycle(
                guarded,
                BASELINE,
                device.observe,
                device.send,
                device.admit,
                device.binding,
            )
        assert not guarded.pending.exists()
        assert not device.sent


class LinkDevice(FullDevice):
    def __init__(
        self,
        guarded: storage.ExerciseLedger,
        port: str,
        bad_position: int,
        occurrence: int = 1,
    ):
        super().__init__(guarded, bad_position=bad_position)
        self.link_port = port
        self.occurrence = occurrence
        self.at_position = 0

    def observe(self) -> dict[str, Any]:
        result = super().observe()
        if self.position == self.bad_position:
            self.at_position += 1
            if self.at_position >= self.occurrence:
                result["responses"]["show interfaces brief"] = brief().replace(
                    self.link_port + " Up Forward Full",
                    self.link_port + " Down None None",
                )
        return result


@pytest.mark.parametrize("port", ["1/2/2", "1/2/6", "1/3/1"])
@pytest.mark.parametrize("position", [0, 3, 22, 24, 28])
def test_full_cycle_carrier_loss_stops_before_more_sends(
    private_root: tuple[Path, Path],
    port: str,
    position: int,
) -> None:
    with storage.locked_exercise(*private_root) as guarded:
        device = LinkDevice(guarded, port, position)
        with pytest.raises(evidence.Rejected, match="carrier"):
            device.run()
        assert len(device.sent) == position
        assert guarded.pending.exists() == (position != 0)
        if position == 0:
            assert not list(guarded.runtime.glob("empty-vlan-phase-*.json"))


@pytest.mark.parametrize("port", ["1/2/2", "1/2/6", "1/3/1"])
def test_full_cycle_final_carrier_loss_retains_pending_without_completion(
    private_root: tuple[Path, Path],
    port: str,
) -> None:
    with storage.locked_exercise(*private_root) as guarded:
        # First two final-state reads pass; last acceptance read loses carrier.
        device = LinkDevice(guarded, port, 28, occurrence=3)
        with pytest.raises(evidence.Rejected, match="carrier"):
            device.run()
        assert len(device.sent) == 28
        assert guarded.pending.exists()
        assert not (guarded.runtime / "empty-vlan-complete.json").exists()
        assert len(list(guarded.runtime.glob("empty-vlan-phase-*.json"))) == 56


def test_full_cycle_carrier_loss_at_durable_callback_has_no_send(
    private_root: tuple[Path, Path],
) -> None:
    with storage.locked_exercise(*private_root) as guarded:
        device = LinkDevice(guarded, "1/2/2", 0, occurrence=3)
        with pytest.raises(evidence.Rejected, match="carrier"):
            device.run()
        assert not device.sent
        assert guarded.pending.exists()
        assert not list(guarded.runtime.glob("empty-vlan-phase-*.json"))


def test_full_cycle_sources_include_carrier_gate() -> None:
    assert "trunk_link_admission" in cycle.SOURCE_PATHS
    assert cycle.SOURCE_MANIFEST["trunk_link_admission"] == storage.digest(
        cycle.SOURCE_PATHS["trunk_link_admission"].read_bytes()
    )


def test_r8_manifest_covers_transitive_local_runtime_imports() -> None:
    expected = {
        "active40g_observation",
        "bond_vlan_membership",
        "r8_pending_restorer",
        "standby_native_membership",
        "writer_syntax",
    }

    assert expected <= cycle.SOURCE_PATHS.keys()
    assert expected <= cycle.SOURCE_MANIFEST.keys()
    assert all(
        cycle.SOURCE_MANIFEST[name]
        == storage.digest(cycle.SOURCE_PATHS[name].read_bytes())
        for name in expected
    )


def test_r8_manifest_covers_every_guest_traffic_artifact() -> None:
    expected = {
        "r8_guest_generator",
        "guest_runner",
        "guest_program",
        "guest_host_keys",
    }

    assert expected <= cycle.SOURCE_PATHS.keys()
    assert expected <= cycle.SOURCE_MANIFEST.keys()
    assert all(
        cycle.SOURCE_MANIFEST[name]
        == storage.digest(cycle.SOURCE_PATHS[name].read_bytes())
        for name in expected
    )


def test_r8_manifest_rejects_changed_guest_program(tmp_path: Path, monkeypatch) -> None:
    changed = tmp_path / "guest.py"
    changed.write_text("# changed guest program\n", encoding="utf-8")
    monkeypatch.setitem(cycle.SOURCE_PATHS, "guest_program", changed)

    with pytest.raises(admission.Rejected, match="current-source digest drift"):
        admission._require_current_source()


class NativeDevice(Device):
    def __init__(
        self,
        guarded: storage.ExerciseLedger,
        *,
        bad_position: int = -1,
        failure: str = "",
        occurrence: int = 1,
    ):
        super().__init__(guarded, failure)
        self.bad_position = bad_position
        self.occurrence = occurrence
        self.at_position = 0
        self.admissions = 0
        self.binding["preview_sha256"] = cycle.standby_native_preview_digest(BASELINE)

    def observe(self) -> dict[str, Any]:
        present = 2 <= self.position <= 14
        tagged = 3 <= self.position <= 13
        native = 6 <= self.position <= 10
        self.at_position += self.position == self.bad_position
        bad = self.position == self.bad_position and self.at_position >= self.occurrence
        if bad and self.failure == "state":
            present = not present
            tagged = tagged and present
        if bad and self.failure == "native_inverse":
            native = True
        additions = (
            (
                "vlan 10 name LAB-MGMT by port",
                *((" tagged ethe 1/2/6",) if tagged else ()),
                "!",
            )
            if present
            else ()
        )
        running = (*BASELINE[:9], *additions, *BASELINE[9:])
        if native:
            index = running.index(" port-name standby")
            running = (*running[:index], " dual-mode", *running[index:])
        startup = BASELINE
        if bad:
            if self.failure == "startup":
                startup = running
            elif self.failure == "extra":
                running = (*running[:-1], "vlan 20 name LAB-DEV by port", "end")
            elif self.failure == "interface_leaf":
                index = running.index(" port-name standby")
                running = (*running[:index], " mtu 9000", *running[index:])
        result = payload(running, startup)  # type: ignore[no-untyped-call]
        assert isinstance(result, dict)
        operational = native_brief(
            tag="Yes" if tagged else "No",
            pvid="1" if native or not tagged else "N/A",
        )
        if bad:
            if self.failure == "down":
                operational = operational.replace(
                    "1/2/6 Up Forward Full", "1/2/6 Down None None"
                )
            elif self.failure in ("unknown", "pvid", "inverse_pvid"):
                lines = operational.splitlines()
                index = next(
                    i for i, line in enumerate(lines) if line.startswith("1/2/6 ")
                )
                words = lines[index].split()
                words[7] = {
                    "unknown": "unknown",
                    "pvid": "10",
                    "inverse_pvid": "No",
                }[self.failure]
                lines[index] = " ".join(words)
                operational = "\n".join(lines)
        result["responses"]["show interfaces brief"] = operational
        return result

    def admit(self) -> None:
        self.admissions += 1
        if self.failure == "admission":
            raise evidence.Rejected("caller traffic admission not satisfied")

    def send(
        self, index: int, command: str, before_send: Callable[[], None]
    ) -> dict[str, Any]:
        self.callback = before_send
        assert index == self.position
        assert command == cycle.STANDBY_NATIVE_COMMANDS[index]
        if self.failure == "missing":
            return {}
        before_send()
        intent = self.guarded.runtime / (
            f"empty-vlan-phase-{2 * index:02d}-command_{index}_intent.json"
        )
        assert intent.exists()
        self.sent.append(command)
        self.position += 1
        if self.failure == "timeout":
            raise TimeoutError("unknown native command outcome")
        if self.failure == "double":
            with pytest.raises(evidence.Rejected, match="callback"):
                before_send()
        body = "raw native diagnostic acknowledgement"
        return {"response_body": body, "response_sha256": storage.digest(body.encode())}

    def run(self) -> dict[str, object]:
        return cycle._run_cycle(
            self.guarded,
            BASELINE,
            self.observe,
            self.send,
            self.admit,
            self.binding,
            baseline_sha256=evidence.configuration_hash(BASELINE),
            profile=cycle.CycleProfile.STANDBY_NATIVE,
        )


def test_native_cycle_all_transitions_journal_and_expired_callback(
    private_root: tuple[Path, Path],
) -> None:
    with storage.locked_exercise(*private_root) as guarded:
        device = NativeDevice(guarded)
        result = device.run()
        assert device.position == 16
        assert tuple(device.sent) == standby_native_transport.COMMANDS
        assert all(
            "write" not in command and "save" not in command for command in device.sent
        )
        assert result["scope"] == "unsaved_standby_native_vlan10_cycle"
        assert result["cycle_passed"] is True
        assert result["task_complete"] is False
        assert result["live_admission"] is False
        assert result["acknowledgement_parser_qualified"] is False
        assert not guarded.pending.exists()
        records = sorted(guarded.runtime.glob("empty-vlan-phase-*.json"))
        assert len(records) == 33
        assert [storage.decode(p.read_bytes())["phase"] for p in records] == list(
            cycle.CycleProfile.STANDBY_NATIVE.phases
        )
        for previous, current in pairwise(records):
            assert storage.decode(current.read_bytes())[
                "prev_digest"
            ] == storage.digest(previous.read_bytes())
        assert device.callback is not None
        with pytest.raises(evidence.Rejected, match="callback"):
            device.callback()
        assert len(device.sent) == 16
        assert device.admissions == 34


@pytest.mark.parametrize("position", range(1, 17))
def test_native_cycle_every_wrong_transition_stops(
    private_root: tuple[Path, Path], position: int
) -> None:
    with storage.locked_exercise(*private_root) as guarded:
        device = NativeDevice(guarded, bad_position=position, failure="state")
        with pytest.raises(evidence.Rejected):
            device.run()
        assert len(device.sent) == position
        assert guarded.pending.exists()
        assert len(list(guarded.runtime.glob("*intent.json"))) == position
        assert not (guarded.runtime / "empty-vlan-complete.json").exists()


@pytest.mark.parametrize("failure", ["unknown", "down", "pvid", "admission"])
def test_native_cycle_rejects_before_begin(
    private_root: tuple[Path, Path], failure: str
) -> None:
    with storage.locked_exercise(*private_root) as guarded:
        device = NativeDevice(guarded, bad_position=0, failure=failure)
        with pytest.raises(evidence.Rejected):
            device.run()
        assert not device.sent
        assert not guarded.pending.exists()
        assert not list(guarded.runtime.glob("empty-vlan-phase-*.json"))


@pytest.mark.parametrize("failure", ["unknown", "down", "pvid"])
def test_native_cycle_callback_rechecks_operational_state(
    private_root: tuple[Path, Path], failure: str
) -> None:
    with storage.locked_exercise(*private_root) as guarded:
        device = NativeDevice(guarded, bad_position=0, failure=failure, occurrence=3)
        with pytest.raises(evidence.Rejected):
            device.run()
        assert not device.sent
        assert guarded.pending.exists()
        assert not list(guarded.runtime.glob("empty-vlan-phase-*.json"))


@pytest.mark.parametrize(
    "failure,position,count",
    [
        ("extra", 3, 3),
        ("interface_leaf", 6, 6),
        ("startup", 6, 6),
        ("native_inverse", 11, 11),
        ("inverse_pvid", 11, 11),
        ("missing", -1, 0),
        ("double", -1, 1),
        ("timeout", -1, 1),
    ],
)
def test_native_cycle_failure_retains_pending_and_never_retries(
    private_root: tuple[Path, Path], failure: str, position: int, count: int
) -> None:
    with storage.locked_exercise(*private_root) as guarded:
        device = NativeDevice(guarded, bad_position=position, failure=failure)
        with pytest.raises((evidence.Rejected, TimeoutError)):
            device.run()
        assert len(device.sent) == count
        assert guarded.pending.exists()
        pending = storage.decode(guarded.pending.read_bytes())
        assert pending["operation"] == cycle.CycleProfile.STANDBY_NATIVE.value
        assert pending["commands"] == list(cycle.STANDBY_NATIVE_COMMANDS)
        assert pending["writer"] == "caller_supplied_transport"
        assert not (guarded.runtime / "empty-vlan-complete.json").exists()
        with pytest.raises((evidence.Rejected, storage.Rejected)):
            device.run()
        assert len(device.sent) == count


def test_native_cycle_fixed_public_baseline(private_root: tuple[Path, Path]) -> None:
    with storage.locked_exercise(*private_root) as guarded:
        device = NativeDevice(guarded)
        with pytest.raises(evidence.Rejected):
            cycle.run_standby_native_cycle(
                guarded,
                BASELINE,
                device.observe,
                device.send,
                device.admit,
                device.binding,
            )
        assert not device.sent
        assert not guarded.pending.exists()


def test_native_cycle_sources_bind_observer_transport_and_dependencies() -> None:
    for name in (
        "standby_native_observation",
        "standby_native_transport",
        "trunk_observation",
        "trunk_plan",
        "trunk_link_admission",
    ):
        assert cycle.SOURCE_MANIFEST[name] == storage.digest(
            cycle.SOURCE_PATHS[name].read_bytes()
        )


@pytest.mark.parametrize("boundary", ["intent", "empty-vlan-complete.json"])
def test_native_cycle_durability_failure_retains_pending(
    private_root: tuple[Path, Path], boundary: str
) -> None:
    with storage.locked_exercise(*private_root) as guarded:
        device = NativeDevice(guarded)
        original = storage.exclusive_write

        def fail(path: Path, raw: bytes) -> None:
            if boundary in path.name:
                raise OSError("native durability failure")
            original(path, raw)

        with (
            patch.object(storage, "exclusive_write", side_effect=fail),
            pytest.raises(storage.Uncertain),
        ):
            device.run()
        assert guarded.pending.exists()
        assert guarded.failed is True
        assert len(device.sent) == (0 if boundary == "intent" else 16)
        with pytest.raises(storage.Uncertain):
            device.run()
        assert len(device.sent) == (0 if boundary == "intent" else 16)
