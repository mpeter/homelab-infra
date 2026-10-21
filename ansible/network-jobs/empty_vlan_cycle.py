"""Fixed unsaved VLAN qualification cycles; transport and live admission are caller-owned."""

import os
from collections.abc import Callable
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

import port_description as evidence
import port_exercise as exercise
import port_exercise_ledger as storage
import native_trunk_observation
import native_trunk_plan
import standby_native_observation
import trunk_link_admission
import trunk_observation
import trunk_plan
import trunk_step

COMMANDS = (
    "configure terminal",
    "vlan 10 name LAB-MGMT by port",
    "exit",
    "no vlan 10",
    "exit",
)
STANDBY_TAGGED_COMMANDS = (
    "configure terminal",
    "vlan 10 name LAB-MGMT by port",
    "tagged ethernet 1/2/6",
    "no tagged ethernet 1/2/6",
    "no vlan 10",
    "exit",
)

STANDBY_NATIVE_COMMANDS = (
    "configure terminal",
    "vlan 10 name LAB-MGMT by port",
    "tagged ethernet 1/2/6",
    "exit",
    "interface ethernet 1/2/6",
    "dual-mode 1",
    "exit",
    "exit",
    "configure terminal",
    "interface ethernet 1/2/6",
    "no dual-mode 1",
    "exit",
    "vlan 10",
    "no tagged ethernet 1/2/6",
    "no vlan 10",
    "exit",
)

FULL_TRUNK_COMMANDS = (
    *trunk_plan.FORWARD_COMMANDS,
    "configure terminal",
    "no vlan 40",
    "no vlan 30",
    "no vlan 20",
    "no vlan 10",
    "exit",
)
R8_PROBE_CYCLE_COMMANDS = (
    *native_trunk_plan.R8_PROBE_FORWARD,
    *native_trunk_plan.r8_probe_inverse_commands(
        native_trunk_plan.R8_PROBE_FINAL_STATE
    ),
)
R8_FULL_TRUNK_CYCLE_COMMANDS = (
    *native_trunk_plan.R8_FULL_FORWARD,
    *native_trunk_plan.R8_FULL_INVERSE,
)


class CycleProfile(Enum):
    EMPTY = "empty_vlan10_cycle"
    STANDBY_TAGGED = "standby_tagged_vlan10_cycle"
    FULL_TRUNK = "full_trunk_cycle"
    STANDBY_NATIVE = "standby_native_vlan10_cycle"
    R8_PROBE = "r8_probe_cycle"
    R8_FULL_TRUNK = "r8_full_trunk_cycle"

    @property
    def commands(self) -> tuple[str, ...]:
        return {
            CycleProfile.EMPTY: COMMANDS,
            CycleProfile.STANDBY_TAGGED: STANDBY_TAGGED_COMMANDS,
            CycleProfile.FULL_TRUNK: FULL_TRUNK_COMMANDS,
            CycleProfile.STANDBY_NATIVE: STANDBY_NATIVE_COMMANDS,
            CycleProfile.R8_PROBE: R8_PROBE_CYCLE_COMMANDS,
            CycleProfile.R8_FULL_TRUNK: R8_FULL_TRUNK_CYCLE_COMMANDS,
        }[self]

    @property
    def phases(self) -> tuple[str, ...]:
        return tuple(
            phase
            for i in range(len(self.commands))
            for phase in (f"command_{i}_intent", f"command_{i}_observed")
        ) + ("final_observed",)


BINDING_KEYS = frozenset(
    (
        "baseline_running_sha256",
        "baseline_startup_sha256",
        "source_binding_sha256",
        "execution_environment_sha256",
        "preview_sha256",
        "native_recovery_proof_sha256",
    )
)
SOURCE_PATHS = {
    **exercise.SOURCE_PATHS,
    **{
        name: Path(__file__).with_name(name + ".py")
        for name in (
            "trunk_plan",
            "trunk_step",
            "trunk_observation",
            "trunk_link_admission",
            "trunk_writer",
            "empty_vlan_cycle",
            "empty_vlan_transport",
            "standby_native_observation",
            "standby_native_transport",
            "native_trunk_plan",
            "native_trunk_observation",
            "native_trunk_transport",
            "bond_vlan_membership",
            "standby_native_membership",
            "native_trunk_serial_plan",
            "r8_probe_admission",
            "r8_root_session",
            "r8_current_observation",
            "r8_probe_runner",
            "r8_pending_restorer",
            "active40g_observation",
            "r8_guest_generator",
            "r8_guest_parent",
            "r8_guest_producer",
            "r8_guest_acceptance",
            "writer_account",
            "exercise_observation",
            "writer_syntax",
        )
    },
}
SOURCE_PATHS["writer_syntax"] = Path(__file__).with_name("inspect-port-syntax.py")
_GUEST_ROOT = Path(__file__).with_name("r8-guest-traffic")
SOURCE_PATHS.update(
    {
        "guest_runner": _GUEST_ROOT / "run.py",
        "guest_program": _GUEST_ROOT / "guest.py",
        "guest_host_keys": _GUEST_ROOT / "required-host-known_hosts",
    }
)
SOURCE_PATHS["native_trunk_resident"] = (
    Path(__file__).resolve().parents[2]
    / "network/config-backup-preflight/native-trunk-resident.py"
)
SOURCE_MANIFEST = {
    name: storage.digest(path.read_bytes()) for name, path in SOURCE_PATHS.items()
}
SOURCE_DIGEST = evidence.digest(SOURCE_MANIFEST)
PHASES = CycleProfile.EMPTY.phases


