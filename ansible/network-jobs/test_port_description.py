"""Offline draft boundaries and exact configuration comparisons."""

from dataclasses import FrozenInstanceError, asdict, replace
import hashlib
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import exercise_observation as observation
import port_description as engine

VERSION = (
    "SW: Version 08.0.30uT7f3\n"
    "UNIT 1: SL 1: ICX6610-48P POE Management Module\n"
    "The system : started=cold start"
)
CONFIG = (
    "ver 08.0.30uT7f3\n"
    "username root password opaque-root-fixture\n"
    "username homelab_audit privilege 5 password opaque-audit-fixture\n"
    "aaa authentication login default local\n"
    "vlan 1\n tagged ethe 1/1/48\n!\n"
    "interface ethernet 1/1/7\n port-name Before\n disable\n!\n"
    "interface ethernet 1/1/12\n port-name Other\n!\nend"
)


def evidence(running=CONFIG, startup=None):
    commands = (*engine.COMMANDS, "show interfaces ethernet 1/1/7")
    return {
        "schema": 1,
        "host": engine.HOST,
        "model": engine.MODEL,
        "release": engine.RELEASE,
        "identity": "homelab_audit",
        "accepted_host_key_fingerprint": engine.FINGERPRINT,
        "selected_port": "1/1/7",
        "commands": list(commands),
        "expected_execution_environment_sha256": engine.EE_DIGEST,
        "source_sha256": {
            k: v for k, v in engine.SOURCE_SHA256.items() if k != "engine"
        },
        "raw_capture_sha256": {f"capture-0{i}.txt": "a" * 64 for i in range(1, 7)},
        "terminal_boundaries_complete": True,
        "responses": dict(
            zip(
                commands,
                (
                    VERSION,
                    running,
                    running if startup is None else startup,
                    "brief",
                    "mac",
                    "detail",
                ),
                strict=True,
            )
        ),
    }


