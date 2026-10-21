"""Offline carrier restoration through real cycle, admission and budget guards."""

import hashlib

import pytest
from unittest.mock import patch

import native_trunk_observation as observation
import test_empty_vlan_cycle as fixtures
from test_empty_vlan_cycle import (
    R8FullTrunkDevice,
    CallbackProducer,
    StrictConsole,
    admission,
    cycle,
    evidence,
    native_plan,
    native_transport,
    rechain_r8_cycle,
    resident,
    storage,
    strict_replies,
    synthetic_evidence,
    valid_guest_proof,
    test_current_r8_full_trunk_runner_restores_and_semantically_admits as run_normal,
)

private_root = fixtures.private_root


def carrier(payload, state):
    rows = []
    for line in payload["responses"]["show interfaces brief"].splitlines():
        row = line.split()
        if row and row[0] == "1/2/2":
            row[1:5] = ["Up", state, "Full", "10G"]
            row[5] = "None"
        rows.append(" ".join(row))
    payload["responses"]["show interfaces brief"] = "\n".join(rows)
    return payload


@pytest.mark.parametrize("settle", ["Forward", "Down"])
def test_restoration_validator_settles_without_relaxing_strict(private_root, settle):
    with storage.locked_exercise(*private_root) as guarded:
        device = R8FullTrunkDevice(guarded)
        payload = device.observe()
        if settle != "Down":
            carrier(payload, settle)
        brief = payload["responses"]["show interfaces brief"]
        observation.require_r8_full_trunk_restoration_operational_state(
            brief, device.state()
        )
        if settle == "Forward":
            with pytest.raises(observation.evidence.Rejected):
                observation.require_r8_full_trunk_operational_state(
                    brief, device.state()
                )


@pytest.mark.parametrize("transient", [False, True])
def test_normal_inverse_accepts_carrier_and_transient_listen(
    private_root, monkeypatch, transient
):
    original = R8FullTrunkDevice.observe
    reads = []

    def observe(device):
        payload = original(device)
        if (
            device.position >= len(device.forward_states)
            and device.position not in reads
        ):
            reads.append(device.position)
            return carrier(
                payload, "Listen" if transient and len(reads) <= 2 else "Forward"
            )
        if device.position >= len(device.forward_states):
            return carrier(payload, "Forward")
        return payload

    monkeypatch.setattr(R8FullTrunkDevice, "observe", observe)
    run_normal(private_root)
    assert reads


class BudgetProducer(CallbackProducer):
    def __call__(self, held, binding, *, deadline=None):
        assert deadline is not None
        return self.callback(held, binding)


class CarrierDevice(R8FullTrunkDevice):
    def __init__(
        self,
        guarded,
        *,
        listen=(),
        settled="Forward",
        persistent=False,
        corrupt=None,
        after_read=None,
        forward_failure=False,
    ):
        super().__init__(guarded)
        self.listen = set(listen)
        self.settled = settled
        self.persistent = persistent
        self.corrupt = corrupt
        self.after_read = after_read
        self.forward_failure = forward_failure
        self.restoring = False
        self.restoration_reads = 0
        self.sent = []
        self.proofs = []
        self.sessions = 0

    def observe(self):
        result = super().observe()
        if self.restoring:
            self.restoration_reads += 1
            number = self.restoration_reads
            if self.persistent or number in self.listen:
                carrier(result, "Listen")
            elif self.settled != "Down":
                carrier(result, self.settled)
            if self.corrupt is not None:
                self.corrupt(result)
            if self.after_read is not None:
                self.after_read(number)
        return result

    def recovery_session(self):
        self.restoring = True
        self.sessions += 1
        initial = self.state()
        inverse = native_plan.r8_full_inverse_commands(initial)
        states = native_plan._states(inverse, initial)
        console = StrictConsole(
            strict_replies(inverse, native_transport._modes(inverse, initial))
        )
        channel_send = console.channel.sendall
        position = 0

        def advance(text):
            nonlocal position
            channel_send(text)
            if text != "\r":
                self.sent.append(text.rstrip("\r"))
                position += 1
                self.live_state = states[position]

        console.channel.sendall = advance
        return self.observe, console, lambda: None


