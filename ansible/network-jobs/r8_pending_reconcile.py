"""Reconcile a restored legacy R8 pending marker while preserving its custody."""

from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
from typing import Any, cast

import port_exercise_ledger as storage


class Rejected(RuntimeError):
    """The legacy pending operation is not proven restored and source-bound."""


R8_UNAVAILABLE_SOURCE_OPERATION = (
    "e8a5b76622d01f4d1b2d1d1f84eb1065a33c7cce621c17c0492ef30b68fcdc02"
)
R8_UNAVAILABLE_SOURCE_BINDING = (
    "770f6294fe3efba5d8b89bb4599dcd5c794d7a11d70541ee43f44b4e194f2893"
)
R8_ACCEPTED_BASELINE = (
    "01b4a646e764f2874a2310b7e0efd1622f779f230d1d77a41a176b720a327eff"
)
R8_COMPLETED_UNQUALIFIED_OPERATION = (
    "202de73dd443cb761ac9620a9a6c91225af55fd51ae8d5610610d32d00a7bffd"
)
R8_COMPLETED_UNQUALIFIED_SOURCE = (
    "b8464112c1dd8463c27278ab4caf089cc89f92b532486f431d9c36d243fceeec"
)
R8_FAILED_COMMANDS = [
    "configure terminal",
    "interface ethernet 1/2/2",
    "no dual-mode 1",
    "exit",
    "vlan 40",
    "no tagged ethernet 1/2/2",
    "exit",
    "interface ethernet 1/2/2",
    "dual-mode 1",
    "exit",
    "vlan 10",
    "no tagged ethernet 1/2/2",
    "exit",
    "vlan 20",
    "no tagged ethernet 1/2/2",
    "exit",
    "vlan 30",
    "no tagged ethernet 1/2/2",
    "exit",
    "exit",
    "configure terminal",
    "vlan 10",
    "tagged ethernet 1/2/2",
    "exit",
    "vlan 20",
    "tagged ethernet 1/2/2",
    "exit",
    "vlan 30",
    "tagged ethernet 1/2/2",
    "exit",
    "vlan 40",
    "tagged ethernet 1/2/2",
    "exit",
    "exit",
]
R8_FAILED_INVERSE = [
    "configure terminal",
    "vlan 10",
    "tagged ethernet 1/2/2",
    "exit",
    "vlan 20",
    "tagged ethernet 1/2/2",
    "exit",
    "vlan 40",
    "tagged ethernet 1/2/2",
    "exit",
    "exit",
]
R8_CURRENT_OPERATION = (
    "8b6ea9ab3eff43b68104ffe59a1d8fc2a424e60f2a49e09ef10d798df1a1d32b"
)
R8_CURRENT_SOURCE_BINDING = (
    "65a4583f6ea4fcff61f745b9cee0d0613f9669a90669cb4e8245ab5cae433b92"
)
R8_CURRENT_SUPPLEMENTAL_SOURCES = {
    "ansible/network-jobs/active40g_observation.py",
    "ansible/network-jobs/bond_vlan_membership.py",
    "ansible/network-jobs/inspect-port-syntax.py",
    "ansible/network-jobs/r8_pending_restorer.py",
    "ansible/network-jobs/standby_native_membership.py",
}
ROOT = Path(__file__).resolve().parents[2]
R8_CAPTURE_FILES = {
    "argv.json",
    "helper.py",
    "known_hosts",
    "payload.json",
    "receipt.json",
    "remote-controller.py",
    "remote-events.json",
    "serial.py",
    "ssh.stderr",
    "ssh.stdout",
}


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _read(path: Path) -> tuple[dict[str, Any], bytes]:
    raw, _ = storage.read_file(path)
    value = storage.decode(raw)
    if type(value) is not dict:
        raise Rejected("expected private JSON object")
    return value, raw


def release_pending_slot(
    pending_path: Path,
    pending_raw: bytes,
    identity: tuple[int, int],
    custody: Path,
    guarded: Any,
) -> None:
    guarded.guard()
    if storage.read_file(pending_path) != (pending_raw, identity):
        raise Rejected("pending changed before slot release")
    guarded.files.pop(pending_path, None)
    pending_path.unlink()
    try:
        storage.sync_directory(pending_path.parent)
        storage.sync_directory(custody)
        guarded.guard()
    except BaseException:
        if not os.path.lexists(pending_path):
            storage.exclusive_write(pending_path, pending_raw)
        guarded.files[pending_path] = storage.read_file(pending_path)
        raise


def read_private_artifact(
    path: Path, limit: int = 6 * 1024 * 1024
) -> tuple[bytes, tuple[int, int]]:
    before = path.lstat()
    if (
        not stat.S_ISREG(before.st_mode)
        or before.st_uid != os.getuid()
        or stat.S_IMODE(before.st_mode) != 0o600
        or before.st_nlink != 1
        or not 0 <= before.st_size <= limit
    ):
        raise Rejected("private PiKVM capture file custody or size")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        opened = os.fstat(fd)

        def key(info: os.stat_result) -> tuple[int, ...]:
            return (
                info.st_dev,
                info.st_ino,
                info.st_size,
                info.st_mtime_ns,
                info.st_mode,
                info.st_uid,
                info.st_nlink,
            )

        if key(opened) != key(before):
            raise Rejected("PiKVM capture file changed before read")
        raw = os.read(fd, limit + 1)
        after = path.lstat()
        if key(after) != key(before) or len(raw) != before.st_size:
            raise Rejected("PiKVM capture file changed during read")
        return raw, (before.st_dev, before.st_ino)
    finally:
        os.close(fd)


def read_capture_file(path: Path) -> tuple[bytes, tuple[int, int]]:
    return read_private_artifact(path)


def verify_snapshot(snapshot: Path, pending: dict[str, Any]) -> dict[str, Any]:
    manifest_path = snapshot / "manifest.json"
    raw = manifest_path.read_bytes()
    try:
        manifest = json.loads(raw)
    except json.JSONDecodeError as error:
        raise Rejected("legacy source snapshot manifest is invalid") from error
    if type(manifest) is not dict or _canonical(manifest) != raw:
        raise Rejected("legacy source snapshot manifest is not canonical")
    files = manifest.get("manifest")
    if (
        manifest.get("schema") != 1
        or manifest.get("operation_id") != pending.get("operation_id")
        or type(files) is not dict
        or manifest.get("source_binding_sha256")
        != pending.get("binding", {}).get("source_binding_sha256")
    ):
        raise Rejected("legacy source snapshot identity differs")
    hashes: dict[str, str] = {}
    for name, item in files.items():
        if type(name) is not str or type(item) is not dict:
            raise Rejected("legacy source snapshot manifest shape")
        relative = Path(item.get("snapshot_path", ""))
        if relative.is_absolute() or ".." in relative.parts:
            raise Rejected("legacy source snapshot path escaped")
        source = snapshot / relative
        raw = source.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest != item.get("sha256"):
            raise Rejected("legacy source snapshot file changed")
        hashes[name] = digest
    source_binding = hashlib.sha256(_canonical(hashes)).hexdigest()
    if source_binding != manifest["source_binding_sha256"]:
        raise Rejected("legacy source closure digest differs")
    return manifest


def verify_legacy_plan(
    snapshot: Path,
    pending_path: Path,
    preflight_path: Path,
    expected_commands: list[str],
) -> dict[str, Any]:
    tool = snapshot / "ansible/network-jobs/r8_pending_restorer.py"
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            str(tool),
            "--pending",
            str(pending_path),
            "--preflight",
            str(preflight_path),
            "--pin",
            "/dev/null",
            "--plan",
        ],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    try:
        plan = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise Rejected("legacy source plan did not return JSON") from error
    if (
        type(plan) is not dict
        or result.returncode != 0
        or plan.get("status") != "pending_restore_plan_valid"
        or plan.get("operation_id") != _read(pending_path)[0].get("operation_id")
        or plan.get("pending_retained") is not True
        or plan.get("commands") != expected_commands
    ):
        raise Rejected("legacy source plan does not match retained operation")
    return cast(dict[str, Any], plan)


