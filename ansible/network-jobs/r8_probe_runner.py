"""Run and semantically admit the fixed R8 probe over a privileged console."""

import hashlib
from collections.abc import Callable
from pathlib import Path
from typing import Any

import native_trunk_transport as transport
import port_exercise_ledger as storage
import r8_probe_admission as admission
import r8_guest_acceptance as guest_acceptance
import r8_guest_producer as guest_producer
import native_trunk_plan as trunk_plan

SOURCE = Path(__file__).resolve()
SOURCE_SHA256 = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
SOURCE_PINS = {
    "active40g_observation.py": "e42f35946342611becfd48a2f265eb08bd0fb9b69b48b0f6df8ba66832180e2e",
    "native_trunk_plan.py": "f3ed46c01844752a95023cbf4f21e9fda4469ed47b2edc78afc92a711aae03ea",
    "native_trunk_transport.py": "d11314cbc21f6ca25054b31a53ee488283353d41bf43a4ed2dd3209f67a4c171",
    "r8_probe_admission.py": "4dde38282113bc59e32f5ee430f7b5fc8f610825cfb1cd8d1eaeadd87093a133",
    "r8_guest_acceptance.py": "d25765cce6406120fe628d6d64a30c32f165bbce49c411ffd3077bf4ef5881f2",
    "r8_guest_producer.py": "a2a25c190bc19555b0cf991ac1ed009d99ae5cd7da72b614b0b19b15f3c9da5e",
    "r8_guest_generator.py": "93a5eef438f754b3792d26b3bd0112227ff9df5f89672b8263b9476ee20003dd",
    "r8_guest_parent.py": "04323e709bd81f4b10420dc8f9ae94e82469b6a553730ef0f24c33234136d6ae",
}


class Rejected(RuntimeError):
    """The current-source R8 caller or one of its dependencies changed."""


def unchanged_sources() -> None:
    if hashlib.sha256(SOURCE.read_bytes()).hexdigest() != SOURCE_SHA256:
        raise Rejected("R8 caller source drift")
    for name, expected in SOURCE_PINS.items():
        if hashlib.sha256(SOURCE.with_name(name).read_bytes()).hexdigest() != expected:
            raise Rejected("R8 caller dependency drift: " + name)
    admission._require_current_source()


def run_and_admit(
    guarded: storage.ExerciseLedger,
    baseline: tuple[str, ...],
    observe: Callable[[], dict[str, Any]],
    console: Any,
    admit: Callable[[], None],
    binding: dict[str, str],
) -> dict[str, object]:
    """Run fixed commands on the supplied console and admit only semantic evidence."""
    unchanged_sources()
    writer = transport.R8ProbeCycleTransport(console)
    try:
        result = admission.run_and_admit_cycle(
            guarded,
            baseline,
            observe,
            writer.send,
            admit,
            binding,
        )
        unchanged_sources()
        return result
    finally:
        writer.close()


def run_and_admit_full_trunk(
    guarded: storage.ExerciseLedger,
    baseline: tuple[str, ...],
    observe: Callable[[], dict[str, Any]],
    console: Any,
    admit: Callable[[], None],
    binding: dict[str, str],
    held_guest_proof: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]],
    guest_policy: dict[str, Any],
    r8_recovery_session: Callable[
        [], tuple[Callable[[], dict[str, Any]], Any, Callable[[], None]]
    ]
    | None = None,
    operation_budget: Any = None,
) -> dict[str, object]:
    """Own the current-source full-tag cycle and semantic receipt admission."""
    unchanged_sources()
    if not isinstance(held_guest_proof, guest_producer.Producer):
        raise guest_acceptance.Rejected("source-bound R8 guest producer required")
    selected = trunk_plan.build_r8_full_trunk_plan(baseline, baseline)
    writer = transport.R8FullTrunkCycleTransport(console, selected.initial_state)

    def validated_guest_proof(
        held: dict[str, Any], proof_binding: dict[str, Any]
    ) -> dict[str, Any]:
        unchanged_sources()
        if operation_budget is None:
            proof = held_guest_proof(held, proof_binding)
        else:
            proof = held_guest_proof(
                held,
                proof_binding,
                deadline=operation_budget.guest_proof_deadline,
            )
        if not isinstance(proof, dict):
            raise guest_acceptance.Rejected("held guest proof object required")
        guest_acceptance.validate(
            proof,
            binding=proof_binding,
            policy=guest_policy,
        )
        unchanged_sources()
        return proof

    try:
        result = admission.run_and_admit_full_trunk_cycle(
            guarded,
            baseline,
            observe,
            writer.send,
            admit,
            binding,
            validated_guest_proof,
            r8_recovery_session,
            operation_budget,
        )
        unchanged_sources()
        return result
    finally:
        writer.close()
