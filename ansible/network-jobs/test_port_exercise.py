"""Real private-ledger integration with a mutating independent-evidence adapter."""

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import port_description as engine
import port_exercise as exercise
from port_exercise_ledger import PHASES, Rejected, locked_exercise
from test_port_description import CONFIG, evidence as base_evidence

BASELINE = engine.configuration(CONFIG)
WRITER = "username homelab_writer privilege 4 password opaque-writer-fixture"
BLOCK = (
    f"interface ethernet {exercise.PORT}",
    f" port-name {exercise.DESCRIPTION}",
    "!",
)


def evidence(running, startup):
    payload = base_evidence("\n".join(running), "\n".join(startup))
    old = "show interfaces ethernet 1/1/7"
    new = f"show interfaces ethernet {exercise.PORT}"
    payload["selected_port"] = exercise.PORT
    payload["commands"][-1] = new
    payload["responses"][new] = payload["responses"].pop(old)
    return payload


class Device:
    def __init__(self, ledger):
        self.ledger = ledger
        self.running = BASELINE
        self.startup = BASELINE
        self.events = []
        self.fail = None
        self.callback = "once"
        self.delta = None
        self.observe_count = 0
        self.drift_at = None
        self.gate_failure = None

    def admit_new_change(self):
        self.events.append("new_gate")
        if self.gate_failure == "new":
            raise engine.Rejected("new gate failed")

    def admit_recovery(self):
        self.events.append("recovery_gate")
        if self.gate_failure == "recovery":
            raise engine.Rejected("recovery gate failed")

    def observe(self):
        self.observe_count += 1
        self.events.append("observe")
        if self.fail == f"observe-{self.observe_count}":
            raise engine.Rejected("observation failed")
        if self.drift_at == self.observe_count:
            self.running = tuple(
                "vlan 2" if line == "vlan 1" else line for line in self.running
            )
        payload = evidence(self.running, self.startup)
        if self.delta == "incomplete":
            payload["responses"].pop("show mac-address")
        return payload

    def mutate(self, phase, before_send, change):
        self.events.append(phase)
        # The intent must already exist on disk, before any simulated send.
        assert self.ledger.phases[-1]["phase"] == phase
        assert self.ledger.phase_path(len(self.ledger.phases), phase).exists()
        if self.fail == phase:
            raise engine.Rejected("write failed")
        if self.callback == "never":
            return None
        if self.callback == "async":

            async def later():
                before_send()

            return later()
        before_send()
        change()
        if self.delta == phase + "-unrelated":
            self.running = tuple(
                "vlan 2" if line == "vlan 1" else line for line in self.running
            )
        if self.delta == phase + "-save":
            self.startup = self.running
        if self.callback == "twice":
            try:
                before_send()
            except engine.Rejected:
                pass
        if self.callback == "unknown":
            return "unknown response"
        return None

    def create_writer(self, before_send):
        def change():
            writer = (
                WRITER
                if self.delta != "wrong-account"
                else WRITER.replace("privilege 4", "privilege 0")
            )
            self.running = (*self.running[:3], writer, *self.running[3:])

        return self.mutate("bootstrap_intent", before_send, change)

    def set_description(self, before_send):
        def change():
            self.running = (*self.running[:-1], *BLOCK, "end")

        return self.mutate("description_intent", before_send, change)

    def clear_description(self, before_send):
        def change():
            self.running = self.running[:-4] + ("end",)
            if self.delta == "residual":
                self.running = (*self.running[:-1], BLOCK[0], "!", "end")

        return self.mutate("inverse_intent", before_send, change)

    def remove_writer(self, before_send):
        def change():
            self.running = tuple(line for line in self.running if line != WRITER)

        return self.mutate("removal_intent", before_send, change)

    def verify_access(self):
        self.events.append("access")
        if self.fail == "access":
            raise engine.Rejected("access failed")


class ExerciseTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.parent = Path(self.folder.name)
        self.runtime = self.parent / "run"
        self.runtime.mkdir(mode=0o700)
        self.preview = engine.build_preview(
            evidence(BASELINE, BASELINE), exercise.PORT, exercise.DESCRIPTION
        )

    def execute(self, device, ledger, preview=None, privilege=4):
        return exercise.run_exercise(
            self.preview if preview is None else preview, ledger, device, privilege
        )

    def test_complete_cycle_uses_real_durable_order_and_exact_baseline(self):
        with locked_exercise(self.parent, self.runtime) as ledger:
            device = Device(ledger)
            result = self.execute(device, ledger)
            self.assertEqual(device.running, BASELINE)
            self.assertEqual(device.startup, BASELINE)
            self.assertEqual(tuple(record["phase"] for record in ledger.phases), PHASES)
            self.assertFalse(ledger.pending.exists())
            self.assertTrue((self.runtime / "exercise-complete.json").exists())
            baseline_hash = engine.configuration_hash(BASELINE)
            ephemeral = (*BASELINE[:3], WRITER, *BASELINE[3:])
            ephemeral_hash = engine.configuration_hash(ephemeral)
            for key in (
                "original_running_sha256",
                "original_startup_sha256",
                "final_running_sha256",
                "final_startup_sha256",
                "serialization_baseline_startup_sha256",
                "serialization_after_startup_sha256",
            ):
                self.assertEqual(result[key], baseline_hash)
            self.assertEqual(
                result["serialization_baseline_running_sha256"], ephemeral_hash
            )
            self.assertNotEqual(
                result["serialization_baseline_running_sha256"],
                result["original_running_sha256"],
            )
            self.assertEqual(
                result["serialization_after_running_sha256"],
                engine.configuration_hash((*ephemeral[:-1], *BLOCK, "end")),
            )
            self.assertTrue(result["rollback_exact_original_running_and_startup"])
            self.assertTrue(result["operation_cycle_passed"])
            self.assertFalse(result["predicted_match"])
            self.assertTrue(result["actual_separator_inserted"])
            self.assertEqual(result["scope"], "configuration_only")
            for flag in (
                "task_complete",
                "live_admission",
                "apply_enabled",
                "observed_serialization_verified",
            ):
                self.assertFalse(result[flag])
            self.assertEqual(device.events.count("new_gate"), 5)
            self.assertEqual(device.events.count("recovery_gate"), 4)

    def test_each_write_failure_retains_intent_and_never_cleans_up(self):
        for phase in PHASES[::2]:
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as folder:
                parent = Path(folder)
                runtime = parent / "run"
                runtime.mkdir(mode=0o700)
                with locked_exercise(parent, runtime) as ledger:
                    device = Device(ledger)
                    device.fail = phase
                    with self.assertRaises(engine.Rejected):
                        self.execute(device, ledger)
                    self.assertTrue(ledger.pending.exists())
                    self.assertEqual(ledger.phases[-1]["phase"], phase)
                    self.assertEqual(
                        [event for event in device.events if event in PHASES],
                        list(PHASES[::2])[: PHASES.index(phase) // 2 + 1],
                    )

    def test_missing_repeated_async_and_unknown_callbacks_stop_pending(self):
        for callback in ("never", "twice", "async", "unknown"):
            with (
                self.subTest(callback=callback),
                tempfile.TemporaryDirectory() as folder,
            ):
                parent = Path(folder)
                runtime = parent / "run"
                runtime.mkdir(mode=0o700)
                with locked_exercise(parent, runtime) as ledger:
                    device = Device(ledger)
                    device.callback = callback
                    with self.assertRaises(engine.Rejected):
                        self.execute(device, ledger)
                    self.assertTrue(ledger.pending.exists())
                    self.assertEqual(ledger.phases[-1]["phase"], "bootstrap_intent")
                    self.assertNotIn("description_intent", device.events)

    def test_unknown_delta_saved_startup_and_residual_stop_without_inverse(self):
        for delta, last in (
            ("wrong-account", "bootstrap_intent"),
            ("bootstrap_intent-unrelated", "bootstrap_intent"),
            ("bootstrap_intent-save", "bootstrap_intent"),
            ("description_intent-unrelated", "description_intent"),
            ("description_intent-save", "description_intent"),
            ("inverse_intent-unrelated", "inverse_intent"),
            ("inverse_intent-save", "inverse_intent"),
            ("residual", "inverse_intent"),
            ("removal_intent-unrelated", "removal_intent"),
            ("removal_intent-save", "removal_intent"),
        ):
            # Removal-save saves E and is harmless; simulate a genuinely changed startup separately.
            if delta == "removal_intent-save":
                continue
            with self.subTest(delta=delta), tempfile.TemporaryDirectory() as folder:
                parent = Path(folder)
                runtime = parent / "run"
                runtime.mkdir(mode=0o700)
                with locked_exercise(parent, runtime) as ledger:
                    device = Device(ledger)
                    device.delta = delta
                    with self.assertRaises(engine.Rejected):
                        self.execute(device, ledger)
                    self.assertTrue(ledger.pending.exists())
                    self.assertEqual(ledger.phases[-1]["phase"], last)
                    if last == "description_intent":
                        self.assertNotIn("inverse_intent", device.events)

    def test_every_postwrite_observation_failure_stops_current_intent(self):
        for number, phase in (
            (4, "bootstrap_intent"),
            (7, "description_intent"),
            (10, "inverse_intent"),
            (13, "removal_intent"),
        ):
            with self.subTest(number=number), tempfile.TemporaryDirectory() as folder:
                parent = Path(folder)
                runtime = parent / "run"
                runtime.mkdir(mode=0o700)
                with locked_exercise(parent, runtime) as ledger:
                    device = Device(ledger)
                    device.fail = f"observe-{number}"
                    with self.assertRaises(engine.Rejected):
                        self.execute(device, ledger)
                    self.assertEqual(ledger.phases[-1]["phase"], phase)
                    self.assertTrue(ledger.pending.exists())

    def test_callback_fresh_check_rejects_concurrent_drift_before_send(self):
        with locked_exercise(self.parent, self.runtime) as ledger:
            device = Device(ledger)
            device.drift_at = 3
            with self.assertRaises(engine.Rejected):
                self.execute(device, ledger)
            self.assertNotIn(WRITER, device.running)
            self.assertEqual(ledger.phases[-1]["phase"], "bootstrap_intent")
            self.assertTrue(ledger.pending.exists())

    def test_access_failure_retains_removal_intent_even_at_exact_baseline(self):
        with locked_exercise(self.parent, self.runtime) as ledger:
            device = Device(ledger)
            device.fail = "access"
            with self.assertRaises(engine.Rejected):
                self.execute(device, ledger)
            self.assertEqual(device.running, BASELINE)
            self.assertTrue(ledger.pending.exists())
            self.assertEqual(ledger.phases[-1]["phase"], "removal_intent")
            self.assertFalse((self.runtime / "exercise-complete.json").exists())

    def test_fixed_scope_preview_hashes_sources_privilege_and_noop_rejected(self):
        for preview, privilege in (
            (replace(self.preview, host="other"), 4),
            (replace(self.preview, original_running_sha256="a" * 64), 4),
            (replace(self.preview, source_sha256=()), 4),
            (replace(self.preview, selected_port="1/1/7"), 4),
            (self.preview, True),
            (self.preview, 0),
            (self.preview, 5),
        ):
            with self.subTest(preview=preview.host, privilege=privilege):
                with locked_exercise(self.parent, self.runtime) as ledger:
                    device = Device(ledger)
                    with self.assertRaises(engine.Rejected):
                        self.execute(device, ledger, preview, privilege)
                    self.assertFalse(device.events)
                    self.assertFalse(ledger.pending.exists())
        with locked_exercise(self.parent, self.runtime) as ledger:
            device = Device(ledger)
            with patch.object(
                exercise,
                "SOURCE_SHA256",
                {**exercise.SOURCE_SHA256, "writer": "a" * 64},
            ):
                with self.assertRaises(engine.Rejected):
                    self.execute(device, ledger)
            self.assertFalse(device.events)

    def test_gate_failure_and_incomplete_evidence_never_start(self):
        with locked_exercise(self.parent, self.runtime) as ledger:
            device = Device(ledger)
            device.gate_failure = "new"
            with self.assertRaises(engine.Rejected):
                self.execute(device, ledger)
            self.assertFalse(ledger.pending.exists())
            device.gate_failure = None
            device.delta = "incomplete"
            with self.assertRaises(engine.Rejected):
                self.execute(device, ledger)
            self.assertFalse(ledger.pending.exists())

    def test_async_gate_observation_and_access_are_rejected_without_warnings(self):
        for method in (
            "admit_new_change",
            "admit_recovery",
            "observe",
            "verify_access",
        ):
            with self.subTest(method=method), tempfile.TemporaryDirectory() as folder:
                parent = Path(folder)
                runtime = parent / "run"
                runtime.mkdir(mode=0o700)
                with locked_exercise(parent, runtime) as ledger:
                    device = Device(ledger)

                    async def asynchronous():
                        return None

                    setattr(device, method, asynchronous)
                    with self.assertRaises(engine.Rejected):
                        self.execute(device, ledger)
                    if method in ("observe", "admit_new_change"):
                        self.assertFalse(ledger.pending.exists())
                    else:
                        self.assertTrue(ledger.pending.exists())

    def test_gate_unknown_response_is_not_admission(self):
        with locked_exercise(self.parent, self.runtime) as ledger:
            device = Device(ledger)
            with patch.object(device, "admit_new_change", return_value=True):
                with self.assertRaises(engine.Rejected):
                    self.execute(device, ledger)
            self.assertFalse(ledger.pending.exists())
            self.assertNotIn("bootstrap_intent", device.events)

    def test_pre_send_source_and_current_intent_are_rechecked(self):
        for failure in ("source", "intent", "gate-swallowed"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as folder:
                parent = Path(folder)
                runtime = parent / "run"
                runtime.mkdir(mode=0o700)
                with locked_exercise(parent, runtime) as ledger:
                    device = Device(ledger)

                    def blocked(before_send):
                        if failure == "source":
                            with patch.object(
                                exercise,
                                "SOURCE_SHA256",
                                {**exercise.SOURCE_SHA256, "writer": "a" * 64},
                            ):
                                before_send()
                        elif failure == "intent":
                            path = ledger.phase_path(1, "bootstrap_intent")
                            path.write_bytes(
                                path.read_bytes().replace(
                                    b"bootstrap_intent", b"inverse_intent"
                                )
                            )
                            before_send()
                        else:
                            device.gate_failure = "new"
                            try:
                                before_send()
                            except engine.Rejected:
                                pass

                    with patch.object(device, "create_writer", side_effect=blocked):
                        with self.assertRaises((engine.Rejected, Rejected)):
                            self.execute(device, ledger)
                    self.assertTrue(ledger.pending.exists())
                    self.assertNotIn(WRITER, device.running)
                    self.assertNotIn("description_intent", device.events)

    def test_each_fresh_prewrite_state_check_stops_further_writes(self):
        for number, last in (
            (2, None),
            (5, "bootstrap_observed"),
            (8, "description_observed"),
            (11, "inverse_observed"),
        ):
            with self.subTest(number=number), tempfile.TemporaryDirectory() as folder:
                parent = Path(folder)
                runtime = parent / "run"
                runtime.mkdir(mode=0o700)
                with locked_exercise(parent, runtime) as ledger:
                    device = Device(ledger)
                    device.drift_at = number
                    with self.assertRaises(engine.Rejected):
                        self.execute(device, ledger)
                    self.assertTrue(ledger.pending.exists())
                    self.assertEqual(
                        ledger.phases[-1]["phase"] if ledger.phases else None, last
                    )

    def test_existing_writer_selected_stanza_or_pending_never_become_noop(self):
        configurations = (
            (*BASELINE[:3], WRITER, *BASELINE[3:]),
            (*BASELINE[:-1], *BLOCK, "end"),
        )
        for configuration in configurations:
            with self.subTest(configuration=configuration):
                preview = engine.build_preview(
                    evidence(configuration, configuration),
                    exercise.PORT,
                    exercise.DESCRIPTION,
                )
                with locked_exercise(self.parent, self.runtime) as ledger:
                    device = Device(ledger)
                    with self.assertRaises(engine.Rejected):
                        self.execute(device, ledger, preview)
                    self.assertFalse(device.events)
        with locked_exercise(self.parent, self.runtime) as ledger:
            device = Device(ledger)
            device.fail = "bootstrap_intent"
            with self.assertRaises(engine.Rejected):
                self.execute(device, ledger)
            device.fail = None
            device.events.clear()
            with self.assertRaises((engine.Rejected, Rejected)):
                self.execute(device, ledger)
            self.assertNotIn("bootstrap_intent", device.events)
            self.assertTrue(ledger.pending.exists())

    def test_final_startup_drift_retains_removal_intent(self):
        with locked_exercise(self.parent, self.runtime) as ledger:
            device = Device(ledger)
            original = device.remove_writer

            def changed_startup(before_send):
                original(before_send)
                device.startup = (*BASELINE[:-1], "!", "end")

            with patch.object(device, "remove_writer", side_effect=changed_startup):
                with self.assertRaises(engine.Rejected):
                    self.execute(device, ledger)
            self.assertEqual(ledger.phases[-1]["phase"], "removal_intent")
            self.assertTrue(ledger.pending.exists())
            self.assertNotIn("access", device.events)

    def test_recovery_gate_failure_preserves_recognized_applied_state(self):
        with locked_exercise(self.parent, self.runtime) as ledger:
            device = Device(ledger)
            device.gate_failure = "recovery"
            with self.assertRaises(engine.Rejected):
                self.execute(device, ledger)
            self.assertEqual(ledger.phases[-1]["phase"], "description_observed")
            self.assertIn(BLOCK[0], device.running)
            self.assertNotIn("inverse_intent", device.events)
            self.assertTrue(ledger.pending.exists())


if __name__ == "__main__":
    unittest.main()