def verify_recovery_chain(
    pending: dict[str, Any],
    pending_raw: bytes,
    runtime: Path,
    previous_digest: str | None = None,
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    paths = [
        runtime / "empty-vlan-recovery-00-observed.json",
        runtime / "empty-vlan-recovery-01-inverse_intent.json",
    ]
    previous = previous_digest or hashlib.sha256(pending_raw).hexdigest()
    receipts = []
    records = []
    for index, path in enumerate(paths):
        record, raw = _read(path)
        phase = "observed" if index == 0 else "inverse_intent"
        if (
            record.get("operation_id") != pending.get("operation_id")
            or record.get("index") != index
            or record.get("phase") != phase
            or record.get("prev_digest") != previous
            or record.get("evidence_sha256")
            != hashlib.sha256(_canonical(record.get("evidence"))).hexdigest()
        ):
            raise Rejected("recovery receipt chain mismatch")
        previous = hashlib.sha256(raw).hexdigest()
        receipts.append({"path": str(path), "sha256": previous})
        records.append(record)
    observed = records[0]["evidence"]
    intent = records[1]["evidence"]
    commands = observed.get("inverse_commands")
    if (
        type(commands) is not list
        or not commands
        or any(type(command) is not str or not command for command in commands)
        or type(observed.get("boundary_index")) is not int
        or type(observed.get("state_sha256")) is not str
        or re.fullmatch(r"[0-9a-f]{64}", observed["state_sha256"]) is None
        or intent.get("index") != 0
        or intent.get("command") != commands[0]
        or intent.get("expected_state_sha256") != observed["state_sha256"]
    ):
        raise Rejected("recovery boundary does not bind its inverse intent")
    return receipts, observed


def verify_phase_prefix(
    pending: dict[str, Any], pending_raw: bytes, runtime: Path, phase_count: int
) -> tuple[list[dict[str, str]], str]:
    paths = sorted(runtime.glob("empty-vlan-phase-*.json"))
    expected = [
        runtime / f"empty-vlan-phase-{index:02d}-command_{index // 2}_"
        f"{'intent' if index % 2 == 0 else 'observed'}.json"
        for index in range(phase_count)
    ]
    if paths != expected:
        raise Rejected("phase prefix file set differs")
    previous = hashlib.sha256(pending_raw).hexdigest()
    receipts = []
    for index, path in enumerate(paths):
        record, raw = _read(path)
        phase = f"command_{index // 2}_{'intent' if index % 2 == 0 else 'observed'}"
        if (
            record.get("operation_id") != pending.get("operation_id")
            or record.get("index") != index
            or record.get("phase") != phase
            or record.get("prev_digest") != previous
            or record.get("evidence_sha256")
            != hashlib.sha256(_canonical(record.get("evidence"))).hexdigest()
        ):
            raise Rejected("phase prefix receipt chain mismatch")
        previous = hashlib.sha256(raw).hexdigest()
        receipts.append({"path": str(path), "sha256": previous})
    return receipts, previous


def _verify_rejected_guest_proof(
    proof: Any,
    payload: dict[str, Any],
    pending: dict[str, Any],
    *,
    field: str,
    boundary: int,
    allow_unreconstructable_boundary: bool = False,
) -> None:
    if field == "held_guest_proof":
        boundary_observation = payload.get("held_boundary_observation")
        expected_boundary = (
            hashlib.sha256(_canonical(boundary_observation)).hexdigest()
            if type(boundary_observation) is dict
            else None
        )
        if expected_boundary is None and allow_unreconstructable_boundary:
            expected_boundary = proof.get("boundary_observation_sha256")
    else:
        expected_boundary = hashlib.sha256(
            _canonical({key: value for key, value in payload.items() if key != field})
        ).hexdigest()

    if (
        type(proof) is not dict
        or set(proof)
        != {
            "status",
            "operation_id",
            "forward_count",
            "boundary_observation_sha256",
            "source_binding_sha256",
            "reason",
        }
        or proof.get("status") != "rejected"
        or proof.get("operation_id") != pending.get("operation_id")
        or proof.get("forward_count") != boundary
        or type(proof.get("boundary_observation_sha256")) is not str
        or re.fullmatch(r"[0-9a-f]{64}", proof["boundary_observation_sha256"]) is None
        or proof.get("source_binding_sha256")
        != pending.get("binding", {}).get("source_binding_sha256")
        or proof.get("boundary_observation_sha256") != expected_boundary
        or type(proof.get("reason")) is not str
        or not proof["reason"]
    ):
        raise Rejected("completed unqualified guest-proof rejection differs")


def verify_completed_unqualified_cycle(
    pending: dict[str, Any],
    pending_raw: bytes,
    runtime: Path,
    source_manifest: dict[str, str],
    allow_unreconstructable_boundary: bool = False,
) -> tuple[list[dict[str, str]], dict[str, Any], tuple[str, ...], dict[str, str]]:
    """Verify a completed R8 cycle that failed guest proof without admitting it."""
    import empty_vlan_cycle as cycle
    import exercise_observation as exercise
    import native_trunk_plan as trunk_plan
    import port_description as evidence
    import r8_probe_admission as admission

    profile = cycle.CycleProfile.R8_FULL_TRUNK
    unsigned = {key: value for key, value in pending.items() if key != "operation_id"}
    binding = pending.get("binding")
    if (
        pending.get("schema") != 4
        or pending.get("operation") != profile.value
        or pending.get("host") != "192.168.0.251"
        or pending.get("fingerprint")
        != "SHA256:UJulVmfAMmHcUctvJrlGzBZR7I7uN8/TWNeJIs25yks"
        or pending.get("writer") != "caller_supplied_transport"
        or storage.digest(storage.canonical(unsigned)) != pending.get("operation_id")
        or type(binding) is not dict
        or set(binding) != set(cycle.BINDING_KEYS)
        or any(
            type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None
            for value in binding.values()
        )
        or binding.get("source_binding_sha256")
        != hashlib.sha256(_canonical(source_manifest)).hexdigest()
        or set(source_manifest) != set(cycle.SOURCE_MANIFEST)
        or binding.get("baseline_running_sha256") != R8_ACCEPTED_BASELINE
        or binding.get("baseline_startup_sha256") != R8_ACCEPTED_BASELINE
        or pending.get("commands") != list(profile.commands)
        or runtime != Path(pending.get("runtime", ""))
    ):
        raise Rejected("completed unqualified R8 operation identity differs")

    expected_phases = [
        runtime / f"empty-vlan-phase-{index:02d}-{phase}.json"
        for index, phase in enumerate(profile.phases)
    ]
    paths = sorted(runtime.glob("empty-vlan-phase-*.json"))
    receipt_path = runtime / "empty-vlan-complete.json"
    entries = list(runtime.iterdir())
    if (
        paths != expected_phases
        or len(paths) != len(profile.phases)
        or {path.name for path in entries}
        != {path.name for path in expected_phases}
        | {receipt_path.name, "audit", "root"}
        or not (runtime / "audit").is_dir()
        or not (runtime / "root").is_dir()
    ):
        raise Rejected("completed unqualified R8 runtime file set differs")

    receipt_raw, _ = read_private_artifact(receipt_path)
    try:
        receipt = json.loads(receipt_raw)
    except json.JSONDecodeError as error:
        raise Rejected(
            "completed unqualified R8 completion receipt malformed"
        ) from error
    if (
        type(receipt) is not dict
        or storage.canonical(receipt) != receipt_raw
        or receipt.get("status") != "complete"
        or receipt.get("operation_id") != pending["operation_id"]
        or receipt.get("operation") != pending
        or receipt.get("phase_count") != len(profile.phases)
    ):
        raise Rejected("completed unqualified R8 completion receipt differs")

    phase_receipts: list[dict[str, str]] = []
    records: list[dict[str, Any]] = []
    previous = hashlib.sha256(pending_raw).hexdigest()
    for index, (path, expected_phase) in enumerate(
        zip(paths, profile.phases, strict=True)
    ):
        raw, _ = read_private_artifact(path)
        try:
            record = json.loads(raw)
        except json.JSONDecodeError as error:
            raise Rejected("completed unqualified R8 phase malformed") from error
        payload = record.get("evidence") if type(record) is dict else None
        if (
            type(record) is not dict
            or storage.canonical(record) != raw
            or record.get("operation_id") != pending["operation_id"]
            or record.get("index") != index
            or record.get("phase") != expected_phase
            or record.get("prev_digest") != previous
            or type(payload) is not dict
            or record.get("evidence_sha256")
            != hashlib.sha256(_canonical(payload)).hexdigest()
        ):
            raise Rejected("completed unqualified R8 phase chain mismatch")
        previous = hashlib.sha256(raw).hexdigest()
        phase_receipts.append({"path": str(path), "sha256": previous})
        records.append(record)

    first = records[0]["evidence"]
    baseline = evidence.evidence_config(first, exercise.PORT)[0]
    if evidence.configuration_hash(baseline) != R8_ACCEPTED_BASELINE:
        raise Rejected("completed unqualified R8 baseline differs")
    vlan_baseline = first.get("r8_vlan_baseline_tables")
    if type(vlan_baseline) is not dict:
        raise Rejected("completed unqualified R8 VLAN baseline missing")

    for index, (record, phase) in enumerate(zip(records, profile.phases, strict=True)):
        payload = record["evidence"]
        if phase.endswith("_intent"):
            position = index // 2
            admission._expected_state(
                payload, baseline, position, profile, vlan_baseline
            )
            if position == len(trunk_plan.R8_FULL_FORWARD):
                _verify_rejected_guest_proof(
                    payload.get("held_guest_proof"),
                    payload,
                    pending,
                    field="held_guest_proof",
                    boundary=len(trunk_plan.R8_FULL_FORWARD),
                    allow_unreconstructable_boundary=allow_unreconstructable_boundary,
                )
        elif phase == "final_observed":
            admission._expected_state(
                payload, baseline, len(profile.commands), profile, vlan_baseline
            )
            _verify_rejected_guest_proof(
                payload.get("restored_guest_proof"),
                payload,
                pending,
                field="restored_guest_proof",
                boundary=len(trunk_plan.R8_FULL_FORWARD),
            )
        else:
            position = index // 2 + 1
            admission._expected_state(
                payload.get("observation"), baseline, position, profile, vlan_baseline
            )
            ack = payload.get("acknowledgement")
            if (
                type(ack) is not dict
                or set(ack) != {"response_body", "response_sha256"}
                or type(ack["response_body"]) is not str
                or ack["response_sha256"]
                != hashlib.sha256(ack["response_body"].encode()).hexdigest()
                or payload.get("acknowledgement_parser_qualified") is not False
                or record.get("acknowledgement") != ack
                or record.get("acknowledgement_parser_qualified") is not False
            ):
                raise Rejected("completed unqualified R8 acknowledgement mismatch")

    final = records[-1]
    if (
        receipt.get("final_digest") != previous
        or receipt.get("final_observation") != final["evidence"]
        or final["evidence"].get("restored_guest_proof", {}).get("status") != "rejected"
    ):
        raise Rejected("completed unqualified R8 final receipt mismatch")
    return phase_receipts, receipt, baseline, vlan_baseline


def verify_source_archive_manifest(
    archive: Path,
    pending: dict[str, Any],
    pending_raw: bytes,
    expected_sources: set[str],
) -> tuple[dict[str, str], dict[str, Any]]:
    archive = archive.resolve(strict=True)
    storage.private_directory(archive)
    manifest_raw, _ = read_private_artifact(archive / "archive-manifest.json")
    try:
        manifest = json.loads(manifest_raw)
    except json.JSONDecodeError as error:
        raise Rejected("completed R8 archive manifest malformed") from error
    if type(manifest) is not dict or storage.canonical(manifest) != manifest_raw:
        raise Rejected("completed R8 archive manifest is not canonical")
    source_manifest = manifest.get("source_manifest")
    if (
        manifest.get("schema") != 1
        or manifest.get("operation_id") != pending.get("operation_id")
        or manifest.get("pending_sha256") != hashlib.sha256(pending_raw).hexdigest()
        or manifest.get("source_binding_sha256")
        != pending.get("binding", {}).get("source_binding_sha256")
        or type(source_manifest) is not dict
        or set(source_manifest) != expected_sources
        or any(
            type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None
            for value in source_manifest.values()
        )
        or hashlib.sha256(_canonical(source_manifest)).hexdigest()
        != manifest.get("source_binding_sha256")
    ):
        raise Rejected("completed R8 archive source binding differs")

    source_dir = archive / "source"
    storage.private_directory(source_dir)
    source_paths = list(source_dir.iterdir())
    if {path.name for path in source_paths} != expected_sources:
        raise Rejected("completed R8 archived source file set differs")
    for name, digest in source_manifest.items():
        if (
            hashlib.sha256(read_private_artifact(source_dir / name)[0]).hexdigest()
            != digest
        ):
            raise Rejected("completed R8 archived source changed")
    archived_pending, _ = read_private_artifact(archive / "pending/pending.json")
    if archived_pending != pending_raw:
        raise Rejected("completed R8 archived pending differs")
    return source_manifest, manifest


def verify_completed_cycle_archive(
    archive: Path,
    pending: dict[str, Any],
    pending_raw: bytes,
    runtime: Path,
) -> tuple[list[dict[str, str]], dict[str, Any], tuple[str, ...], dict[str, str]]:
    """Verify an immutable private archive before reconciling a failed cycle."""
    import empty_vlan_cycle as cycle

    source_manifest, manifest = verify_source_archive_manifest(
        archive, pending, pending_raw, set(cycle.SOURCE_MANIFEST)
    )
    runtime_files = manifest.get("runtime_files")
    if type(runtime_files) is not dict:
        raise Rejected("completed R8 archive manifest binding differs")

    archived_runtime = archive / "runtime"
    storage.private_directory(archived_runtime)
    expected_paths = set(runtime_files)
    for relative, digest in runtime_files.items():
        relative_path = Path(relative)
        if (
            relative_path.is_absolute()
            or ".." in relative_path.parts
            or type(digest) is not str
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None
        ):
            raise Rejected("completed R8 archive runtime manifest malformed")
        archived = read_private_artifact(archived_runtime / relative_path)[0]
        current = read_private_artifact(runtime / relative_path)[0]
        if hashlib.sha256(archived).hexdigest() != digest or current != archived:
            raise Rejected("completed R8 archived runtime differs")
    for root in (archived_runtime, runtime):
        actual = {
            path.relative_to(root).as_posix()
            for path in root.rglob("*")
            if path.is_file()
        }
        if actual != expected_paths:
            raise Rejected("completed R8 runtime file set differs")

    return verify_completed_unqualified_cycle(
        pending,
        pending_raw,
        runtime,
        source_manifest,
        allow_unreconstructable_boundary=(
            pending.get("operation_id") == R8_COMPLETED_UNQUALIFIED_OPERATION
            and pending.get("binding", {}).get("source_binding_sha256")
            == R8_COMPLETED_UNQUALIFIED_SOURCE
        ),
    )


def verify_completed_cycle_unchanged(
    archive: Path,
    pending: dict[str, Any],
    pending_raw: bytes,
    runtime: Path,
    expected_phase_chain: list[dict[str, str]],
    expected_completion: dict[str, Any],
) -> None:
    phase_chain, completion, _, _ = verify_completed_cycle_archive(
        archive, pending, pending_raw, runtime
    )
    if phase_chain != expected_phase_chain or completion != expected_completion:
        raise Rejected("completed R8 archive changed before pending release")


def verify_completed_cycle_readback(
    pending: dict[str, Any],
    readback_path: Path,
    baseline: tuple[str, ...],
    vlan_baseline: dict[str, str],
) -> tuple[dict[str, Any], bytes, dict[str, Any], bytes]:
    import empty_vlan_cycle as cycle
    import exercise_observation as exercise
    import port_description as evidence
    import r8_current_observation
    import r8_probe_admission as admission

    readback_path = readback_path.resolve(strict=True)
    if readback_path.name != "readback.json":
        raise Rejected("completed R8 read-back path differs")
    readback_raw, _ = read_private_artifact(readback_path.resolve(strict=True))
    observation_path: Path
    try:
        readback = json.loads(readback_raw)
        if type(readback) is not dict or storage.canonical(readback) != readback_raw:
            raise Rejected("completed R8 read-back is not canonical")
        observation_path = Path(readback["observation_path"]).resolve(strict=True)
        if (
            observation_path.parent != readback_path.parent
            or observation_path.name != "observation.json"
        ):
            raise Rejected("completed R8 observation path differs")
        storage.private_directory(observation_path.parent)
        observation_raw, _ = read_private_artifact(observation_path)
        observation = json.loads(observation_raw)
    except (KeyError, OSError, json.JSONDecodeError) as error:
        raise Rejected("completed R8 read-back artifact malformed") from error

    observed_at = readback.get("observed_at")
    try:
        observed = datetime.fromisoformat(observed_at)
        completed = datetime.fromisoformat(readback.get("completed_at"))
    except (TypeError, ValueError) as error:
        raise Rejected("completed R8 read-back timestamp malformed") from error
    age = datetime.now(timezone.utc) - observed
    duration = completed - observed
    if (
        observed.tzinfo is None
        or completed.tzinfo is None
        or age.total_seconds() < 0
        or age.total_seconds() > 1800
        or duration.total_seconds() < 0
        or duration.total_seconds() > 1800
    ):
        raise Rejected("completed R8 read-back is not fresh")
    r8_current_observation.unchanged_sources()
    if (
        readback.get("schema") != 1
        or readback.get("operation_id") != pending.get("operation_id")
        or readback.get("source_binding_sha256")
        != pending.get("binding", {}).get("source_binding_sha256")
        or readback.get("host") != "192.168.0.251"
        or readback.get("identity") != "homelab_audit"
        or readback.get("accepted_host_key_fingerprint") != pending.get("fingerprint")
        or readback.get("configuration_write_attempted") is not False
        or readback.get("source_sha256") != exercise.collector.SOURCE_SHA256
        or readback.get("observation_source_sha256")
        != r8_current_observation.SOURCE_SHA256
        or readback.get("observation_sha256")
        != hashlib.sha256(observation_raw).hexdigest()
        or type(observation) is not dict
        or storage.canonical(observation) != observation_raw
        or observation.get("observed_at") != observed_at
        or observation.get("completed_at") != readback.get("completed_at")
        or observation.get("host") != readback.get("host")
        or observation.get("identity") != readback.get("identity")
        or observation.get("accepted_host_key_fingerprint")
        != readback.get("accepted_host_key_fingerprint")
        or observation.get("source_sha256") != readback.get("source_sha256")
        or observation.get("observation_source_sha256")
        != readback.get("observation_source_sha256")
    ):
        raise Rejected("completed R8 read-back source or operation binding differs")
    running, startup = evidence.evidence_config(observation, exercise.PORT)
    if (
        list(running) != readback.get("running_lines")
        or list(startup) != readback.get("startup_lines")
        or evidence.configuration_hash(running) != readback.get("running_sha256")
        or evidence.configuration_hash(startup) != readback.get("startup_sha256")
        or evidence.configuration_hash(running)
        != pending.get("binding", {}).get("baseline_running_sha256")
        or evidence.configuration_hash(startup)
        != pending.get("binding", {}).get("baseline_startup_sha256")
    ):
        raise Rejected("completed R8 running/startup read-back differs")
    observation["r8_vlan_baseline_tables"] = vlan_baseline
    admission._expected_state(
        observation,
        baseline,
        len(cycle.CycleProfile.R8_FULL_TRUNK.commands),
        cycle.CycleProfile.R8_FULL_TRUNK,
        vlan_baseline,
    )
    return readback, readback_raw, observation, observation_raw


def reconcile_completed_unqualified_archive(
    *,
    pending_path: Path,
    archive: Path,
    preflight_path: Path,
    readback_path: Path,
) -> dict[str, Any]:
    """Archive an exactly restored failed qualification without admitting it."""
    pending_path = pending_path.resolve(strict=True)
    archive = archive.resolve(strict=True)
    preflight_path = preflight_path.resolve(strict=True)
    readback_path = readback_path.resolve(strict=True)
    if (
        pending_path.parent.name != "brocade-persistence-ledger"
        or archive.name != R8_COMPLETED_UNQUALIFIED_OPERATION
        or pending_path.parent.parent.resolve() == ROOT
    ):
        raise Rejected("canonical completed R8 reconciliation paths required")
    parent = pending_path.parent.parent
    runtime_lock = parent / "completed-unqualified-reconciliation-runtime"
    runtime_lock.mkdir(mode=0o700, exist_ok=True)
    storage.private_directory(runtime_lock)
    with storage.locked_exercise(parent, runtime_lock) as guarded:
        pending, pending_raw = _read(pending_path)
        pending_identity = storage.read_file(pending_path)[1]
        binding = pending.get("binding")
        preflight_raw, _ = read_private_artifact(preflight_path)
        try:
            preflight = json.loads(preflight_raw)
        except json.JSONDecodeError as error:
            raise Rejected("completed R8 original preflight malformed") from error
        if (
            hashlib.sha256(preflight_raw).hexdigest()
            != binding.get("native_recovery_proof_sha256")
            or preflight.get("schema") != 2
            or preflight.get("configuration_write_attempted") is not False
            or preflight.get("independent_rescue_currently_verified") is not True
        ):
            raise Rejected("completed R8 original preflight binding differs")

        phase_chain, completion, baseline, vlan_baseline = (
            verify_completed_cycle_archive(
                archive, pending, pending_raw, Path(pending["runtime"])
            )
        )
        readback, readback_raw, observation, observation_raw = (
            verify_completed_cycle_readback(
                pending, readback_path, baseline, vlan_baseline
            )
        )
        operation_runtime = Path(pending["runtime"])
        guarded.files[pending_path] = (pending_raw, pending_identity)
        guarded.directories[operation_runtime] = storage.private_directory(
            operation_runtime
        )
        for path in (preflight_path, readback_path, Path(readback["observation_path"])):
            guarded.files[path] = read_private_artifact(path)
        for directory in (
            archive,
            archive / "source",
            archive / "pending",
            archive / "runtime",
            *[path for path in (archive / "runtime").rglob("*") if path.is_dir()],
            *[path for path in operation_runtime.rglob("*") if path.is_dir()],
        ):
            guarded.directories[directory] = storage.private_directory(directory)
        guarded.guard()

        evidence_dir = archive / "reconciliation-evidence"
        if not os.path.lexists(evidence_dir):
            evidence_dir.mkdir(mode=0o700)
            storage.sync_directory(archive)
        guarded.directories[evidence_dir] = storage.private_directory(evidence_dir)
        storage.private_directory(evidence_dir)
        expected_evidence_names = {
            "preflight.json",
            "readback.json",
            "observation.json",
        }
        if any(
            path.is_symlink() or not path.is_file() for path in evidence_dir.iterdir()
        ):
            raise Rejected("completed R8 reconciliation evidence entries differ")
        if {path.name for path in evidence_dir.iterdir()} - expected_evidence_names:
            raise Rejected("completed R8 reconciliation evidence contains extra files")
        evidence_files = {
            "preflight.json": preflight_raw,
            "readback.json": readback_raw,
            "observation.json": observation_raw,
        }
        for name, raw in evidence_files.items():
            path = evidence_dir / name
            if os.path.lexists(path):
                if read_private_artifact(path)[0] != raw:
                    raise Rejected("completed R8 reconciliation evidence differs")
            else:
                storage.exclusive_write(path, raw)
        custody_hashes = {
            name: hashlib.sha256(raw).hexdigest()
            for name, raw in evidence_files.items()
        }
        receipt_path = archive / "reconciliation.json"
        receipt = {
            "schema": 1,
            "status": "restored_unqualified_pending_custody_archived",
            "operation_id": pending["operation_id"],
            "source_binding_sha256": binding["source_binding_sha256"],
            "source_provenance_verified": True,
            "source_closure_complete": True,
            "restoration_verified": True,
            "restoration_evidence": "69 chained phase records plus fresh independent running/startup and VLAN read-back",
            "completion_status": completion.get("status"),
            "guest_proof_boundary_verified": False,
            "qualification_admitted": False,
            "completion_receipt_sha256": hashlib.sha256(
                storage.read_file(operation_runtime / "empty-vlan-complete.json")[0]
            ).hexdigest(),
            "phase_chain": phase_chain,
            "final_readback": {
                "observed_at": readback["observed_at"],
                "running_sha256": readback["running_sha256"],
                "startup_sha256": readback["startup_sha256"],
                "readback_sha256": hashlib.sha256(readback_raw).hexdigest(),
                "observation_sha256": hashlib.sha256(observation_raw).hexdigest(),
            },
            "custody_evidence_sha256": custody_hashes,
            "reconciled_at": datetime.now(timezone.utc).isoformat(),
        }
        receipt_raw = storage.canonical(receipt)
        if os.path.lexists(receipt_path):
            existing_raw, _ = read_private_artifact(receipt_path)
            try:
                existing = json.loads(existing_raw)
            except json.JSONDecodeError as error:
                raise Rejected(
                    "completed R8 reconciliation receipt malformed"
                ) from error
            if (
                type(existing) is not dict
                or storage.canonical(existing) != existing_raw
                or {
                    key: value
                    for key, value in existing.items()
                    if key != "reconciled_at"
                }
                != {
                    key: value
                    for key, value in receipt.items()
                    if key != "reconciled_at"
                }
            ):
                raise Rejected("completed R8 reconciliation receipt already differs")
            receipt = existing
            receipt_raw = existing_raw
        else:
            storage.exclusive_write(receipt_path, receipt_raw)
        storage.sync_directory(evidence_dir)
        storage.sync_directory(archive)
        expected_archive_entries = {
            "archive-manifest.json",
            "pending",
            "runtime",
            "source",
            "reconciliation-evidence",
            "reconciliation.json",
        }
        if {path.name for path in archive.iterdir()} != expected_archive_entries:
            raise Rejected("completed R8 custody archive entries differ")

        guarded.guard()
        if storage.read_file(pending_path) != (pending_raw, pending_identity):
            raise Rejected("completed R8 pending changed before release")
        verify_completed_cycle_unchanged(
            archive,
            pending,
            pending_raw,
            operation_runtime,
            phase_chain,
            completion,
        )
        verify_completed_cycle_readback(pending, readback_path, baseline, vlan_baseline)
        for name, raw in evidence_files.items():
            if read_private_artifact(evidence_dir / name)[0] != raw:
                raise Rejected("completed R8 custody evidence changed before release")
        if read_private_artifact(receipt_path)[0] != receipt_raw:
            raise Rejected("completed R8 reconciliation receipt changed before release")
        release_pending_slot(
            pending_path, pending_raw, pending_identity, archive, guarded
        )
        return {**receipt, "pending_slot_released": True, "custody_path": str(archive)}


def verify_current_incomplete_operation(
    pending: dict[str, Any], pending_raw: bytes, runtime: Path, parent: Path
) -> tuple[list[dict[str, str]], list[dict[str, str]], dict[str, Any]]:
    unsigned = {key: value for key, value in pending.items() if key != "operation_id"}
    binding = pending.get("binding")
    if (
        pending.get("schema") != 4
        or pending.get("operation") != "r8_full_trunk_cycle"
        or pending.get("host") != "192.168.0.251"
        or pending.get("fingerprint")
        != "SHA256:UJulVmfAMmHcUctvJrlGzBZR7I7uN8/TWNeJIs25yks"
        or pending.get("writer") != "caller_supplied_transport"
        or pending.get("operation_id") != R8_CURRENT_OPERATION
        or storage.digest(storage.canonical(unsigned)) != R8_CURRENT_OPERATION
        or type(binding) is not dict
        or binding.get("source_binding_sha256") != R8_CURRENT_SOURCE_BINDING
        or binding.get("baseline_running_sha256") != R8_ACCEPTED_BASELINE
        or binding.get("baseline_startup_sha256") != R8_ACCEPTED_BASELINE
        or runtime != Path(pending.get("runtime", ""))
        or runtime.parent != parent
    ):
        raise Rejected(
            "operation is outside the current incomplete-source R8 allowlist"
        )
    phases, previous = verify_phase_prefix(pending, pending_raw, runtime, 29)
    recovery, observed = verify_recovery_chain(pending, pending_raw, runtime, previous)
    if observed.get("boundary_index") != 15:
        raise Rejected("current R8 failure boundary differs")
    return phases, recovery, observed


def verify_restore_chain(
    pending: dict[str, Any], runtime: Path, restore_dir: Path
) -> dict[str, Any]:
    operation_id = pending["operation_id"]
    inverse_path = runtime / "empty-vlan-recovery-01-inverse_intent.json"
    inverse, inverse_raw = _read(inverse_path)
    if inverse.get("phase") != "inverse_intent":
        raise Rejected("original inverse intent is missing")
    previous = hashlib.sha256(inverse_raw).hexdigest()
    paths = sorted(restore_dir.glob("r8-restore-*-*.json"))
    if not paths:
        raise Rejected("complete retained restore chain required")
    records = []
    final: dict[str, Any] | None = None
    for index, candidate in enumerate(paths, start=2):
        record, raw = _read(candidate)
        if (
            record.get("operation_id") != operation_id
            or record.get("index") != index
            or record.get("prev_digest") != previous
            or record.get("evidence_sha256")
            != hashlib.sha256(_canonical(record.get("evidence"))).hexdigest()
        ):
            raise Rejected("restore receipt chain mismatch")
        previous = hashlib.sha256(raw).hexdigest()
        records.append({"path": str(candidate), "sha256": previous})
        final = record
    assert final is not None
    evidence = final.get("evidence")
    binding = pending["binding"]
    if (
        final.get("phase") != "restored"
        or final.get("index") != len(paths) + 1
        or type(evidence) is not dict
        or evidence.get("pending_retained") is not True
        or evidence.get("running_sha256") != binding["baseline_running_sha256"]
        or evidence.get("startup_sha256") != binding["baseline_startup_sha256"]
    ):
        raise Rejected("restore receipt does not prove exact retained recovery")
    return {"records": records, "final_sha256": previous}


def verify_readback(snapshot: Path, readback_path: Path) -> dict[str, str]:
    readback, _ = _read(readback_path)
    observed_at = readback.get("observed_at")
    if type(observed_at) is not str:
        raise Rejected("independent R8 read-back timestamp required")
    age = datetime.now(timezone.utc) - datetime.fromisoformat(observed_at)
    if age.total_seconds() < 0 or age.total_seconds() > 1800:
        raise Rejected("independent R8 read-back is older than 30 minutes")
    code = (
        "import json,sys; import port_description as p; "
        "import native_trunk_plan as n; "
        "d=json.load(open(sys.argv[1])); "
        "a,b=p.evidence_config(d,'1/1/47'); "
        "assert a==b and p.configuration_hash(a)==n.R8_BASELINE_SHA256; "
        "print(json.dumps({'running_sha256':p.configuration_hash(a),"
        "'startup_sha256':p.configuration_hash(b)}))"
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        (
            str(snapshot / "ansible/network-jobs"),
            str(snapshot / "ansible/network-audit"),
        )
    )
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        [sys.executable, "-c", code, str(readback_path)],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
        env=env,
    )
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise Rejected("independent R8 read-back did not validate") from error
    if result.returncode != 0 or type(value) is not dict:
        raise Rejected("independent R8 read-back did not match baseline")
    return cast(dict[str, str], value)


