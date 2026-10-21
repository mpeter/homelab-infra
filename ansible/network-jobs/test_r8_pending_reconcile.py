"""Custody checks for a restored pre-upgrade R8 pending operation."""

import hashlib
import json
import stat
from datetime import datetime, timedelta, timezone
from pathlib import Path
from contextlib import contextmanager

import pytest

import port_exercise_ledger as storage
import r8_pending_reconcile as reconcile


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def test_completed_reconciliation_creates_private_lock_runtime_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    parent = tmp_path / "recovery"
    pending_dir = parent / "brocade-persistence-ledger"
    pending_dir.mkdir(parents=True, mode=0o700)
    pending = pending_dir / "pending.json"
    pending.write_text("{}")
    archive = tmp_path / reconcile.R8_COMPLETED_UNQUALIFIED_OPERATION
    archive.mkdir(mode=0o700)
    preflight = tmp_path / "preflight.json"
    readback = tmp_path / "readback.json"
    preflight.write_text("{}")
    readback.write_text("{}")

    @contextmanager
    def enter_lock(lock_parent: Path, runtime: Path):
        assert lock_parent == parent
        assert runtime.is_dir()
        assert stat.S_IMODE(runtime.stat().st_mode) == 0o700
        raise RuntimeError("lock entered")
        yield  # pragma: no cover

    monkeypatch.setattr(reconcile.storage, "locked_exercise", enter_lock)
    with pytest.raises(RuntimeError, match="lock entered"):
        reconcile.reconcile_completed_unqualified_archive(
            pending_path=pending,
            archive=archive,
            preflight_path=preflight,
            readback_path=readback,
        )


def test_completed_reconciliation_rejects_archive_chain_changed_before_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    expected_chain = [{"path": "phase.json", "sha256": "a" * 64}]
    completion = {"status": "complete"}
    monkeypatch.setattr(
        reconcile,
        "verify_completed_cycle_archive",
        lambda *_args: (
            [{"path": "phase.json", "sha256": "b" * 64}],
            completion,
            (),
            {},
        ),
    )

    with pytest.raises(
        reconcile.Rejected, match="archive changed before pending release"
    ):
        reconcile.verify_completed_cycle_unchanged(
            tmp_path,
            {},
            b"pending",
            tmp_path,
            expected_chain,
            completion,
        )


def test_snapshot_requires_the_original_source_closure(tmp_path: Path) -> None:
    source = tmp_path / "source.py"
    source.write_bytes(b"original source\n")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    operation_id = "a" * 64
    binding = hashlib.sha256(canonical({"module": digest})).hexdigest()
    manifest = {
        "schema": 1,
        "operation_id": operation_id,
        "source_binding_sha256": binding,
        "manifest": {
            "module": {
                "snapshot_path": "source.py",
                "sha256": digest,
            }
        },
    }
    storage.exclusive_write(tmp_path / "manifest.json", canonical(manifest))
    pending = {
        "operation_id": operation_id,
        "binding": {"source_binding_sha256": binding},
    }

    assert reconcile.verify_snapshot(tmp_path, pending) == manifest
    source.write_bytes(b"edited source\n")
    with pytest.raises(reconcile.Rejected, match="snapshot file changed"):
        reconcile.verify_snapshot(tmp_path, pending)


def test_completed_archive_binds_source_bytes_and_pending(tmp_path: Path) -> None:
    archive = tmp_path / "archive"
    archive.mkdir(mode=0o700)
    (archive / "source").mkdir(mode=0o700)
    (archive / "pending").mkdir(mode=0o700)
    source = b"archived source\n"
    storage.exclusive_write(archive / "source/module", source)
    source_manifest = {"module": hashlib.sha256(source).hexdigest()}
    source_binding = hashlib.sha256(canonical(source_manifest)).hexdigest()
    pending = {
        "operation_id": "a" * 64,
        "binding": {"source_binding_sha256": source_binding},
    }
    pending_raw = storage.canonical(pending)
    storage.exclusive_write(archive / "pending/pending.json", pending_raw)
    manifest = {
        "schema": 1,
        "operation_id": pending["operation_id"],
        "pending_sha256": hashlib.sha256(pending_raw).hexdigest(),
        "source_binding_sha256": source_binding,
        "source_manifest": source_manifest,
        "runtime_files": {},
    }
    storage.exclusive_write(
        archive / "archive-manifest.json", storage.canonical(manifest)
    )

    verified, _ = reconcile.verify_source_archive_manifest(
        archive, pending, pending_raw, {"module"}
    )

    assert verified == source_manifest
    (archive / "source/module").write_bytes(b"changed source\n")
    with pytest.raises(reconcile.Rejected, match="archived source changed"):
        reconcile.verify_source_archive_manifest(
            archive, pending, pending_raw, {"module"}
        )


