"""Semantic validation for a completed, unsaved R8 VLAN probe cycle."""

import os
from collections.abc import Callable
from pathlib import Path
import stat
from typing import Any

import empty_vlan_cycle as cycle
import native_trunk_observation as observation
import native_trunk_plan as plan
import port_description as evidence
import port_exercise as exercise
import port_exercise_ledger as storage


class Rejected(ValueError):
    """A retained cycle does not prove the fixed R8 operation."""


def payload_without_proof(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if key != "held_guest_proof"}


def _require_current_source() -> None:
    if set(cycle.SOURCE_PATHS) != set(cycle.SOURCE_MANIFEST):
        raise Rejected("current-source manifest drift")
    current = {
        name: storage.digest(path.read_bytes())
        for name, path in cycle.SOURCE_PATHS.items()
    }
    if (
        current != cycle.SOURCE_MANIFEST
        or evidence.digest(current) != cycle.SOURCE_DIGEST
    ):
        raise Rejected("current-source digest drift")


def _private(path: Path, *, directory: bool = False) -> None:
    if not path.is_absolute() or path != path.resolve():
        raise Rejected("receipt path must be absolute and canonical")
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise Rejected("receipt path contains a symlink")
    info = path.lstat()
    expected_mode = 0o700 if directory else 0o600
    if (
        info.st_uid != os.getuid()
        or stat.S_IMODE(info.st_mode) != expected_mode
        or not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))
        or (not directory and info.st_nlink != 1)
    ):
        raise Rejected("receipt ownership, mode, type or links")


def _read_json(path: Path) -> tuple[dict[str, Any], bytes, tuple[int, int]]:
    try:
        raw, identity = storage.read_file(path)
        value = storage.decode(raw)
    except (OSError, storage.Rejected) as error:
        raise Rejected("receipt JSON") from error
    return value, raw, identity


def _expected_state(
    payload: Any,
    baseline: tuple[str, ...],
    position: int,
    profile: cycle.CycleProfile,
    vlan_baseline: dict[str, str] | None = None,
    *,
    restoration: bool = False,
) -> None:
    running, startup = evidence.evidence_config(payload, exercise.PORT)
    if profile is cycle.CycleProfile.R8_PROBE:
        probe_observed = observation._classify_r8_probe_observation(
            baseline,
            running,
            startup,
            baseline_sha256=evidence.configuration_hash(baseline),
        )
        forward = len(plan.R8_PROBE_FORWARD)
        inverse = position > forward
        completed = position - forward if inverse else position
        observation.require_r8_probe_state(
            probe_observed, completed=completed, inverse=inverse
        )
        observation.require_r8_probe_operational_state(
            payload["responses"]["show interfaces brief"],
            baseline,
            probe_observed.state,
        )
        return
    selected = plan.build_r8_full_trunk_plan(baseline, startup)
    full_observed = observation.classify_r8_full_trunk_observation(
        baseline, running, startup
    )
    forward = len(plan.R8_FULL_FORWARD)
    inverse = position > forward
    completed = position - forward if inverse else position
    observation.require_r8_full_trunk_state(
        full_observed,
        completed=completed,
        inverse=inverse,
        initial_state=selected.initial_state,
    )
    operational = (
        observation.require_r8_full_trunk_restoration_operational_state
        if restoration
        else observation.require_r8_full_trunk_operational_state
    )
    operational(payload["responses"]["show interfaces brief"], full_observed.state)
    if position == len(profile.commands):
        observation.require_r8_full_trunk_restored(
            full_observed, evidence.configuration_hash(baseline)
        )
    captured_tables = observation.require_r8_vlan_capture(payload)
    captured_baseline = payload.get("r8_vlan_baseline_tables")
    if not isinstance(captured_baseline, dict) or captured_baseline != vlan_baseline:
        raise Rejected("R8 VLAN baseline binding mismatch")
    observation.require_r8_full_trunk_membership(
        captured_tables,
        captured_baseline,
        full_observed.state,
        selected.initial_state,
    )


