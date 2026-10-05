#!/usr/bin/env python3
import hashlib
import importlib.util
import json
import os
import sys
import tempfile
from unittest.mock import patch
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "check_scratch_apply_plan.py"
spec = importlib.util.spec_from_file_location("check_scratch_apply_plan", SCRIPT)
assert spec is not None and spec.loader is not None
plan = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = plan
spec.loader.exec_module(plan)


def report(
    blocks=None,
    additions=(),
    boot_id="b478c236-f6fe-4490-852e-868339e84ffd",
):
    findings = list(plan.REQUIRED_CLEAR_FINDINGS)
    findings.extend(blocks if blocks is not None else plan.EXPECTED_BLOCKS)
    findings.extend(additions)
    return "\n".join(
        [
            "Read-only scratch candidate preflight; no disks or pool state are changed.",
            "observed_at=2026-10-04T11:39:53-04:00",
            f"boot_id={boot_id}",
            *findings,
            "overall=BLOCK",
            "CLEAR is a time-bound host-state preflight, not authorization.",
        ]
    )


class ScratchApplyPlanTests(unittest.TestCase):
    whole_c = "/dev/disk/by-id/nvme-INTEL_SSDPEKKF512G8_PHHH8505034Q512H_1"
    whole_d = "/dev/disk/by-id/nvme-INTEL_SSDPEKKF512G8_BTHH8244042V512D_1"
    recovery_devices = {
        plan.SERIAL_C: (
            "/dev/nvme4n1",
            "33ca00c2-6ae0-bc4e-b3f9-dc43f21ac3f6",
            "80382b69-7eb9-6244-93fb-ca92d67f37a1",
            "zfs-fa68c08ad42041d8",
        ),
        plan.SERIAL_D: (
            "/dev/nvme5n1",
            "8282810a-6b21-fb4d-b529-bdb504349d2f",
            "4bd505f5-419f-374d-a70c-9cf69f373f21",
            "zfs-5ef8a3ce0cbbe874",
        ),
    }

    def recovery_layout(self, serial, *, generated=True):
        device, p1_uuid, p9_uuid, label = self.recovery_devices[serial]
        root = {
            "name": device,
            "type": "disk",
            "serial": serial,
            "size": 512110190592,
            "fstype": None,
        }
        if generated:
            root["children"] = [
                {
                    "name": f"{device}p1",
                    "type": "part",
                    "size": 512100401152,
                    "start": 2048,
                    "parttype": "6a898cc3-1dd2-11b2-99a6-080020736631",
                    "partlabel": label,
                    "partuuid": p1_uuid,
                    "fstype": None,
                },
                {
                    "name": f"{device}p9",
                    "type": "part",
                    "size": 8388608,
                    "start": 1000198144,
                    "parttype": "6a945a3b-1dd2-11b2-99a6-080020736631",
                    "partlabel": None,
                    "partuuid": p9_uuid,
                    "fstype": None,
                },
            ]
        return json.dumps({"blockdevices": [root]})

    def generated_gpt_signatures(self, device):
        name = Path(device).name
        return json.dumps(
            {
                "signatures": [
                    {
                        "device": name,
                        "type": "gpt",
                        "offset": "0x200",
                        "usage": "partition-table",
                        "uuid": None,
                    },
                    {
                        "device": name,
                        "type": "gpt",
                        "offset": "0x773c255e00",
                        "usage": "partition-table",
                        "uuid": None,
                    },
                    {
                        "device": name,
                        "type": "PMBR",
                        "offset": "0x1fe",
                        "usage": "partition-table",
                        "uuid": None,
                    },
                ]
            }
        )

    def journal_text(
        self,
        *,
        plan_sha=None,
        findings_sha=None,
        phase="labels-cleared",
        serial_c=None,
        boot_id="b478c236-f6fe-4490-852e-868339e84ffd",
    ):
        return "\n".join(
            (
                "format=scratch-apply-plan-v1",
                f"plan_sha256={plan_sha or plan.INTERRUPTED_PLAN_SHA256}",
                f"boot_id={boot_id}",
                f"serial_c={serial_c or plan.SERIAL_C}",
                f"serial_d={plan.SERIAL_D}",
                f"findings_sha256={findings_sha or plan.INTERRUPTED_FINDINGS_SHA256}",
                f"phase={phase}",
            )
        )

    def test_transaction_journal_allows_only_exact_interrupted_predecessor(self):
        current_plan = "a" * 64
        values = plan.validate_transaction_journal(
            self.journal_text(), current_plan, "", "b" * 64, "preview"
        )
        self.assertEqual(
            values,
            (
                plan.INTERRUPTED_PLAN_SHA256,
                "b478c236-f6fe-4490-852e-868339e84ffd",
                plan.INTERRUPTED_FINDINGS_SHA256,
                "labels-cleared",
                True,
            ),
        )
        for text, operation, expected_boot, message in (
            (self.journal_text(findings_sha="c" * 64), "preview", "", "plan differs"),
            (self.journal_text(phase="prepared"), "preview", "", "plan differs"),
            (self.journal_text(), "rollback", "", "plan differs"),
            (self.journal_text(serial_c="X" * 16), "preview", "", "serials differ"),
            (self.journal_text(), "preview", "0" * 36, "boot ID differs"),
        ):
            with (
                self.subTest(message=message),
                self.assertRaisesRegex(plan.PlanError, message),
            ):
                plan.validate_transaction_journal(
                    text, current_plan, expected_boot, "", operation
                )

    def test_current_labels_cleared_journal_rebinds_fresh_recovery_findings(self):
        current_plan = "d" * 64
        values = plan.validate_transaction_journal(
            self.journal_text(plan_sha=current_plan),
            current_plan,
            "b478c236-f6fe-4490-852e-868339e84ffd",
            "e" * 64,
            "apply",
        )
        self.assertFalse(values[-1])
        rollback = plan.validate_transaction_journal(
            self.journal_text(plan_sha=current_plan),
            current_plan,
            "",
            plan.INTERRUPTED_FINDINGS_SHA256,
            "rollback",
        )
        self.assertEqual(rollback[3], "labels-cleared")
        with self.assertRaisesRegex(plan.PlanError, "findings hash differs"):
            plan.validate_transaction_journal(
                self.journal_text(plan_sha=current_plan, phase="pool-created"),
                current_plan,
                "",
                "e" * 64,
                "apply",
            )

    def test_transaction_journal_allows_exact_interrupted_pool_creation(self):
        current_plan = "f" * 64
        previous_plan = (
            "fb832d1e722ece4eec3ed068a86b67d31f60f40ae4acd3a10c8fe1ade4217c8d"
        )
        previous_findings = (
            "ec484023e39a961d2e7af45a8e9b2fe9eb6e4c2df5fc5c5524e6e42a5a3ebcd7"
        )
        text = self.journal_text(
            plan_sha=previous_plan,
            findings_sha=previous_findings,
            phase="zpool-create-started",
        )
        values = plan.validate_transaction_journal(
            text, current_plan, "", previous_findings, "preview"
        )
        self.assertEqual(values[0], previous_plan)
        self.assertEqual(values[2:], (previous_findings, "zpool-create-started", True))
        for changed_text in (
            self.journal_text(
                plan_sha=previous_plan,
                findings_sha="c" * 64,
                phase="zpool-create-started",
            ),
            self.journal_text(
                plan_sha=previous_plan,
                findings_sha=previous_findings,
                phase="pool-created",
            ),
        ):
            with self.assertRaisesRegex(plan.PlanError, "plan differs"):
                plan.validate_transaction_journal(
                    changed_text, current_plan, "", "", "preview"
                )

    def test_transaction_journal_allows_exact_monitor_installed_predecessor(self):
        current_plan = "9" * 64
        previous_plan = (
            "e2b9109814b8fa292c11aaa95439e092c79b26b173df724bf07adbce844a7cfd"
        )
        previous_findings = (
            "ec484023e39a961d2e7af45a8e9b2fe9eb6e4c2df5fc5c5524e6e42a5a3ebcd7"
        )
        text = self.journal_text(
            plan_sha=previous_plan,
            findings_sha=previous_findings,
            phase="monitor-installed",
        )
        values = plan.validate_transaction_journal(
            text, current_plan, "", previous_findings, "preview"
        )
        self.assertEqual(values[0], previous_plan)
        self.assertEqual(values[2:], (previous_findings, "monitor-installed", True))
        for changed_text in (
            self.journal_text(
                plan_sha=previous_plan,
                findings_sha="d" * 64,
                phase="monitor-installed",
            ),
            self.journal_text(
                plan_sha=previous_plan,
                findings_sha=previous_findings,
                phase="storage-registered",
            ),
        ):
            with self.assertRaisesRegex(plan.PlanError, "plan differs"):
                plan.validate_transaction_journal(
                    changed_text, current_plan, "", "", "preview"
                )

    def test_completed_transaction_predecessor_is_read_only(self):
        current_plan = "a" * 64
        previous_plan, previous_findings, phase = (
            plan.COMPLETED_JOURNAL_PREDECESSORS[0]
        )
        text = self.journal_text(
            plan_sha=previous_plan,
            findings_sha=previous_findings,
            phase=phase,
        )
        for operation in ("preview", "check"):
            with self.subTest(operation=operation):
                values = plan.validate_transaction_journal(
                    text, current_plan, "", "", operation
                )
                self.assertTrue(values[-1])
                self.assertEqual(values[3], "complete")

        for operation in ("apply", "rollback"):
            with (
                self.subTest(operation=operation),
                self.assertRaisesRegex(plan.PlanError, "plan differs"),
            ):
                plan.validate_transaction_journal(
                    text, current_plan, "", "", operation
                )

    def test_recovery_layout_classifies_clean_and_exact_generated_gpt_per_disk(self):
        for serial in (plan.SERIAL_C, plan.SERIAL_D):
            device = self.recovery_devices[serial][0]
            with self.subTest(serial=serial):
                self.assertEqual(
                    plan.validate_recovery_layout(
                        serial, device, self.recovery_layout(serial)
                    ),
                    "generated",
                )
                self.assertEqual(
                    plan.validate_recovery_layout(
                        serial, device, self.recovery_layout(serial, generated=False)
                    ),
                    "clean",
                )

    def test_recovery_layout_rejects_any_non_exact_partition_state(self):
        for mutation in ("extra", "partuuid", "size", "signature"):
            with self.subTest(mutation=mutation):
                data = json.loads(self.recovery_layout(plan.SERIAL_C))
                p1 = data["blockdevices"][0]["children"][0]
                if mutation == "extra":
                    data["blockdevices"][0]["children"].append(
                        {"name": "/dev/nvme4n1p2", "type": "part"}
                    )
                elif mutation == "partuuid":
                    p1["partuuid"] = "a" * 36
                elif mutation == "size":
                    p1["size"] -= 512
                else:
                    p1["fstype"] = "zfs_member"
                with self.assertRaisesRegex(plan.PlanError, "recovery layout"):
                    plan.validate_recovery_layout(
                        plan.SERIAL_C, "/dev/nvme4n1", json.dumps(data)
                    )

    def test_wipefs_recovery_signatures_require_only_generated_gpt_and_empty_children(
        self,
    ):
        device = "/dev/nvme4n1"
        generated = self.generated_gpt_signatures(device)
        plan.validate_recovery_signatures(generated, device, "generated-disk")
        plan.validate_recovery_signatures(
            '{"signatures": []}', f"{device}p1", "partition"
        )
        plan.validate_recovery_signatures('{"signatures": []}', device, "clean-disk")
        altered = generated.replace('"0x200"', '"0x201"')
        with self.assertRaisesRegex(plan.PlanError, "signature set"):
            plan.validate_recovery_signatures(altered, device, "generated-disk")
        with self.assertRaisesRegex(plan.PlanError, "unexpected signature"):
            plan.validate_recovery_signatures(generated, f"{device}p1", "partition")

    def recovery_report(self, layouts, *, extra=(), boundary_blocks=()):
        findings = list(plan.REQUIRED_CLEAR_FINDINGS)
        for serial in (plan.SERIAL_C, plan.SERIAL_D):
            device, _, _, _ = self.recovery_devices[serial]
            if layouts[serial] == "generated":
                findings.extend(
                    (
                        f"BLOCK: {serial}: partition or child devices remain: {device}p1, {device}p9",
                        f"BLOCK: {serial}: signature present on {device}",
                        f"BLOCK: {serial}: signature present on {device}p1",
                        f"BLOCK: {serial}: signature present on {device}p9",
                    )
                )
            else:
                findings.extend(
                    (
                        f"CLEAR: {serial}: no child devices reported",
                        f"CLEAR: {serial}: no blkid signature reported on {device}",
                    )
                )
            for region in ("first", "last"):
                block = f"BLOCK: {serial}: non-zero unsigned bytes in {region} 8 MiB; review required"
                if (serial, region) in boundary_blocks:
                    findings.append(block)
                else:
                    findings.append(
                        f"CLEAR: {serial}: {region} 8 MiB are zero (sha256 {'a' * 64})"
                    )
        findings.extend(extra)
        blocked = any(item.startswith("BLOCK:") for item in findings)
        return (
            "\n".join(
                (
                    "Read-only scratch candidate preflight; no disks or pool state are changed.",
                    "observed_at=2026-10-04T13:49:21-04:00",
                    "boot_id=b478c236-f6fe-4490-852e-868339e84ffd",
                    *findings,
                    f"overall={'BLOCK' if blocked else 'CLEAR'}",
                    "CLEAR is a time-bound host-state preflight, not authorization.",
                )
            ),
            1 if blocked else 0,
        )

    def test_recovery_preflight_accepts_exact_generated_layout_and_discardable_boundaries(
        self,
    ):
        layouts = {plan.SERIAL_C: "generated", plan.SERIAL_D: "generated"}
        text, exit_code = self.recovery_report(
            layouts,
            boundary_blocks=tuple(
                (serial, region)
                for serial in (plan.SERIAL_C, plan.SERIAL_D)
                for region in ("first", "last")
            ),
        )
        boot_id, findings_sha = plan.validate_recovery_preflight(
            text, exit_code, layouts
        )
        self.assertEqual(boot_id, "b478c236-f6fe-4490-852e-868339e84ffd")
        self.assertEqual(len(findings_sha), 64)

    def test_recovery_preflight_supports_independent_cleanup_resume(self):
        layouts = {plan.SERIAL_C: "clean", plan.SERIAL_D: "generated"}
        text, exit_code = self.recovery_report(
            layouts, boundary_blocks=((plan.SERIAL_D, "last"),)
        )
        self.assertEqual(
            plan.validate_recovery_preflight(text, exit_code, layouts)[0],
            "b478c236-f6fe-4490-852e-868339e84ffd",
        )

    def test_recovery_preflight_rejects_unexpected_block_unknown_and_duplicate_findings(
        self,
    ):
        layouts = {plan.SERIAL_C: "generated", plan.SERIAL_D: "generated"}
        base, exit_code = self.recovery_report(layouts)
        for addition, message in (
            ("BLOCK: unrelated device changed", "unexpected"),
            ("UNKNOWN: serial read unavailable", "UNKNOWN"),
        ):
            with self.subTest(addition=addition):
                text, status = self.recovery_report(layouts, extra=(addition,))
                with self.assertRaisesRegex(plan.PlanError, message):
                    plan.validate_recovery_preflight(text, status, layouts)
        duplicated = base + "\n" + plan.REQUIRED_CLEAR_FINDINGS[0]
        with self.assertRaisesRegex(plan.PlanError, "findings differ"):
            plan.validate_recovery_preflight(duplicated, exit_code, layouts)

    def test_reviewed_preflight_returns_boot_id_and_stable_findings_hash(self):
        first = plan.validate_preflight(report(), 1)
        second = plan.validate_preflight(report(), 1)
        self.assertEqual(first[0], "b478c236-f6fe-4490-852e-868339e84ffd")
        self.assertEqual(first, second)
        self.assertEqual(len(first[1]), 64)

    def test_unexpected_block_refuses_apply(self):
        with self.assertRaisesRegex(plan.PlanError, "BLOCK findings differ"):
            plan.validate_preflight(report(additions=("BLOCK: new host reference",)), 1)

    def test_missing_known_block_refuses_stale_plan(self):
        with self.assertRaisesRegex(plan.PlanError, "BLOCK findings differ"):
            plan.validate_preflight(report(blocks=plan.EXPECTED_BLOCKS[:-1]), 1)

    def test_missing_required_clear_refuses_apply(self):
        text = report().replace(f"{plan.REQUIRED_CLEAR_FINDINGS[0]}\n", "", 1)
        with self.assertRaisesRegex(plan.PlanError, "missing required CLEAR evidence"):
            plan.validate_preflight(text, 1)

    def test_unknown_finding_refuses_apply(self):
        with self.assertRaisesRegex(plan.PlanError, "UNKNOWN findings"):
            plan.validate_preflight(
                report(additions=("UNKNOWN: probe unavailable",)), 1
            )

    def test_unexpected_overall_state_refuses_apply(self):
        text = report().replace("overall=BLOCK", "overall=CLEAR")
        with self.assertRaisesRegex(plan.PlanError, "overall=BLOCK"):
            plan.validate_preflight(text, 1)

    def test_preflight_exit_code_must_match_the_reviewed_block_state(self):
        with self.assertRaisesRegex(plan.PlanError, "exit status"):
            plan.validate_preflight(report(), 0)

    def test_malformed_boot_id_is_rejected(self):
        for boot_id in ("-" * 36, "a" * 36):
            with self.subTest(boot_id=boot_id):
                with self.assertRaisesRegex(plan.PlanError, "valid boot_id"):
                    plan.validate_preflight(report(boot_id=boot_id), 1)

    def test_duplicate_boot_ids_are_rejected(self):
        text = report() + "\nboot_id=b478c236-f6fe-4490-852e-868339e84ffd"
        with self.assertRaisesRegex(plan.PlanError, "valid boot_id"):
            plan.validate_preflight(text, 1)

    def test_capture_manifest_is_exact_and_detects_changed_hashes(self):
        manifest = plan.capture_manifest_text()
        plan.validate_capture_manifest(manifest)
        with self.assertRaisesRegex(plan.PlanError, "six reviewed"):
            plan.validate_capture_manifest(manifest.replace("b2ec4c", "a2ec4c"))

    def test_capture_directory_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as scratch:
            evidence_dir = Path(scratch) / "evidence"
            evidence_dir.mkdir(mode=0o700)
            os.chmod(evidence_dir, 0o700)
            target = Path(scratch) / "target"
            target.mkdir(mode=0o700)
            (evidence_dir / "scratch-boundary-capture-2010").symlink_to(
                target, target_is_directory=True
            )

            with self.assertRaisesRegex(plan.PlanError, "real directory"):
                plan.build_capture_manifest(evidence_dir)

    def test_capture_directory_permissions_are_checked(self):
        with tempfile.TemporaryDirectory() as scratch:
            evidence_dir = Path(scratch) / "evidence"
            evidence_dir.mkdir(mode=0o700)
            os.chmod(evidence_dir, 0o700)
            capture_dir = evidence_dir / "scratch-boundary-capture-2010"
            capture_dir.mkdir(mode=0o755)
            os.chmod(capture_dir, 0o755)

            with self.assertRaisesRegex(plan.PlanError, "mode 0700"):
                plan.build_capture_manifest(evidence_dir)

    def test_capture_evidence_owner_is_checked(self):
        with tempfile.TemporaryDirectory() as scratch:
            evidence_dir = Path(scratch) / "evidence"
            evidence_dir.mkdir(mode=0o700)
            os.chmod(evidence_dir, 0o700)
            with patch.object(plan.os, "getuid", return_value=-1):
                with self.assertRaisesRegex(
                    plan.PlanError, "owned by the current user"
                ):
                    plan.build_capture_manifest(evidence_dir)

    def capture_fixtures(self, evidence_dir):
        captures = []
        for index in range(6):
            relative_path = f"capture-{index}/capture.bin"
            capture_dir = evidence_dir / f"capture-{index}"
            capture_dir.mkdir(mode=0o700)
            os.chmod(capture_dir, 0o700)
            content = f"data-{index}".encode()
            path = evidence_dir / relative_path
            path.write_bytes(content)
            os.chmod(path, 0o600)
            captures.append(
                (
                    f"SERIAL-{index}",
                    "whole",
                    "first",
                    hashlib.sha256(content).hexdigest(),
                    relative_path,
                )
            )
        return tuple(captures)

    def test_all_six_capture_files_are_verified(self):
        with tempfile.TemporaryDirectory() as scratch:
            evidence_dir = Path(scratch) / "evidence"
            evidence_dir.mkdir(mode=0o700)
            os.chmod(evidence_dir, 0o700)
            captures = self.capture_fixtures(evidence_dir)
            expected = "".join(
                f"{serial}\t{target}\t{region}\t{digest}\n"
                for serial, target, region, digest, _ in captures
            )
            with (
                patch.object(plan, "CAPTURES", captures),
                patch.object(plan, "CAPTURE_BYTES", len(b"data-0")),
            ):
                self.assertEqual(plan.build_capture_manifest(evidence_dir), expected)

    def test_capture_file_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as scratch:
            evidence_dir = Path(scratch) / "evidence"
            evidence_dir.mkdir(mode=0o700)
            os.chmod(evidence_dir, 0o700)
            captures = list(self.capture_fixtures(evidence_dir))
            path = evidence_dir / captures[0][4]
            outside = Path(scratch) / "outside.bin"
            outside.write_bytes(path.read_bytes())
            path.unlink()
            path.symlink_to(outside)
            with (
                patch.object(plan, "CAPTURES", tuple(captures)),
                patch.object(plan, "CAPTURE_BYTES", len(b"data-0")),
            ):
                with self.assertRaisesRegex(plan.PlanError, "non-symlink"):
                    plan.build_capture_manifest(evidence_dir)

    def test_capture_file_mode_and_size_are_enforced(self):
        for mutation, message in (("mode", "mode 0600"), ("size", "exactly 8 MiB")):
            with (
                self.subTest(mutation=mutation),
                tempfile.TemporaryDirectory() as scratch,
            ):
                evidence_dir = Path(scratch) / "evidence"
                evidence_dir.mkdir(mode=0o700)
                os.chmod(evidence_dir, 0o700)
                captures = self.capture_fixtures(evidence_dir)
                path = evidence_dir / captures[0][4]
                if mutation == "mode":
                    os.chmod(path, 0o644)
                else:
                    path.write_bytes(b"x")
                    os.chmod(path, 0o600)
                with (
                    patch.object(plan, "CAPTURES", captures),
                    patch.object(plan, "CAPTURE_BYTES", len(b"data-0")),
                ):
                    with self.assertRaisesRegex(plan.PlanError, message):
                        plan.build_capture_manifest(evidence_dir)

    def test_changed_hash_is_rejected_for_each_of_all_six_captures(self):
        for index in range(6):
            with (
                self.subTest(capture=index),
                tempfile.TemporaryDirectory() as scratch,
            ):
                evidence_dir = Path(scratch) / "evidence"
                evidence_dir.mkdir(mode=0o700)
                os.chmod(evidence_dir, 0o700)
                captures = self.capture_fixtures(evidence_dir)
                path = evidence_dir / captures[index][4]
                path.write_bytes(b"x" * len(b"data-0"))
                os.chmod(path, 0o600)
                with (
                    patch.object(plan, "CAPTURES", captures),
                    patch.object(plan, "CAPTURE_BYTES", len(b"data-0")),
                ):
                    with self.assertRaisesRegex(plan.PlanError, "hash changed"):
                        plan.build_capture_manifest(evidence_dir)

    def zpool_status(
        self,
        members=None,
        state="ONLINE",
        errors="No known data errors",
        topology_rows=None,
    ):
        if members is None:
            members = (
                f"{self.whole_c}-part1 ONLINE",
                f"{self.whole_d}-part1 ONLINE",
            )
        if topology_rows is None:
            topology_rows = (
                "    scratch ONLINE 0 0 0",
                *(f"      {member} 0 0 0" for member in members),
            )
        return "\n".join(
            (
                "  pool: scratch",
                f" state: {state}",
                "config:",
                "        NAME STATE READ WRITE CKSUM",
                *topology_rows,
                f"errors: {errors}",
            )
        )

    def test_zpool_status_accepts_exact_generated_whole_disk_partitions(self):
        plan.validate_zpool_status(self.zpool_status(), self.whole_c, self.whole_d)

    def test_zpool_status_accepts_tab_then_space_indentation_from_pve(self):
        rows = (
            "\tscratch ONLINE 0 0 0",
            f"\t  {self.whole_c}-part1 ONLINE 0 0 0",
            f"\t  {self.whole_d}-part1 ONLINE 0 0 0",
        )
        plan.validate_zpool_status(
            self.zpool_status(topology_rows=rows), self.whole_c, self.whole_d
        )

    def test_zpool_status_rejects_unpartitioned_whole_disk_members(self):
        with self.assertRaisesRegex(plan.PlanError, "two-device stripe"):
            plan.validate_zpool_status(
                self.zpool_status((f"{self.whole_c} ONLINE", f"{self.whole_d} ONLINE")),
                self.whole_c,
                self.whole_d,
            )

    def test_zpool_status_rejects_extra_members_and_unhealthy_state(self):
        extra = (
            f"{self.whole_c}-part1 ONLINE",
            f"{self.whole_d}-part1 ONLINE",
            "/dev/disk/by-id/other-part1 ONLINE",
        )
        with self.assertRaisesRegex(plan.PlanError, "two-device stripe"):
            plan.validate_zpool_status(
                self.zpool_status(extra), self.whole_c, self.whole_d
            )
        with self.assertRaisesRegex(plan.PlanError, "not healthy"):
            plan.validate_zpool_status(
                self.zpool_status(state="DEGRADED"), self.whole_c, self.whole_d
            )

    def test_zpool_status_rejects_nonzero_or_malformed_error_counters(self):
        rows = (
            "    scratch ONLINE 0 0 0",
            f"      {self.whole_c}-part1 ONLINE 0 0 0",
            f"      {self.whole_d}-part1 ONLINE 0 0 0",
        )
        for row_index in range(3):
            for counter_index in range(3):
                with self.subTest(row=row_index, counter=counter_index):
                    changed = list(rows)
                    fields = changed[row_index].split()
                    fields[counter_index + 2] = "1"
                    indentation = len(changed[row_index]) - len(
                        changed[row_index].lstrip()
                    )
                    changed[row_index] = " " * indentation + " ".join(fields)
                    with self.assertRaisesRegex(plan.PlanError, "counter"):
                        plan.validate_zpool_status(
                            self.zpool_status(topology_rows=changed),
                            self.whole_c,
                            self.whole_d,
                        )

        for counter in ("1.2K", "-"):
            with self.subTest(counter=counter):
                changed = list(rows)
                fields = changed[1].split()
                fields[2] = counter
                changed[1] = "      " + " ".join(fields)
                with self.assertRaisesRegex(plan.PlanError, "counter"):
                    plan.validate_zpool_status(
                        self.zpool_status(topology_rows=changed),
                        self.whole_c,
                        self.whole_d,
                    )

        for malformed_row in (
            f"      {self.whole_c}-part1 ONLINE 0 0",
            f"      {self.whole_c}-part1 ONLINE 0 0 0 (resilvering)",
        ):
            with self.subTest(row=malformed_row):
                changed = (rows[0], malformed_row, rows[2])
                with self.assertRaisesRegex(plan.PlanError, "row"):
                    plan.validate_zpool_status(
                        self.zpool_status(topology_rows=changed),
                        self.whole_c,
                        self.whole_d,
                    )

    def zdb_config(
        self,
        ashifts=(12, 12),
        paths=None,
        child_indexes=(0, 1),
        vdev_children=2,
        types=("disk", "disk"),
        is_logs=(0, 0),
    ):
        if paths is None:
            paths = (f"{self.whole_c}-part1", f"{self.whole_d}-part1")
        lines = ["MOS Configuration:", "  vdev_tree:", "    type: 'root'", f"    vdev_children: {vdev_children}"]
        for index, path, ashift, vdev_type, is_log in zip(
            child_indexes, paths, ashifts, types, is_logs
        ):
            lines.extend(
                (
                    f"    children[{index}]:",
                    f"      type: '{vdev_type}'",
                    f"      path: '{path}'",
                    f"      ashift: {ashift}",
                    f"      is_log: {is_log}",
                )
            )
        return "\n".join(lines)

    def test_zdb_config_requires_exact_two_disk_children_with_ashift_12(self):
        plan.validate_zdb_config(self.zdb_config(), self.whole_c, self.whole_d)

        invalid_configs = (
            (self.zdb_config(ashifts=(9, 12)), "ashift"),
            (self.zdb_config(ashifts=(12, None)), "ashift"),
            (self.zdb_config(ashifts=(120, 12)), "ashift"),
            (
                self.zdb_config(
                    child_indexes=(0,),
                    paths=(f"{self.whole_c}-part1",),
                    ashifts=(12,),
                ),
                "child",
            ),
            (self.zdb_config(child_indexes=(0, 1, 2), paths=(f"{self.whole_c}-part1", f"{self.whole_d}-part1", "/dev/disk/by-id/other-part1"), ashifts=(12, 12, 12), vdev_children=3), "children"),
            (
                self.zdb_config(
                    paths=("/dev/disk/by-id/wrong-part1", f"{self.whole_d}-part1")
                ),
                "path",
            ),
            (self.zdb_config(types=("disk", "log")), "disk"),
            (self.zdb_config(is_logs=(1, 0)), "log"),
        )
        for text, message in invalid_configs:
            with (
                self.subTest(message=message, text=text),
                self.assertRaisesRegex(plan.PlanError, message),
            ):
                plan.validate_zdb_config(text, self.whole_c, self.whole_d)

    def test_zpool_status_rejects_extra_raw_device_member(self):
        members = (
            f"{self.whole_c}-part1 ONLINE",
            f"{self.whole_d}-part1 ONLINE",
            "/dev/nvme6n1p1 ONLINE",
        )
        with self.assertRaisesRegex(plan.PlanError, "two-device stripe"):
            plan.validate_zpool_status(
                self.zpool_status(members), self.whole_c, self.whole_d
            )

    def test_zpool_status_rejects_mirror_topology_with_expected_leaves(self):
        rows = (
            "    scratch ONLINE 0 0 0",
            "      mirror-0 ONLINE 0 0 0",
            f"        {self.whole_c}-part1 ONLINE 0 0 0",
            f"        {self.whole_d}-part1 ONLINE 0 0 0",
        )
        with self.assertRaisesRegex(plan.PlanError, "vdev layer"):
            plan.validate_zpool_status(
                self.zpool_status(topology_rows=rows), self.whole_c, self.whole_d
            )

    def test_pvesm_empty_listing_requires_real_header_and_no_rows(self):
        plan.validate_empty_pvesm_listing("Volid Format Type Size VMID\n")
        for text, message in (
            ("", "unexpected header"),
            ("Volid Format Type Size\n", "unexpected header"),
            (
                "Volid Format Type Size VMID\nscratch:vm-100-disk-0 raw images 1024 100\n",
                "contains volumes",
            ),
            (
                "Volid Format Type Size VMID\nscratch:vm-100-disk-0 raw images many 100\n",
                "malformed row",
            ),
        ):
            with (
                self.subTest(text=text),
                self.assertRaisesRegex(plan.PlanError, message),
            ):
                plan.validate_empty_pvesm_listing(text)

    def test_scratch_storage_content_requires_one_exact_content_directive(self):
        for content in ("images,rootdir", "rootdir,images"):
            with self.subTest(content=content):
                plan.validate_scratch_storage_content(
                    f"zfspool: scratch\n content {content}\n"
                )
        for block in (
            "zfspool: scratch\n content images,rootdir\n content snippets\n",
            "zfspool: scratch\n content images,rootdir\n content rootdir,images\n",
            "zfspool: scratch\n content images,rootdir,backup\n",
            "zfspool: scratch\n content images\n",
        ):
            with (
                self.subTest(block=block),
                self.assertRaisesRegex(plan.PlanError, "content"),
            ):
                plan.validate_scratch_storage_content(block)


if __name__ == "__main__":
    unittest.main()