def test_completed_rejected_proof_only_accepts_legacy_unreconstructable_boundary() -> (
    None
):
    pending = {
        "operation_id": reconcile.R8_COMPLETED_UNQUALIFIED_OPERATION,
        "binding": {
            "source_binding_sha256": reconcile.R8_COMPLETED_UNQUALIFIED_SOURCE,
        },
    }
    proof = {
        "status": "rejected",
        "operation_id": pending["operation_id"],
        "forward_count": 14,
        "boundary_observation_sha256": "a" * 64,
        "source_binding_sha256": pending["binding"]["source_binding_sha256"],
        "reason": "Rejected",
    }
    with pytest.raises(reconcile.Rejected, match="guest-proof rejection differs"):
        reconcile._verify_rejected_guest_proof(
            proof,
            {},
            pending,
            field="held_guest_proof",
            boundary=14,
        )
    reconcile._verify_rejected_guest_proof(
        proof,
        {},
        pending,
        field="held_guest_proof",
        boundary=14,
        allow_unreconstructable_boundary=True,
    )
    proof["boundary_observation_sha256"] = "not-a-digest"
    with pytest.raises(reconcile.Rejected, match="guest-proof rejection differs"):
        reconcile._verify_rejected_guest_proof(
            proof,
            {},
            pending,
            field="held_guest_proof",
            boundary=14,
            allow_unreconstructable_boundary=True,
        )


def test_recovery_chain_binds_observed_boundary_to_inverse_intent(
    tmp_path: Path,
) -> None:
    operation_id = "a" * 64
    pending = {"operation_id": operation_id}
    pending_raw = storage.canonical(pending)
    state_sha256 = "b" * 64
    observed = {
        "boundary_index": 15,
        "inverse_commands": ["configure terminal", "exit"],
        "state_sha256": state_sha256,
    }
    intent = {
        "index": 0,
        "command": "configure terminal",
        "expected_state_sha256": state_sha256,
    }
    previous = hashlib.sha256(pending_raw).hexdigest()
    for index, (phase, evidence) in enumerate(
        (("observed", observed), ("inverse_intent", intent))
    ):
        record = {
            "operation_id": operation_id,
            "index": index,
            "phase": phase,
            "prev_digest": previous,
            "evidence_sha256": hashlib.sha256(canonical(evidence)).hexdigest(),
            "evidence": evidence,
        }
        path = tmp_path / f"empty-vlan-recovery-{index:02d}-{phase}.json"
        storage.exclusive_write(path, storage.canonical(record))
        previous = hashlib.sha256(path.read_bytes()).hexdigest()

    receipts, recovered = reconcile.verify_recovery_chain(
        pending, pending_raw, tmp_path
    )

    assert len(receipts) == 2
    assert recovered == observed
    intent_path = tmp_path / "empty-vlan-recovery-01-inverse_intent.json"
    record = json.loads(intent_path.read_text())
    record["evidence"]["expected_state_sha256"] = "c" * 64
    record["evidence_sha256"] = hashlib.sha256(
        canonical(record["evidence"])
    ).hexdigest()
    intent_path.write_bytes(storage.canonical(record))
    with pytest.raises(
        reconcile.Rejected, match="recovery boundary does not bind its inverse intent"
    ):
        reconcile.verify_recovery_chain(pending, pending_raw, tmp_path)


def test_phase_prefix_requires_contiguous_intent_observation_chain(
    tmp_path: Path,
) -> None:
    pending = {"operation_id": "d" * 64}
    pending_raw = storage.canonical(pending)
    evidence = {"baseline_sha256": "e" * 64}
    record = {
        "operation_id": pending["operation_id"],
        "index": 0,
        "phase": "command_0_intent",
        "prev_digest": hashlib.sha256(pending_raw).hexdigest(),
        "evidence_sha256": hashlib.sha256(canonical(evidence)).hexdigest(),
        "evidence": evidence,
    }
    path = tmp_path / "empty-vlan-phase-00-command_0_intent.json"
    storage.exclusive_write(path, storage.canonical(record))

    receipts, digest = reconcile.verify_phase_prefix(pending, pending_raw, tmp_path, 1)

    assert receipts == [{"path": str(path), "sha256": digest}]
    with pytest.raises(reconcile.Rejected, match="phase prefix file set differs"):
        reconcile.verify_phase_prefix(pending, pending_raw, tmp_path, 3)