def _preview_digest(baseline: tuple[str, ...], profile: CycleProfile) -> str:
    return evidence.digest(
        {
            "operation": profile.value,
            "commands": profile.commands,
            "baseline_sha256": evidence.configuration_hash(baseline),
        }
    )


def preview_digest(baseline: tuple[str, ...]) -> str:
    return _preview_digest(baseline, CycleProfile.EMPTY)


def standby_tagged_preview_digest(baseline: tuple[str, ...]) -> str:
    return _preview_digest(baseline, CycleProfile.STANDBY_TAGGED)


def standby_native_preview_digest(baseline: tuple[str, ...]) -> str:
    return _preview_digest(baseline, CycleProfile.STANDBY_NATIVE)


def full_trunk_preview_digest(baseline: tuple[str, ...]) -> str:
    return _preview_digest(baseline, CycleProfile.FULL_TRUNK)


def r8_full_trunk_preview_digest(baseline: tuple[str, ...]) -> str:
    return _preview_digest(baseline, CycleProfile.R8_FULL_TRUNK)


class EmptyVlanLedger:
    """Dedicated schema sharing the canonical persistence lock and pending slot."""

    def __init__(
        self,
        guarded: storage.ExerciseLedger,
        profile: CycleProfile = CycleProfile.EMPTY,
    ):
        self.profile = profile
        self.guarded = guarded
        self.data: dict[str, object] | None = None
        self.records: list[Path] = []
        self.recovery_records: list[Path] = []

    def guard(self) -> None:
        self.guarded.guard()
        expected_records = set(self.records)
        expected_records.update(self.recovery_records)
        receipt = self.guarded.runtime / "empty-vlan-complete.json"
        if receipt in self.guarded.files:
            expected_records.add(receipt)
        if (
            self.data is None
            or storage.canonical(self.data)
            != self.guarded.files[self.guarded.pending][0]
        ):
            raise storage.Uncertain("empty VLAN pending drift")
        if {
            p
            for p in self.guarded.runtime.iterdir()
            if p.name.startswith("empty-vlan-")
        } != expected_records:
            raise storage.Uncertain("empty VLAN journal drift")

    def begin(self, binding: dict[str, str]) -> None:
        self.guarded.guard()
        storage.hashes(binding, BINDING_KEYS)
        if self.data is not None or os.path.lexists(self.guarded.pending):
            raise storage.Uncertain("pending operation blocks empty VLAN cycle")
        if any(
            p.name.startswith("empty-vlan-") for p in self.guarded.runtime.iterdir()
        ):
            raise storage.Rejected("empty VLAN runtime already used")
        data: dict[str, object] = {
            "schema": 4,
            "operation": self.profile.value,
            "host": evidence.HOST,
            "fingerprint": evidence.FINGERPRINT,
            "writer": "caller_supplied_transport",
            "commands": self.profile.commands,
            "binding": dict(binding),
            "runtime": str(self.guarded.runtime),
            "created_at": datetime.now(UTC).isoformat(),
        }
        data["operation_id"] = storage.digest(storage.canonical(data))
        try:
            storage.exclusive_write(self.guarded.pending, storage.canonical(data))
            self.data = self.guarded.remember(self.guarded.pending)
        except (OSError, storage.Rejected, KeyboardInterrupt) as error:
            self.guarded.failed = True
            raise storage.Uncertain("empty VLAN begin durability uncertain") from error

    def append(self, phase: str, payload: dict[str, Any]) -> None:
        self.guard()
        assert self.data is not None
        index = len(self.records)
        if index >= len(self.profile.phases) or phase != self.profile.phases[index]:
            raise storage.Rejected("empty VLAN phase out of order")
        previous = self.records[-1] if self.records else self.guarded.pending
        data = {
            "operation_id": self.data["operation_id"],
            "index": index,
            "phase": phase,
            "prev_digest": storage.digest(self.guarded.files[previous][0]),
            "evidence_sha256": evidence.digest(payload),
            "evidence": payload,
        }
        if "acknowledgement" in payload:
            data["acknowledgement"] = payload["acknowledgement"]
            data["acknowledgement_parser_qualified"] = False
        path = self.guarded.runtime / f"empty-vlan-phase-{index:02d}-{phase}.json"
        try:
            storage.exclusive_write(path, storage.canonical(data))
            self.guarded.remember(path)
            self.records.append(path)
        except (OSError, storage.Rejected, KeyboardInterrupt) as error:
            self.guarded.failed = True
            raise storage.Uncertain("empty VLAN phase durability uncertain") from error

    def append_recovery(self, phase: str, payload: dict[str, Any]) -> None:
        self.guard()
        assert self.data is not None
        index = len(self.recovery_records)
        previous = (
            self.recovery_records[-1]
            if self.recovery_records
            else self.records[-1]
            if self.records
            else self.guarded.pending
        )
        data = {
            "operation_id": self.data["operation_id"],
            "index": index,
            "phase": phase,
            "prev_digest": storage.digest(self.guarded.files[previous][0]),
            "evidence_sha256": evidence.digest(payload),
            "evidence": payload,
        }
        path = self.guarded.runtime / f"empty-vlan-recovery-{index:02d}-{phase}.json"
        try:
            storage.exclusive_write(path, storage.canonical(data))
            self.guarded.remember(path)
            self.recovery_records.append(path)
        except (OSError, storage.Rejected, KeyboardInterrupt) as error:
            self.guarded.failed = True
            raise storage.Uncertain(
                "empty VLAN recovery durability uncertain"
            ) from error

    def finish(self, *, defer_clear: bool = False) -> None:
        self.guard()
        assert self.data is not None
        if len(self.records) != len(self.profile.phases):
            raise storage.Rejected("empty VLAN operation incomplete")
        raw = self.guarded.files[self.guarded.pending][0]
        receipt = self.guarded.runtime / "empty-vlan-complete.json"
        try:
            storage.exclusive_write(
                receipt,
                storage.canonical(
                    {
                        "operation_id": self.data["operation_id"],
                        "status": "complete",
                        "operation": self.data,
                        "phase_count": len(self.records),
                        "final_observation": storage.decode(
                            self.guarded.files[self.records[-1]][0]
                        )["evidence"],
                        "final_digest": storage.digest(
                            self.guarded.files[self.records[-1]][0]
                        ),
                    }
                ),
            )
            self.guarded.remember(receipt)
            self.guarded.guard()
            if not defer_clear:
                self._clear_pending(raw)
        except (OSError, storage.Rejected, KeyboardInterrupt) as error:
            self.guarded.failed = True
            raise storage.Uncertain("empty VLAN finish durability uncertain") from error
        if not defer_clear:
            self.guarded.files.pop(self.guarded.pending)
            self.data = None

    def _clear_pending(self, raw: bytes) -> None:
        self.guarded.guard()
        self.guarded.pending.unlink()
        try:
            storage.sync_directory(self.guarded.path)
        except (OSError, KeyboardInterrupt):
            if not os.path.lexists(self.guarded.pending):
                storage.exclusive_write(self.guarded.pending, raw)
            raise

    def close_admitted(self) -> None:
        """Clear custody only after the completed receipt passed admission."""
        self.guard()
        assert self.data is not None
        receipt = self.guarded.runtime / "empty-vlan-complete.json"
        if receipt not in self.guarded.files:
            raise storage.Rejected("semantic admission receipt missing")
        raw = self.guarded.files[self.guarded.pending][0]
        try:
            self._clear_pending(raw)
        except (OSError, storage.Rejected, KeyboardInterrupt) as error:
            self.guarded.failed = True
            raise storage.Uncertain(
                "empty VLAN admitted close durability uncertain"
            ) from error
        self.guarded.files.pop(self.guarded.pending)
        self.data = None


