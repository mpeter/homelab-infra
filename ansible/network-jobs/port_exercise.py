"""Bounded configuration exercise with injected, independently admitted adapters.

No operational adapter or command entrypoint is supplied here. Fixture success
establishes configuration protocol behavior, not live admission or restoration.
"""

from collections.abc import Callable
from dataclasses import asdict
import hashlib
import inspect
from pathlib import Path
import re
from typing import Any, Protocol

import port_description as engine
from port_exercise_ledger import ExerciseLedger

PORT = "1/1/47"
DESCRIPTION = "homelab-description-exercise"
SOURCE_PATHS = {
    **engine.SOURCE_PATHS,
    "writer": Path(__file__).with_name("port_writer.py"),
    "ledger": Path(__file__).with_name("port_exercise_ledger.py"),
    "orchestrator": Path(__file__).resolve(),
}
SOURCE_SHA256 = {
    name: hashlib.sha256(path.read_bytes()).hexdigest()
    for name, path in SOURCE_PATHS.items()
}


class Adapter(Protocol):
    """Trusted adapter owns operational gates, identities and fixed commands.

    Write methods synchronously invoke before_send exactly once immediately
    before sending the fixed operation. They never retry or save configuration.
    observe returns complete independent homelab_audit collector evidence.
    """

    def admit_new_change(self) -> None: ...
    def admit_recovery(self) -> None: ...
    def observe(self) -> dict[str, Any]: ...
    def create_writer(self, before_send: Callable[[], None]) -> None: ...
    def set_description(self, before_send: Callable[[], None]) -> None: ...
    def clear_description(self, before_send: Callable[[], None]) -> None: ...
    def remove_writer(self, before_send: Callable[[], None]) -> None: ...
    def verify_access(self) -> None: ...


def synchronous(value: Any) -> Any:
    if inspect.isawaitable(value):
        if inspect.iscoroutine(value):
            value.close()
        raise engine.Rejected("synchronous adapter required")
    return value


def no_result(method: Callable[..., Any], *args: Any) -> None:
    if synchronous(method(*args)) is not None:
        raise engine.Rejected("unexpected adapter response")


def unchanged_sources() -> None:
    engine.unchanged_sources()
    if any(
        hashlib.sha256(path.read_bytes()).hexdigest() != SOURCE_SHA256[name]
        for name, path in SOURCE_PATHS.items()
    ):
        raise engine.Rejected("exercise source drift")


def validate_preview(preview: engine.Preview, writer_privilege: int) -> None:
    unchanged_sources()
    if (
        type(writer_privilege) is not int
        or writer_privilege != 4
        or not isinstance(preview, engine.Preview)
        or type(preview.schema) is not int
        or preview.schema != 1
        or preview.selected_port != PORT
        or preview.desired_description != DESCRIPTION
        or preview.original_description is not None
        or preview.host != engine.HOST
        or preview.model != engine.MODEL
        or preview.release != engine.RELEASE
        or preview.accepted_host_key_fingerprint != engine.FINGERPRINT
        or preview.expected_execution_environment_sha256 != engine.EE_DIGEST
        or preview.source_sha256 != tuple(sorted(engine.SOURCE_SHA256.items()))
        or preview.before_running != preview.before_startup
        or preview.original_running_sha256
        != engine.configuration_hash(preview.before_running)
        or preview.original_startup_sha256
        != engine.configuration_hash(preview.before_startup)
        or preview.expected_running_sha256
        != engine.configuration_hash(preview.expected_running)
        or not engine.valid_digest(preview.input_binding_sha256)
        or preview.forward_commands
        != (
            "configure terminal",
            f"interface ethernet {PORT}",
            f"port-name {DESCRIPTION}",
            "exit",
            "exit",
        )
        or preview.inverse_commands
        != (
            "configure terminal",
            f"interface ethernet {PORT}",
            "no port-name",
            "exit",
            "exit",
        )
    ):
        raise engine.Rejected("fixed exercise preview binding")
    before = preview.before_running
    if engine.configuration("\n".join(before)) != before or PORT in engine.stanzas(
        before
    ):
        raise engine.Rejected("absent selected interface required")
    if any(re.match(r"username homelab_writer\b", line.lstrip()) for line in before):
        raise engine.Rejected("writer must be absent")
    audit = [
        line for line in before if re.match(r"username homelab_audit\b", line.lstrip())
    ]
    if len(audit) != 1 or not re.fullmatch(
        r"username homelab_audit privilege 5 password \S[^\r\n]*", audit[0]
    ):
        raise engine.Rejected("persisted audit identity required")
    candidate = engine.classify_observed_serialization(
        before, before, preview.expected_running, before, PORT, DESCRIPTION
    )
    if candidate["classification"] != "observed":
        raise engine.Rejected("invalid preview candidate")
    commands = (*engine.COMMANDS, f"show interfaces ethernet {PORT}")
    if (
        tuple(name for name, _ in preview.response_sha256) != commands
        or any(not engine.valid_digest(value) for _, value in preview.response_sha256)
        or len(preview.raw_capture_sha256) not in (6, 10)
        or tuple(name for name, _ in preview.raw_capture_sha256)
        != tuple(
            f"capture-{i:02}.txt" for i in range(1, len(preview.raw_capture_sha256) + 1)
        )
        or any(
            not engine.valid_digest(value) for _, value in preview.raw_capture_sha256
        )
    ):
        raise engine.Rejected("preview capture binding")