@pytest.mark.parametrize("last_index", (25, 31))
def test_restore_chain_binds_every_receipt_and_exact_final_state(
    tmp_path: Path, last_index: int
) -> None:
    runtime = tmp_path / "runtime"
    restore_dir = tmp_path / "restore"
    runtime.mkdir(mode=0o700)
    restore_dir.mkdir()
    pending = {
        "operation_id": "b" * 64,
        "binding": {
            "baseline_running_sha256": "c" * 64,
            "baseline_startup_sha256": "c" * 64,
        },
    }
    inverse = {"phase": "inverse_intent"}
    inverse_path = runtime / "empty-vlan-recovery-01-inverse_intent.json"
    storage.exclusive_write(inverse_path, storage.canonical(inverse))
    previous = hashlib.sha256(inverse_path.read_bytes()).hexdigest()

    for index in range(2, last_index + 1):
        evidence = (
            {
                "pending_retained": True,
                "running_sha256": "c" * 64,
                "startup_sha256": "c" * 64,
            }
            if index == last_index
            else {"step": index}
        )
        name = "restored" if index == last_index else f"step-{index}"
        record = {
            "operation_id": pending["operation_id"],
            "index": index,
            "phase": name,
            "prev_digest": previous,
            "evidence_sha256": hashlib.sha256(canonical(evidence)).hexdigest(),
            "evidence": evidence,
        }
        path = restore_dir / f"r8-restore-{index:02d}-{name}.json"
        storage.exclusive_write(path, storage.canonical(record))
        previous = hashlib.sha256(path.read_bytes()).hexdigest()

    result = reconcile.verify_restore_chain(pending, runtime, restore_dir)
    assert len(result["records"]) == last_index - 1
    assert result["final_sha256"] == previous

    final_path = restore_dir / f"r8-restore-{last_index:02d}-restored.json"
    final = json.loads(final_path.read_text())
    final["prev_digest"] = "d" * 64
    final_path.write_bytes(storage.canonical(final))
    with pytest.raises(reconcile.Rejected, match="receipt chain mismatch"):
        reconcile.verify_restore_chain(pending, runtime, restore_dir)


def test_interrupted_prefix_requires_exact_current_source_native_boundary(
    tmp_path: Path,
) -> None:
    runtime = tmp_path / "runtime"
    runtime.mkdir(mode=0o700)
    operation_id = "e" * 64
    pending = {
        "schema": 4,
        "operation": "r8_full_trunk_cycle",
        "host": "192.168.0.251",
        "fingerprint": "SHA256:UJulVmfAMmHcUctvJrlGzBZR7I7uN8/TWNeJIs25yks",
        "operation_id": operation_id,
        "runtime": str(runtime),
        "commands": [
            "configure terminal",
            "interface ethernet 1/2/2",
            "no dual-mode 1",
        ],
    }
    pending_raw = canonical(pending)
    previous = hashlib.sha256(pending_raw).hexdigest()
    for index in range(5):
        phase = f"command_{index // 2}_{'intent' if index % 2 == 0 else 'observed'}"
        evidence = {"step": index}
        record = {
            "operation_id": operation_id,
            "index": index,
            "phase": phase,
            "prev_digest": previous,
            "evidence_sha256": hashlib.sha256(canonical(evidence)).hexdigest(),
            "evidence": evidence,
        }
        path = runtime / f"empty-vlan-phase-{index:02d}-{phase}.json"
        storage.exclusive_write(path, storage.canonical(record))
        previous = hashlib.sha256(path.read_bytes()).hexdigest()

    result = reconcile.verify_interrupted_prefix(pending, pending_raw, runtime)
    assert len(result) == 5

    final = runtime / "empty-vlan-phase-04-command_2_intent.json"
    record = json.loads(final.read_text())
    record["prev_digest"] = "f" * 64
    final.write_bytes(storage.canonical(record))
    with pytest.raises(reconcile.Rejected, match="phase chain mismatch"):
        reconcile.verify_interrupted_prefix(pending, pending_raw, runtime)