def _run_cycle(
    guarded: storage.ExerciseLedger,
    baseline: tuple[str, ...],
    observe: Callable[[], dict[str, Any]],
    send: Callable[[int, str, Callable[[], None]], dict[str, Any]],
    admit: Callable[[], None],
    binding: dict[str, str],
    *,
    baseline_sha256: str,
    profile: CycleProfile = CycleProfile.EMPTY,
    semantic_admit: Callable[[], dict[str, object]] | None = None,
    held_guest_proof: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]
    | None = None,
    r8_recovery_session: Callable[
        [], tuple[Callable[[], dict[str, Any]], Any, Callable[[], None]]
    ]
    | None = None,
    operation_budget: Any = None,
) -> dict[str, object]:
    snapshot = dict(storage.hashes(binding, BINDING_KEYS))
    ledger = EmptyVlanLedger(guarded, profile)
    r8_baseline_tables: dict[str, str] | None = None
    observe_current = observe
    send_current = send

    def guard() -> None:
        guarded.guard()
        if operation_budget is not None:
            operation_budget.check()
        if (
            snapshot != binding
            or snapshot["source_binding_sha256"] != SOURCE_DIGEST
            or any(
                storage.digest(path.read_bytes()) != SOURCE_MANIFEST[name]
                for name, path in SOURCE_PATHS.items()
            )
        ):
            raise evidence.Rejected("source or binding drift")

    if (
        snapshot["baseline_running_sha256"] != baseline_sha256
        or snapshot["baseline_startup_sha256"] != baseline_sha256
        or snapshot["execution_environment_sha256"] != evidence.EE_DIGEST
        or snapshot["preview_sha256"] != _preview_digest(baseline, profile)
    ):
        raise evidence.Rejected("fixed empty VLAN binding")

    selected_r8_plan = (
        native_trunk_plan.build_r8_full_trunk_plan(baseline, baseline)
        if profile is CycleProfile.R8_FULL_TRUNK
        else None
    )

    restoration_extra_reads = 0

    def exact_read(
        position: int,
        observer: Callable[[], dict[str, Any]] | None = None,
        *,
        expected_r8_state: native_trunk_plan.State | None = None,
        restoration: bool = False,
        recovery_boundary: bool = False,
    ) -> dict[str, Any]:
        nonlocal r8_baseline_tables
        guard()
        payload = exercise.synchronous((observer or observe_current)())
        guard()
        if not isinstance(payload, dict):
            raise evidence.Rejected("audited whole payload required")
        running, startup = evidence.evidence_config(payload, exercise.PORT)
        if profile is CycleProfile.EMPTY:
            trunk_step._check_step(
                baseline,
                running,
                startup,
                2 if position in (2, 3) else 0,
                baseline_sha256=baseline_sha256,
            )
        elif profile is CycleProfile.STANDBY_NATIVE:
            observation = standby_native_observation._classify_observation(
                baseline, running, startup, baseline_sha256=baseline_sha256
            )
            present = 2 <= position <= 14
            tagged = 3 <= position <= 13
            native = 6 <= position <= 10
            if (
                observation["vlan_present"] != present
                or observation["tagged_standby"] != tagged
                or observation["native_mode"] != native
            ):
                raise evidence.Rejected("fixed standby native VLAN state required")
            standby_native_observation.require_operational_state(
                payload["responses"]["show interfaces brief"],
                phase="native" if native else "standby" if tagged else "baseline",
            )
        elif profile is CycleProfile.FULL_TRUNK:
            trunk_link_admission.require_links(
                payload["responses"]["show interfaces brief"]
            )
            if position <= len(trunk_plan.FORWARD_COMMANDS):
                trunk_step._check_step(
                    baseline,
                    running,
                    startup,
                    position,
                    baseline_sha256=baseline_sha256,
                )
            else:
                observation = trunk_observation._classify_observation(
                    baseline, running, startup, baseline_sha256=baseline_sha256
                )
                remaining = max(0, 27 - position)
                for vlan_index, (vlan_id, _) in enumerate(trunk_plan.TARGET_VLANS):
                    vlan = observation["vlans"][str(vlan_id)]
                    present = vlan_index < remaining
                    if vlan["present"] != present or vlan["observed_members"] != (
                        trunk_plan.PORTS if present else ()
                    ):
                        raise evidence.Rejected(
                            "fixed full trunk inverse state required"
                        )
        elif profile is CycleProfile.R8_PROBE:
            inverse = position > len(native_trunk_plan.R8_PROBE_FORWARD)
            completed = (
                position - len(native_trunk_plan.R8_PROBE_FORWARD)
                if inverse
                else position
            )
            r8_observation = native_trunk_observation._classify_r8_probe_observation(
                baseline,
                running,
                startup,
                baseline_sha256=baseline_sha256,
            )
            native_trunk_observation.require_r8_probe_state(
                r8_observation, completed=completed, inverse=inverse
            )
            native_trunk_observation.require_r8_probe_operational_state(
                payload["responses"]["show interfaces brief"],
                baseline,
                r8_observation.state,
            )
        elif profile is CycleProfile.R8_FULL_TRUNK:
            assert selected_r8_plan is not None
            forward_count = len(native_trunk_plan.R8_FULL_FORWARD)
            inverse = position > forward_count
            completed = position - forward_count if inverse else position
            full_observation = (
                native_trunk_observation.classify_r8_full_trunk_observation(
                    baseline, running, startup
                )
            )
            if recovery_boundary:
                if full_observation.state not in native_trunk_plan._states(
                    native_trunk_plan.R8_FULL_FORWARD, selected_r8_plan.initial_state
                ):
                    raise evidence.Rejected("unsupported R8 recovery command boundary")
            elif expected_r8_state is None:
                native_trunk_observation.require_r8_full_trunk_state(
                    full_observation,
                    completed=completed,
                    inverse=inverse,
                    initial_state=selected_r8_plan.initial_state,
                )
            elif full_observation.state != expected_r8_state:
                raise evidence.Rejected(
                    "R8 recovery state changed between observations"
                )
            if position == len(profile.commands) or (
                restoration and full_observation.state == selected_r8_plan.initial_state
            ):
                native_trunk_observation.require_r8_full_trunk_restored(
                    full_observation, baseline_sha256
                )
            observed_tables = native_trunk_observation.require_r8_vlan_capture(payload)
            if r8_baseline_tables is None:
                if position != 0:
                    raise evidence.Rejected("R8 VLAN baseline observation missing")
                r8_baseline_tables = observed_tables
            payload["r8_vlan_baseline_tables"] = r8_baseline_tables
            native_trunk_observation.require_r8_full_trunk_membership(
                observed_tables,
                r8_baseline_tables,
                full_observation.state,
                selected_r8_plan.initial_state,
            )
            guard()
            operational = (
                native_trunk_observation.require_r8_full_trunk_restoration_operational_state
                if restoration
                else native_trunk_observation.require_r8_full_trunk_operational_state
            )
            operational(
                payload["responses"]["show interfaces brief"], full_observation.state
            )
        else:
            observation = trunk_observation._classify_observation(
                baseline, running, startup, baseline_sha256=baseline_sha256
            )
            present = position in (2, 3, 4)
            members = ("1/2/6",) if position == 3 else ()
            for vlan_id, vlan in observation["vlans"].items():
                if vlan["present"] != (vlan_id == "10" and present) or vlan[
                    "observed_members"
                ] != (members if vlan_id == "10" else ()):
                    raise evidence.Rejected("fixed standby tagged VLAN state required")
        return payload

    def exact(
        position: int,
        observer: Callable[[], dict[str, Any]] | None = None,
        *,
        expected_r8_state: native_trunk_plan.State | None = None,
        restoration: bool = False,
        recovery_boundary: bool = False,
    ) -> dict[str, Any]:
        nonlocal restoration_extra_reads
        while True:
            try:
                return exact_read(
                    position,
                    observer,
                    expected_r8_state=expected_r8_state,
                    restoration=restoration,
                    recovery_boundary=recovery_boundary,
                )
            except native_trunk_observation.R8PrimaryListening:
                if not restoration or restoration_extra_reads >= 2:
                    raise
                guard()
                restoration_extra_reads += 1

    exact(0)
    exercise.no_result(admit)
    guard()
    ledger.begin(snapshot)
    assert ledger.data is not None
    operation_id = str(ledger.data["operation_id"])
    held_proof_record: dict[str, Any] | None = None
    held_proof_failed = False
    restored_proof_record: dict[str, Any] | None = None

    def command(index: int, text: str) -> None:
        if (
            operation_budget is not None
            and profile is CycleProfile.R8_FULL_TRUNK
            and index >= len(native_trunk_plan.R8_FULL_FORWARD)
        ):
            operation_budget.begin_inverse(emergency=True)
        restoring = profile is CycleProfile.R8_FULL_TRUNK and index >= len(
            native_trunk_plan.R8_FULL_FORWARD
        )
        exact(index, restoration=restoring)
        exercise.no_result(admit)
        calls = 0
        authorized = False
        active = True

        def before_send() -> None:
            nonlocal calls, authorized
            calls += 1
            if not active or calls != 1:
                authorized = False
                raise evidence.Rejected("synchronous single command callback required")
            if operation_budget is not None:
                if profile is CycleProfile.R8_FULL_TRUNK and index >= len(
                    native_trunk_plan.R8_FULL_FORWARD
                ):
                    operation_budget.before_inverse_send()
                else:
                    operation_budget.before_forward_send()
            payload = exact(index, restoration=restoring)
            if profile is CycleProfile.R8_FULL_TRUNK and index == len(
                native_trunk_plan.R8_FULL_FORWARD
            ):
                if held_proof_record is None:
                    payload["held_guest_proof"] = {
                        "status": "rejected",
                        "reason": "proof callback did not complete",
                    }
                else:
                    payload["held_guest_proof"] = held_proof_record
                payload["held_boundary_observation"] = storage.decode(
                    storage.canonical(held)
                )
            exercise.no_result(admit)
            guard()
            ledger.append(f"command_{index}_intent", payload)
            guard()
            if operation_budget is not None:
                if profile is CycleProfile.R8_FULL_TRUNK and index >= len(
                    native_trunk_plan.R8_FULL_FORWARD
                ):
                    operation_budget.before_inverse_send()
                else:
                    operation_budget.before_forward_send()
            authorized = True

        try:
            if operation_budget is not None:
                if profile is CycleProfile.R8_FULL_TRUNK and index >= len(
                    native_trunk_plan.R8_FULL_FORWARD
                ):
                    operation_budget.before_inverse_send()
                else:
                    operation_budget.before_forward_send()
            acknowledgement = exercise.synchronous(
                send_current(index, text, before_send)
            )
        finally:
            active = False
        if calls != 1 or not authorized:
            raise evidence.Rejected("command callback not accepted")
        guard()
        if (
            not isinstance(acknowledgement, dict)
            or set(acknowledgement) != {"response_body", "response_sha256"}
            or not isinstance(acknowledgement["response_body"], str)
            or acknowledgement["response_sha256"]
            != storage.digest(acknowledgement["response_body"].encode())
        ):
            raise evidence.Rejected("raw diagnostic acknowledgement required")
        payload = exact(index + 1, restoration=restoring)
        ledger.append(
            f"command_{index}_observed",
            {
                "observation": payload,
                "acknowledgement": acknowledgement,
                "acknowledgement_parser_qualified": False,
            },
        )

    forward_count = (
        len(native_trunk_plan.R8_FULL_FORWARD)
        if profile is CycleProfile.R8_FULL_TRUNK
        else len(profile.commands)
    )
    try:
        for index, text in enumerate(profile.commands[:forward_count]):
            command(index, text)
        if profile is CycleProfile.R8_FULL_TRUNK:
            held = exact(forward_count)
            exercise.no_result(admit)
            guard()
    except (Exception, KeyboardInterrupt) as forward_error:
        if profile is not CycleProfile.R8_FULL_TRUNK or r8_recovery_session is None:
            raise
        if operation_budget is not None:
            operation_budget.begin_inverse(emergency=True)
        recovery_observe, recovery_console, close_recovery = r8_recovery_session()
        recovery_writer: Any = None
        try:
            observed_payload = exact(
                0, recovery_observe, restoration=True, recovery_boundary=True
            )
            running, startup = evidence.evidence_config(observed_payload, exercise.PORT)
            observed = native_trunk_observation.classify_r8_full_trunk_observation(
                baseline, running, startup
            )
            assert selected_r8_plan is not None
            forward_states = native_trunk_plan._states(
                native_trunk_plan.R8_FULL_FORWARD, selected_r8_plan.initial_state
            )
            if observed.state not in forward_states:
                raise evidence.Rejected("unsupported R8 recovery command boundary")
            state_index = forward_states.index(observed.state)
            recovery_payload = exact(
                state_index,
                recovery_observe,
                expected_r8_state=observed.state,
                restoration=True,
            )
            native_trunk_observation.require_r8_full_trunk_membership(
                native_trunk_observation.require_r8_vlan_capture(recovery_payload),
                r8_baseline_tables or {},
                observed.state,
                selected_r8_plan.initial_state,
            )
            inverse = (
                ()
                if observed.state == selected_r8_plan.initial_state
                else native_trunk_plan.r8_full_inverse_commands(observed.state)
            )
            if inverse:
                import native_trunk_transport

                recovery_writer = native_trunk_transport.R8FullTrunkRecoveryTransport(
                    recovery_console, observed.state
                )
            states = native_trunk_plan._states(inverse, observed.state)
            ledger.append_recovery(
                "observed",
                {
                    "forward_failure": type(forward_error).__name__,
                    "boundary_index": state_index,
                    "observation": recovery_payload,
                    "state_sha256": evidence.digest(
                        (observed.state.vlans, observed.state.native)
                    ),
                    "inverse_commands": inverse,
                },
            )
            for index, text in enumerate(inverse):

                def before_recovery_send() -> None:
                    if operation_budget is not None:
                        operation_budget.before_inverse_send()
                    before = exact(
                        0,
                        recovery_observe,
                        expected_r8_state=states[index],
                        restoration=True,
                    )
                    native_trunk_observation.require_r8_full_trunk_membership(
                        native_trunk_observation.require_r8_vlan_capture(before),
                        r8_baseline_tables or {},
                        states[index],
                        selected_r8_plan.initial_state,
                    )
                    if operation_budget is not None:
                        operation_budget.before_inverse_send()
                    exercise.no_result(admit)
                    guard()
                    ledger.append_recovery(
                        "inverse_intent",
                        {
                            "index": index,
                            "command": text,
                            "pre_send_observation": before,
                            "expected_state_sha256": evidence.digest(
                                (states[index].vlans, states[index].native)
                            ),
                        },
                    )
                    guard()
                    if operation_budget is not None:
                        operation_budget.before_inverse_send()

                acknowledgement = exercise.synchronous(
                    recovery_writer.send(index, text, before_recovery_send)
                )
                if operation_budget is not None:
                    operation_budget.check()
                if (
                    not isinstance(acknowledgement, dict)
                    or set(acknowledgement) != {"response_body", "response_sha256"}
                    or not isinstance(acknowledgement["response_body"], str)
                    or acknowledgement["response_sha256"]
                    != storage.digest(acknowledgement["response_body"].encode())
                ):
                    raise evidence.Rejected("raw recovery acknowledgement required")
                post = exact(
                    0,
                    recovery_observe,
                    expected_r8_state=states[index + 1],
                    restoration=True,
                )
                ledger.append_recovery(
                    "inverse_observed",
                    {
                        "index": index,
                        "observation": post,
                        "acknowledgement": acknowledgement,
                        "state_sha256": evidence.digest(
                            (states[index + 1].vlans, states[index + 1].native)
                        ),
                    },
                )
            final_recovery = exact(
                0,
                recovery_observe,
                expected_r8_state=selected_r8_plan.initial_state,
                restoration=True,
            )
            native_trunk_observation.require_r8_full_trunk_restored(
                native_trunk_observation.classify_r8_full_trunk_observation(
                    baseline,
                    *evidence.evidence_config(final_recovery, exercise.PORT),
                ),
                baseline_sha256,
            )
            ledger.append_recovery("restored", {"observation": final_recovery})
        except (Exception, KeyboardInterrupt) as recovery_error:
            raise evidence.Rejected(
                "R8 forward failed; fresh-session recovery incomplete; custody retained"
            ) from recovery_error
        finally:
            if recovery_writer is not None:
                recovery_writer.close()
            close_recovery()
            if operation_budget is not None:
                operation_budget.check()
        raise evidence.Rejected(
            "R8 forward failed; exact restoration verified; custody retained"
        ) from forward_error
    if profile is CycleProfile.R8_FULL_TRUNK:
        try:
            if held_guest_proof is None:
                raise evidence.Rejected("held-state guest proof callback required")
            if operation_budget is not None:
                operation_budget.begin_guest_proof()
            proof_binding = {
                "operation_id": operation_id,
                "forward_count": forward_count,
                "boundary_observation_sha256": evidence.digest(held),
                "source_binding_sha256": snapshot["source_binding_sha256"],
            }
            proof = exercise.synchronous(held_guest_proof(held, proof_binding))
            if operation_budget is not None:
                operation_budget.check()
            if not isinstance(proof, dict):
                raise evidence.Rejected("held-state guest proof object required")
            held_proof_record = {
                "status": "accepted",
                "operation_id": operation_id,
                "forward_count": forward_count,
                "boundary_observation_sha256": evidence.digest(held),
                "source_binding_sha256": snapshot["source_binding_sha256"],
                "proof_sha256": evidence.digest(proof),
                "proof": proof,
            }
        except (Exception, KeyboardInterrupt) as error:
            held_proof_failed = True
            held_proof_record = {
                "status": "rejected",
                "operation_id": operation_id,
                "forward_count": forward_count,
                "boundary_observation_sha256": evidence.digest(held),
                "source_binding_sha256": snapshot["source_binding_sha256"],
                "reason": type(error).__name__,
            }
    if profile is CycleProfile.R8_FULL_TRUNK:
        if r8_recovery_session is None:
            raise evidence.Rejected("fresh R8 inverse session required")
        inverse_observe, inverse_console, close_inverse = r8_recovery_session()
        inverse_writer: Any = None
        try:
            assert selected_r8_plan is not None
            held_state = native_trunk_plan._states(
                native_trunk_plan.R8_FULL_FORWARD,
                selected_r8_plan.initial_state,
            )[-1]
            exact(
                forward_count,
                inverse_observe,
                expected_r8_state=held_state,
                restoration=True,
            )
            exercise.no_result(admit)
            guard()
            import native_trunk_transport

            inverse_commands = native_trunk_plan.r8_full_inverse_commands(held_state)
            if inverse_commands != profile.commands[forward_count:]:
                raise evidence.Rejected("fixed R8 full-trunk inverse differs")
            inverse_writer = native_trunk_transport.R8FullTrunkRecoveryTransport(
                inverse_console, held_state
            )
            observe_current = inverse_observe
            send_current = lambda index, text, before_send: inverse_writer.send(
                index - forward_count, text, before_send
            )
            for index, text in enumerate(
                profile.commands[forward_count:], start=forward_count
            ):
                command(index, text)
        finally:
            if inverse_writer is not None:
                inverse_writer.close()
            close_inverse()
    else:
        for index, text in enumerate(
            profile.commands[forward_count:], start=forward_count
        ):
            command(index, text)
    final = exact(
        len(profile.commands), restoration=profile is CycleProfile.R8_FULL_TRUNK
    )
    exercise.no_result(admit)
    guard()
    final = exact(
        len(profile.commands), restoration=profile is CycleProfile.R8_FULL_TRUNK
    )
    if profile is CycleProfile.R8_FULL_TRUNK:
        if operation_budget is not None and operation_budget.phase == "recovery":
            final["restored_guest_proof"] = {
                "status": "rejected",
                "reason": "emergency inverse used the proof and cleanup reserve",
            }
            ledger.append("final_observed", final)
            raise evidence.Rejected(
                "R8 emergency inverse restored the switch; custody retained"
            )
        try:
            if held_guest_proof is None:
                raise evidence.Rejected("restored-state guest proof callback required")
            if operation_budget is not None:
                operation_budget.begin_guest_proof()
            proof_binding = {
                "operation_id": operation_id,
                "forward_count": forward_count,
                "boundary_observation_sha256": evidence.digest(final),
                "source_binding_sha256": snapshot["source_binding_sha256"],
            }
            proof = exercise.synchronous(held_guest_proof(final, proof_binding))
            if operation_budget is not None:
                operation_budget.check()
            if not isinstance(proof, dict):
                raise evidence.Rejected("restored-state guest proof object required")
            restored_proof_record = {
                "status": "accepted",
                "operation_id": operation_id,
                "forward_count": forward_count,
                "boundary_observation_sha256": evidence.digest(final),
                "source_binding_sha256": snapshot["source_binding_sha256"],
                "proof_sha256": evidence.digest(proof),
                "proof": proof,
            }
        except (Exception, KeyboardInterrupt) as error:
            held_proof_failed = True
            restored_proof_record = {
                "status": "rejected",
                "operation_id": operation_id,
                "forward_count": forward_count,
                "boundary_observation_sha256": evidence.digest(final),
                "source_binding_sha256": snapshot["source_binding_sha256"],
                "reason": type(error).__name__,
            }
        final["restored_guest_proof"] = restored_proof_record
    if operation_budget is not None:
        operation_budget.begin_cleanup()
    ledger.append("final_observed", final)
    guard()
    ledger.finish(defer_clear=semantic_admit is not None)
    if held_proof_failed:
        raise evidence.Rejected(
            "R8 guest proof failed; inverse completed; custody retained"
        )
    result: dict[str, object] = {
        "scope": "unsaved_" + profile.value,
        "cycle_passed": True,
        "acknowledgement_parser_qualified": False,
        "live_admission": False,
        "task_complete": False,
        "final_evidence_sha256": evidence.digest(final),
    }
    if semantic_admit is not None:
        result["semantic_admission"] = semantic_admit()
        if operation_budget is not None:
            operation_budget.check()
        ledger.close_admitted()
    return result