class PreviewTests(unittest.TestCase):
    def test_actual_warm_reload_footer(self):
        for footer in (
            "The system : started=warm start",
            'The system : started=warm start   reloaded=by "reload"',
            'The system : started=warm start\treloaded=by "reload"',
        ):
            with self.subTest(footer=footer):
                payload = evidence()
                payload["responses"]["show version"] = (
                    VERSION.rsplit("\n", 1)[0] + "\n" + footer
                )
                self.assertEqual(
                    engine.evidence_config(payload, "1/1/7"),
                    (tuple(CONFIG.splitlines()),) * 2,
                )

    def test_reload_footer_rejects_truncation_and_unobserved_suffixes(self):
        for footer in (
            'The system : started=warm start reloaded=by "reload',
            'The system : started=warm start reloaded=by "reboot"',
            'The system : started=cold start reloaded=by "reload"',
            'The system : started=warm startreloaded=by "reload"',
            'The system : started=warm start\nreloaded=by "reload"',
            'The system : started=warm start reloaded=by "reload" extra',
        ):
            with self.subTest(footer=footer):
                payload = evidence()
                payload["responses"]["show version"] = (
                    VERSION.rsplit("\n", 1)[0] + "\n" + footer
                )
                with self.assertRaisesRegex(engine.Rejected, "version boundary"):
                    engine.evidence_config(payload, "1/1/7")

    def test_audit_and_exercise_agree_on_reload_footer_boundaries(self):
        accepted = (
            "The system : started=cold start",
            "The system : started=warm start",
            'The system : started=warm start   reloaded=by "reload"',
            'The system : started=warm start\treloaded=by "reload"',
        )
        rejected = (
            'The system : started=cold start reloaded=by "reload"',
            'The system : started=warm startreloaded=by "reload"',
            'The system : started=warm start\nreloaded=by "reload"',
            'The system : started=warm start reloaded=by "reboot"',
            'The system : started=warm start reloaded=by "reload" extra',
        )
        suffix = ' reloaded=by "reload"'
        rejected += tuple(
            "The system : started=warm start" + suffix[:length]
            for length in range(2, len(suffix))
        )
        for expected, footers in ((True, accepted), (False, rejected)):
            for footer in footers:
                with self.subTest(footer=footer, expected=expected):
                    payload = evidence()
                    version = VERSION.rsplit("\n", 1)[0] + "\n" + footer
                    payload["responses"]["show version"] = version
                    if expected:
                        observation.collector.capture.validate(
                            [version, CONFIG, CONFIG]
                        )
                        engine.evidence_config(payload, "1/1/7")
                    else:
                        with self.assertRaises(ValueError):
                            observation.collector.capture.validate(
                                [version, CONFIG, CONFIG]
                            )
                        with self.assertRaises(engine.Rejected):
                            engine.evidence_config(payload, "1/1/7")

    def test_exact_preservation_and_inverse(self):
        preview = engine.build_preview(evidence(), "1/1/7", "Lab spare_7.1")
        self.assertEqual(
            preview.expected_running,
            tuple(
                CONFIG.replace(
                    " port-name Before", " port-name Lab spare_7.1"
                ).splitlines()
            ),
        )
        self.assertEqual(preview.before_running, preview.before_startup)
        self.assertEqual(
            preview.inverse_commands,
            (
                "configure terminal",
                "interface ethernet 1/1/7",
                "port-name Before",
                "exit",
                "exit",
            ),
        )
        self.assertEqual(preview.forward_commands[2], "port-name Lab spare_7.1")
        self.assertFalse(preview.apply_enabled)
        self.assertFalse(preview.admitted)
        with self.assertRaises(FrozenInstanceError):
            preview.status = "admitted"
        self.assertIn("opaque-audit-fixture", "\n".join(preview.expected_running))
        self.assertEqual(preview.preview_sha256, engine.digest(asdict(preview)))

    def test_configuration_hash_matches_recovery_canonical_bytes(self):
        preview = engine.build_preview(evidence(), "1/1/7", "After")
        expected = hashlib.sha256((CONFIG + "\n").encode("ascii")).hexdigest()
        self.assertEqual(preview.original_running_sha256, expected)
        self.assertEqual(preview.original_startup_sha256, expected)
        result = engine.verify_configuration(preview, evidence())
        self.assertEqual(result["running_sha256"], expected)
        self.assertEqual(result["startup_sha256"], expected)
        changed = hashlib.sha256(
            (CONFIG.replace(" port-name Before", " port-name After") + "\n").encode(
                "ascii"
            )
        ).hexdigest()
        self.assertEqual(preview.expected_running_sha256, changed)
        self.assertNotEqual(expected, engine.digest(preview.before_running))

    def test_absent_stanza_candidate_and_absent_leaf_are_drafts(self):
        absent = CONFIG.replace(
            "interface ethernet 1/1/7\n port-name Before\n disable\n!\n", ""
        )
        preview = engine.build_preview(evidence(absent), "1/1/7", "Spare")
        selected = preview.expected_running.index("interface ethernet 1/1/7")
        later = preview.expected_running.index("interface ethernet 1/1/12")
        self.assertLess(selected, later)
        self.assertEqual(preview.expected_running[selected + 1], " port-name Spare")
        self.assertEqual(preview.inverse_commands[2], "no port-name")
        self.assertFalse(preview.observed_serialization_verified)
        self.assertFalse(preview.admitted)
        no_leaf = CONFIG.replace(" port-name Before\n", "")
        leaf_preview = engine.build_preview(evidence(no_leaf), "1/1/7", "Spare")
        self.assertEqual(
            leaf_preview.expected_running,
            tuple(
                no_leaf.replace(
                    "interface ethernet 1/1/7",
                    "interface ethernet 1/1/7\n port-name Spare",
                ).splitlines()
            ),
        )

    def test_configuration_only_classification(self):
        preview = engine.build_preview(evidence(), "1/1/7", "After")
        after = "\n".join(preview.expected_running)
        unchanged = engine.verify_configuration(preview, evidence())
        self.assertEqual(unchanged["classification"], "unchanged")
        self.assertTrue(unchanged["rollback_exact_original_running_and_startup"])
        applied = engine.verify_configuration(preview, evidence(after, CONFIG))
        self.assertEqual(applied["classification"], "applied")
        self.assertEqual(applied["scope"], "configuration_only")
        self.assertFalse(applied["rollback_exact_original_running_and_startup"])
        for running, startup in (
            (after, after),
            (after.replace("vlan 1", "vlan 2"), CONFIG),
            (after.replace("default local", "default radius"), CONFIG),
            (after.replace(" port-name Other", " port-name Different"), CONFIG),
            (
                after.replace(
                    "vlan 1\n tagged ethe 1/1/48", "tagged ethe 1/1/48\nvlan 1"
                ),
                CONFIG,
            ),
            (CONFIG, after),
        ):
            with self.subTest(running=running, startup=startup):
                result = engine.verify_configuration(
                    preview, evidence(running, startup)
                )
                self.assertEqual(result["classification"], "uncertain")
                self.assertFalse(result["rollback_exact_original_running_and_startup"])

    def test_noop_is_unchanged_not_apply_acceptance(self):
        preview = engine.build_preview(evidence(), "1/1/7", "Before")
        self.assertEqual(
            engine.verify_configuration(preview, evidence())["classification"],
            "unchanged",
        )
        self.assertFalse(preview.admitted)

    def test_injection_error_echo_and_port_boundaries(self):
        for value in (
            "",
            " A",
            "A ",
            "A" * 49,
            "a\nb",
            "a\rb",
            "a;b",
            '"A"',
            "É",
            "invalid input",
            "Unknown command",
            "Permission denied",
            "not allowed",
        ):
            with self.subTest(value=value), self.assertRaises(engine.Rejected):
                engine.description(value)
        for value in ("1/1/0", "1/1/48", "1/2/1", "1/1/01", "1/1/7\nreload", "1/1/7 "):
            with self.subTest(value=value), self.assertRaises(engine.Rejected):
                engine.port(value)
        for number in range(1, 48):
            self.assertEqual(engine.port(f"1/1/{number}"), f"1/1/{number}")
        self.assertEqual(engine.description("A" * 48), "A" * 48)

    def test_ambiguous_duplicate_and_range_stanzas_rejected(self):
        for changed in (
            CONFIG.replace(" port-name Before", " port-name Before\n port-name Again"),
            CONFIG.replace("interface ethernet 1/1/12", "interface ethernet 1/1/7"),
            CONFIG.replace(
                "interface ethernet 1/1/7", "interface ethernet 1/1/7 to 1/1/9"
            ),
            CONFIG.replace("interface ethernet 1/1/7", " interface ethernet 1/1/7"),
            CONFIG.replace(" port-name Before", "  port-name Before"),
            CONFIG.replace(" port-name Before", "port-name Before"),
            CONFIG.replace(" port-name Before", " port-nameBefore"),
        ):
            with self.subTest(changed=changed), self.assertRaises(engine.Rejected):
                engine.build_preview(evidence(changed), "1/1/7", "After")

    def test_ten_capture_persisted_audit_with_ve_and_rear_interfaces(self):
        config = CONFIG.replace(
            "vlan 1", "interface ve 1\n ip address 10.72.0.1 255.255.255.0\n!\nvlan 1"
        )
        config = config.replace("end", "interface ethernet 1/3/1\n disable\n!\nend")
        item = evidence(config)
        item["raw_capture_sha256"] = {
            f"capture-{i:02}.txt": "b" * 64 for i in range(1, 11)
        }
        preview = engine.build_preview(item, "1/1/7", "After")
        self.assertEqual(len(preview.raw_capture_sha256), 10)
        self.assertEqual(len(preview.response_sha256), 6)
        self.assertEqual(
            preview.expected_running,
            tuple(config.replace(" port-name Before", " port-name After").splitlines()),
        )
        item["raw_capture_sha256"]["capture-11.txt"] = item["raw_capture_sha256"].pop(
            "capture-10.txt"
        )
        with self.assertRaises(engine.Rejected):
            engine.build_preview(item, "1/1/7", "After")

    def test_nonphysical_interfaces_are_preserved(self):
        config = CONFIG.replace(
            "vlan 1", "interface ve 1\n ip address 10.72.0.1 255.255.255.0\n!\nvlan 1"
        )
        preview = engine.build_preview(evidence(config), "1/1/7", "After")
        self.assertEqual(
            preview.expected_running,
            tuple(config.replace(" port-name Before", " port-name After").splitlines()),
        )

    def test_complete_pinned_persisted_baseline_and_stale_metadata(self):
        for config in (
            CONFIG.removesuffix("end"),
            CONFIG + "\nother",
            CONFIG.replace("privilege 5", "privilege 0"),
            CONFIG.replace("username homelab_audit", "username removed"),
            CONFIG.replace("ver 08.0.30uT7f3", "ver 08.0.31"),
        ):
            with self.subTest(config=config), self.assertRaises(engine.Rejected):
                engine.build_preview(evidence(config), "1/1/7", "After")
        with self.assertRaises(engine.Rejected):
            engine.build_preview(
                evidence(CONFIG, CONFIG.replace("vlan 1", "vlan 2")), "1/1/7", "After"
            )
        for key, value in (
            ("schema", True),
            ("schema", 2),
            ("release", "08.0.31"),
            ("identity", "root"),
            ("terminal_boundaries_complete", 1),
            ("source_sha256", {}),
            ("raw_capture_sha256", {}),
        ):
            item = evidence()
            item[key] = value
            with self.subTest(key=key), self.assertRaises(engine.Rejected):
                engine.build_preview(item, "1/1/7", "After")
        item = evidence()
        item.update(
            admitted=True, apply_enabled=True, exact_firmware_syntax_verified=True
        )
        self.assertFalse(engine.build_preview(item, "1/1/7", "After").admitted)

    def test_input_binding_and_source_drift(self):
        first = evidence()
        second = evidence()
        second["responses"]["show mac-address"] = "other MAC evidence"
        one = engine.build_preview(first, "1/1/7", "After")
        two = engine.build_preview(second, "1/1/7", "After")
        self.assertNotEqual(one.input_binding_sha256, two.input_binding_sha256)
        self.assertNotEqual(one.preview_sha256, two.preview_sha256)
        with (
            patch.object(Path, "read_bytes", return_value=b"drift"),
            self.assertRaises(engine.Rejected),
        ):
            engine.build_preview(first, "1/1/7", "After")

    def test_private_files_and_duplicate_json(self):
        with tempfile.TemporaryDirectory() as folder:
            parent = Path(folder)
            path = parent / "input.json"
            engine.write_private(path, evidence())
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(engine.read_private(path), evidence())
            with self.assertRaises(engine.Rejected):
                engine.write_private(path, {})
            path.write_text('{"schema":1,"schema":1}')
            with self.assertRaises(engine.Rejected):
                engine.read_private(path)
            path.chmod(0o644)
            with self.assertRaises(engine.Rejected):
                engine.read_private(path)
            path.chmod(0o600)
            linked = parent / "link.json"
            linked.symlink_to(path)
            with self.assertRaises(engine.Rejected):
                engine.read_private(linked)
            hard = parent / "hard.json"
            os.link(path, hard)
            with self.assertRaises(engine.Rejected):
                engine.read_private(path)
            hard.unlink()
            with (
                patch.object(engine.os, "getuid", return_value=os.getuid() + 1),
                self.assertRaises(engine.Rejected),
            ):
                engine.read_private(path)
            with (
                patch.object(engine, "MAX_BYTES", 3),
                self.assertRaises(engine.Rejected),
            ):
                engine.read_private(path)
            parent.chmod(0o755)
            with self.assertRaises(engine.Rejected):
                engine.read_private(path)
            parent.chmod(0o700)
        with self.assertRaises(engine.Rejected):
            engine.private_path(engine.CHECKOUT / "output.json", output=True)

    def test_cli_public_output_and_rejections_never_disclose_config(self):
        with tempfile.TemporaryDirectory() as folder:
            parent = Path(folder)
            source, output = parent / "input.json", parent / "output.json"
            engine.write_private(source, evidence())
            args = [
                "preview",
                "--draft-preview",
                str(source),
                "--port",
                "1/1/7",
                "--description",
                "After",
                "--output",
                str(output),
                "--verify-capture",
                str(source),
            ]
            stdout, stderr = io.StringIO(), io.StringIO()
            with (
                patch.object(engine.sys, "argv", args),
                patch.object(engine.sys, "stdout", stdout),
                patch.object(engine.sys, "stderr", stderr),
            ):
                self.assertEqual(engine.main(), 0)
            self.assertNotIn("opaque", stdout.getvalue() + stderr.getvalue())
            saved = engine.read_private(output)
            self.assertEqual(saved["verification"]["classification"], "unchanged")
            self.assertFalse(saved["preview"]["admitted"])
            with (
                patch.object(engine.sys, "argv", args),
                patch.object(engine.sys, "stderr", stderr),
            ):
                self.assertEqual(engine.main(), 2)
            self.assertNotIn("opaque", stderr.getvalue())

    def test_runtime_has_no_transport_or_credential_consumption(self):
        import ast

        tree = ast.parse(Path(engine.__file__).read_text())
        imports = {
            node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
        }
        imports.update(
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        )
        self.assertFalse(
            imports & {"socket", "paramiko", "subprocess", "requests", "urllib"}
        )
        with (
            patch.object(engine.sys, "stdin") as stdin,
            patch.dict(os.environ, {"BROCADE_ROOT_PASSWORD": "must-not-read"}),
        ):
            engine.build_preview(evidence(), "1/1/7", "After")
        stdin.read.assert_not_called()