class Guard:
    def __init__(self, fail_at: int | None = None) -> None:
        self.files: dict[Path, tuple[bytes, tuple[int, int]]] = {}
        self.calls = 0
        self.fail_at = fail_at

    def guard(self) -> None:
        self.calls += 1
        if self.calls == self.fail_at:
            raise storage.Rejected("injected post-release guard failure")


@pytest.mark.parametrize("fail_after_release", (False, True))
def test_pending_slot_release_preserves_or_restores_exact_marker(
    tmp_path: Path, fail_after_release: bool
) -> None:
    pending = tmp_path / "pending.json"
    raw = storage.canonical({"operation_id": "f" * 64})
    storage.exclusive_write(pending, raw)
    identity = storage.read_file(pending)[1]
    custody = tmp_path / "custody"
    custody.mkdir(mode=0o700)
    storage.exclusive_write(custody / "pending.json", raw)
    guard = Guard(fail_at=2 if fail_after_release else None)
    guard.files[pending] = (raw, identity)

    if fail_after_release:
        with pytest.raises(storage.Rejected, match="post-release"):
            reconcile.release_pending_slot(pending, raw, identity, custody, guard)
        assert storage.read_file(pending)[0] == raw
    else:
        reconcile.release_pending_slot(pending, raw, identity, custody, guard)
        assert not pending.exists()
    assert storage.read_file(custody / "pending.json")[0] == raw


