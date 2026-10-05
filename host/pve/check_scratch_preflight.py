#!/usr/bin/env python3
"""Read-only, serial-bound PVE preflight for the two scratch NVMe candidates."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence


SERIAL_C = "PHHH8505034Q512H"
SERIAL_D = "BTHH8244042V512D"
SERIALS = (SERIAL_C, SERIAL_D)
BOUNDARY_BYTES = 8 * 1024 * 1024
REFERENCE_CHECKS = (
    "mounts",
    "swap",
    "holders",
    "imported pools",
    "importable pools",
    "host configuration",
    "firmware",
)
POSITIVE_CONTROLS = (
    "imported rpool",
    "imported fast-vm",
    "rpool member BTHH95021LD4512D",
    "rpool member BTHH8122061E512D",
    "fast-vm member PHHH829001A91P0E",
    "fast-vm member PHHH828600761P0E",
    "mounted /etc/pve",
    "fast-vm storage entry",
    "Proxmox ESP A filesystem UUID",
    "Proxmox ESP B filesystem UUID",
    "firmware ESP A PARTUUID",
    "firmware ESP B PARTUUID",
)
EXPECTED_ESP_FILESYSTEM_UUIDS = ("929D-9F5B", "929E-65B4")
EXPECTED_ESP_PARTUUIDS = (
    "a6ab2778-6cfa-4764-864d-4c63bb08364e",
    "c0096bb5-4bfc-4fc0-ad5b-156a16e0a9ab",
)
EXPECTED_ESP_PARTITION_TYPE = "c12a7328-f81f-11d2-ba4b-00a0c93ec93b"


class ReadOnlyViolation(RuntimeError):
    """Raised when a command falls outside the explicit read-only allow-list."""


@dataclass(frozen=True)
class Finding:
    state: str
    detail: str


@dataclass
class CandidateEvidence:
    serial: str
    whole_disks: list[tuple[str, str, str]]
    aliases: list[tuple[str, str]]
    children: list[dict[str, Any]] | None
    signatures: dict[str, tuple[int, str]] | None
    boundaries: dict[str, tuple[str, bool] | None] | None
    smart: dict[str, Any] | None
    references: dict[str, list[str] | None]


@dataclass
class PreflightEvidence:
    candidates: dict[str, CandidateEvidence]
    controls: dict[str, bool | None]
    scratch_collision: bool | None
    collection_issues: list[str] = field(default_factory=list)


@dataclass
class Report:
    state: str
    findings: list[Finding]
    authorization_note: str
    observed_at: str | None = None
    boot_id: str | None = None


def _command_is_read_only(argv: Sequence[str]) -> bool:
    if not argv:
        return False
    command = Path(argv[0]).name
    args = list(argv[1:])
    if command == "lsblk":
        return True
    if command == "readlink":
        return bool(args) and args[0] == "-f"
    if command == "blkid":
        return len(args) == 4 and args[:3] == ["-p", "-o", "export"]
    if command == "blockdev":
        return len(args) == 2 and args[0] == "--getsize64"
    if command == "dd":
        return (
            any(arg.startswith("if=") for arg in args)
            and not any(
                arg.startswith(("of=", "seek=", "conv=", "oflag=")) for arg in args
            )
            and "status=none" in args
        )
    if command == "zpool":
        if args[:3] == ["list", "-H", "-o"] and args[3:] == ["name"]:
            return True
        if (
            len(args) == 4
            and args[:1] == ["status"]
            and args[1:3] == ["-P", "-v"]
            and re.fullmatch(r"[A-Za-z0-9_.:][A-Za-z0-9_.:-]*", args[3]) is not None
        ):
            return True
        return args == ["import", "-d", "/dev/disk/by-id"]
    if command == "smartctl":
        return len(args) == 3 and args[:2] == ["-j", "-a"]
    if command == "findmnt":
        return args == ["-rn", "-o", "MAJ:MIN"]
    if command == "efibootmgr":
        return args == ["-v"]
    return False


def run_readonly(
    argv: Sequence[str], *, binary: bool = False
) -> subprocess.CompletedProcess[Any]:
    if not _command_is_read_only(argv):
        raise ReadOnlyViolation(f"command is not allow-listed as read-only: {argv!r}")
    return subprocess.run(
        list(argv),
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=not binary,
    )


def _finding(state: str, detail: str) -> Finding:
    return Finding(state, detail)


def _smart_integer(value: Any, *, maximum: int | None = None) -> int | None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        return None
    if maximum is not None and value > maximum:
        return None
    return value


def _assess_candidate(candidate: CandidateEvidence) -> list[Finding]:
    findings: list[Finding] = []
    matches = [
        (path, serial)
        for path, serial, kind in candidate.whole_disks
        if kind == "disk" and serial == candidate.serial
    ]
    if len(matches) != 1:
        findings.append(
            _finding(
                "UNKNOWN",
                f"{candidate.serial}: expected one whole-disk match; found {len(matches)}",
            )
        )
        device = None
    else:
        device = matches[0][0]
        linked = [
            (link, target)
            for link, target in candidate.aliases
            if target == device and candidate.serial in Path(link).name
        ]
        if linked:
            findings.append(
                _finding(
                    "CLEAR",
                    f"{candidate.serial}: lsblk serial and by-id alias agree on {device}",
                )
            )
        else:
            findings.append(
                _finding(
                    "UNKNOWN",
                    f"{candidate.serial}: no matching serial-bearing by-id alias resolves to {device}",
                )
            )

    children = candidate.children
    if children is None:
        findings.append(
            _finding(
                "UNKNOWN", f"{candidate.serial}: child-device inventory unavailable"
            )
        )
        node_paths: list[str] = [device] if device else []
    else:
        node_paths = ([device] if device else []) + [
            str(row["name"]) for row in children
        ]
        if children:
            names = ", ".join(str(row["name"]) for row in children)
            findings.append(
                _finding(
                    "BLOCK",
                    f"{candidate.serial}: partition or child devices remain: {names}",
                )
            )
        else:
            findings.append(
                _finding("CLEAR", f"{candidate.serial}: no child devices reported")
            )

    if candidate.signatures is None:
        findings.append(
            _finding("UNKNOWN", f"{candidate.serial}: signature probes unavailable")
        )
    else:
        for path in node_paths:
            probe = candidate.signatures.get(path)
            if probe is None:
                findings.append(
                    _finding(
                        "UNKNOWN",
                        f"{candidate.serial}: missing signature result for {path}",
                    )
                )
            elif probe[0] == 0 and probe[1].strip():
                findings.append(
                    _finding(
                        "BLOCK", f"{candidate.serial}: signature present on {path}"
                    )
                )
            elif probe[0] == 2 and not probe[1].strip():
                findings.append(
                    _finding(
                        "CLEAR",
                        f"{candidate.serial}: no blkid signature reported on {path}",
                    )
                )
            else:
                findings.append(
                    _finding(
                        "UNKNOWN",
                        f"{candidate.serial}: blkid could not classify {path} (exit {probe[0]})",
                    )
                )

    if candidate.boundaries is None:
        findings.append(
            _finding("UNKNOWN", f"{candidate.serial}: boundary reads unavailable")
        )
    else:
        for region in ("first", "last"):
            boundary = candidate.boundaries.get(region)
            if boundary is None:
                findings.append(
                    _finding(
                        "UNKNOWN", f"{candidate.serial}: missing {region} 8 MiB read"
                    )
                )
            elif boundary[1]:
                findings.append(
                    _finding(
                        "BLOCK",
                        f"{candidate.serial}: non-zero unsigned bytes in {region} 8 MiB; review required",
                    )
                )
            else:
                findings.append(
                    _finding(
                        "CLEAR",
                        f"{candidate.serial}: {region} 8 MiB are zero (sha256 {boundary[0]})",
                    )
                )

    smart = candidate.smart
    if smart is None:
        findings.append(
            _finding("UNKNOWN", f"{candidate.serial}: SMART read unavailable")
        )
    else:
        numeric_fields = (
            "critical_warning",
            "available_spare",
            "available_spare_threshold",
            "media_errors",
        )
        required = ("passed",) + numeric_fields
        missing = [key for key in required if key not in smart]
        if missing:
            findings.append(
                _finding(
                    "UNKNOWN",
                    f"{candidate.serial}: SMART fields missing: {', '.join(missing)}",
                )
            )
        else:
            values = {
                "critical_warning": _smart_integer(
                    smart["critical_warning"], maximum=255
                ),
                "available_spare": _smart_integer(
                    smart["available_spare"], maximum=100
                ),
                "available_spare_threshold": _smart_integer(
                    smart["available_spare_threshold"], maximum=100
                ),
                "media_errors": _smart_integer(smart["media_errors"]),
            }
            invalid = [key for key, value in values.items() if value is None]
            if not isinstance(smart["passed"], bool):
                invalid.append("passed")
            if invalid:
                findings.append(
                    _finding(
                        "UNKNOWN",
                        f"{candidate.serial}: SMART fields invalid: {', '.join(invalid)}",
                    )
                )
            else:
                valid_values = {
                    key: value for key, value in values.items() if value is not None
                }
                if (
                    smart["passed"] is not True
                    or valid_values["critical_warning"] != 0
                    or valid_values["media_errors"] != 0
                    or valid_values["available_spare"]
                    < valid_values["available_spare_threshold"]
                ):
                    findings.append(
                        _finding(
                            "BLOCK",
                            f"{candidate.serial}: SMART health, critical warning, media errors, or spare threshold failed",
                        )
                    )
                else:
                    findings.append(
                        _finding(
                            "CLEAR",
                            f"{candidate.serial}: SMART health and required error/spare fields pass",
                        )
                    )

    for name in REFERENCE_CHECKS:
        references = candidate.references.get(name)
        if references is None:
            findings.append(
                _finding("UNKNOWN", f"{candidate.serial}: {name} check unavailable")
            )
        elif references:
            findings.append(
                _finding(
                    "BLOCK",
                    f"{candidate.serial}: {name} reference found: {', '.join(references)}",
                )
            )
        else:
            findings.append(
                _finding("CLEAR", f"{candidate.serial}: no {name} reference found")
            )
    return findings


def assess(evidence: PreflightEvidence) -> Report:
    findings = [_finding("UNKNOWN", issue) for issue in evidence.collection_issues]
    for serial in SERIALS:
        candidate = evidence.candidates.get(serial)
        if candidate is None:
            findings.append(
                _finding("UNKNOWN", f"{serial}: candidate evidence missing")
            )
        else:
            findings.extend(_assess_candidate(candidate))
    for control in POSITIVE_CONTROLS:
        control_state = evidence.controls.get(control)
        if control_state is True:
            findings.append(_finding("CLEAR", f"positive control present: {control}"))
        else:
            findings.append(
                _finding("UNKNOWN", f"positive control unavailable: {control}")
            )
    if evidence.scratch_collision is True:
        findings.append(
            _finding("BLOCK", "a scratch pool or PVE storage ID already exists")
        )
    elif evidence.scratch_collision is False:
        findings.append(_finding("CLEAR", "no scratch pool or PVE storage ID exists"))
    else:
        findings.append(_finding("UNKNOWN", "scratch-name collision check unavailable"))

    if any(item.state == "BLOCK" for item in findings):
        overall_state = "BLOCK"
    elif any(item.state == "UNKNOWN" for item in findings):
        overall_state = "UNKNOWN"
    else:
        overall_state = "CLEAR"
    return Report(
        state=overall_state,
        findings=findings,
        authorization_note=(
            "CLEAR is a time-bound host-state preflight, not authorization; operator classification, "
            "off-target metadata capture, source review, and separate write approval remain required."
        ),
    )


def _flatten_devices(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    devices: list[dict[str, Any]] = []
    for row in rows:
        devices.append(row)
        devices.extend(_flatten_devices(row.get("children", [])))
    return devices


def _read_text(path: Path, *, required: bool = False) -> tuple[str | None, str | None]:
    try:
        return path.read_text(), None
    except FileNotFoundError:
        return (None, f"required file missing: {path}") if required else ("", None)
    except OSError as error:
        return None, f"cannot read {path}: {error}"


def _read_bytes(
    path: Path, *, required: bool = False
) -> tuple[bytes | None, str | None]:
    try:
        return path.read_bytes(), None
    except FileNotFoundError:
        return (None, f"required file missing: {path}") if required else (b"", None)
    except OSError as error:
        return None, f"cannot read {path}: {error}"


def _mountpoint_is_live(mountinfo: str, target: str) -> bool:
    for line in mountinfo.splitlines():
        fields = line.split()
        if len(fields) < 5:
            continue
        mountpoint = re.sub(
            r"\\([0-7]{3})", lambda match: chr(int(match[1], 8)), fields[4]
        )
        if mountpoint == target:
            return True
    return False


def _candidate_tokens(candidate: CandidateEvidence) -> set[str]:
    tokens = {candidate.serial}
    for path, _, _ in candidate.whole_disks:
        tokens.add(path)
        tokens.add(Path(path).name)
    for link, target in candidate.aliases:
        tokens.update((link, Path(link).name, target, Path(target).name))
    for child in candidate.children or []:
        for key in ("name", "partuuid", "uuid", "partlabel"):
            value = child.get(key)
            if value:
                tokens.add(str(value))
                if key == "name":
                    tokens.add(Path(str(value)).name)
    if candidate.serial == SERIAL_C:
        tokens.add("14828205673918207700")
        tokens.add("rpool-OLD-14828205673918207700")
    return {token for token in tokens if token}


def _scan_paths(paths: list[Path], tokens: set[str]) -> list[str] | None:
    matches: list[str] = []
    required_paths = {
        Path("/etc/pve/storage.cfg"),
        Path("/etc/fstab"),
        Path("/etc/zfs/zpool.cache"),
    }
    for path in paths:
        contents, error = _read_bytes(path, required=path in required_paths)
        if error:
            return None
        if contents is None:
            continue
        for token in tokens:
            if token.encode() in contents:
                matches.append(f"{path}:{token}")
    return matches


def _pve_config_paths() -> tuple[list[Path] | None, str | None]:
    root = Path("/etc/pve")
    storage = root / "storage.cfg"
    nodes = root / "nodes"
    if not nodes.is_dir():
        return None, "PVE node config directory unavailable"
    paths = [storage]
    try:
        for node in nodes.iterdir():
            if not node.is_dir():
                continue
            for directory in (node / "qemu-server", node / "lxc"):
                if directory.is_dir():
                    paths.extend(item for item in directory.iterdir() if item.is_file())
        mapping = root / "mapping"
        if mapping.is_dir():
            for path in mapping.iterdir():
                if path.is_file():
                    paths.append(path)
    except OSError as error:
        return None, f"cannot enumerate PVE config: {error}"
    return paths, None


def _read_smart(device: str) -> dict[str, Any] | None:
    result = run_readonly(["smartctl", "-j", "-a", device])
    if result.returncode != 0:
        return None
    try:
        document = json.loads(result.stdout)
        health = document.get("smart_status", {})
        nvme = document.get("nvme_smart_health_information_log", {})
        return {
            "passed": health.get("passed"),
            "critical_warning": nvme.get("critical_warning"),
            "available_spare": nvme.get("available_spare"),
            "available_spare_threshold": nvme.get("available_spare_threshold"),
            "media_errors": nvme.get("media_errors"),
        }
    except (json.JSONDecodeError, AttributeError, TypeError):
        return None


def _read_boundary(device: str, size: int, *, last: bool) -> tuple[str, bool] | None:
    if size < 2 * BOUNDARY_BYTES:
        return None
    if last:
        offset = size - BOUNDARY_BYTES
        argv = [
            "dd",
            f"if={device}",
            "iflag=skip_bytes,count_bytes",
            f"skip={offset}",
            f"count={BOUNDARY_BYTES}",
            "status=none",
        ]
    else:
        argv = [
            "dd",
            f"if={device}",
            "bs=1048576",
            "count=8",
            "iflag=fullblock",
            "status=none",
        ]
    result = run_readonly(argv, binary=True)
    if result.returncode != 0 or len(result.stdout) != BOUNDARY_BYTES:
        return None
    return hashlib.sha256(result.stdout).hexdigest(), any(result.stdout)


def _block_paths(device: str, children: list[dict[str, Any]]) -> set[str]:
    return {
        os.path.realpath(path)
        for path in [device] + [str(row["name"]) for row in children]
    }


def _device_major_minor(row: dict[str, Any]) -> str | None:
    value = row.get("maj:min") or row.get("maj_min")
    return str(value) if value else None


def _swap_references(candidate_paths: set[str], tokens: set[str]) -> list[str] | None:
    text, error = _read_text(Path("/proc/swaps"), required=True)
    if error or text is None:
        return None
    hits: list[str] = []
    for line in text.splitlines()[1:]:
        fields = line.split()
        if not fields:
            continue
        source = fields[0]
        if any(token in source for token in tokens):
            hits.append(source)
            continue
        try:
            info = os.stat(source)
        except OSError:
            if source.startswith("/dev/"):
                return None
            continue
        if stat.S_ISBLK(info.st_mode) and os.path.realpath(source) in candidate_paths:
            hits.append(source)
    return hits


def _holder_references(rows: list[dict[str, Any]]) -> list[str] | None:
    hits: list[str] = []
    for row in rows:
        name = Path(str(row.get("name", ""))).name
        if not name:
            return None
        holders = Path("/sys/class/block") / name / "holders"
        try:
            entries = list(holders.iterdir())
        except OSError:
            return None
        hits.extend(f"{name}->{entry.name}" for entry in entries)
    return hits


def _zpool_paths(text: str) -> set[str]:
    paths = set(re.findall(r"/dev/[^\s]+", text))
    return {os.path.realpath(path) for path in paths}


def _pool_member_serials(text: str, devices: list[dict[str, Any]]) -> set[str]:
    by_name = {Path(str(row.get("name", ""))).name: row for row in devices}
    serials: set[str] = set()
    for path in re.findall(r"/dev/[^\s]+", text):
        canonical = os.path.realpath(path)
        row = next(
            (
                item
                for item in devices
                if os.path.realpath(str(item.get("name", ""))) == canonical
            ),
            None,
        )
        if row is None:
            continue
        if row.get("type") == "disk" and row.get("serial"):
            serials.add(str(row["serial"]))
            continue
        parent = row.get("pkname")
        if parent:
            parent_row = by_name.get(Path(str(parent)).name)
            if parent_row and parent_row.get("serial"):
                serials.add(str(parent_row["serial"]))
    return serials


def _references_in_output(text: str, tokens: set[str]) -> list[str]:
    return sorted(token for token in tokens if token in text)


def _configured_esp_controls(
    boot_uuids_text: str | None, devices: list[dict[str, Any]]
) -> dict[str, bool | None]:
    controls: dict[str, bool | None] = {
        "Proxmox ESP A filesystem UUID": None,
        "Proxmox ESP B filesystem UUID": None,
    }
    if boot_uuids_text is None:
        return controls

    configured: set[str] = set()
    for line in boot_uuids_text.splitlines():
        value = line.partition("#")[0].strip().upper()
        if not value:
            continue
        if not re.fullmatch(r"[0-9A-F]{4}-[0-9A-F]{4}", value):
            return controls
        configured.add(value)

    for control, expected_uuid, expected_partuuid in zip(
        controls,
        EXPECTED_ESP_FILESYSTEM_UUIDS,
        EXPECTED_ESP_PARTUUIDS,
        strict=True,
    ):
        if expected_uuid not in configured:
            controls[control] = False
            continue
        uuid_matches = [
            row for row in devices if str(row.get("uuid", "")).upper() == expected_uuid
        ]
        partuuid_matches = [
            row
            for row in devices
            if str(row.get("partuuid", "")).lower() == expected_partuuid
        ]
        if len(uuid_matches) > 1 or len(partuuid_matches) > 1:
            continue
        if not uuid_matches or not partuuid_matches:
            controls[control] = False
            continue

        row = uuid_matches[0]
        controls[control] = (
            row is partuuid_matches[0]
            and str(row.get("type", "")).lower() == "part"
            and str(row.get("parttype", "")).lower() == EXPECTED_ESP_PARTITION_TYPE
            and str(row.get("fstype", "")).lower() in {"vfat", "fat", "fat16", "fat32"}
        )
    return controls


def _read_imported_pool_statuses(
    pool_names: set[str], devices: list[dict[str, Any]]
) -> tuple[dict[str, str], dict[str, set[str]], list[str]]:
    statuses: dict[str, str] = {}
    member_serials: dict[str, set[str]] = {}
    issues: list[str] = []
    for name in sorted(pool_names):
        status = run_readonly(["zpool", "status", "-P", "-v", name])
        if status.returncode != 0:
            issues.append(f"zpool status failed for {name}")
            continue
        statuses[name] = status.stdout
        member_serials[name] = _pool_member_serials(status.stdout, devices)
    return statuses, member_serials, issues


def _collect() -> tuple[PreflightEvidence, str | None, str | None]:
    issues: list[str] = []
    observed_at = datetime.now().astimezone().isoformat(timespec="seconds")
    boot_id, error = _read_text(Path("/proc/sys/kernel/random/boot_id"), required=True)
    if error:
        issues.append(error)
    elif boot_id:
        boot_id = boot_id.strip()

    empty_candidates = {
        serial: CandidateEvidence(serial, [], [], None, None, None, None, {})
        for serial in SERIALS
    }
    empty_controls: dict[str, bool | None] = {name: None for name in POSITIVE_CONTROLS}
    block_json = run_readonly(
        [
            "lsblk",
            "--json",
            "--bytes",
            "--paths",
            "--output",
            "NAME,TYPE,SERIAL,PKNAME,PARTUUID,UUID,PARTTYPE,PARTLABEL,FSTYPE,SIZE,MAJ:MIN",
        ]
    )
    if block_json.returncode != 0:
        issues.append("lsblk inventory command failed")
        return (
            PreflightEvidence(empty_candidates, empty_controls, None, issues),
            observed_at,
            boot_id,
        )
    try:
        tree = json.loads(block_json.stdout)["blockdevices"]
    except (json.JSONDecodeError, KeyError, TypeError):
        issues.append("lsblk inventory was not valid JSON")
        return (
            PreflightEvidence(empty_candidates, empty_controls, None, issues),
            observed_at,
            boot_id,
        )

    all_devices = _flatten_devices(tree)
    top_disks = [row for row in tree if row.get("type") == "disk"]
    by_id_dir = Path("/dev/disk/by-id")
    try:
        by_id_links = [path for path in by_id_dir.iterdir() if path.is_symlink()]
        resolved_aliases = [(str(path), os.path.realpath(path)) for path in by_id_links]
    except OSError as error:
        issues.append(f"cannot enumerate {by_id_dir}: {error}")
        resolved_aliases = []

    candidates: dict[str, CandidateEvidence] = {}
    for serial in SERIALS:
        matches = [
            (
                str(row.get("name", "")),
                str(row.get("serial", "")),
                str(row.get("type", "")),
            )
            for row in top_disks
            if row.get("serial") == serial
        ]
        candidate = CandidateEvidence(serial, matches, [], None, None, None, None, {})
        candidates[serial] = candidate
        if len(matches) != 1:
            continue
        device = matches[0][0]
        candidate.aliases = [
            pair for pair in resolved_aliases if pair[1] == os.path.realpath(device)
        ]
        device_row = next(row for row in top_disks if row.get("serial") == serial)
        candidate.children = _flatten_devices(device_row.get("children", []))
        paths = [device] + [str(row.get("name", "")) for row in candidate.children]
        candidate.signatures = {}
        for path in paths:
            probe = run_readonly(["blkid", "-p", "-o", "export", path])
            candidate.signatures[path] = (probe.returncode, probe.stdout)

        size_result = run_readonly(["blockdev", "--getsize64", device])
        try:
            size = int(size_result.stdout.strip()) if size_result.returncode == 0 else 0
        except ValueError:
            size = 0
        if size:
            candidate.boundaries = {
                "first": _read_boundary(device, size, last=False),
                "last": _read_boundary(device, size, last=True),
            }
        else:
            candidate.boundaries = None
        candidate.smart = _read_smart(device)

    mountinfo, mountinfo_error = _read_text(Path("/proc/self/mountinfo"), required=True)
    storage_cfg, storage_error = _read_text(Path("/etc/pve/storage.cfg"), required=True)
    pve_live = (
        _mountpoint_is_live(mountinfo or "", "/etc/pve")
        if mountinfo is not None
        else None
    )
    controls: dict[str, bool | None] = dict(empty_controls)
    controls["mounted /etc/pve"] = pve_live
    controls["fast-vm storage entry"] = (
        bool(re.search(r"(?m)^zfspool:\s+fast-vm\s*$", storage_cfg))
        if storage_cfg is not None and pve_live
        else None
    )
    if mountinfo_error:
        issues.append(mountinfo_error)
    if storage_error:
        issues.append(storage_error)

    pools_result = run_readonly(["zpool", "list", "-H", "-o", "name"])
    pool_names = (
        set(pools_result.stdout.splitlines()) if pools_result.returncode == 0 else set()
    )
    if pools_result.returncode != 0:
        issues.append("zpool list command failed")
    controls["imported rpool"] = (
        "rpool" in pool_names if pools_result.returncode == 0 else None
    )
    controls["imported fast-vm"] = (
        "fast-vm" in pool_names if pools_result.returncode == 0 else None
    )
    pool_statuses, pool_member_serials, pool_issues = _read_imported_pool_statuses(
        pool_names, all_devices
    )
    issues.extend(pool_issues)
    expected_pool_members = {
        "rpool member BTHH95021LD4512D": ("rpool", "BTHH95021LD4512D"),
        "rpool member BTHH8122061E512D": ("rpool", "BTHH8122061E512D"),
        "fast-vm member PHHH829001A91P0E": ("fast-vm", "PHHH829001A91P0E"),
        "fast-vm member PHHH828600761P0E": ("fast-vm", "PHHH828600761P0E"),
    }
    for control, (pool, serial) in expected_pool_members.items():
        controls[control] = (
            serial in pool_member_serials[pool] if pool in pool_member_serials else None
        )

    import_result = run_readonly(["zpool", "import", "-d", "/dev/disk/by-id"])
    if import_result.returncode != 0:
        issues.append("read-only zpool import-list command failed")

    storage_text = storage_cfg or ""
    scratch_collision: bool | None = None
    if pve_live and pools_result.returncode == 0 and storage_cfg is not None:
        storage_ids = re.findall(r"(?m)^[^#\s][^:]*:\s+scratch\s*$", storage_text)
        import_collision = (
            bool(re.search(r"(?m)^\s*pool:\s*scratch\s*$", import_result.stdout))
            if import_result.returncode == 0
            else None
        )
        if "scratch" in pool_names or storage_ids or import_collision is True:
            scratch_collision = True
        elif import_collision is None:
            scratch_collision = None
        else:
            scratch_collision = False

    boot_uuids_text, boot_uuids_error = _read_text(
        Path("/etc/kernel/proxmox-boot-uuids"), required=True
    )
    if boot_uuids_error:
        issues.append(boot_uuids_error)
    controls.update(_configured_esp_controls(boot_uuids_text, all_devices))
    firmware = run_readonly(["efibootmgr", "-v"])
    controls["firmware ESP A PARTUUID"] = (
        EXPECTED_ESP_PARTUUIDS[0] in firmware.stdout
        if firmware.returncode == 0
        else None
    )
    controls["firmware ESP B PARTUUID"] = (
        EXPECTED_ESP_PARTUUIDS[1] in firmware.stdout
        if firmware.returncode == 0
        else None
    )

    findmnt = run_readonly(["findmnt", "-rn", "-o", "MAJ:MIN"])
    mounted_devices = (
        set(findmnt.stdout.splitlines())
        if findmnt.returncode == 0 and findmnt.stdout.strip()
        else None
    )
    if mounted_devices is None:
        issues.append("findmnt device inventory failed")

    config_paths, config_error = (
        _pve_config_paths() if pve_live else (None, "PVE is not mounted")
    )
    if config_error:
        issues.append(config_error)
    system_paths = [
        Path("/etc/fstab"),
        Path("/etc/crypttab"),
        Path("/etc/zfs/zpool.cache"),
    ]
    for candidate in candidates.values():
        if len(candidate.whole_disks) != 1:
            candidate.references = {name: None for name in REFERENCE_CHECKS}
            continue
        device = candidate.whole_disks[0][0]
        rows = [row for row in all_devices if row.get("name") == device]
        if not rows:
            candidate.references = {name: None for name in REFERENCE_CHECKS}
            continue
        root_row = rows[0]
        candidate_paths = _block_paths(device, candidate.children or [])
        tokens = _candidate_tokens(candidate)

        mount_hits: list[str] | None
        if mounted_devices is None:
            mount_hits = None
        else:
            candidate_numbers = {
                str(row.get("maj:min"))
                for row in [root_row] + (candidate.children or [])
                if row.get("maj:min")
            }
            mount_hits = sorted(candidate_numbers & mounted_devices)

        swap_hits: list[str] | None = _swap_references(candidate_paths, tokens)
        holder_hits: list[str] | None = _holder_references(
            [root_row] + (candidate.children or [])
        )

        status_output = "\n".join(pool_statuses.values())
        pool_hits: list[str] | None = (
            _references_in_output(status_output, tokens)
            if {"rpool", "fast-vm"} <= pool_names
            and set(pool_statuses) == pool_names
            and pools_result.returncode == 0
            else None
        )
        import_hits: list[str] | None = (
            _references_in_output(import_result.stdout, tokens)
            if import_result.returncode == 0
            else None
        )
        config_hits: list[str] | None
        if config_paths is None:
            config_hits = None
        else:
            config_hits = _scan_paths(config_paths + system_paths, tokens)

        boot_output = "\n".join(
            output
            for output, available in (
                (boot_uuids_text, boot_uuids_text is not None),
                (firmware.stdout, firmware.returncode == 0),
            )
            if available and output is not None
        )
        firmware_hits: list[str] | None = (
            _references_in_output(boot_output, tokens)
            if boot_uuids_text is not None and firmware.returncode == 0
            else None
        )
        candidate.references = {
            "mounts": mount_hits,
            "swap": swap_hits,
            "holders": holder_hits,
            "imported pools": pool_hits,
            "importable pools": import_hits,
            "host configuration": config_hits,
            "firmware": firmware_hits,
        }
    return (
        PreflightEvidence(candidates, controls, scratch_collision, issues),
        observed_at,
        boot_id,
    )


def _print(report: Report) -> None:
    print("Read-only scratch candidate preflight; no disks or pool state are changed.")
    if report.observed_at:
        print(f"observed_at={report.observed_at}")
    if report.boot_id:
        print(f"boot_id={report.boot_id}")
    for finding in report.findings:
        print(f"{finding.state}: {finding.detail}")
    print(f"overall={report.state}")
    print(report.authorization_note)


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args:
        print("usage: check_scratch_preflight.py", file=sys.stderr)
        return 2
    if os.geteuid() != 0:
        print("UNKNOWN: run this read-only preflight as root on PVE", file=sys.stderr)
        return 1
    try:
        evidence, observed_at, boot_id = _collect()
    except (
        OSError,
        ValueError,
        ReadOnlyViolation,
        subprocess.SubprocessError,
    ) as error:
        evidence = PreflightEvidence(
            candidates={},
            controls={name: None for name in POSITIVE_CONTROLS},
            scratch_collision=None,
            collection_issues=[f"collector failed closed: {error}"],
        )
        observed_at = datetime.now().astimezone().isoformat(timespec="seconds")
        boot_id = None
    report = assess(evidence)
    report.observed_at = observed_at
    report.boot_id = boot_id
    _print(report)
    return 0 if report.state == "CLEAR" else 1


if __name__ == "__main__":
    raise SystemExit(main())
