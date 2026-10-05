#!/usr/bin/env python3
"""Validate the reviewed, serial-specific scratch-pool apply inputs."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path
from typing import Sequence, TypedDict


SERIAL_C = "PHHH8505034Q512H"
SERIAL_D = "BTHH8244042V512D"
INTERRUPTED_PLAN_SHA256 = (
    "9ecdfefbb0fdf8961491a76b6e309814d77c2a921fd6997f2b78983d6d0af762"
)
INTERRUPTED_FINDINGS_SHA256 = (
    "e5ea3fede8addeafb661b763cf4bfe21b43a4b9ff367bf483be2e28c1beccdc5"
)
INTERRUPTED_JOURNAL_PREDECESSORS = (
    (
        INTERRUPTED_PLAN_SHA256,
        INTERRUPTED_FINDINGS_SHA256,
        "labels-cleared",
    ),
    (
        "fb832d1e722ece4eec3ed068a86b67d31f60f40ae4acd3a10c8fe1ade4217c8d",
        "ec484023e39a961d2e7af45a8e9b2fe9eb6e4c2df5fc5c5524e6e42a5a3ebcd7",
        "zpool-create-started",
    ),
    (
        "e2b9109814b8fa292c11aaa95439e092c79b26b173df724bf07adbce844a7cfd",
        "ec484023e39a961d2e7af45a8e9b2fe9eb6e4c2df5fc5c5524e6e42a5a3ebcd7",
        "monitor-installed",
    ),
)
COMPLETED_JOURNAL_PREDECESSORS = (
    (
        "02c3dc82e93638383f4ef45c0bc9a6268e621207c782f0b769716f590d092a7c",
        "ec484023e39a961d2e7af45a8e9b2fe9eb6e4c2df5fc5c5524e6e42a5a3ebcd7",
        "complete",
    ),
)
CAPTURE_BYTES = 8 * 1024 * 1024


class RecoveryPartition(TypedDict):
    name: str
    size: int
    start: int
    parttype: str
    partlabel: str | None
    partuuid: str


class RecoveryDisk(TypedDict):
    device: str
    partitions: tuple[RecoveryPartition, RecoveryPartition]


RECOVERY_DISKS: dict[str, RecoveryDisk] = {
    SERIAL_C: {
        "device": "/dev/nvme4n1",
        "partitions": (
            {
                "name": "/dev/nvme4n1p1",
                "size": 512100401152,
                "start": 2048,
                "parttype": "6a898cc3-1dd2-11b2-99a6-080020736631",
                "partlabel": "zfs-fa68c08ad42041d8",
                "partuuid": "33ca00c2-6ae0-bc4e-b3f9-dc43f21ac3f6",
            },
            {
                "name": "/dev/nvme4n1p9",
                "size": 8388608,
                "start": 1000198144,
                "parttype": "6a945a3b-1dd2-11b2-99a6-080020736631",
                "partlabel": None,
                "partuuid": "80382b69-7eb9-6244-93fb-ca92d67f37a1",
            },
        ),
    },
    SERIAL_D: {
        "device": "/dev/nvme5n1",
        "partitions": (
            {
                "name": "/dev/nvme5n1p1",
                "size": 512100401152,
                "start": 2048,
                "parttype": "6a898cc3-1dd2-11b2-99a6-080020736631",
                "partlabel": "zfs-5ef8a3ce0cbbe874",
                "partuuid": "8282810a-6b21-fb4d-b529-bdb504349d2f",
            },
            {
                "name": "/dev/nvme5n1p9",
                "size": 8388608,
                "start": 1000198144,
                "parttype": "6a945a3b-1dd2-11b2-99a6-080020736631",
                "partlabel": None,
                "partuuid": "4bd505f5-419f-374d-a70c-9cf69f373f21",
            },
        ),
    },
}
EXPECTED_BLOCKS = (
    "BLOCK: PHHH8505034Q512H: partition or child devices remain: "
    "/dev/nvme4n1p1, /dev/nvme4n1p2, /dev/nvme4n1p3",
    "BLOCK: PHHH8505034Q512H: signature present on /dev/nvme4n1",
    "BLOCK: PHHH8505034Q512H: signature present on /dev/nvme4n1p1",
    "BLOCK: PHHH8505034Q512H: signature present on /dev/nvme4n1p2",
    "BLOCK: PHHH8505034Q512H: signature present on /dev/nvme4n1p3",
    "BLOCK: PHHH8505034Q512H: non-zero unsigned bytes in first 8 MiB; review required",
    "BLOCK: PHHH8505034Q512H: non-zero unsigned bytes in last 8 MiB; review required",
    "BLOCK: PHHH8505034Q512H: importable pools reference found: "
    "14828205673918207700, nvme-eui.0000000001000000e4d25c1a03645001, "
    "rpool-OLD-14828205673918207700",
    "BLOCK: BTHH8244042V512D: non-zero unsigned bytes in last 8 MiB; review required",
)
REQUIRED_CLEAR_FINDINGS: tuple[str, ...] = (
    f"CLEAR: {SERIAL_C}: lsblk serial and by-id alias agree on /dev/nvme4n1",
    f"CLEAR: {SERIAL_D}: lsblk serial and by-id alias agree on /dev/nvme5n1",
    f"CLEAR: {SERIAL_C}: SMART health and required error/spare fields pass",
    f"CLEAR: {SERIAL_D}: SMART health and required error/spare fields pass",
    "CLEAR: positive control present: imported rpool",
    "CLEAR: positive control present: imported fast-vm",
    "CLEAR: positive control present: rpool member BTHH95021LD4512D",
    "CLEAR: positive control present: rpool member BTHH8122061E512D",
    "CLEAR: positive control present: fast-vm member PHHH829001A91P0E",
    "CLEAR: positive control present: fast-vm member PHHH828600761P0E",
    "CLEAR: positive control present: mounted /etc/pve",
    "CLEAR: positive control present: fast-vm storage entry",
    "CLEAR: positive control present: Proxmox ESP A filesystem UUID",
    "CLEAR: positive control present: Proxmox ESP B filesystem UUID",
    "CLEAR: positive control present: firmware ESP A PARTUUID",
    "CLEAR: positive control present: firmware ESP B PARTUUID",
    "CLEAR: no scratch pool or PVE storage ID exists",
)
for _serial in (SERIAL_C, SERIAL_D):
    for _reference in (
        "mounts",
        "swap",
        "holders",
        "imported pools",
        "importable pools",
        "host configuration",
        "firmware",
    ):
        REQUIRED_CLEAR_FINDINGS += (
            f"CLEAR: {_serial}: no {_reference} reference found",
        )

CAPTURES = (
    (
        SERIAL_C,
        "whole",
        "first",
        "b2ec4c876b4dc34fe195e3aae3e7f7153070ee8abbde3f5dad855b716519e7c6",
        "scratch-boundary-capture-2010/PHHH8505034Q512H-first-8MiB.bin",
    ),
    (
        SERIAL_C,
        "whole",
        "last",
        "7f5c5d8cb1c1bcd52adc39622a008d1bab7696eb61dd91367157208019088c41",
        "scratch-boundary-capture-2010/PHHH8505034Q512H-last-8MiB.bin",
    ),
    (
        SERIAL_D,
        "whole",
        "first",
        "2daeb1f36095b44b318410b3f4e8b5d989dcc7bb023d1426c492dab0a3053e74",
        "scratch-boundary-capture-2010/BTHH8244042V512D-first-8MiB.bin",
    ),
    (
        SERIAL_D,
        "whole",
        "last",
        "e92c13df072c73f2722c8de2b057c21ce00fba8f0ef78e3d4f201d94b14618ce",
        "scratch-boundary-capture-2010/BTHH8244042V512D-last-8MiB.bin",
    ),
    (
        SERIAL_C,
        "p3",
        "first",
        "f1f43a5f22cc6c614e6edd88bc9c95f6f8fce1a2c7f10cebdd902dd9f131cdd6",
        "scratch-label-capture-20261004/PHHH8505034Q512H-p3-first-8MiB.bin",
    ),
    (
        SERIAL_C,
        "p3",
        "last",
        "78ff364a53c865bb96b249378102d08694e25747648fc383585e4a37d4d3863c",
        "scratch-label-capture-20261004/PHHH8505034Q512H-p3-last-8MiB.bin",
    ),
)


class PlanError(ValueError):
    """Raised when a destructive apply input differs from the reviewed plan."""


def validate_transaction_journal(
    text: str,
    expected_plan: str,
    expected_boot: str,
    expected_findings: str,
    operation: str,
) -> tuple[str, str, str, str, bool]:
    fields = text.splitlines()
    if len(fields) != 7 or fields[0] != "format=scratch-apply-plan-v1":
        raise PlanError("scratch transaction journal format is invalid")
    values = {}
    for line in fields[1:]:
        key, separator, value = line.partition("=")
        if not separator or key in values:
            raise PlanError("scratch transaction journal fields are malformed")
        values[key] = value
    if set(values) != {
        "plan_sha256",
        "boot_id",
        "serial_c",
        "serial_d",
        "findings_sha256",
        "phase",
    }:
        raise PlanError("scratch transaction journal fields are unexpected")

    recorded_plan = values["plan_sha256"]
    recorded_boot = values["boot_id"]
    recorded_findings = values["findings_sha256"]
    phase = values["phase"]
    if re.fullmatch(r"[0-9a-f]{64}", recorded_plan) is None:
        raise PlanError("scratch transaction plan hash is malformed")
    if (
        re.fullmatch(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            recorded_boot,
        )
        is None
    ):
        raise PlanError("scratch transaction boot ID is malformed")
    if re.fullmatch(r"[0-9a-f]{64}", recorded_findings) is None:
        raise PlanError("scratch transaction findings hash is malformed")
    if values["serial_c"] != SERIAL_C or values["serial_d"] != SERIAL_D:
        raise PlanError(
            "scratch transaction serials differ from the reviewed candidates"
        )
    if phase not in {
        "prepared",
        "labels-cleared",
        "zpool-create-started",
        "pool-created",
        "dataset-created",
        "monitor-installed",
        "storage-registered",
        "complete",
        "rolled-back",
    }:
        raise PlanError("scratch transaction phase is unsupported")
    if operation not in {"preview", "check", "apply", "rollback"}:
        raise PlanError("scratch transaction operation is unsupported")
    if expected_boot and recorded_boot != expected_boot:
        raise PlanError("scratch transaction boot ID differs from the reviewed plan")
    if expected_findings and re.fullmatch(r"[0-9a-f]{64}", expected_findings) is None:
        raise PlanError("reviewed findings hash is malformed")

    predecessor = recorded_plan != expected_plan
    if predecessor:
        journal_identity = (recorded_plan, recorded_findings, phase)
        completed_read = (
            phase == "complete"
            and operation in {"preview", "check"}
            and journal_identity in COMPLETED_JOURNAL_PREDECESSORS
        )
        interrupted_resume = (
            phase != "complete"
            and operation != "rollback"
            and journal_identity in INTERRUPTED_JOURNAL_PREDECESSORS
        )
        if not completed_read and not interrupted_resume:
            raise PlanError(
                "scratch transaction journal plan differs from the reviewed plan"
            )
    elif phase != "labels-cleared" or operation == "rollback":
        if expected_findings and recorded_findings != expected_findings:
            raise PlanError(
                "scratch transaction findings hash differs from the reviewed plan"
            )

    return recorded_plan, recorded_boot, recorded_findings, phase, predecessor


def validate_preflight(text: str, exit_code: int) -> tuple[str, str]:
    if exit_code != 1:
        raise PlanError(
            f"preflight exit status must be 1 for the reviewed BLOCK state, got {exit_code}"
        )

    lines = text.splitlines()
    boot_ids = [
        line.removeprefix("boot_id=") for line in lines if line.startswith("boot_id=")
    ]
    states = [line for line in lines if line.startswith("overall=")]
    findings = [
        line for line in lines if line.startswith(("CLEAR:", "BLOCK:", "UNKNOWN:"))
    ]
    blocks = tuple(sorted(line for line in findings if line.startswith("BLOCK:")))

    if (
        len(boot_ids) != 1
        or re.fullmatch(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            boot_ids[0],
        )
        is None
    ):
        raise PlanError("preflight must contain one valid boot_id")
    if states != ["overall=BLOCK"]:
        raise PlanError("preflight must report exactly overall=BLOCK")
    if any(line.startswith("UNKNOWN:") for line in findings):
        raise PlanError("preflight contains UNKNOWN findings")
    if blocks != tuple(sorted(EXPECTED_BLOCKS)):
        raise PlanError(
            "preflight BLOCK findings differ from the reviewed serial-specific set"
        )
    missing = sorted(set(REQUIRED_CLEAR_FINDINGS) - set(findings))
    if missing:
        raise PlanError(f"preflight is missing required CLEAR evidence: {missing!r}")

    findings_text = "\n".join(findings) + "\n"
    findings_sha256 = hashlib.sha256(findings_text.encode()).hexdigest()
    return boot_ids[0], findings_sha256


def validate_recovery_layout(serial: str, expected_device: str, text: str) -> str:
    expected = RECOVERY_DISKS.get(serial)
    if expected is None or expected["device"] != expected_device:
        raise PlanError("recovery layout requested for an unreviewed serial or path")
    try:
        devices = json.loads(text)["blockdevices"]
    except (json.JSONDecodeError, KeyError, TypeError) as error:
        raise PlanError("recovery layout is not valid lsblk JSON") from error
    if not isinstance(devices, list) or len(devices) != 1:
        raise PlanError("recovery layout must contain exactly one candidate disk")
    disk = devices[0]
    if (
        not isinstance(disk, dict)
        or disk.get("name") != expected_device
        or disk.get("type") != "disk"
        or disk.get("serial") != serial
        or disk.get("size") != 512110190592
        or disk.get("fstype") is not None
    ):
        raise PlanError("recovery layout disk identity or size differs from review")
    children = disk.get("children") or []
    if not isinstance(children, list):
        raise PlanError("recovery layout children are malformed")
    if not children:
        return "clean"
    if len(children) != 2:
        raise PlanError("recovery layout contains unexpected partition nodes")
    for actual, wanted in zip(children, expected["partitions"], strict=True):
        if not isinstance(actual, dict):
            raise PlanError("recovery layout partition row is malformed")
        for key, value in wanted.items():
            if actual.get(key) != value:
                raise PlanError(
                    "recovery layout partition differs from exact generated GPT"
                )
        if actual.get("type") != "part" or actual.get("fstype") is not None:
            raise PlanError(
                "recovery layout partition contains an unexpected content type"
            )
    return "generated"


def validate_recovery_signatures(text: str, device: str, kind: str) -> None:
    try:
        signatures = json.loads(text)["signatures"]
    except (json.JSONDecodeError, KeyError, TypeError) as error:
        raise PlanError("recovery wipefs result is not valid JSON") from error
    if not isinstance(signatures, list):
        raise PlanError("recovery wipefs signatures are malformed")
    if kind == "generated-disk":
        expected = sorted(
            (
                (Path(device).name, "gpt", "0x200", "partition-table", ""),
                (Path(device).name, "gpt", "0x773c255e00", "partition-table", ""),
                (Path(device).name, "PMBR", "0x1fe", "partition-table", ""),
            )
        )
    elif kind in {"clean-disk", "partition"}:
        expected = []
    else:
        raise PlanError("recovery wipefs check has an unsupported target kind")
    required_fields = {"device", "type", "offset", "usage", "uuid"}
    if any(
        not isinstance(row, dict)
        or set(row) != required_fields
        or any(
            not isinstance(row[key], str)
            for key in ("device", "type", "offset", "usage")
        )
        or (row["uuid"] is not None and not isinstance(row["uuid"], str))
        for row in signatures
    ):
        raise PlanError("recovery wipefs signature row is malformed")
    actual = sorted(
        (
            row["device"],
            row["type"],
            row["offset"],
            row["usage"],
            row["uuid"] or "",
        )
        for row in signatures
    )
    if kind == "partition" and actual:
        raise PlanError("recovery partition has an unexpected signature")
    if actual != expected:
        raise PlanError("recovery wipefs signature set differs from review")


def validate_recovery_preflight(
    text: str, exit_code: int, layouts: dict[str, str]
) -> tuple[str, str]:
    lines = text.splitlines()
    boot_ids = [
        line.removeprefix("boot_id=") for line in lines if line.startswith("boot_id=")
    ]
    states = [line for line in lines if line.startswith("overall=")]
    findings = [
        line for line in lines if line.startswith(("CLEAR:", "BLOCK:", "UNKNOWN:"))
    ]
    if (
        len(boot_ids) != 1
        or re.fullmatch(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            boot_ids[0],
        )
        is None
    ):
        raise PlanError("recovery preflight must contain one valid boot_id")
    if any(line.startswith("UNKNOWN:") for line in findings):
        raise PlanError("recovery preflight contains UNKNOWN findings")
    if set(layouts) != {SERIAL_C, SERIAL_D} or any(
        layout not in {"clean", "generated"} for layout in layouts.values()
    ):
        raise PlanError("recovery preflight layout classification is incomplete")

    expected = set(REQUIRED_CLEAR_FINDINGS)
    for serial, layout in layouts.items():
        device = RECOVERY_DISKS[serial]["device"]
        if layout == "clean":
            expected.add(f"CLEAR: {serial}: no child devices reported")
            expected.add(f"CLEAR: {serial}: no blkid signature reported on {device}")
        else:
            part1, part9 = (row["name"] for row in RECOVERY_DISKS[serial]["partitions"])
            expected.add(
                f"BLOCK: {serial}: partition or child devices remain: {part1}, {part9}"
            )
            expected.update(
                f"BLOCK: {serial}: signature present on {node}"
                for node in (device, part1, part9)
            )

    boundary_findings: set[str] = set()
    for serial in (SERIAL_C, SERIAL_D):
        for region in ("first", "last"):
            matches = [
                line
                for line in findings
                if re.fullmatch(
                    rf"(?:CLEAR: {serial}: {region} 8 MiB are zero \(sha256 [0-9a-f]{{64}}\)|"
                    rf"BLOCK: {serial}: non-zero unsigned bytes in {region} 8 MiB; review required)",
                    line,
                )
            ]
            if len(matches) != 1:
                raise PlanError(
                    "recovery preflight boundary findings are incomplete or duplicated"
                )
            boundary_findings.add(matches[0])

    expected_findings = expected | boundary_findings
    actual_findings = set(findings)
    unexpected = actual_findings - expected_findings
    if unexpected:
        raise PlanError(
            f"recovery preflight contains unexpected findings: {sorted(unexpected)!r}"
        )
    if len(findings) != len(expected_findings) or actual_findings != expected_findings:
        raise PlanError(
            "recovery preflight findings differ from exact layouts and references"
        )
    blocks = [line for line in findings if line.startswith("BLOCK:")]
    expected_state = "overall=BLOCK" if blocks else "overall=CLEAR"
    expected_exit = 1 if blocks else 0
    if states != [expected_state] or exit_code != expected_exit:
        raise PlanError("recovery preflight state and exit status do not agree")
    findings_sha256 = hashlib.sha256(("\n".join(findings) + "\n").encode()).hexdigest()
    return boot_ids[0], findings_sha256


def capture_manifest_text() -> str:
    return "".join(
        f"{serial}\t{target}\t{region}\t{digest}\n"
        for serial, target, region, digest, _ in CAPTURES
    )


def validate_capture_manifest(text: str) -> None:
    if text != capture_manifest_text():
        raise PlanError(
            "capture manifest differs from the six reviewed off-target hashes"
        )


def validate_zpool_status(text: str, whole_c: str, whole_d: str) -> None:
    states = [
        line.split(":", 1)[1].strip()
        for line in text.splitlines()
        if line.lstrip().startswith("state:")
    ]
    errors = [
        line.split(":", 1)[1].strip()
        for line in text.splitlines()
        if line.lstrip().startswith("errors:")
    ]
    lines = text.splitlines()
    config_indexes = [
        index for index, line in enumerate(lines) if line.strip() == "config:"
    ]
    error_indexes = [
        index for index, line in enumerate(lines) if line.lstrip().startswith("errors:")
    ]
    if len(config_indexes) != 1 or len(error_indexes) != 1:
        raise PlanError("scratch zpool topology table is missing or ambiguous")
    config_index, error_index = config_indexes[0], error_indexes[0]
    if config_index >= error_index:
        raise PlanError("scratch zpool topology table has invalid boundaries")

    topology_rows = []
    header_count = 0
    for line in lines[config_index + 1 : error_index]:
        fields = line.split()
        if not fields:
            continue
        if fields[0] == "NAME":
            if fields != ["NAME", "STATE", "READ", "WRITE", "CKSUM"]:
                raise PlanError("scratch zpool topology header is unexpected")
            header_count += 1
            continue
        if len(fields) != 5:
            raise PlanError("scratch zpool topology row is malformed")
        if fields[2:] != ["0", "0", "0"]:
            raise PlanError("scratch zpool topology has nonzero or malformed error counters")
        indentation = line[: len(line) - len(line.lstrip())]
        expanded_indentation = indentation.expandtabs(8)
        if (
            any(character != " " for character in expanded_indentation)
            or len(expanded_indentation) % 2
        ):
            raise PlanError("scratch zpool topology indentation is malformed")
        depth = len(expanded_indentation)
        topology_rows.append((depth, fields))
    if header_count != 1:
        raise PlanError("scratch zpool topology header is missing or ambiguous")

    roots = [row for row in topology_rows if row[1][0] == "scratch"]
    if len(roots) != 1:
        raise PlanError("scratch zpool topology root is missing or ambiguous")
    root_indent = roots[0][0]
    members = [row for row in topology_rows if row[1][0].startswith("/dev/")]
    if any(
        name != "scratch" and not name.startswith("/dev/")
        for _, (name, *_) in topology_rows
    ):
        raise PlanError("scratch zpool topology contains an unexpected vdev layer")
    if roots[0][1][1] != "ONLINE" or any(
        fields[1] != "ONLINE" or indent != root_indent + 2
        for indent, fields in members
    ):
        raise PlanError("scratch stripe members are not direct ONLINE children")

    for line in lines:
        fields = line.split()
        if (
            fields
            and fields[0].startswith("/dev/")
            and not any(
                fields[:2] == member_fields[:2] for _, member_fields in members
            )
        ):
            raise PlanError(
                "scratch zpool has a device leaf outside its topology table"
            )

    expected = sorted(((f"{whole_c}-part1", "ONLINE"), (f"{whole_d}-part1", "ONLINE")))
    if states != ["ONLINE"] or errors != ["No known data errors"]:
        raise PlanError("scratch zpool status is not healthy")
    if sorted(tuple(fields[:2]) for _, fields in members) != expected:
        raise PlanError(
            "scratch zpool is not the exact two-device stripe from expected partition paths"
        )


def validate_zdb_config(text: str, whole_c: str, whole_d: str) -> None:
    lines = text.splitlines()
    child_counts = [
        match.group(1)
        for line in lines
        if (match := re.fullmatch(r"\s*vdev_children:\s*([0-9]+)\s*", line))
    ]
    child_indexes = [
        int(match.group(1))
        for line in lines
        if (match := re.fullmatch(r"\s*children\[([0-9]+)\]:\s*", line))
    ]
    if child_counts and child_counts != ["2"]:
        raise PlanError("scratch zdb config does not declare exactly two children")
    if child_indexes and sorted(child_indexes) != [0, 1]:
        raise PlanError("scratch zdb config child indexes are not exactly 0 and 1")

    path_rows = []
    for index, line in enumerate(lines):
        match = re.fullmatch(r"\s*path:\s*'([^']+)'\s*", line)
        if match:
            path_rows.append((index, match.group(1)))

    expected = sorted((f"{whole_c}-part1", f"{whole_d}-part1"))
    if sorted(path for _, path in path_rows) != expected:
        raise PlanError("scratch zdb config does not contain the exact two expected member paths")

    all_ashifts = [
        match.group(1)
        for line in lines
        if (match := re.fullmatch(r"\s*ashift:\s*([0-9]+)\s*", line))
    ]
    if len(all_ashifts) != 2:
        raise PlanError("scratch zdb config must report ashift once for each member")

    for position, (index, _) in enumerate(path_rows):
        end = path_rows[position + 1][0] if position + 1 < len(path_rows) else len(lines)
        member_lines = lines[index:end]
        ashifts = [
            match.group(1)
            for line in member_lines
            if (match := re.fullmatch(r"\s*ashift:\s*([0-9]+)\s*", line))
        ]
        types = [
            match.group(1)
            for line in member_lines
            if (match := re.fullmatch(r"\s*type:\s*'([^']+)'\s*", line))
        ]
        log_flags = [
            match.group(1)
            for line in member_lines
            if (match := re.fullmatch(r"\s*is_log:\s*([0-9]+)\s*", line))
        ]
        if ashifts != ["12"]:
            raise PlanError("scratch zdb member ashift is not exactly 12")
        if types and types != ["disk"]:
            raise PlanError("scratch zdb member is not a disk vdev")
        if any(value != "0" for value in log_flags):
            raise PlanError("scratch zdb member is a log vdev")


def validate_empty_pvesm_listing(text: str) -> None:
    lines = [line.split() for line in text.splitlines() if line.strip()]
    if not lines or lines[0] != ["Volid", "Format", "Type", "Size", "VMID"]:
        raise PlanError("PVE storage volume listing has an unexpected header")

    for fields in lines[1:]:
        if (
            len(fields) != 5
            or not re.fullmatch(r"[0-9]+", fields[3])
            or (fields[4] != "-" and not re.fullmatch(r"[0-9]+", fields[4]))
        ):
            raise PlanError("PVE storage volume listing contains a malformed row")
        raise PlanError("scratch storage contains volumes; refusing config rollback")


def validate_scratch_storage_content(text: str) -> None:
    directives = []
    for line in text.splitlines():
        fields = line.split()
        if fields and fields[0] == "content":
            directives.append(fields)
    if len(directives) != 1 or len(directives[0]) != 2:
        raise PlanError("PVE scratch storage must have exactly one content directive")
    if directives[0][1] not in {"images,rootdir", "rootdir,images"}:
        raise PlanError(
            "PVE scratch storage content must be exactly images and rootdir"
        )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_capture_manifest(evidence_dir: Path) -> str:
    if evidence_dir.is_symlink() or not evidence_dir.is_dir():
        raise PlanError("evidence directory must be a real directory")
    evidence_stat = evidence_dir.stat()
    if stat.S_IMODE(evidence_stat.st_mode) != 0o700:
        raise PlanError("evidence directory must have mode 0700")
    if evidence_stat.st_uid != os.getuid():
        raise PlanError("evidence directory must be owned by the current user")

    for serial, target, region, expected_hash, relative_path in CAPTURES:
        path = evidence_dir / relative_path
        parent = path.parent
        if parent.is_symlink() or not parent.is_dir():
            raise PlanError(
                f"capture directory must be a real directory: {relative_path}"
            )
        if stat.S_IMODE(parent.stat().st_mode) != 0o700:
            raise PlanError(f"capture directory must have mode 0700: {relative_path}")
        if parent.stat().st_uid != os.getuid():
            raise PlanError(
                f"capture directory must be owned by the current user: {relative_path}"
            )
        if path.is_symlink() or not path.is_file():
            raise PlanError(
                f"capture must be a regular non-symlink file: {relative_path}"
            )
        capture_stat = path.stat()
        if stat.S_IMODE(capture_stat.st_mode) != 0o600:
            raise PlanError(f"capture must have mode 0600: {relative_path}")
        if capture_stat.st_uid != os.getuid():
            raise PlanError(
                f"capture must be owned by the current user: {relative_path}"
            )
        if capture_stat.st_size != CAPTURE_BYTES:
            raise PlanError(f"capture must be exactly 8 MiB: {relative_path}")
        if _sha256_file(path) != expected_hash:
            raise PlanError(f"capture hash changed: {relative_path}")

    return capture_manifest_text()


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)

    def read_text(path: str) -> str:
        if path == "-":
            return sys.stdin.read()
        return Path(path).read_text(encoding="utf-8")

    if len(args) == 2 and args[0] == "capture-manifest":
        try:
            print(build_capture_manifest(Path(args[1])), end="")
        except (OSError, PlanError) as error:
            print(f"scratch apply plan: {error}", file=sys.stderr)
            return 1
        return 0
    if len(args) == 2 and args[0] == "validate-capture-manifest":
        try:
            validate_capture_manifest(Path(args[1]).read_text(encoding="utf-8"))
        except (OSError, PlanError) as error:
            print(f"scratch apply plan: {error}", file=sys.stderr)
            return 1
        print("capture manifest PASS")
        return 0
    if len(args) == 3 and args[0] == "validate-preflight":
        try:
            boot_id, findings_sha256 = validate_preflight(
                read_text(args[1]), int(args[2])
            )
        except (OSError, ValueError) as error:
            print(f"scratch apply plan: {error}", file=sys.stderr)
            return 1
        print(f"boot_id={boot_id}")
        print(f"findings_sha256={findings_sha256}")
        return 0
    if len(args) == 6 and args[0] == "validate-transaction-journal":
        try:
            values = validate_transaction_journal(
                read_text(args[5]), args[1], args[2], args[3], args[4]
            )
        except (OSError, ValueError) as error:
            print(f"scratch apply plan: {error}", file=sys.stderr)
            return 1
        plan_sha256, boot_id, findings_sha256, phase, predecessor = values
        print(f"plan_sha256={plan_sha256}")
        print(f"boot_id={boot_id}")
        print(f"findings_sha256={findings_sha256}")
        print(f"phase={phase}")
        print(f"predecessor={'true' if predecessor else 'false'}")
        return 0
    if len(args) == 5 and args[0] == "validate-recovery-preflight":
        try:
            boot_id, findings_sha256 = validate_recovery_preflight(
                read_text(args[1]),
                int(args[2]),
                {SERIAL_C: args[3], SERIAL_D: args[4]},
            )
        except (OSError, ValueError) as error:
            print(f"scratch apply plan: {error}", file=sys.stderr)
            return 1
        print(f"boot_id={boot_id}")
        print(f"findings_sha256={findings_sha256}")
        return 0
    if len(args) == 4 and args[0] == "validate-recovery-layout":
        try:
            state = validate_recovery_layout(args[1], args[2], read_text(args[3]))
        except (OSError, PlanError) as error:
            print(f"scratch apply plan: {error}", file=sys.stderr)
            return 1
        print(f"layout={state}")
        return 0
    if len(args) == 4 and args[0] == "validate-recovery-signatures":
        try:
            validate_recovery_signatures(read_text(args[3]), args[1], args[2])
        except (OSError, PlanError) as error:
            print(f"scratch apply plan: {error}", file=sys.stderr)
            return 1
        print("recovery signatures PASS")
        return 0
    if len(args) == 4 and args[0] == "validate-zpool-status":
        try:
            validate_zpool_status(read_text(args[1]), args[2], args[3])
        except (OSError, PlanError) as error:
            print(f"scratch apply plan: {error}", file=sys.stderr)
            return 1
        print("zpool status PASS")
        return 0
    if len(args) == 4 and args[0] == "validate-zdb-config":
        try:
            validate_zdb_config(read_text(args[1]), args[2], args[3])
        except (OSError, PlanError) as error:
            print(f"scratch apply plan: {error}", file=sys.stderr)
            return 1
        print("zdb config PASS")
        return 0
    if len(args) == 2 and args[0] == "validate-empty-pvesm-list":
        try:
            validate_empty_pvesm_listing(read_text(args[1]))
        except (OSError, PlanError) as error:
            print(f"scratch apply plan: {error}", file=sys.stderr)
            return 1
        print("PVE storage volume listing is empty")
        return 0
    if len(args) == 2 and args[0] == "validate-scratch-storage-content":
        try:
            validate_scratch_storage_content(read_text(args[1]))
        except (OSError, PlanError) as error:
            print(f"scratch apply plan: {error}", file=sys.stderr)
            return 1
        print("PVE scratch storage content PASS")
        return 0
    print(
        "usage: check_scratch_apply_plan.py "
        "capture-manifest EVIDENCE_DIR | validate-capture-manifest FILE | "
        "validate-preflight FILE EXIT_STATUS | "
        "validate-transaction-journal EXPECTED_PLAN EXPECTED_BOOT EXPECTED_FINDINGS OPERATION FILE|- | "
        "validate-recovery-preflight FILE|- EXIT_STATUS C_LAYOUT D_LAYOUT | "
        "validate-recovery-layout SERIAL DEVICE FILE|- | "
        "validate-recovery-signatures DEVICE KIND FILE|- | "
        "validate-zpool-status FILE|- WHOLE_C WHOLE_D | "
        "validate-zdb-config FILE|- WHOLE_C WHOLE_D | "
        "validate-empty-pvesm-list FILE|- | "
        "validate-scratch-storage-content FILE|-",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
