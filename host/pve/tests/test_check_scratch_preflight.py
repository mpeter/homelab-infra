#!/usr/bin/env python3
import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "check_scratch_preflight.py"
spec = importlib.util.spec_from_file_location("check_scratch_preflight", SCRIPT)
assert spec is not None and spec.loader is not None
preflight = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = preflight
spec.loader.exec_module(preflight)


class ScratchPreflightTests(unittest.TestCase):
    def candidate(self, serial, device):
        return preflight.CandidateEvidence(
            serial=serial,
            whole_disks=[(device, serial, "disk")],
            aliases=[(f"/dev/disk/by-id/nvme-model_{serial}", device)],
            children=[],
            signatures={device: (2, "")},
            boundaries={
                "first": ("a" * 64, False),
                "last": ("b" * 64, False),
            },
            smart={
                "passed": True,
                "critical_warning": 0,
                "available_spare": 100,
                "available_spare_threshold": 10,
                "media_errors": 0,
            },
            references={name: [] for name in preflight.REFERENCE_CHECKS},
        )

    def evidence(self):
        return preflight.PreflightEvidence(
            candidates={
                preflight.SERIAL_C: self.candidate(preflight.SERIAL_C, "/dev/nvme4n1"),
                preflight.SERIAL_D: self.candidate(preflight.SERIAL_D, "/dev/nvme5n1"),
            },
            controls={name: True for name in preflight.POSITIVE_CONTROLS},
            scratch_collision=False,
        )

    def test_all_clear_evidence_passes_only_the_current_state_gate(self):
        result = preflight.assess(self.evidence())
        self.assertEqual(result.state, "CLEAR")
        self.assertIn("not authorization", result.authorization_note)

    def test_candidate_partitions_and_signatures_block(self):
        evidence = self.evidence()
        candidate = evidence.candidates[preflight.SERIAL_C]
        candidate.children = [
            {
                "name": "/dev/nvme4n1p3",
                "type": "part",
                "partuuid": "01153cd9-d265-4292-a8f3-d66ace72ac89",
                "fstype": "zfs_member",
            }
        ]
        candidate.signatures["/dev/nvme4n1p3"] = (0, "TYPE=zfs_member\n")
        result = preflight.assess(evidence)
        self.assertEqual(result.state, "BLOCK")
        self.assertTrue(any("partition" in item.detail for item in result.findings))

    def test_ambiguous_serial_identity_is_unknown_and_cannot_pass(self):
        evidence = self.evidence()
        candidate = evidence.candidates[preflight.SERIAL_D]
        candidate.whole_disks.append(("/dev/nvme6n1", preflight.SERIAL_D, "disk"))
        result = preflight.assess(evidence)
        self.assertEqual(result.state, "UNKNOWN")
        self.assertTrue(any(item.state == "UNKNOWN" for item in result.findings))

    def test_nonzero_unsigned_boundary_blocks_for_review(self):
        evidence = self.evidence()
        evidence.candidates[preflight.SERIAL_D].boundaries["last"] = (
            "c" * 64,
            True,
        )
        result = preflight.assess(evidence)
        self.assertEqual(result.state, "BLOCK")
        self.assertTrue(any("non-zero" in item.detail for item in result.findings))

    def test_missing_positive_control_is_unknown(self):
        evidence = self.evidence()
        evidence.controls[preflight.POSITIVE_CONTROLS[0]] = None
        result = preflight.assess(evidence)
        self.assertEqual(result.state, "UNKNOWN")
        self.assertTrue(any(item.state == "UNKNOWN" for item in result.findings))

    def test_unhealthy_smart_readback_blocks(self):
        evidence = self.evidence()
        evidence.candidates[preflight.SERIAL_C].smart["critical_warning"] = 1
        result = preflight.assess(evidence)
        self.assertEqual(result.state, "BLOCK")
        self.assertTrue(
            any("critical warning" in item.detail for item in result.findings)
        )

    def test_reference_presence_blocks(self):
        evidence = self.evidence()
        evidence.candidates[preflight.SERIAL_D].references["mounts"] = [
            "/dev/nvme5n1p1"
        ]
        self.assertEqual(preflight.assess(evidence).state, "BLOCK")

    def test_partition_pool_path_resolves_to_parent_serial(self):
        devices = [
            {"name": "/dev/nvme0n1", "type": "disk", "serial": "SERIAL-A"},
            {
                "name": "/dev/nvme0n1p3",
                "type": "part",
                "serial": None,
                "pkname": "/dev/nvme0n1",
            },
        ]
        resolutions = {
            "/dev/disk/by-id/nvme-model_SERIAL-A-part3": "/dev/nvme0n1p3",
            "/dev/nvme0n1p3": "/dev/nvme0n1p3",
        }
        with patch.object(
            preflight.os.path,
            "realpath",
            side_effect=lambda path: resolutions.get(path, path),
        ):
            serials = preflight._pool_member_serials(
                "  /dev/disk/by-id/nvme-model_SERIAL-A-part3 ONLINE\n", devices
            )
        self.assertEqual(serials, {"SERIAL-A"})

    def test_signature_probe_error_is_unknown(self):
        evidence = self.evidence()
        evidence.candidates[preflight.SERIAL_C].signatures["/dev/nvme4n1"] = (4, "")
        result = preflight.assess(evidence)
        self.assertEqual(result.state, "UNKNOWN")
        self.assertTrue(
            any("blkid could not classify" in item.detail for item in result.findings)
        )

    def test_missing_smart_field_is_unknown(self):
        evidence = self.evidence()
        del evidence.candidates[preflight.SERIAL_D].smart["media_errors"]
        result = preflight.assess(evidence)
        self.assertEqual(result.state, "UNKNOWN")
        self.assertTrue(
            any("SMART fields missing" in item.detail for item in result.findings)
        )

    def test_null_or_non_numeric_smart_values_are_unknown(self):
        for field in (
            "passed",
            "critical_warning",
            "available_spare",
            "available_spare_threshold",
            "media_errors",
        ):
            with self.subTest(field=field):
                evidence = self.evidence()
                evidence.candidates[preflight.SERIAL_C].smart[field] = None
                result = preflight.assess(evidence)
                self.assertEqual(result.state, "UNKNOWN")
                self.assertTrue(
                    any(
                        f"SMART fields invalid: {field}" in item.detail
                        for item in result.findings
                    )
                )

    def test_out_of_range_smart_counters_and_percentages_are_unknown(self):
        cases = (
            {"critical_warning": 256},
            {"available_spare": -1, "available_spare_threshold": -2},
            {"available_spare": 101},
            {"available_spare_threshold": 101},
            {"media_errors": -1},
        )
        for updates in cases:
            with self.subTest(updates=updates):
                evidence = self.evidence()
                evidence.candidates[preflight.SERIAL_C].smart.update(updates)
                self.assertEqual(preflight.assess(evidence).state, "UNKNOWN")

    def test_large_media_error_counter_blocks_without_numeric_overflow(self):
        evidence = self.evidence()
        evidence.candidates[preflight.SERIAL_C].smart["media_errors"] = 10**400
        self.assertEqual(preflight.assess(evidence).state, "BLOCK")

    def test_importable_scratch_name_collision_blocks(self):
        evidence = self.evidence()
        evidence.scratch_collision = True
        self.assertEqual(preflight.assess(evidence).state, "BLOCK")

    def test_read_only_runner_rejects_write_capable_commands(self):
        for command in (
            ["wipefs", "--all", "/dev/nvme5n1"],
            ["smartctl", "-t", "short", "/dev/nvme5n1"],
            ["zpool", "import", "scratch"],
            ["dd", "if=/dev/nvme5n1", "of=/dev/nvme4n1"],
            ["proxmox-boot-tool", "status"],
        ):
            with self.subTest(command=command):
                with self.assertRaises(preflight.ReadOnlyViolation):
                    preflight.run_readonly(command)

    def test_read_only_runner_allows_each_safe_imported_pool_status(self):
        self.assertTrue(
            preflight._command_is_read_only(
                ["zpool", "status", "-P", "-v", "archive-pool"]
            )
        )
        self.assertFalse(
            preflight._command_is_read_only(["zpool", "status", "-P", "-v", "--help"])
        )

    def test_every_imported_pool_is_checked_for_candidate_references(self):
        pool_names = {"rpool", "fast-vm", "archive-pool"}
        calls = []

        def run(argv):
            calls.append(argv)
            output = f"pool: {argv[-1]}\n"
            if argv[-1] == "archive-pool":
                output += f"  /dev/disk/by-id/nvme_{preflight.SERIAL_C}-part1 ONLINE\n"
            return preflight.subprocess.CompletedProcess(argv, 0, output, "")

        with patch.object(preflight, "run_readonly", side_effect=run):
            statuses, _, issues = preflight._read_imported_pool_statuses(pool_names, [])

        self.assertEqual(set(statuses), pool_names)
        self.assertEqual(issues, [])
        self.assertIn(
            ["zpool", "status", "-P", "-v", "archive-pool"],
            calls,
        )
        self.assertEqual(
            preflight._references_in_output(
                "\n".join(statuses.values()), {preflight.SERIAL_C}
            ),
            [preflight.SERIAL_C],
        )

    def test_imported_pool_status_failure_is_reported_incomplete(self):
        pool_names = {"rpool", "fast-vm", "archive-pool"}

        def run(argv):
            status = 1 if argv[-1] == "archive-pool" else 0
            return preflight.subprocess.CompletedProcess(argv, status, "", "failed")

        with patch.object(preflight, "run_readonly", side_effect=run):
            statuses, _, issues = preflight._read_imported_pool_statuses(pool_names, [])

        self.assertEqual(set(statuses), {"rpool", "fast-vm"})
        self.assertEqual(issues, ["zpool status failed for archive-pool"])

    def test_configured_esp_identity_requires_same_partition_evidence(self):
        devices = [
            {
                "name": "/dev/nvme0n1p2",
                "type": "part",
                "uuid": "929d-9f5b",
                "partuuid": preflight.EXPECTED_ESP_PARTUUIDS[0],
                "parttype": preflight.EXPECTED_ESP_PARTITION_TYPE,
                "fstype": "vfat",
            },
            {
                "name": "/dev/nvme3n1p2",
                "type": "part",
                "uuid": "929E-65B4",
                "partuuid": preflight.EXPECTED_ESP_PARTUUIDS[1],
                "parttype": preflight.EXPECTED_ESP_PARTITION_TYPE,
                "fstype": "vfat",
            },
        ]
        configured = "929D-9F5B\n929E-65B4\n"
        self.assertEqual(
            preflight._configured_esp_controls(configured, devices),
            {
                "Proxmox ESP A filesystem UUID": True,
                "Proxmox ESP B filesystem UUID": True,
            },
        )

    def test_missing_or_malformed_esp_configuration_is_unknown(self):
        devices = [
            {
                "type": "part",
                "uuid": uuid,
                "partuuid": partuuid,
                "parttype": preflight.EXPECTED_ESP_PARTITION_TYPE,
                "fstype": "vfat",
            }
            for uuid, partuuid in zip(
                preflight.EXPECTED_ESP_FILESYSTEM_UUIDS,
                preflight.EXPECTED_ESP_PARTUUIDS,
                strict=True,
            )
        ]
        self.assertTrue(
            all(
                value is None
                for value in preflight._configured_esp_controls(None, devices).values()
            )
        )
        self.assertTrue(
            all(
                value is None
                for value in preflight._configured_esp_controls(
                    "not-a-uuid\n", devices
                ).values()
            )
        )

    def test_esp_configuration_without_independent_vfat_readback_does_not_pass(self):
        devices = [
            {
                "type": "part",
                "uuid": preflight.EXPECTED_ESP_FILESYSTEM_UUIDS[0],
                "partuuid": preflight.EXPECTED_ESP_PARTUUIDS[0],
                "parttype": preflight.EXPECTED_ESP_PARTITION_TYPE,
                "fstype": "ext4",
            },
            {
                "type": "part",
                "uuid": preflight.EXPECTED_ESP_FILESYSTEM_UUIDS[1],
                "partuuid": preflight.EXPECTED_ESP_PARTUUIDS[1],
                "parttype": preflight.EXPECTED_ESP_PARTITION_TYPE,
                "fstype": "vfat",
            },
        ]
        result = preflight._configured_esp_controls(
            "\n".join(preflight.EXPECTED_ESP_FILESYSTEM_UUIDS), devices
        )
        self.assertEqual(result["Proxmox ESP A filesystem UUID"], False)
        self.assertEqual(result["Proxmox ESP B filesystem UUID"], True)

    def test_esp_uuid_and_partuuid_must_match_the_same_efi_partition(self):
        devices = [
            {
                "type": "part",
                "uuid": preflight.EXPECTED_ESP_FILESYSTEM_UUIDS[0],
                "partuuid": "wrong-partuuid",
                "parttype": preflight.EXPECTED_ESP_PARTITION_TYPE,
                "fstype": "vfat",
            },
            {
                "type": "part",
                "uuid": "wrong-filesystem-uuid",
                "partuuid": preflight.EXPECTED_ESP_PARTUUIDS[0],
                "parttype": preflight.EXPECTED_ESP_PARTITION_TYPE,
                "fstype": "vfat",
            },
            {
                "type": "part",
                "uuid": preflight.EXPECTED_ESP_FILESYSTEM_UUIDS[1],
                "partuuid": preflight.EXPECTED_ESP_PARTUUIDS[1],
                "parttype": preflight.EXPECTED_ESP_PARTITION_TYPE,
                "fstype": "vfat",
            },
        ]
        result = preflight._configured_esp_controls(
            "\n".join(preflight.EXPECTED_ESP_FILESYSTEM_UUIDS), devices
        )
        self.assertEqual(result["Proxmox ESP A filesystem UUID"], False)
        self.assertEqual(result["Proxmox ESP B filesystem UUID"], True)

    def test_duplicate_esp_identity_is_unknown(self):
        row = {
            "type": "part",
            "uuid": preflight.EXPECTED_ESP_FILESYSTEM_UUIDS[0],
            "partuuid": preflight.EXPECTED_ESP_PARTUUIDS[0],
            "parttype": preflight.EXPECTED_ESP_PARTITION_TYPE,
            "fstype": "vfat",
        }
        devices = [
            row,
            dict(row),
            {
                "type": "part",
                "uuid": preflight.EXPECTED_ESP_FILESYSTEM_UUIDS[1],
                "partuuid": preflight.EXPECTED_ESP_PARTUUIDS[1],
                "parttype": preflight.EXPECTED_ESP_PARTITION_TYPE,
                "fstype": "vfat",
            },
        ]
        result = preflight._configured_esp_controls(
            "\n".join(preflight.EXPECTED_ESP_FILESYSTEM_UUIDS), devices
        )
        self.assertIsNone(result["Proxmox ESP A filesystem UUID"])
        self.assertTrue(result["Proxmox ESP B filesystem UUID"])


if __name__ == "__main__":
    unittest.main()