class ObservedSerializationTests(unittest.TestCase):
    def setUp(self):
        self.baseline = CONFIG.replace(
            "interface ethernet 1/1/7\n port-name Before\n disable\n!\n", ""
        )
        self.preview = engine.build_preview(evidence(self.baseline), "1/1/7", "Spare")
        self.lines = self.preview.before_running
        self.block = ("interface ethernet 1/1/7", " port-name Spare")

    def inserted(self, index, separator=False):
        block = (*self.block, "!") if separator else self.block
        return "\n".join((*self.lines[:index], *block, *self.lines[index:]))

    def verify(self, after, restored=None, startup=None):
        return engine.verify_observed_serialization(
            self.preview,
            evidence(after, self.baseline if startup is None else startup),
            evidence(self.baseline if restored is None else restored),
        )

    def assert_not_observed(self, after, restored=None, startup=None):
        try:
            result = self.verify(after, restored, startup)
        except engine.Rejected:
            return
        self.assertFalse(result["observed_insertion_configuration_only"])
        self.assertNotEqual(result["classification"], "observed")
        self.assertFalse(result["live_admission"])

    def test_top_level_positions_with_optional_separator(self):
        # Exercise every body boundary, including global commands, ! and end.
        for index, line in enumerate(self.lines):
            if index == 0 or line.startswith(" "):
                continue
            for separator in (False, True):
                with self.subTest(index=index, separator=separator):
                    after = self.inserted(index, separator)
                    result = self.verify(after)
                    self.assertEqual(result["classification"], "observed")
                    self.assertTrue(result["observed_insertion_configuration_only"])
                    self.assertEqual(result["actual_insertion_index"], index)
                    self.assertEqual(result["actual_separator_inserted"], separator)
                    block = (*self.block, "!") if separator else self.block
                    self.assertEqual(
                        result["actual_inserted_block_sha256"],
                        hashlib.sha256(
                            ("\n".join(block) + "\n").encode("ascii")
                        ).hexdigest(),
                    )
                    self.assertTrue(
                        result["rollback_exact_original_running_and_startup"]
                    )
                    self.assertFalse(self.preview.observed_serialization_verified)
                    self.assertFalse(self.preview.admitted)

    def test_prediction_is_diagnostic_and_exact_verifier_is_preserved(self):
        predicted = "\n".join(self.preview.expected_running)
        self.assertTrue(self.verify(predicted)["predicted_match"])
        other_position = self.inserted(1, True)
        result = self.verify(other_position)
        self.assertFalse(result["predicted_match"])
        self.assertEqual(result["classification"], "observed")
        self.assertEqual(
            engine.verify_configuration(
                self.preview, evidence(other_position, self.baseline)
            )["classification"],
            "uncertain",
        )
        self.assertEqual(result["scope"], "configuration_only")
        for flag in (
            "live_admission",
            "apply_enabled",
            "task_complete",
            "observed_serialization_verified",
        ):
            self.assertFalse(result[flag])

    def test_unchanged_never_establishes_observation(self):
        result = self.verify(self.baseline)
        self.assertEqual(result["classification"], "unchanged")
        self.assertFalse(result["observed_insertion_configuration_only"])
        self.assertIsNone(result["actual_insertion_index"])
        self.assertIsNone(result["actual_inserted_block_sha256"])
        bad_restore = self.verify(
            self.baseline, restored=self.baseline.replace("vlan 1", "vlan 2")
        )
        self.assertEqual(bad_restore["classification"], "uncertain")
        self.assertFalse(bad_restore["observed_insertion_configuration_only"])
        self.assertFalse(bad_restore["rollback_exact_original_running_and_startup"])

    def test_extra_leaves_unrelated_changes_reordering_and_duplicates_fail(self):
        after = self.inserted(len(self.lines) - 1, True)
        for changed in (
            after.replace(" port-name Spare", " port-name Spare\n disable"),
            after.replace(" port-name Spare", " port-name Other"),
            after.replace(" port-name Spare\n", ""),
            after.replace(" port-name Spare", " port-name Spare\n port-name Spare"),
            after.replace("end", "\n".join(self.block) + "\nend"),
            after.replace("vlan 1", "vlan 2"),
            after.replace(" port-name Other", " port-name Changed"),
            after.replace("!\ninterface ethernet 1/1/12", "interface ethernet 1/1/12"),
            after.replace(" port-name Spare\n!", " port-name Spare\n!\n!"),
            after.replace(
                "username root password opaque-root-fixture\n"
                "username homelab_audit privilege 5 password opaque-audit-fixture",
                "username homelab_audit privilege 5 password opaque-audit-fixture\n"
                "username root password opaque-root-fixture",
            ),
        ):
            with self.subTest(changed=changed):
                self.assert_not_observed(changed)

    def test_indented_stanzas_and_global_boundaries_fail(self):
        for index, line in enumerate(self.lines):
            if index == 0 or line.startswith(" "):
                with self.subTest(index=index):
                    self.assert_not_observed(self.inserted(index))
        self.assert_not_observed(self.inserted(len(self.lines)))
        # The same rule covers nonphysical interfaces and general indented stanzas.
        for stanza in (
            "interface ve 1\n ip address 10.72.0.1 255.255.255.0\n!\n",
            "router ospf\n area 0\n!\n",
        ):
            baseline = self.baseline.replace("vlan 1", stanza + "vlan 1")
            preview = engine.build_preview(evidence(baseline), "1/1/7", "Spare")
            lines = preview.before_running
            index = next(i for i, line in enumerate(lines) if line.startswith(" "))
            after = "\n".join((*lines[:index], *self.block, *lines[index:]))
            result = engine.verify_observed_serialization(
                preview, evidence(after, baseline), evidence(baseline)
            )
            self.assertEqual(result["classification"], "uncertain")

    def test_startup_and_exact_restore_are_required(self):
        after = self.inserted(1)
        for startup in (after, self.baseline.replace("vlan 1", "vlan 2")):
            with self.subTest(startup=startup):
                self.assert_not_observed(after, startup=startup)
        for restored in (
            after,
            self.baseline.replace("end", "interface ethernet 1/1/7\n!\nend"),
            self.baseline.replace("vlan 1", "vlan 2"),
        ):
            with self.subTest(restored=restored):
                result = self.verify(after, restored)
                self.assertEqual(result["classification"], "uncertain")
                self.assertFalse(result["rollback_exact_original_running_and_startup"])
        result = engine.verify_observed_serialization(
            self.preview,
            evidence(after, self.baseline),
            evidence(self.baseline, after),
        )
        self.assertFalse(result["observed_insertion_configuration_only"])

    def test_absent_saved_baseline_scope_is_required(self):
        for preview in (
            engine.build_preview(evidence(), "1/1/7", "Spare"),
            replace(self.preview, before_startup=(*self.lines[:-1], "!", "end")),
        ):
            with self.subTest(preview=preview), self.assertRaises(engine.Rejected):
                engine.verify_observed_serialization(
                    preview,
                    evidence(self.inserted(1), self.baseline),
                    evidence(self.baseline),
                )

    def test_pure_classifier_preserves_distinct_ephemeral_writer_startup_anchor(self):
        writer = "username temporary_writer privilege 0 password opaque-writer-fixture"
        before = (*self.lines[:-1], writer, "end")
        after = (*before[:-1], *self.block, "!", "end")
        result = engine.classify_observed_serialization(
            before, self.lines, after, self.lines, "1/1/7", "Spare"
        )
        self.assertEqual(result["classification"], "observed")
        self.assertEqual(result["actual_insertion_index"], len(before) - 1)
        self.assertEqual(
            result["original_startup_sha256"], engine.configuration_hash(self.lines)
        )
        self.assertNotEqual(
            result["original_running_sha256"], result["original_startup_sha256"]
        )
        self.assertFalse(result["live_admission"])
        self.assertIn(
            "pure classification does not establish baseline authorization",
            result["limitations"],
        )
        for startup in (before, after):
            with self.subTest(startup=startup):
                changed = engine.classify_observed_serialization(
                    before, self.lines, after, startup, "1/1/7", "Spare"
                )
                self.assertEqual(changed["classification"], "uncertain")
        with self.assertRaises(engine.Rejected):
            engine.build_preview(
                evidence("\n".join(before), self.baseline), "1/1/7", "Spare"
            )

    def test_complete_after_and_restored_digest_bindings(self):
        after, restored = (
            evidence(self.inserted(1), self.baseline),
            evidence(self.baseline),
        )
        result = engine.verify_observed_serialization(self.preview, after, restored)
        self.assertEqual(result["preview_sha256"], self.preview.preview_sha256)
        self.assertEqual(
            result["baseline_input_binding_sha256"], self.preview.input_binding_sha256
        )
        for name, payload in (("after", after), ("restored", restored)):
            self.assertEqual(
                result[f"{name}_input_binding_sha256"], engine.digest(payload)
            )
            self.assertEqual(
                result[f"{name}_raw_capture_sha256"], payload["raw_capture_sha256"]
            )
            for key, value in (
                ("terminal_boundaries_complete", False),
                ("source_sha256", {}),
                ("raw_capture_sha256", {}),
                ("identity", "root"),
            ):
                changed = {**payload, key: value}
                arguments = (changed, restored) if name == "after" else (after, changed)
                with (
                    self.subTest(name=name, key=key),
                    self.assertRaises(engine.Rejected),
                ):
                    engine.verify_observed_serialization(self.preview, *arguments)
            changed = {**payload, "responses": {**payload["responses"]}}
            changed["responses"].pop("show mac-address")
            arguments = (changed, restored) if name == "after" else (after, changed)
            with self.assertRaises(engine.Rejected):
                engine.verify_observed_serialization(self.preview, *arguments)
        altered = {
            **restored,
            "responses": {**restored["responses"], "show mac-address": "different"},
        }
        rebound = engine.verify_observed_serialization(self.preview, after, altered)
        self.assertNotEqual(
            result["restored_input_binding_sha256"],
            rebound["restored_input_binding_sha256"],
        )
        self.assertTrue(rebound["observed_insertion_configuration_only"])


if __name__ == "__main__":
    unittest.main()