def run_cycle(
    guarded: storage.ExerciseLedger,
    baseline: tuple[str, ...],
    observe: Callable[[], dict[str, Any]],
    send: Callable[[int, str, Callable[[], None]], dict[str, Any]],
    admit: Callable[[], None],
    binding: dict[str, str],
) -> dict[str, object]:
    """Run only the fixed five-command path; failures retain pending for manual reconciliation."""
    return _run_cycle(
        guarded,
        baseline,
        observe,
        send,
        admit,
        binding,
        baseline_sha256=trunk_plan.BASELINE_SHA256,
    )


def run_standby_tagged_cycle(
    guarded: storage.ExerciseLedger,
    baseline: tuple[str, ...],
    observe: Callable[[], dict[str, Any]],
    send: Callable[[int, str, Callable[[], None]], dict[str, Any]],
    admit: Callable[[], None],
    binding: dict[str, str],
) -> dict[str, object]:
    """Run the fixed unsaved standby tag and reversal with durable intent."""
    return _run_cycle(
        guarded,
        baseline,
        observe,
        send,
        admit,
        binding,
        baseline_sha256=trunk_plan.BASELINE_SHA256,
        profile=CycleProfile.STANDBY_TAGGED,
    )


def run_full_trunk_cycle(
    guarded: storage.ExerciseLedger,
    baseline: tuple[str, ...],
    observe: Callable[[], dict[str, Any]],
    send: Callable[[int, str, Callable[[], None]], dict[str, Any]],
    admit: Callable[[], None],
    binding: dict[str, str],
) -> dict[str, object]:
    """Run the fixed unsaved 22-command trunk and six-command inverse."""
    return _run_cycle(
        guarded,
        baseline,
        observe,
        send,
        admit,
        binding,
        baseline_sha256=trunk_plan.BASELINE_SHA256,
        profile=CycleProfile.FULL_TRUNK,
    )