def validate_completed_cycle(
    runtime: Path,
    baseline: tuple[str, ...],
    expected_binding: dict[str, str],
    *,
    profile: cycle.CycleProfile = cycle.CycleProfile.R8_PROBE,
) -> dict[str, object]:
    """Accept only the complete current-source cycle with semantic phase evidence."""
    _require_current_source()
    _private(runtime, directory=True)
    runtime_identity = storage.private_directory(runtime)
    required = dict(storage.hashes(expected_binding, cycle.BINDING_KEYS))
    baseline_hash = evidence.configuration_hash(baseline)
    if (
        baseline_hash != plan.R8_BASELINE_SHA256
        or required["baseline_running_sha256"] != baseline_hash
        or required["baseline_startup_sha256"] != baseline_hash
        or required["source_binding_sha256"] != cycle.SOURCE_DIGEST
        or required["execution_environment_sha256"] != evidence.EE_DIGEST
        or required["preview_sha256"] != cycle._preview_digest(baseline, profile)
    ):
        raise Rejected("current-source R8 binding mismatch")

    receipt_path = runtime / "empty-vlan-complete.json"
    receipt, receipt_raw, receipt_identity = _read_json(receipt_path)
    snapshots = {receipt_path: (receipt_raw, receipt_identity)}
    operation = receipt.get("operation")
    if not isinstance(operation, dict):
        raise Rejected("retained operation binding required")
    operation_id = operation.get("operation_id")
    unsigned = {key: value for key, value in operation.items() if key != "operation_id"}
    if (
        receipt.get("status") != "complete"
        or receipt.get("operation_id") != operation_id
        or not isinstance(operation_id, str)
        or operation_id != storage.digest(storage.canonical(unsigned))
        or operation.get("schema") != 4
        or operation.get("operation") != profile.value
        or operation.get("host") != evidence.HOST
        or operation.get("fingerprint") != evidence.FINGERPRINT
        or operation.get("writer") != "caller_supplied_transport"
        or operation.get("commands") != list(profile.commands)
        or operation.get("binding") != required
        or receipt.get("phase_count") != len(profile.phases)
    ):
        raise Rejected("completed operation identity or scope")

    records = sorted(runtime.glob("empty-vlan-phase-*.json"))
    phases = profile.phases
    expected_files = {receipt_path, *records}
    if (
        len(records) != len(phases)
        or len(list(runtime.iterdir())) != len(expected_files)
        or set(runtime.iterdir()) != expected_files
    ):
        raise Rejected("incomplete or extra phase chain")
    previous = storage.digest(storage.canonical(operation))
    vlan_baseline = None
    for index, (path, expected_phase) in enumerate(zip(records, phases, strict=True)):
        record, raw, identity = _read_json(path)
        snapshots[path] = (raw, identity)
        payload = record.get("evidence")
        if (
            record.get("operation_id") != operation_id
            or record.get("index") != index
            or record.get("phase") != expected_phase
            or record.get("prev_digest") != previous
            or not isinstance(payload, dict)
            or record.get("evidence_sha256") != evidence.digest(payload)
        ):
            raise Rejected("phase chain or retained evidence mismatch")
        previous = storage.digest(raw)
        if expected_phase.endswith("_intent"):
            position = index // 2
            if profile is cycle.CycleProfile.R8_FULL_TRUNK and vlan_baseline is None:
                candidate = payload.get("r8_vlan_baseline_tables")
                if not isinstance(candidate, dict):
                    raise Rejected("R8 VLAN baseline readbacks required")
                vlan_baseline = candidate
            _expected_state(
                payload,
                baseline,
                position,
                profile,
                vlan_baseline,
                restoration=position >= len(plan.R8_FULL_FORWARD),
            )
            if profile is cycle.CycleProfile.R8_FULL_TRUNK and position == len(
                plan.R8_FULL_FORWARD
            ):
                proof = payload.get("held_guest_proof")
                boundary = payload.get("held_boundary_observation")
                if isinstance(boundary, dict):
                    _expected_state(
                        boundary, baseline, position, profile, vlan_baseline
                    )
                if (
                    not isinstance(proof, dict)
                    or set(proof)
                    != {
                        "status",
                        "operation_id",
                        "forward_count",
                        "boundary_observation_sha256",
                        "source_binding_sha256",
                        "proof_sha256",
                        "proof",
                    }
                    or proof.get("status") != "accepted"
                    or proof.get("operation_id") != operation_id
                    or proof.get("forward_count") != len(plan.R8_FULL_FORWARD)
                    or not isinstance(boundary, dict)
                    or proof.get("boundary_observation_sha256")
                    != evidence.digest(boundary)
                    or proof.get("source_binding_sha256") != cycle.SOURCE_DIGEST
                    or not isinstance(proof.get("proof"), dict)
                    or proof.get("proof_sha256") != evidence.digest(proof["proof"])
                ):
                    raise Rejected("held-state guest proof binding mismatch")
        elif expected_phase == "final_observed":
            _expected_state(
                payload,
                baseline,
                len(profile.commands),
                profile,
                vlan_baseline,
                restoration=True,
            )
            if profile is cycle.CycleProfile.R8_FULL_TRUNK:
                proof = payload.get("restored_guest_proof")
                if (
                    not isinstance(proof, dict)
                    or set(proof)
                    != {
                        "status",
                        "operation_id",
                        "forward_count",
                        "boundary_observation_sha256",
                        "source_binding_sha256",
                        "proof_sha256",
                        "proof",
                    }
                    or proof.get("status") != "accepted"
                    or proof.get("operation_id") != operation_id
                    or proof.get("forward_count") != len(plan.R8_FULL_FORWARD)
                    or proof.get("boundary_observation_sha256")
                    != evidence.digest(
                        {
                            key: value
                            for key, value in payload.items()
                            if key != "restored_guest_proof"
                        }
                    )
                    or proof.get("source_binding_sha256") != cycle.SOURCE_DIGEST
                    or not isinstance(proof.get("proof"), dict)
                    or proof.get("proof_sha256") != evidence.digest(proof["proof"])
                ):
                    raise Rejected("restored-state guest proof binding mismatch")
        elif expected_phase.endswith("_observed"):
            position = index // 2 + 1
            _expected_state(
                payload.get("observation"),
                baseline,
                position,
                profile,
                vlan_baseline,
                restoration=position > len(plan.R8_FULL_FORWARD),
            )
            acknowledgement = payload.get("acknowledgement")
            if (
                not isinstance(acknowledgement, dict)
                or set(acknowledgement) != {"response_body", "response_sha256"}
                or not isinstance(acknowledgement["response_body"], str)
                or acknowledgement["response_sha256"]
                != storage.digest(acknowledgement["response_body"].encode())
                or payload.get("acknowledgement_parser_qualified") is not False
                or record.get("acknowledgement") != acknowledgement
                or record.get("acknowledgement_parser_qualified") is not False
            ):
                raise Rejected("raw acknowledgement binding")

    final = records[-1]
    final_record = storage.decode(snapshots[final][0])
    if receipt.get("final_digest") != storage.digest(
        snapshots[final][0]
    ) or receipt.get("final_observation") != final_record.get("evidence"):
        raise Rejected("final restoration evidence mismatch")
    if (
        storage.private_directory(runtime) != runtime_identity
        or set(runtime.iterdir()) != set(snapshots)
        or any(
            storage.read_file(path) != snapshot for path, snapshot in snapshots.items()
        )
    ):
        raise Rejected("receipt changed during semantic validation")
    _require_current_source()
    return {
        "operation_id": operation_id,
        "status": (
            "semantically_valid_unsaved_r8_cycle"
            if profile is cycle.CycleProfile.R8_PROBE
            else "semantically_valid_unsaved_r8_full_trunk_cycle"
        ),
        "source_binding_sha256": required["source_binding_sha256"],
        "baseline_sha256": baseline_hash,
        "phase_count": len(records),
        "final_running_sha256": baseline_hash,
        "final_startup_sha256": baseline_hash,
        "live_admission": False,
        "task_complete": False,
    }