def writer_state(before: tuple[str, ...], after: tuple[str, ...]) -> None:
    accounts = [
        (i, line)
        for i, line in enumerate(after)
        if re.match(r"username homelab_writer\b", line.lstrip())
    ]
    if len(accounts) != 1:
        raise engine.Rejected("account-only writer observation required")
    index, line = accounts[0]
    if (
        not re.fullmatch(
            r"username homelab_writer privilege 4 password \S[^\r\n]*", line
        )
        or index == 0
        or index >= len(after) - 1
        or before[index].startswith(" ")
        or after[:index] + after[index + 1 :] != before
    ):
        raise engine.Rejected("unexpected writer delta")


def run_exercise(
    preview: engine.Preview,
    ledger: ExerciseLedger,
    adapter: Adapter,
    writer_privilege: int,
) -> dict[str, Any]:
    """Execute one cycle; any uncertainty leaves pending intent for inspection.

    The caller holds the canonical ledger lock throughout. There is deliberately
    no resume, cleanup-on-error, blind inverse, retry, save or recovery override.
    """
    validate_preview(preview, writer_privilege)
    baseline = preview.before_running
    binding = {
        "baseline_running_sha256": preview.original_running_sha256,
        "baseline_startup_sha256": preview.original_startup_sha256,
        "preview_sha256": preview.preview_sha256,
        "execution_environment_sha256": engine.EE_DIGEST,
        "engine_sha256": SOURCE_SHA256["engine"],
        "writer_sha256": SOURCE_SHA256["writer"],
        "bootstrap_sha256": SOURCE_SHA256["bootstrap"],
    }

    def observe() -> tuple[tuple[str, ...], tuple[str, ...], dict[str, str]]:
        payload = synchronous(adapter.observe())
        running, startup = engine.evidence_config(payload, PORT)
        return (
            running,
            startup,
            {
                "running_sha256": engine.configuration_hash(running),
                "startup_sha256": engine.configuration_hash(startup),
                "evidence_sha256": engine.digest(payload),
            },
        )

    def exact(expected: tuple[str, ...]) -> None:
        running, startup, _ = observe()
        if running != expected or startup != baseline:
            raise engine.Rejected("fresh state differs from expected prior state")

    exact(baseline)
    no_result(adapter.admit_new_change)
    unchanged_sources()
    ledger.begin(binding)

    def write(
        phase: str,
        method: Callable[[Callable[[], None]], None],
        expected: tuple[str, ...],
        gate: Callable[[], None],
    ) -> None:
        exact(expected)
        no_result(gate)
        unchanged_sources()
        ledger.append_phase(phase, {})
        intent = dict(ledger.phases[-1])
        calls = 0
        authorized = False
        active = True

        def before_send() -> None:
            nonlocal calls, authorized
            calls += 1
            if not active or calls != 1:
                authorized = False
                raise engine.Rejected("write callback must run once synchronously")
            ledger.load(binding)
            if ledger.phases[-1] != intent:
                raise engine.Rejected("current durable intent changed")
            exact(expected)
            no_result(gate)
            unchanged_sources()
            ledger.load(binding)
            if ledger.phases[-1] != intent:
                raise engine.Rejected("current durable intent changed")
            unchanged_sources()
            authorized = True

        try:
            no_result(method, before_send)
        finally:
            active = False
        if calls != 1 or not authorized:
            raise engine.Rejected("write callback was not invoked")

    write("bootstrap_intent", adapter.create_writer, baseline, adapter.admit_new_change)
    ephemeral, startup, metadata = observe()
    writer_state(baseline, ephemeral)
    if startup != baseline:
        raise engine.Rejected("writer bootstrap persisted configuration")
    ledger.append_phase("bootstrap_observed", metadata)

    write(
        "description_intent",
        adapter.set_description,
        ephemeral,
        adapter.admit_new_change,
    )
    applied, startup, metadata = observe()
    result = engine.classify_observed_serialization(
        ephemeral, baseline, applied, startup, PORT, DESCRIPTION
    )
    if result["classification"] != "observed":
        raise engine.Rejected("description observation is uncertain")
    ledger.append_phase("description_observed", metadata)

    write("inverse_intent", adapter.clear_description, applied, adapter.admit_recovery)
    restored, startup, metadata = observe()
    if restored != ephemeral or startup != baseline:
        raise engine.Rejected("inverse did not restore exact account-only state")
    ledger.append_phase("inverse_observed", metadata)

    write("removal_intent", adapter.remove_writer, ephemeral, adapter.admit_recovery)
    final, startup, metadata = observe()
    if final != baseline or startup != baseline:
        raise engine.Rejected("writer removal did not restore exact baseline")
    no_result(adapter.verify_access)
    unchanged_sources()
    ledger.append_phase("final_observed", metadata)
    ledger.finish()
    predicted = tuple(
        line for line in applied if not re.match(r"username homelab_writer\b", line)
    )
    result["serialization_baseline_running_sha256"] = result.pop(
        "original_running_sha256"
    )
    result["serialization_baseline_startup_sha256"] = result.pop(
        "original_startup_sha256"
    )
    result["serialization_after_running_sha256"] = result.pop("after_running_sha256")
    result["serialization_after_startup_sha256"] = result.pop("after_startup_sha256")
    result.update(
        original_running_sha256=preview.original_running_sha256,
        original_startup_sha256=preview.original_startup_sha256,
        final_running_sha256=engine.configuration_hash(final),
        final_startup_sha256=engine.configuration_hash(startup),
        operation_cycle_passed=True,
        predicted_match=predicted == preview.expected_running,
        rollback_exact_original_running_and_startup=True,
        preview_sha256=engine.digest(asdict(preview)),
        task_complete=False,
    )
    return result