def run_candidate(device, budget, *, proof_failure=None):
    commands = cycle.R8_FULL_TRUNK_CYCLE_COMMANDS
    console = StrictConsole(
        strict_replies(commands, native_transport._modes(commands, device.initial))
    )
    channel_send = console.channel.sendall

    def advance(text):
        channel_send(text)
        if text != "\r":
            device.position += 1
            if device.forward_failure and device.position == 10:
                raise TimeoutError("uncertain forward acknowledgement")

    def proof(held, binding):
        device.proofs.append(device.state())
        if proof_failure == len(device.proofs):
            raise ValueError("guest proof failed")
        return valid_guest_proof(held, binding)

    console.channel.sendall = advance
    with patch.object(
        admission.plan,
        "R8_BASELINE_SHA256",
        evidence.configuration_hash(device.baseline),
    ):
        return resident.run_r8_full_trunk_candidate(
            device.guarded,
            device.baseline,
            device.observe,
            console,
            device.admit,
            device.binding,
            BudgetProducer(proof),
            synthetic_evidence()[2],
            device.recovery_session,
            operation_budget=budget,
        )


@pytest.mark.parametrize(
    "listen", [(), (1,), (2,), (3,), (4,), (52,), (53,), (54,), (1, 4)]
)
@pytest.mark.parametrize("settled", ["Forward", "Down"])
def test_real_budget_all_inverse_boundaries_and_receipt(private_root, listen, settled):
    with storage.locked_exercise(*private_root) as guarded:
        device = CarrierDevice(guarded, listen=listen, settled=settled)
        budget = resident.R8OperationBudget()
        result = run_candidate(device, budget)
        assert (
            result["admission"]["status"]
            == "semantically_valid_unsaved_r8_full_trunk_cycle"
        )
        assert device.state() == device.initial
        assert device.sent == list(native_plan.R8_FULL_INVERSE)
        assert device.restoration_reads == 54 + len(listen)
        assert len(device.proofs) == 2
        assert budget.phase == "cleanup"
        assert not guarded.pending.exists()


@pytest.mark.parametrize(
    "listen,persistent,expected_reads,sent_count",
    [((1, 3, 5), False, 5, 0), ((), True, 3, 0), ((4, 5, 6), False, 6, 1)],
)
def test_listen_exhausts_one_global_allowance_without_sending(
    private_root, listen, persistent, expected_reads, sent_count
):
    with storage.locked_exercise(*private_root) as guarded:
        device = CarrierDevice(guarded, listen=listen, persistent=persistent)
        with pytest.raises(observation.R8PrimaryListening):
            run_candidate(device, resident.R8OperationBudget())
        assert device.restoration_reads == expected_reads
        assert device.sent == list(native_plan.R8_FULL_INVERSE[:sent_count])
        assert guarded.pending.exists()
        assert not (guarded.runtime / "empty-vlan-complete.json").exists()


@pytest.mark.parametrize(
    "corruption",
    [
        "vlan",
        "vlan_membership",
        "startup",
        "pvid",
        "other_port",
        "malformed",
        "binding",
    ],
)
def test_listen_with_other_drift_never_retries(private_root, corruption):
    def corrupt(payload):
        if corruption == "vlan":
            payload["r8_vlan_tables"]["40"] += "\nunknown"
        elif corruption == "vlan_membership":
            table = payload["r8_vlan_tables"]["40"].replace(
                "Tagged Ports: (U1/M2) 6", "Tagged Ports: (U1/M2) 2 6"
            )
            payload["r8_vlan_tables"]["40"] = table
            payload["r8_vlan_capture_sha256"]["show vlan 40"] = hashlib.sha256(
                f"show vlan 40\n{table}".encode()
            ).hexdigest()
        elif corruption == "startup":
            payload["responses"]["show configuration"] += "\nunknown"
        else:
            text = payload["responses"]["show interfaces brief"]
            if corruption == "malformed":
                text += "\n1/2/2 Up Listen Full 10G None Yes 1 0 bad"
            elif corruption == "pvid":
                rows = [line.split() for line in text.splitlines()]
                for row in rows:
                    if row and row[0] == "1/2/2":
                        row[7] = "999"
                text = "\n".join(" ".join(row) for row in rows)
            else:
                text = text.replace("1/2/6 Up Forward", "1/2/6 Up Listen")
            payload["responses"]["show interfaces brief"] = text

    with storage.locked_exercise(*private_root) as guarded:
        device = CarrierDevice(guarded, persistent=True, corrupt=corrupt)
        if corruption == "binding":
            device.corrupt = None
            device.after_read = lambda number: device.binding.update(
                preview_sha256="0" * 64
            )
        with pytest.raises(evidence.Rejected) as failure:
            run_candidate(device, resident.R8OperationBudget())
        assert not isinstance(failure.value, observation.R8PrimaryListening)
        assert device.restoration_reads == 1
        assert not device.sent
        assert guarded.pending.exists()