def run_r8_probe_cycle(
    guarded: storage.ExerciseLedger,
    baseline: tuple[str, ...],
    observe: Callable[[], dict[str, Any]],
    send: Callable[[int, str, Callable[[], None]], dict[str, Any]],
    admit: Callable[[], None],
    binding: dict[str, str],
    *,
    semantic_admit: Callable[[], dict[str, object]] | None = None,
) -> dict[str, object]:
    """Exercise only the temporary VLAN 60 delta on the accepted R8 baseline."""
    return _run_cycle(
        guarded,
        baseline,
        observe,
        send,
        admit,
        binding,
        baseline_sha256=native_trunk_plan.R8_BASELINE_SHA256,
        profile=CycleProfile.R8_PROBE,
        semantic_admit=semantic_admit,
    )


def run_r8_full_trunk_cycle(
    guarded: storage.ExerciseLedger,
    baseline: tuple[str, ...],
    observe: Callable[[], dict[str, Any]],
    send: Callable[[int, str, Callable[[], None]], dict[str, Any]],
    admit: Callable[[], None],
    binding: dict[str, str],
    *,
    semantic_admit: Callable[[], dict[str, object]] | None = None,
    held_guest_proof: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]
    | None = None,
    r8_recovery_session: Callable[
        [], tuple[Callable[[], dict[str, Any]], Any, Callable[[], None]]
    ]
    | None = None,
    operation_budget: Any = None,
) -> dict[str, object]:
    """Cycle primary-down tags on the accepted R8 trunk without deleting VLANs."""
    return _run_cycle(
        guarded,
        baseline,
        observe,
        send,
        admit,
        binding,
        baseline_sha256=native_trunk_plan.R8_BASELINE_SHA256,
        profile=CycleProfile.R8_FULL_TRUNK,
        semantic_admit=semantic_admit,
        held_guest_proof=held_guest_proof,
        r8_recovery_session=r8_recovery_session,
        operation_budget=operation_budget,
    )


def run_standby_native_cycle(
    guarded: storage.ExerciseLedger,
    baseline: tuple[str, ...],
    observe: Callable[[], dict[str, Any]],
    send: Callable[[int, str, Callable[[], None]], dict[str, Any]],
    admit: Callable[[], None],
    binding: dict[str, str],
) -> dict[str, object]:
    """Run the fixed unsaved native candidate with caller-owned traffic proof.

    Observe and admit own actual VLAN tables and host/source traffic acceptance;
    configuration and interface brief checks do not establish packet traversal.
    """
    return _run_cycle(
        guarded,
        baseline,
        observe,
        send,
        admit,
        binding,
        baseline_sha256=trunk_plan.BASELINE_SHA256,
        profile=CycleProfile.STANDBY_NATIVE,
    )