def _unavailable_source_pending(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    parent = tmp_path / "operation-parent"
    parent.mkdir(mode=0o700)
    runtime = parent / "runtime"
    runtime.mkdir(mode=0o700)
    (parent / "source-snapshots").mkdir(mode=0o700)
    binding = {
        "baseline_running_sha256": "a" * 64,
        "baseline_startup_sha256": "a" * 64,
        "execution_environment_sha256": "b" * 64,
        "native_recovery_proof_sha256": "c" * 64,
        "preview_sha256": "d" * 64,
        "source_binding_sha256": "e" * 64,
    }
    monkeypatch.setattr(reconcile, "R8_ACCEPTED_BASELINE", "a" * 64)
    monkeypatch.setattr(reconcile, "R8_UNAVAILABLE_SOURCE_BINDING", "e" * 64)
    pending = {
        "schema": 4,
        "operation": "r8_full_trunk_cycle",
        "host": "192.168.0.251",
        "fingerprint": "SHA256:UJulVmfAMmHcUctvJrlGzBZR7I7uN8/TWNeJIs25yks",
        "writer": "caller_supplied_transport",
        "runtime": str(runtime),
        "commands": reconcile.R8_FAILED_COMMANDS,
        "binding": binding,
    }
    operation_id = hashlib.sha256(storage.canonical(pending)).hexdigest()
    monkeypatch.setattr(reconcile, "R8_UNAVAILABLE_SOURCE_OPERATION", operation_id)
    pending["operation_id"] = operation_id
    return parent, runtime, pending, storage.canonical(pending)


def _write_unavailable_source_chains(
    runtime: Path, pending: dict[str, object], pending_raw: bytes
) -> None:
    operation_id = pending["operation_id"]
    previous = hashlib.sha256(pending_raw).hexdigest()
    for index in range(35):
        phase = f"command_{index // 2}_{'intent' if index % 2 == 0 else 'observed'}"
        evidence = {"step": index}
        record = {
            "operation_id": operation_id,
            "index": index,
            "phase": phase,
            "prev_digest": previous,
            "evidence_sha256": hashlib.sha256(
                reconcile._canonical(evidence)
            ).hexdigest(),
            "evidence": evidence,
        }
        path = runtime / f"empty-vlan-phase-{index:02d}-{phase}.json"
        storage.exclusive_write(path, storage.canonical(record))
        previous = hashlib.sha256(path.read_bytes()).hexdigest()
    state_sha = "f" * 64
    recovery_evidence = {
        "boundary_index": 15,
        "forward_failure": "Rejected",
        "inverse_commands": reconcile.R8_FAILED_INVERSE,
        "state_sha256": state_sha,
    }
    intent_evidence = {
        "index": 0,
        "command": "configure terminal",
        "expected_state_sha256": state_sha,
    }
    for index, (phase, evidence) in enumerate(
        (("observed", recovery_evidence), ("inverse_intent", intent_evidence))
    ):
        record = {
            "operation_id": operation_id,
            "index": index,
            "phase": phase,
            "prev_digest": previous,
            "evidence_sha256": hashlib.sha256(
                reconcile._canonical(evidence)
            ).hexdigest(),
            "evidence": evidence,
        }
        path = runtime / f"empty-vlan-recovery-{index:02d}-{phase}.json"
        storage.exclusive_write(path, storage.canonical(record))
        previous = hashlib.sha256(path.read_bytes()).hexdigest()


def test_unavailable_source_path_is_allowlisted_and_chain_bound(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    parent, runtime, pending, pending_raw = _unavailable_source_pending(
        tmp_path, monkeypatch
    )
    _write_unavailable_source_chains(runtime, pending, pending_raw)

    phases, recoveries = reconcile.verify_unavailable_source_operation(
        pending, pending_raw, runtime, parent
    )
    assert len(phases) == 35
    assert len(recoveries) == 2

    changed = runtime / "empty-vlan-phase-34-command_17_intent.json"
    record = json.loads(changed.read_text())
    record["prev_digest"] = "0" * 64
    changed.write_bytes(storage.canonical(record))
    with pytest.raises(reconcile.Rejected, match="phase chain mismatch"):
        reconcile.verify_unavailable_source_operation(
            pending, pending_raw, runtime, parent
        )


def test_unavailable_source_path_rejects_other_operation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    parent, runtime, pending, pending_raw = _unavailable_source_pending(
        tmp_path, monkeypatch
    )
    pending["operation_id"] = "0" * 64
    with pytest.raises(reconcile.Rejected, match="outside the source-unavailable"):
        reconcile.verify_unavailable_source_operation(
            pending, pending_raw, runtime, parent
        )


def test_unavailable_source_readback_requires_fresh_exact_baseline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, _, pending, _ = _unavailable_source_pending(tmp_path, monkeypatch)
    lines = ["ver 08.0.30uT7f3", "end"]
    digest = hashlib.sha256(("\n".join(lines) + "\n").encode()).hexdigest()
    monkeypatch.setattr(reconcile, "R8_ACCEPTED_BASELINE", digest)
    pending["binding"]["baseline_running_sha256"] = digest
    pending["binding"]["baseline_startup_sha256"] = digest
    readback = {
        "schema": 1,
        "operation_id": pending["operation_id"],
        "source_provenance": "source_binding_unavailable",
        "capture_mode": "configurations",
        "configuration_write_admitted": False,
        "configurations_complete": True,
        "capture_receipt_sha256": "1" * 64,
        "capture_events_sha256": "2" * 64,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "running_lines": lines,
        "startup_lines": lines,
        "running_sha256": digest,
        "startup_sha256": digest,
    }
    path = tmp_path / "readback.json"
    storage.exclusive_write(path, storage.canonical(readback))
    assert (
        reconcile.verify_unavailable_source_readback(pending, path)["running_sha256"]
        == digest
    )

    readback["startup_lines"] = ["ver 08.0.30uT7f3", "other", "end"]
    storage.exclusive_write(tmp_path / "stale.json", storage.canonical(readback))
    with pytest.raises(reconcile.Rejected, match="configuration hash differs"):
        reconcile.verify_unavailable_source_readback(pending, tmp_path / "stale.json")

    readback["startup_lines"] = lines
    readback["observed_at"] = (
        datetime.now(timezone.utc) - timedelta(hours=1)
    ).isoformat()
    storage.exclusive_write(tmp_path / "old.json", storage.canonical(readback))
    with pytest.raises(reconcile.Rejected, match="older than 30 minutes"):
        reconcile.verify_unavailable_source_readback(pending, tmp_path / "old.json")


def test_unavailable_source_capture_requires_exact_private_file_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, _, pending, _ = _unavailable_source_pending(tmp_path, monkeypatch)
    capture = tmp_path / "capture"
    capture.mkdir(mode=0o700)
    readback_path = tmp_path / "readback.json"
    storage.exclusive_write(readback_path, storage.canonical({}))
    with pytest.raises(reconcile.Rejected, match="capture file set differs"):
        reconcile.verify_unavailable_source_capture(
            capture,
            readback_path,
            {"capture_receipt_sha256": "1" * 64, "capture_events_sha256": "2" * 64},
        )