def test_pending_custody_blocks_new_run_without_new_settles(private_root):
    with storage.locked_exercise(*private_root) as guarded:
        device = CarrierDevice(guarded, persistent=True)
        with pytest.raises(observation.R8PrimaryListening):
            run_candidate(device, resident.R8OperationBudget())
        pending = guarded.pending.read_bytes()
    with storage.locked_exercise(*private_root) as restarted:
        fresh = CarrierDevice(restarted, persistent=True)
        with pytest.raises(storage.Uncertain, match="pending operation blocks"):
            run_candidate(fresh, resident.R8OperationBudget())
        assert fresh.restoration_reads == 0
        assert not fresh.sent
        assert restarted.pending.read_bytes() == pending


@pytest.mark.parametrize("proof_failure", [1, 2])
def test_proof_failure_restores_carrier_but_retains_custody(
    private_root, proof_failure
):
    with storage.locked_exercise(*private_root) as guarded:
        device = CarrierDevice(guarded, listen=(1, 4))
        with pytest.raises(evidence.Rejected):
            run_candidate(
                device, resident.R8OperationBudget(), proof_failure=proof_failure
            )
        assert device.state() == device.initial
        assert device.sent == list(native_plan.R8_FULL_INVERSE)
        assert guarded.pending.exists()


def test_entry_listen_cannot_borrow_inverse_or_proof_reserve(private_root, monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(resident.time, "monotonic", lambda: clock[0])
    budget = resident.R8OperationBudget()
    cutoff = budget.observation_deadline

    def expire_on_read(number):
        assert number == 1
        assert budget.phase == "held"
        assert budget.observation_deadline == cutoff
        clock[0] = cutoff

    with storage.locked_exercise(*private_root) as guarded:
        device = CarrierDevice(guarded, persistent=True, after_read=expire_on_read)
        with pytest.raises(TimeoutError, match="phase deadline"):
            run_candidate(device, budget)
        assert device.restoration_reads == 1
        assert budget.phase == "held"
        assert budget.deadline == 1800
        assert not device.sent
        assert guarded.pending.exists()


@pytest.mark.parametrize("listen", [(1,), (2,), (3,), (4,), (25,), (1, 4), ()])
def test_emergency_carrier_restore_retains_custody(private_root, listen):
    with storage.locked_exercise(*private_root) as guarded:
        device = CarrierDevice(guarded, listen=listen, forward_failure=True)
        with pytest.raises(
            evidence.Rejected, match="exact restoration verified; custody retained"
        ):
            run_candidate(device, resident.R8OperationBudget())
        assert device.state() == device.initial
        assert device.sent
        assert guarded.pending.exists()
        assert device.sessions == 1


@pytest.mark.parametrize(
    "target", ["inverse_intent", "inverse_observed", "final", "held"]
)
def test_receipt_never_accepts_listen_and_held_stays_strict(private_root, target):
    with storage.locked_exercise(*private_root) as guarded:
        device = CarrierDevice(guarded)
        run_candidate(device, resident.R8OperationBudget())
        records = sorted(guarded.runtime.glob("empty-vlan-phase-*.json"))
        index = {
            "inverse_intent": 34,
            "inverse_observed": 35,
            "final": len(records) - 1,
            "held": 34,
        }[target]
        record = storage.decode(records[index].read_bytes())
        payload = record["evidence"]
        if target == "inverse_observed":
            payload = payload["observation"]
        elif target == "held":
            payload = payload["held_boundary_observation"]
        carrier(payload, "Forward" if target == "held" else "Listen")
        record["evidence_sha256"] = evidence.digest(record["evidence"])
        records[index].write_bytes(storage.canonical(record))
        rechain_r8_cycle(guarded.runtime)
        with patch.object(
            admission.plan,
            "R8_BASELINE_SHA256",
            evidence.configuration_hash(device.baseline),
        ):
            with pytest.raises(evidence.Rejected):
                admission.validate_completed_cycle(
                    guarded.runtime,
                    device.baseline,
                    device.binding,
                    profile=cycle.CycleProfile.R8_FULL_TRUNK,
                )