def verify_unavailable_source_operation(
    pending: dict[str, Any], pending_raw: bytes, runtime: Path, parent: Path
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Verify the one restored R8 failure whose original source snapshot is absent."""
    unsigned = {key: value for key, value in pending.items() if key != "operation_id"}
    binding = pending.get("binding")
    if (
        pending.get("schema") != 4
        or pending.get("operation") != "r8_full_trunk_cycle"
        or pending.get("host") != "192.168.0.251"
        or pending.get("fingerprint")
        != "SHA256:UJulVmfAMmHcUctvJrlGzBZR7I7uN8/TWNeJIs25yks"
        or pending.get("writer") != "caller_supplied_transport"
        or pending.get("operation_id") != R8_UNAVAILABLE_SOURCE_OPERATION
        or storage.digest(storage.canonical(unsigned))
        != R8_UNAVAILABLE_SOURCE_OPERATION
        or type(binding) is not dict
        or set(binding)
        != {
            "baseline_running_sha256",
            "baseline_startup_sha256",
            "execution_environment_sha256",
            "native_recovery_proof_sha256",
            "preview_sha256",
            "source_binding_sha256",
        }
        or any(
            type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None
            for value in binding.values()
        )
        or binding.get("source_binding_sha256") != R8_UNAVAILABLE_SOURCE_BINDING
        or binding.get("baseline_running_sha256") != R8_ACCEPTED_BASELINE
        or binding.get("baseline_startup_sha256") != R8_ACCEPTED_BASELINE
        or pending.get("commands") != R8_FAILED_COMMANDS
        or runtime != Path(pending.get("runtime", ""))
        or runtime.parent != parent
    ):
        raise Rejected("operation is outside the source-unavailable R8 allowlist")
    if os.path.lexists(parent / "source-snapshots" / R8_UNAVAILABLE_SOURCE_OPERATION):
        raise Rejected(
            "source snapshot exists; the provenance-unavailable path is forbidden"
        )
    phases = sorted(runtime.glob("empty-vlan-phase-*.json"))
    expected_phases = [
        runtime
        / f"empty-vlan-phase-{i:02d}-command_{i // 2}_{'intent' if i % 2 == 0 else 'observed'}.json"
        for i in range(35)
    ]
    recoveries = sorted(runtime.glob("empty-vlan-recovery-*.json"))
    expected_recoveries = [
        runtime / "empty-vlan-recovery-00-observed.json",
        runtime / "empty-vlan-recovery-01-inverse_intent.json",
    ]
    if phases != expected_phases or recoveries != expected_recoveries:
        raise Rejected("source-unavailable R8 phase or recovery file set differs")
    previous = hashlib.sha256(pending_raw).hexdigest()
    phase_receipts = []
    for index, path in enumerate(phases):
        record, raw = _read(path)
        phase = f"command_{index // 2}_{'intent' if index % 2 == 0 else 'observed'}"
        if (
            record.get("operation_id") != R8_UNAVAILABLE_SOURCE_OPERATION
            or record.get("index") != index
            or record.get("phase") != phase
            or record.get("prev_digest") != previous
            or record.get("evidence_sha256")
            != hashlib.sha256(_canonical(record.get("evidence"))).hexdigest()
        ):
            raise Rejected("source-unavailable R8 phase chain mismatch")
        previous = hashlib.sha256(raw).hexdigest()
        phase_receipts.append({"path": str(path), "sha256": previous})
    recovery_receipts = []
    records = []
    for index, path in enumerate(recoveries):
        record, raw = _read(path)
        phase = "observed" if index == 0 else "inverse_intent"
        if (
            record.get("operation_id") != R8_UNAVAILABLE_SOURCE_OPERATION
            or record.get("index") != index
            or record.get("phase") != phase
            or record.get("prev_digest") != previous
            or record.get("evidence_sha256")
            != hashlib.sha256(_canonical(record.get("evidence"))).hexdigest()
        ):
            raise Rejected("source-unavailable R8 recovery chain mismatch")
        previous = hashlib.sha256(raw).hexdigest()
        records.append(record)
        recovery_receipts.append({"path": str(path), "sha256": previous})
    recovery = records[0]["evidence"]
    intent = records[1]["evidence"]
    if (
        recovery.get("boundary_index") != 15
        or recovery.get("forward_failure") != "Rejected"
        or recovery.get("inverse_commands") != R8_FAILED_INVERSE
        or intent.get("index") != 0
        or intent.get("command") != "configure terminal"
        or intent.get("expected_state_sha256") != recovery.get("state_sha256")
    ):
        raise Rejected("source-unavailable R8 recovery boundary differs")
    return phase_receipts, recovery_receipts


def verify_unavailable_source_readback(
    pending: dict[str, Any], readback_path: Path
) -> dict[str, str]:
    """Verify a fresh, independently captured full running/startup configuration."""
    readback, _ = _read(readback_path)
    observed_at = readback.get("observed_at")
    if type(observed_at) is not str:
        raise Rejected("source-unavailable R8 read-back timestamp required")
    age = datetime.now(timezone.utc) - datetime.fromisoformat(observed_at)
    if age.total_seconds() < 0 or age.total_seconds() > 1800:
        raise Rejected("source-unavailable R8 read-back is older than 30 minutes")
    if (
        readback.get("schema") != 1
        or readback.get("operation_id") != R8_UNAVAILABLE_SOURCE_OPERATION
        or readback.get("source_provenance") != "source_binding_unavailable"
        or readback.get("capture_mode") != "configurations"
        or readback.get("configuration_write_admitted") is not False
        or readback.get("configurations_complete") is not True
        or not all(
            isinstance(readback.get(key), str)
            and re.fullmatch(r"[0-9a-f]{64}", readback[key])
            for key in ("capture_receipt_sha256", "capture_events_sha256")
        )
    ):
        raise Rejected("source-unavailable R8 read-back receipt differs")
    lines: dict[str, list[str]] = {}
    for name in ("running", "startup"):
        value = readback.get(f"{name}_lines")
        if (
            type(value) is not list
            or not value
            or any(type(line) is not str or not line.isascii() for line in value)
            or value[-1] != "end"
            or "end" in value[:-1]
        ):
            raise Rejected("source-unavailable R8 canonical configuration differs")
        lines[name] = value
        actual = hashlib.sha256(("\n".join(value) + "\n").encode("ascii")).hexdigest()
        if readback.get(f"{name}_sha256") != actual:
            raise Rejected("source-unavailable R8 configuration hash differs")
    binding = pending["binding"]
    if (
        readback["running_sha256"] != R8_ACCEPTED_BASELINE
        or readback["startup_sha256"] != R8_ACCEPTED_BASELINE
        or readback["running_sha256"] != binding["baseline_running_sha256"]
        or readback["startup_sha256"] != binding["baseline_startup_sha256"]
        or lines["running"] != lines["startup"]
    ):
        raise Rejected("source-unavailable R8 read-back differs from accepted baseline")
    return {
        "observed_at": observed_at,
        "running_sha256": readback["running_sha256"],
        "startup_sha256": readback["startup_sha256"],
        "capture_receipt_sha256": readback["capture_receipt_sha256"],
        "capture_events_sha256": readback["capture_events_sha256"],
    }


def verify_unavailable_source_capture(
    capture_dir: Path, readback_path: Path, readback: dict[str, str]
) -> dict[str, str]:
    capture_dir = capture_dir.resolve(strict=True)
    storage.private_directory(capture_dir)
    paths = sorted(capture_dir.iterdir())
    if {path.name for path in paths} != R8_CAPTURE_FILES:
        raise Rejected("source-unavailable R8 PiKVM capture file set differs")
    captured: dict[str, bytes] = {}
    for path in paths:
        raw, _ = read_capture_file(path)
        captured[path.name] = raw
    receipt = json.loads(captured["receipt.json"])
    if (
        receipt.get("mode") != "configurations"
        or receipt.get("operation_complete") is not True
        or receipt.get("source_stage_removed") is not True
        or receipt.get("restore_verified") is not False
        or receipt.get("ssh_returncode") != 0
        or receipt.get("runner_terminal") is not True
        or receipt.get("runner_exit_status") != 0
        or receipt.get("pending_retained") is not False
        or hashlib.sha256(captured["receipt.json"]).hexdigest()
        != readback["capture_receipt_sha256"]
        or hashlib.sha256(captured["remote-events.json"]).hexdigest()
        != readback["capture_events_sha256"]
    ):
        raise Rejected("source-unavailable R8 PiKVM receipt differs")
    spec = importlib.util.spec_from_file_location(
        "r8_pikvm_invocation_verifier",
        ROOT / "network/config-backup-preflight/invoke-pikvm-screen-capture.py",
    )
    if spec is None or spec.loader is None:
        raise Rejected("source-unavailable R8 PiKVM verifier unavailable")
    verifier = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = verifier
    spec.loader.exec_module(verifier)
    events = json.loads(captured["remote-events.json"])
    verifier.validate_events(events, "configurations")
    runtime = next(
        item["runtime"]
        for item in events
        if item.get("event") == "runtime-collected"
        and item.get("mode") == "configurations"
    )
    evidence_record = next(
        item for item in runtime["files"] if item["path"].endswith("/evidence.json")
    )
    evidence = json.loads(base64.b64decode(evidence_record["base64"], validate=True))
    response_lines = {
        item["operation"]: item["canonical_lines"]
        for item in evidence["configuration_responses"]
    }
    source_readback, _ = _read(readback_path)
    for name in ("running", "startup"):
        if source_readback.get(f"{name}_lines") != response_lines.get(name):
            raise Rejected("source-unavailable R8 PiKVM configuration differs")
    return {
        "capture_directory": str(capture_dir),
        "capture_receipt_sha256": readback["capture_receipt_sha256"],
        "capture_events_sha256": readback["capture_events_sha256"],
        "readback_sha256": hashlib.sha256(readback_path.read_bytes()).hexdigest(),
        "file_count": str(len(captured)),
    }


def verify_interrupted_prefix(
    pending: dict[str, Any], pending_raw: bytes, runtime: Path
) -> list[dict[str, str]]:
    """Verify the exact current-source command prefix that stopped at native mode."""
    if (
        pending.get("schema") != 4
        or pending.get("operation") != "r8_full_trunk_cycle"
        or pending.get("host") != "192.168.0.251"
        or pending.get("fingerprint")
        != "SHA256:UJulVmfAMmHcUctvJrlGzBZR7I7uN8/TWNeJIs25yks"
        or runtime != Path(pending.get("runtime", ""))
        or not runtime.is_absolute()
    ):
        raise Rejected("interrupted R8 runtime identity differs")
    storage.private_directory(runtime)
    paths = sorted(runtime.glob("empty-vlan-phase-*.json"))
    expected = [
        f"empty-vlan-phase-{index:02d}-command_{index // 2}_"
        f"{'intent' if index % 2 == 0 else 'observed'}.json"
        for index in range(5)
    ]
    if [path.name for path in paths] != expected or list(
        runtime.glob("empty-vlan-recovery-*.json")
    ):
        raise Rejected("interrupted R8 phase prefix differs")

    operation_id = pending.get("operation_id")
    previous = hashlib.sha256(pending_raw).hexdigest()
    verified = []
    for index, path in enumerate(paths):
        record, raw = _read(path)
        phase = f"command_{index // 2}_{'intent' if index % 2 == 0 else 'observed'}"
        if (
            record.get("operation_id") != operation_id
            or record.get("index") != index
            or record.get("phase") != phase
            or record.get("prev_digest") != previous
            or record.get("evidence_sha256")
            != hashlib.sha256(_canonical(record.get("evidence"))).hexdigest()
        ):
            raise Rejected("interrupted R8 phase chain mismatch")
        previous = hashlib.sha256(raw).hexdigest()
        verified.append({"path": str(path), "sha256": previous})
    commands = pending.get("commands")
    if (
        type(commands) is not list
        or len(commands) <= 2
        or commands[2] != "no dual-mode 1"
    ):
        raise Rejected("interrupted R8 operation did not stop at native transition")
    return verified


def verify_interrupted_commands(snapshot: Path, pending: dict[str, Any]) -> list[str]:
    code = (
        "import json; import native_trunk_plan as p; "
        "print(json.dumps({'forward':p.R8_FULL_FORWARD,'inverse':p.R8_FULL_INVERSE}))"
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        (
            str(snapshot / "ansible/network-jobs"),
            str(snapshot / "ansible/network-audit"),
        )
    )
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        [sys.executable, "-c", code],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
        env=env,
    )
    try:
        commands = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise Rejected("interrupted R8 source plan did not load") from error
    if (
        result.returncode != 0
        or type(commands) is not dict
        or type(commands.get("forward")) is not list
        or type(commands.get("inverse")) is not list
    ):
        raise Rejected("interrupted R8 source plan shape is invalid")
    expected = [*commands["forward"], *commands["inverse"]]
    if expected != pending.get("commands"):
        raise Rejected("interrupted R8 command list differs from source snapshot")
    return cast(list[str], commands["inverse"])


def reconcile_interrupted_current(
    *,
    pending_path: Path,
    snapshot: Path,
    preflight_path: Path,
    readback_path: Path,
) -> dict[str, Any]:
    """Archive a source-bound interrupted operation after exact baseline read-back."""
    pending_path = pending_path.resolve(strict=True)
    parent = pending_path.parent.parent
    if pending_path.parent.name != "brocade-persistence-ledger":
        raise Rejected("canonical Brocade pending path required")
    runtime = parent / "r8-interrupted-reconciliation-runtime"
    runtime.mkdir(mode=0o700, exist_ok=True)
    with storage.locked_exercise(parent, runtime) as guarded:
        pending, pending_raw = _read(pending_path)
        identity = storage.read_file(pending_path)[1]
        manifest = verify_snapshot(snapshot, pending)
        verify_interrupted_commands(snapshot, pending)
        preflight_raw, _ = storage.read_file(preflight_path)
        preflight = json.loads(preflight_raw)
        if (
            hashlib.sha256(preflight_raw).hexdigest()
            != pending.get("binding", {}).get("native_recovery_proof_sha256")
            or preflight.get("schema") != 2
            or preflight.get("configuration_write_attempted") is not False
            or preflight.get("independent_rescue_currently_verified") is not True
        ):
            raise Rejected("interrupted R8 preflight binding differs")
        readback = verify_readback(snapshot, readback_path)
        binding = pending["binding"]
        if (
            readback.get("running_sha256") != binding.get("baseline_running_sha256")
            or readback.get("startup_sha256") != binding.get("baseline_startup_sha256")
            or readback.get("running_sha256") != readback.get("startup_sha256")
        ):
            raise Rejected("interrupted R8 read-back differs from bound baseline")
        phases = verify_interrupted_prefix(
            pending, pending_raw, Path(pending["runtime"])
        )
        guarded.files[pending_path] = (pending_raw, identity)
        guarded.files[preflight_path] = storage.read_file(preflight_path)
        guarded.files[readback_path] = storage.read_file(readback_path)
        guarded.directories[snapshot] = storage.private_directory(snapshot)
        guarded.files[snapshot / "manifest.json"] = storage.read_file(
            snapshot / "manifest.json"
        )
        guarded.directories[Path(pending["runtime"])] = storage.private_directory(
            Path(pending["runtime"])
        )
        for entry in phases:
            path = Path(entry["path"])
            guarded.files[path] = storage.read_file(path)
        guarded.guard()
        if storage.read_file(pending_path) != (pending_raw, identity):
            raise Rejected("interrupted R8 pending changed during reconciliation")

        custody = parent / "legacy-custody" / pending["operation_id"]
        custody.mkdir(mode=0o700, parents=True, exist_ok=True)
        archived_pending = custody / "pending.json"
        if os.path.lexists(archived_pending):
            raise Rejected("interrupted R8 custody archive already exists")
        storage.exclusive_write(archived_pending, pending_raw)
        readback_raw = readback_path.read_bytes()
        receipt = {
            "schema": 1,
            "status": "interrupted_current_baseline_verified_custody_archived",
            "operation_id": pending["operation_id"],
            "source_binding_sha256": manifest["source_binding_sha256"],
            "source_snapshot_manifest_sha256": hashlib.sha256(
                (snapshot / "manifest.json").read_bytes()
            ).hexdigest(),
            "interrupted_phase_chain": phases,
            "preflight_sha256": hashlib.sha256(preflight_raw).hexdigest(),
            "baseline_readback": {
                **readback,
                "path": str(readback_path),
                "sha256": hashlib.sha256(readback_raw).hexdigest(),
            },
            "restoration_attribution": "not_established",
            "archived_pending_sha256": hashlib.sha256(pending_raw).hexdigest(),
        }
        storage.exclusive_write(
            custody / "reconciliation.json", storage.canonical(receipt)
        )
        guarded.guard()
        verify_snapshot(snapshot, pending)
        release_pending_slot(pending_path, pending_raw, identity, custody, guarded)
        return receipt


def reconcile_restored_unavailable_source(
    *,
    pending_path: Path,
    preflight_path: Path,
    restore_dir: Path,
    readback_path: Path,
    capture_dir: Path,
    custody_root: Path,
) -> dict[str, Any]:
    """Preserve and release the single restored R8 record with missing provenance."""
    pending_path = pending_path.resolve(strict=True)
    preflight_path = preflight_path.resolve(strict=True)
    restore_dir = restore_dir.resolve(strict=True)
    readback_path = readback_path.resolve(strict=True)
    capture_dir = capture_dir.resolve(strict=True)
    parent = pending_path.parent.parent
    if pending_path.parent.name != "brocade-persistence-ledger":
        raise Rejected("canonical Brocade pending path required")
    runtime = parent / "r8-unavailable-source-reconciliation-runtime"
    runtime.mkdir(mode=0o700, exist_ok=True)
    with storage.locked_exercise(parent, runtime) as guarded:
        pending, pending_raw = _read(pending_path)
        identity = storage.read_file(pending_path)[1]
        runtime_path = Path(pending.get("runtime", ""))
        preflight_raw, _ = storage.read_file(preflight_path)
        preflight = json.loads(preflight_raw)
        if (
            hashlib.sha256(preflight_raw).hexdigest()
            != pending.get("binding", {}).get("native_recovery_proof_sha256")
            or preflight.get("schema") != 2
            or preflight.get("configuration_write_attempted") is not False
            or preflight.get("independent_rescue_currently_verified") is not True
        ):
            raise Rejected("source-unavailable R8 preflight binding differs")
        phases, recoveries = verify_unavailable_source_operation(
            pending, pending_raw, runtime_path, parent
        )
        restored = verify_restore_chain(pending, runtime_path, restore_dir)
        readback = verify_unavailable_source_readback(pending, readback_path)
        capture = verify_unavailable_source_capture(
            capture_dir, readback_path, readback
        )
        restorer_hash = hashlib.sha256(
            (ROOT / "ansible/network-jobs/r8_pending_restorer.py").read_bytes()
        ).hexdigest()
        for row in restored["records"]:
            record, _ = _read(Path(row["path"]))
            if record.get("restorer_source_sha256") != restorer_hash:
                raise Rejected("source-unavailable R8 restorer source differs")

        guarded.files[pending_path] = (pending_raw, identity)
        guarded.directories[runtime_path] = storage.private_directory(runtime_path)
        guarded.directories[restore_dir] = storage.private_directory(restore_dir)
        guarded.directories[capture_dir] = storage.private_directory(capture_dir)
        guarded.files[preflight_path] = storage.read_file(preflight_path)
        guarded.files[readback_path] = storage.read_file(readback_path)
        for row in (*phases, *recoveries, *restored["records"]):
            path = Path(row["path"])
            guarded.files[path] = storage.read_file(path)
        guarded.guard()
        if storage.read_file(pending_path) != (pending_raw, identity):
            raise Rejected(
                "source-unavailable R8 pending changed during reconciliation"
            )

        custody_root = custody_root.resolve()
        if not custody_root.exists():
            storage.private_directory(custody_root.parent)
            custody_root.mkdir(mode=0o700)
            storage.sync_directory(custody_root.parent)
        storage.private_directory(custody_root)
        custody = custody_root / R8_UNAVAILABLE_SOURCE_OPERATION
        if not custody.exists():
            custody.mkdir(mode=0o700)
            storage.sync_directory(custody_root)
        storage.private_directory(custody)

        archive: dict[str, bytes] = {
            "pending.json": pending_raw,
            "preflight.json": preflight_raw,
        }
        archive["readback.json"] = storage.read_file(readback_path)[0]
        for group, rows in (
            ("phases", phases),
            ("recovery", recoveries),
            ("restoration", restored["records"]),
        ):
            for row in rows:
                source = Path(row["path"])
                archive[f"{group}/{source.name}"] = storage.read_file(source)[0]
        for source in capture_dir.iterdir():
            archive[f"pikvm-capture/{source.name}"] = read_capture_file(source)[0]
        file_hashes = {
            name: hashlib.sha256(raw).hexdigest() for name, raw in archive.items()
        }
        receipt_path = custody / "reconciliation.json"
        if os.path.lexists(receipt_path):
            receipt, receipt_raw = _read(receipt_path)
            if (
                receipt.get("operation_id") != R8_UNAVAILABLE_SOURCE_OPERATION
                or receipt.get("status")
                != "restored_pending_custody_archived_provenance_unavailable"
                or receipt.get("custody_file_sha256") != file_hashes
                or receipt.get("qualification_admitted") is not False
            ):
                raise Rejected("existing source-unavailable R8 custody differs")
        else:
            receipt = {
                "schema": 1,
                "status": "restored_pending_custody_archived_provenance_unavailable",
                "operation_id": R8_UNAVAILABLE_SOURCE_OPERATION,
                "source_binding_sha256": R8_UNAVAILABLE_SOURCE_BINDING,
                "source_provenance_verified": False,
                "source_snapshot_available": False,
                "restoration_verified": True,
                "qualification_admitted": False,
                "custody_file_sha256": file_hashes,
                "interrupted_phase_chain": phases,
                "interrupted_recovery_chain": recoveries,
                "restoration_chain": restored,
                "independent_baseline_readback": readback,
                "readback_capture": capture,
                "reconciled_at": datetime.now(timezone.utc).isoformat(),
            }
            receipt_raw = storage.canonical(receipt)

        expected = {**archive, "reconciliation.json": receipt_raw}
        expected_directories = {
            "phases",
            "recovery",
            "restoration",
            "pikvm-capture",
        }
        for directory in expected_directories:
            path = custody / directory
            if not path.exists():
                path.mkdir(mode=0o700)
                storage.sync_directory(custody)
            storage.private_directory(path)
        actual_files = {
            path.relative_to(custody).as_posix()
            for path in custody.rglob("*")
            if path.is_file() or path.is_symlink()
        }
        actual_directories = {
            path.relative_to(custody).as_posix()
            for path in custody.rglob("*")
            if path.is_dir()
        }
        if actual_files - expected.keys() or actual_directories - expected_directories:
            raise Rejected("source-unavailable R8 custody contains unexpected entries")
        for relative, raw in expected.items():
            path = custody / relative
            if os.path.lexists(path):
                existing = (
                    read_capture_file(path)[0]
                    if relative.startswith("pikvm-capture/")
                    else storage.read_file(path)[0]
                )
                if existing != raw:
                    raise Rejected("source-unavailable R8 custody content differs")
            else:
                storage.exclusive_write(path, raw)
        for relative, raw in expected.items():
            path = custody / relative
            actual = (
                read_capture_file(path)[0]
                if relative.startswith("pikvm-capture/")
                else storage.read_file(path)[0]
            )
            if actual != raw:
                raise Rejected("source-unavailable R8 custody read-back differs")
        storage.sync_directory(custody)
        guarded.guard()
        if storage.read_file(pending_path) != (pending_raw, identity):
            raise Rejected("source-unavailable R8 pending changed before release")
        if storage.read_file(preflight_path)[0] != preflight_raw:
            raise Rejected("source-unavailable R8 preflight changed before release")
        readback = verify_unavailable_source_readback(pending, readback_path)
        verify_unavailable_source_capture(capture_dir, readback_path, readback)
        if any(
            read_capture_file(source)[0] != archive[f"pikvm-capture/{source.name}"]
            for source in capture_dir.iterdir()
        ):
            raise Rejected("source-unavailable R8 PiKVM capture changed before release")
        release_pending_slot(pending_path, pending_raw, identity, custody, guarded)
        return {**receipt, "pending_slot_released": True, "custody_path": str(custody)}


def reconcile_current_restored_incomplete_source(
    *,
    pending_path: Path,
    snapshot: Path,
    preflight_path: Path,
    restore_dir: Path,
    custody_root: Path,
) -> dict[str, Any]:
    """Archive an exactly restored R8 trial while declaring incomplete source closure."""
    pending_path = pending_path.resolve(strict=True)
    snapshot = snapshot.resolve(strict=True)
    preflight_path = preflight_path.resolve(strict=True)
    restore_dir = restore_dir.resolve(strict=True)
    parent = pending_path.parent.parent
    if pending_path.parent.name != "brocade-persistence-ledger":
        raise Rejected("canonical Brocade pending path required")
    runtime = parent / "r8-current-source-reconciliation-runtime"
    runtime.mkdir(mode=0o700, exist_ok=True)
    with storage.locked_exercise(parent, runtime) as guarded:
        pending, pending_raw = _read(pending_path)
        identity = storage.read_file(pending_path)[1]
        operation_runtime = Path(pending.get("runtime", ""))
        manifest = verify_snapshot(snapshot, pending)
        declared_paths = {
            item["snapshot_path"] for item in manifest["manifest"].values()
        }
        supplemental = sorted(R8_CURRENT_SUPPLEMENTAL_SOURCES - declared_paths)
        if set(supplemental) != R8_CURRENT_SUPPLEMENTAL_SOURCES:
            raise Rejected("incomplete R8 source closure differs from allowlist")
        snapshot_entries = list(snapshot.rglob("*"))
        if any(path.is_symlink() for path in snapshot_entries):
            raise Rejected("current R8 snapshot contains a symbolic link")
        snapshot_files = {
            path.relative_to(snapshot).as_posix(): path
            for path in snapshot_entries
            if path.is_file()
        }
        expected_snapshot_files = {
            "manifest.json",
            *declared_paths,
            *R8_CURRENT_SUPPLEMENTAL_SOURCES,
        }
        if set(snapshot_files) != expected_snapshot_files:
            raise Rejected("incomplete R8 snapshot file set differs")
        snapshot_raws = {
            relative: read_private_artifact(path)
            for relative, path in snapshot_files.items()
        }
        if snapshot_raws["manifest.json"][0] != _canonical(manifest):
            raise Rejected("current R8 snapshot manifest changed during verification")
        if any(
            hashlib.sha256(snapshot_raws[item["snapshot_path"]][0]).hexdigest()
            != item["sha256"]
            for item in manifest["manifest"].values()
        ):
            raise Rejected("current R8 source snapshot changed during verification")
        if any(
            hashlib.sha256(snapshot_raws[item["snapshot_path"]][0]).hexdigest()
            != item["sha256"]
            for item in manifest["manifest"].values()
        ):
            raise Rejected("current R8 source snapshot changed during verification")
        if any(
            hashlib.sha256(snapshot_raws[item["snapshot_path"]][0]).hexdigest()
            != item["sha256"]
            for item in manifest["manifest"].values()
        ):
            raise Rejected("R8 source snapshot changed during verification")
        preflight_raw, _ = storage.read_file(preflight_path)
        preflight = json.loads(preflight_raw)
        if (
            hashlib.sha256(preflight_raw).hexdigest()
            != pending.get("binding", {}).get("native_recovery_proof_sha256")
            or preflight.get("schema") != 2
            or preflight.get("configuration_write_attempted") is not False
            or preflight.get("independent_rescue_currently_verified") is not True
        ):
            raise Rejected("current R8 recovery preflight binding differs")
        phases, recoveries, _ = verify_current_incomplete_operation(
            pending, pending_raw, operation_runtime, parent
        )
        plan = verify_legacy_plan(
            snapshot,
            pending_path,
            preflight_path,
            cast(
                list[str],
                _read(operation_runtime / "empty-vlan-recovery-00-observed.json")[0][
                    "evidence"
                ]["inverse_commands"],
            ),
        )
        restored = verify_restore_chain(pending, operation_runtime, restore_dir)
        restorer_hash = hashlib.sha256(
            (ROOT / "ansible/network-jobs/r8_pending_restorer.py").read_bytes()
        ).hexdigest()
        for row in restored["records"]:
            record, _ = _read(Path(row["path"]))
            if record.get("restorer_source_sha256") != restorer_hash:
                raise Rejected("current R8 restorer source differs from receipt chain")
        final_path = Path(restored["records"][-1]["path"])
        final = _read(final_path)[0]
        final_evidence = final["evidence"]
        observation = final_evidence.get("observation")
        observed_at = final_evidence.get("observed_at")
        age = (
            datetime.now(timezone.utc) - datetime.fromisoformat(observed_at)
            if type(observed_at) is str
            else None
        )
        if (
            type(observation) is not dict
            or observation.get("host") != "192.168.0.251"
            or observation.get("identity") != "homelab_audit"
            or observation.get("accepted_host_key_fingerprint")
            != pending.get("fingerprint")
            or observation.get("expected_execution_environment_sha256")
            != pending.get("binding", {}).get("execution_environment_sha256")
            or observation.get("terminal_boundaries_complete") is not True
            or age is None
            or age.total_seconds() < 0
            or age.total_seconds() > 1800
            or final_evidence.get("pending_retained") is not True
            or final_evidence.get("running_sha256")
            != pending.get("binding", {}).get("baseline_running_sha256")
            or final_evidence.get("startup_sha256")
            != pending.get("binding", {}).get("baseline_startup_sha256")
        ):
            raise Rejected("current R8 final audit read-back is not fresh and exact")

        guarded.files[pending_path] = (pending_raw, identity)
        guarded.directories[operation_runtime] = storage.private_directory(
            operation_runtime
        )
        guarded.directories[restore_dir] = storage.private_directory(restore_dir)
        guarded.directories[snapshot] = storage.private_directory(snapshot)
        guarded.files[preflight_path] = storage.read_file(preflight_path)
        for row in (*phases, *recoveries, *restored["records"]):
            path = Path(row["path"])
            current = storage.read_file(path)
            if hashlib.sha256(current[0]).hexdigest() != row["sha256"]:
                raise Rejected("current R8 receipt changed during reconciliation")
            guarded.files[path] = current
        guarded.guard()
        if storage.read_file(pending_path) != (pending_raw, identity):
            raise Rejected("current R8 pending changed during reconciliation")

        custody_root = custody_root.resolve()
        if not custody_root.exists():
            storage.private_directory(custody_root.parent)
            custody_root.mkdir(mode=0o700)
            storage.sync_directory(custody_root.parent)
        storage.private_directory(custody_root)
        custody = custody_root / R8_CURRENT_OPERATION
        archive: dict[str, bytes] = {
            "pending.json": pending_raw,
            "preflight.json": preflight_raw,
            "snapshot_manifest.json": snapshot_raws["manifest.json"][0],
        }
        for relative, path in snapshot_files.items():
            if relative != "manifest.json":
                archive[f"source__{relative.replace('/', '__')}"] = snapshot_raws[
                    relative
                ][0]
        for group, rows in (
            ("phase", phases),
            ("recovery", recoveries),
            ("restoration", restored["records"]),
        ):
            for row in rows:
                source = Path(row["path"])
                archive[f"{group}__{source.name}"] = storage.read_file(source)[0]
        file_hashes = {
            name: hashlib.sha256(raw).hexdigest() for name, raw in archive.items()
        }
        receipt = {
            "schema": 1,
            "status": "restored_pending_custody_archived_source_closure_incomplete",
            "operation_id": R8_CURRENT_OPERATION,
            "source_binding_sha256": R8_CURRENT_SOURCE_BINDING,
            "source_provenance_verified": False,
            "source_closure_complete": False,
            "supplemental_source_sha256": {
                relative: hashlib.sha256(snapshot_raws[relative][0]).hexdigest()
                for relative in supplemental
            },
            "restoration_verified": True,
            "qualification_admitted": False,
            "legacy_plan": plan,
            "phase_chain": phases,
            "recovery_chain": recoveries,
            "restoration_chain": restored,
            "final_audit_readback": {
                "observed_at": observed_at,
                "running_sha256": final_evidence["running_sha256"],
                "startup_sha256": final_evidence["startup_sha256"],
                "path": str(final_path),
            },
            "custody_file_sha256": file_hashes,
            "reconciled_at": datetime.now(timezone.utc).isoformat(),
        }
        receipt_path = custody / "reconciliation.json"
        if os.path.lexists(receipt_path):
            existing, receipt_raw = _read(receipt_path)
            if (
                existing.get("operation_id") != R8_CURRENT_OPERATION
                or existing.get("status") != receipt["status"]
                or existing.get("custody_file_sha256") != file_hashes
                or existing.get("qualification_admitted") is not False
            ):
                raise Rejected("current R8 custody receipt differs")
            receipt = existing
        else:
            receipt_raw = storage.canonical(receipt)
        archive["reconciliation.json"] = receipt_raw
        if not os.path.lexists(custody):
            custody.mkdir(mode=0o700)
            storage.sync_directory(custody_root)
        storage.private_directory(custody)
        entries = list(custody.iterdir())
        if any(not path.is_file() and not path.is_symlink() for path in entries):
            raise Rejected("current R8 custody contains unexpected directories")
        actual_files = {path.name for path in entries}
        if actual_files - archive.keys():
            raise Rejected("current R8 custody contains unexpected files")
        for name, raw in archive.items():
            path = custody / name
            if os.path.lexists(path):
                if read_private_artifact(path)[0] != raw:
                    raise Rejected("current R8 custody file differs")
            else:
                storage.exclusive_write(path, raw)
        storage.sync_directory(custody)
        for name, raw in archive.items():
            if read_private_artifact(custody / name)[0] != raw:
                raise Rejected("current R8 custody read-back differs")
        guarded.guard()
        if any(
            read_private_artifact(path) != snapshot_raws[relative]
            for relative, path in snapshot_files.items()
        ):
            raise Rejected("current R8 source snapshot changed before slot release")
        if storage.read_file(pending_path) != (pending_raw, identity):
            raise Rejected("current R8 pending changed before slot release")
        release_pending_slot(pending_path, pending_raw, identity, custody, guarded)
        return {**receipt, "pending_slot_released": True, "custody_path": str(custody)}


def reconcile_current_source_restored(
    *,
    pending_path: Path,
    snapshot: Path,
    preflight_path: Path,
    restore_dir: Path,
    custody_root: Path,
) -> dict[str, Any]:
    """Archive a restored R8 operation whose bound source closure is proven."""
    import empty_vlan_cycle as cycle
    import port_description as evidence

    pending_path = pending_path.resolve(strict=True)
    snapshot = snapshot.resolve(strict=True)
    preflight_path = preflight_path.resolve(strict=True)
    restore_dir = restore_dir.resolve(strict=True)
    parent = pending_path.parent.parent
    if pending_path.parent.name != "brocade-persistence-ledger":
        raise Rejected("canonical Brocade pending path required")
    operation_runtime = parent / "r8-current-restored-reconciliation-runtime"
    operation_runtime.mkdir(mode=0o700, exist_ok=True)

    with storage.locked_exercise(parent, operation_runtime) as guarded:
        pending, pending_raw = _read(pending_path)
        identity = storage.read_file(pending_path)[1]
        binding = pending.get("binding")
        unsigned = {
            key: value for key, value in pending.items() if key != "operation_id"
        }
        if (
            pending.get("schema") != 4
            or pending.get("operation") != "r8_full_trunk_cycle"
            or pending.get("host") != "192.168.0.251"
            or pending.get("fingerprint")
            != "SHA256:UJulVmfAMmHcUctvJrlGzBZR7I7uN8/TWNeJIs25yks"
            or pending.get("writer") != "caller_supplied_transport"
            or storage.digest(storage.canonical(unsigned))
            != pending.get("operation_id")
            or type(binding) is not dict
            or set(binding) != set(cycle.BINDING_KEYS)
            or any(
                type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None
                for value in binding.values()
            )
            or binding.get("baseline_running_sha256") != R8_ACCEPTED_BASELINE
            or binding.get("baseline_startup_sha256") != R8_ACCEPTED_BASELINE
            or Path(pending.get("runtime", "")).parent != parent
        ):
            raise Rejected("restored current-source R8 operation identity differs")

        manifest = verify_snapshot(snapshot, pending)
        expected_manifest = cycle.SOURCE_MANIFEST
        if set(manifest["manifest"]) != set(expected_manifest) or evidence.digest(
            {name: item.get("sha256") for name, item in manifest["manifest"].items()}
        ) != binding.get("source_binding_sha256"):
            raise Rejected(
                "R8 snapshot does not contain the complete operation-bound source closure"
            )
        snapshot_entries = list(snapshot.rglob("*"))
        if any(path.is_symlink() for path in snapshot_entries):
            raise Rejected("current R8 snapshot contains a symbolic link")
        snapshot_files = {
            path.relative_to(snapshot).as_posix(): path
            for path in snapshot_entries
            if path.is_file()
        }
        expected_files = {
            "manifest.json",
            *(item["snapshot_path"] for item in manifest["manifest"].values()),
        }
        if set(snapshot_files) != expected_files:
            raise Rejected("current R8 snapshot contains missing or extra files")
        snapshot_raws = {
            relative: read_private_artifact(path)
            for relative, path in snapshot_files.items()
        }
        if snapshot_raws["manifest.json"][0] != _canonical(manifest):
            raise Rejected("current R8 snapshot manifest changed during verification")
        if any(
            hashlib.sha256(snapshot_raws[item["snapshot_path"]][0]).hexdigest()
            != item["sha256"]
            for item in manifest["manifest"].values()
        ):
            raise Rejected("current R8 source snapshot changed during verification")
        preflight_raw, _ = storage.read_file(preflight_path)
        preflight = json.loads(preflight_raw)
        if (
            hashlib.sha256(preflight_raw).hexdigest()
            != binding.get("native_recovery_proof_sha256")
            or preflight.get("schema") != 2
            or preflight.get("configuration_write_attempted") is not False
            or preflight.get("independent_rescue_currently_verified") is not True
        ):
            raise Rejected("current R8 recovery preflight binding differs")

        operation_runtime = Path(pending["runtime"])
        phase_paths = sorted(operation_runtime.glob("empty-vlan-phase-*.json"))
        if len(phase_paths) not in (23, 29, 35):
            raise Rejected(
                "current R8 phase count is not recognized by the source restorer"
            )
        phases, previous = verify_phase_prefix(
            pending, pending_raw, operation_runtime, len(phase_paths)
        )
        phase_records = [_read(Path(row["path"]))[0] for row in phases]
        if not phase_records[-1]["phase"].endswith("_intent"):
            raise Rejected("current R8 failure boundary is not a command intent")
        recoveries, observed = verify_recovery_chain(
            pending, pending_raw, operation_runtime, previous
        )
        source_inverse = verify_interrupted_commands(snapshot, pending)
        if observed["inverse_commands"] != source_inverse:
            raise Rejected("current R8 inverse differs from its bound source plan")
        plan = {
            "status": "pending_restore_plan_valid",
            "operation_id": pending["operation_id"],
            "pending_retained": True,
            "commands": source_inverse,
        }
        restored = verify_restore_chain(pending, operation_runtime, restore_dir)
        snapshot_restorer_hash = hashlib.sha256(
            (snapshot / "ansible/network-jobs/r8_pending_restorer.py").read_bytes()
        ).hexdigest()
        for row in restored["records"]:
            record, _ = _read(Path(row["path"]))
            if record.get("restorer_source_sha256") != snapshot_restorer_hash:
                raise Rejected("restore receipt does not bind the snapshotted restorer")
        final_path = Path(restored["records"][-1]["path"])
        final = _read(final_path)[0]
        evidence = final.get("evidence")
        observation = evidence.get("observation") if type(evidence) is dict else None
        observed_at = evidence.get("observed_at") if type(evidence) is dict else None
        age = (
            datetime.now(timezone.utc) - datetime.fromisoformat(observed_at)
            if type(observed_at) is str
            else None
        )
        if (
            type(observation) is not dict
            or observation.get("host") != pending["host"]
            or observation.get("identity") != "homelab_audit"
            or observation.get("accepted_host_key_fingerprint")
            != pending["fingerprint"]
            or observation.get("expected_execution_environment_sha256")
            != binding.get("execution_environment_sha256")
            or observation.get("terminal_boundaries_complete") is not True
            or age is None
            or age.total_seconds() < 0
            or age.total_seconds() > 1800
            or evidence.get("pending_retained") is not True
            or evidence.get("running_sha256") != binding["baseline_running_sha256"]
            or evidence.get("startup_sha256") != binding["baseline_startup_sha256"]
        ):
            raise Rejected("current R8 final audit read-back is not fresh and exact")

        guarded.files[pending_path] = (pending_raw, identity)
        guarded.directories[operation_runtime] = storage.private_directory(
            operation_runtime
        )
        guarded.directories[restore_dir] = storage.private_directory(restore_dir)
        guarded.directories[snapshot] = storage.private_directory(snapshot)
        guarded.files[preflight_path] = storage.read_file(preflight_path)
        for row in (*phases, *recoveries, *restored["records"]):
            path = Path(row["path"])
            current = storage.read_file(path)
            if hashlib.sha256(current[0]).hexdigest() != row["sha256"]:
                raise Rejected("current R8 receipt changed during reconciliation")
            guarded.files[path] = current
        guarded.guard()

        custody_root = custody_root.resolve()
        if not custody_root.exists():
            storage.private_directory(custody_root.parent)
            custody_root.mkdir(mode=0o700)
            storage.sync_directory(custody_root.parent)
        storage.private_directory(custody_root)
        custody = custody_root / pending["operation_id"]
        archive: dict[str, bytes] = {
            "pending.json": pending_raw,
            "preflight.json": preflight_raw,
            "snapshot_manifest.json": snapshot_raws["manifest.json"][0],
        }
        for relative in expected_files - {"manifest.json"}:
            archive[f"source__{relative.replace('/', '__')}"] = snapshot_raws[relative][
                0
            ]
        for group, rows in (
            ("phase", phases),
            ("recovery", recoveries),
            ("restoration", restored["records"]),
        ):
            for row in rows:
                source = Path(row["path"])
                archive[f"{group}__{source.name}"] = storage.read_file(source)[0]
        hashes = {
            name: hashlib.sha256(raw).hexdigest() for name, raw in archive.items()
        }
        receipt = {
            "schema": 1,
            "status": "restored_pending_custody_archived_source_closure_complete",
            "operation_id": pending["operation_id"],
            "source_binding_sha256": binding["source_binding_sha256"],
            "source_provenance_verified": True,
            "source_closure_complete": True,
            "restoration_verified": True,
            "qualification_admitted": False,
            "legacy_plan": plan,
            "phase_chain": phases,
            "recovery_chain": recoveries,
            "restoration_chain": restored,
            "final_audit_readback": {
                "observed_at": observed_at,
                "running_sha256": evidence["running_sha256"],
                "startup_sha256": evidence["startup_sha256"],
                "path": str(final_path),
            },
            "custody_file_sha256": hashes,
            "reconciled_at": datetime.now(timezone.utc).isoformat(),
        }
        receipt_path = custody / "reconciliation.json"
        if os.path.lexists(receipt_path):
            existing, receipt_raw = _read(receipt_path)
            if (
                existing.get("operation_id") != pending["operation_id"]
                or existing.get("status") != receipt["status"]
                or existing.get("custody_file_sha256") != hashes
                or existing.get("qualification_admitted") is not False
            ):
                raise Rejected("current R8 custody receipt differs")
            receipt = existing
        else:
            receipt_raw = storage.canonical(receipt)
        archive["reconciliation.json"] = receipt_raw
        if not os.path.lexists(custody):
            custody.mkdir(mode=0o700)
            storage.sync_directory(custody_root)
        storage.private_directory(custody)
        entries = list(custody.iterdir())
        if any(not path.is_file() and not path.is_symlink() for path in entries):
            raise Rejected("current R8 custody contains unexpected directories")
        if {path.name for path in entries} - archive.keys():
            raise Rejected("current R8 custody contains unexpected files")
        for name, raw in archive.items():
            path = custody / name
            if os.path.lexists(path):
                if read_private_artifact(path)[0] != raw:
                    raise Rejected("current R8 custody file differs")
            else:
                storage.exclusive_write(path, raw)
        storage.sync_directory(custody)
        for name, raw in archive.items():
            if read_private_artifact(custody / name)[0] != raw:
                raise Rejected("current R8 custody read-back differs")
        guarded.guard()
        if any(
            read_private_artifact(path) != snapshot_raws[relative]
            for relative, path in snapshot_files.items()
        ):
            raise Rejected("current R8 source snapshot changed before slot release")
        if any(
            hashlib.sha256(storage.read_file(Path(row["path"]))[0]).hexdigest()
            != row["sha256"]
            for row in (*phases, *recoveries, *restored["records"])
        ):
            raise Rejected("current R8 receipt changed before slot release")
        if storage.read_file(pending_path) != (pending_raw, identity):
            raise Rejected("current R8 pending changed before slot release")
        release_pending_slot(pending_path, pending_raw, identity, custody, guarded)
        return {**receipt, "pending_slot_released": True, "custody_path": str(custody)}


def reconcile(
    *,
    pending_path: Path,
    snapshot: Path,
    preflight_path: Path,
    restore_dir: Path,
    readback_path: Path,
) -> dict[str, Any]:
    pending_path = pending_path.resolve(strict=True)
    parent = pending_path.parent.parent
    if pending_path.parent.name != "brocade-persistence-ledger":
        raise Rejected("canonical Brocade pending path required")
    runtime = parent / "r8-legacy-reconciliation-runtime"
    runtime.mkdir(mode=0o700, exist_ok=True)
    with storage.locked_exercise(parent, runtime) as guarded:
        pending, pending_raw = _read(pending_path)
        identity = storage.read_file(pending_path)[1]
        manifest = verify_snapshot(snapshot, pending)
        recovery, recovered = verify_recovery_chain(
            pending, pending_raw, Path(pending["runtime"])
        )
        plan = verify_legacy_plan(
            snapshot,
            pending_path,
            preflight_path,
            cast(list[str], recovered["inverse_commands"]),
        )
        restored = verify_restore_chain(pending, Path(pending["runtime"]), restore_dir)
        readback = verify_readback(snapshot, readback_path)
        guarded.guard()
        if storage.read_file(pending_path) != (pending_raw, identity):
            raise Rejected("legacy pending changed during reconciliation")

        custody = parent / "legacy-custody" / pending["operation_id"]
        custody.mkdir(mode=0o700, parents=True, exist_ok=True)
        archived_pending = custody / "pending.json"
        if os.path.lexists(archived_pending):
            raise Rejected("legacy custody archive already exists")
        storage.exclusive_write(archived_pending, pending_raw)
        receipt = {
            "schema": 1,
            "status": "restored_legacy_pending_custody_archived",
            "operation_id": pending["operation_id"],
            "source_binding_sha256": manifest["source_binding_sha256"],
            "source_snapshot_manifest_sha256": hashlib.sha256(
                (snapshot / "manifest.json").read_bytes()
            ).hexdigest(),
            "legacy_plan": plan,
            "recovery_chain": recovery,
            "restore_chain": restored,
            "independent_readback": {
                **readback,
                "path": str(readback_path),
                "sha256": hashlib.sha256(readback_path.read_bytes()).hexdigest(),
            },
            "archived_pending_sha256": hashlib.sha256(pending_raw).hexdigest(),
        }
        storage.exclusive_write(
            custody / "reconciliation.json", storage.canonical(receipt)
        )
        guarded.guard()
        release_pending_slot(pending_path, pending_raw, identity, custody, guarded)
        return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pending", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--preflight", type=Path, required=True)
    parser.add_argument("--restore-dir", type=Path)
    parser.add_argument("--readback", type=Path)
    parser.add_argument("--interrupted-current", action="store_true")
    parser.add_argument("--source-unavailable-restored", action="store_true")
    parser.add_argument("--current-incomplete-source-restored", action="store_true")
    parser.add_argument("--current-source-restored", action="store_true")
    parser.add_argument("--completed-unqualified-archive", type=Path)
    parser.add_argument("--capture-dir", type=Path)
    parser.add_argument(
        "--custody-root",
        type=Path,
        default=ROOT / "inventory/local/r8-pending-custody",
    )
    args = parser.parse_args()
    if args.completed_unqualified_archive is not None:
        if (
            args.snapshot is not None
            or args.restore_dir is not None
            or args.readback is None
            or args.capture_dir is not None
            or args.interrupted_current
            or args.source_unavailable_restored
            or args.current_incomplete_source_restored
            or args.current_source_restored
        ):
            parser.error(
                "--completed-unqualified-archive requires --readback and --preflight only"
            )
    elif args.current_incomplete_source_restored:
        if (
            args.snapshot is None
            or args.restore_dir is None
            or args.readback is not None
            or args.capture_dir is not None
            or args.interrupted_current
            or args.source_unavailable_restored
        ):
            parser.error(
                "--current-incomplete-source-restored requires --snapshot and --restore-dir only"
            )
    elif args.current_source_restored:
        if (
            args.snapshot is None
            or args.restore_dir is None
            or args.readback is not None
            or args.capture_dir is not None
            or args.interrupted_current
            or args.source_unavailable_restored
        ):
            parser.error(
                "--current-source-restored requires --snapshot and --restore-dir only"
            )
    elif args.readback is None:
        parser.error("--readback is required for this reconciliation mode")
    if args.completed_unqualified_archive is not None:
        pass
    elif args.source_unavailable_restored:
        if (
            args.restore_dir is None
            or args.capture_dir is None
            or args.snapshot is not None
            or args.interrupted_current
        ):
            parser.error(
                "--source-unavailable-restored requires --restore-dir and --capture-dir; omit --snapshot"
            )
    elif args.snapshot is None:
        parser.error("--snapshot is required for source-bound reconciliation")
    elif not args.interrupted_current and args.restore_dir is None:
        print(
            json.dumps(
                {
                    "status": "reconciliation_failed",
                    "reason": "--restore-dir is required for legacy reconciliation",
                }
            )
        )
        return 1
    snapshot = cast(Path, args.snapshot)
    try:
        if args.completed_unqualified_archive is not None:
            action = reconcile_completed_unqualified_archive(
                pending_path=args.pending,
                archive=args.completed_unqualified_archive,
                preflight_path=args.preflight,
                readback_path=cast(Path, args.readback),
            )
        elif args.current_incomplete_source_restored:
            action = reconcile_current_restored_incomplete_source(
                pending_path=args.pending,
                snapshot=snapshot,
                preflight_path=args.preflight,
                restore_dir=cast(Path, args.restore_dir),
                custody_root=args.custody_root,
            )
        elif args.current_source_restored:
            action = reconcile_current_source_restored(
                pending_path=args.pending,
                snapshot=snapshot,
                preflight_path=args.preflight,
                restore_dir=cast(Path, args.restore_dir),
                custody_root=args.custody_root,
            )
        elif args.source_unavailable_restored:
            action = reconcile_restored_unavailable_source(
                pending_path=args.pending,
                preflight_path=args.preflight,
                restore_dir=args.restore_dir,
                readback_path=args.readback,
                capture_dir=args.capture_dir,
                custody_root=args.custody_root,
            )
        else:
            action = (
                reconcile_interrupted_current(
                    pending_path=args.pending,
                    snapshot=snapshot,
                    preflight_path=args.preflight,
                    readback_path=args.readback,
                )
                if args.interrupted_current
                else reconcile(
                    pending_path=args.pending,
                    snapshot=snapshot,
                    preflight_path=args.preflight,
                    restore_dir=args.restore_dir,
                    readback_path=args.readback,
                )
            )
        print(json.dumps(action, sort_keys=True))
        return 0
    except (Exception, KeyboardInterrupt) as error:
        print(json.dumps({"status": "reconciliation_failed", "reason": str(error)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