def run_and_admit_cycle(
    guarded: storage.ExerciseLedger,
    baseline: tuple[str, ...],
    observe: Callable[[], dict[str, Any]],
    send: Callable[[int, str, Callable[[], None]], dict[str, Any]],
    admit: Callable[[], None],
    binding: dict[str, str],
) -> dict[str, object]:
    """Run the fixed unsaved R8 cycle and admit only its semantic receipt."""
    result = cycle.run_r8_probe_cycle(
        guarded,
        baseline,
        observe,
        send,
        admit,
        binding,
        semantic_admit=lambda: validate_completed_cycle(
            guarded.runtime, baseline, binding
        ),
    )
    if result.get("cycle_passed") is not True:
        raise Rejected("R8 cycle did not complete")
    return {"cycle": result, "admission": result["semantic_admission"]}


def run_and_admit_full_trunk_cycle(
    guarded: storage.ExerciseLedger,
    baseline: tuple[str, ...],
    observe: Callable[[], dict[str, Any]],
    send: Callable[[int, str, Callable[[], None]], dict[str, Any]],
    admit: Callable[[], None],
    binding: dict[str, str],
    held_guest_proof: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]],
    r8_recovery_session: Callable[
        [], tuple[Callable[[], dict[str, Any]], Any, Callable[[], None]]
    ]
    | None = None,
    operation_budget: Any = None,
) -> dict[str, object]:
    """Run and semantically admit the current-source R8 full-tag cycle."""
    result = cycle.run_r8_full_trunk_cycle(
        guarded,
        baseline,
        observe,
        send,
        admit,
        binding,
        held_guest_proof=held_guest_proof,
        r8_recovery_session=r8_recovery_session,
        operation_budget=operation_budget,
        semantic_admit=lambda: validate_completed_cycle(
            guarded.runtime,
            baseline,
            binding,
            profile=cycle.CycleProfile.R8_FULL_TRUNK,
        ),
    )
    if result.get("cycle_passed") is not True:
        raise Rejected("R8 full trunk cycle did not complete")
    return {"cycle": result, "admission": result["semantic_admission"]}
