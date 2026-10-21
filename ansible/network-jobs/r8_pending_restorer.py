"""Restore a retained partial R8 trunk cycle without clearing its custody marker."""

from __future__ import annotations

import argparse
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [
    str(ROOT / "ansible/network-jobs"),
    str(ROOT / "ansible/network-audit"),
]

import empty_vlan_cycle as cycle  # noqa: E402
import empty_vlan_transport as base_transport  # noqa: E402
import exercise_observation as host_observation  # noqa: E402
import native_trunk_observation as trunk_observation  # noqa: E402
import native_trunk_plan as trunk_plan  # noqa: E402
import native_trunk_transport as trunk_transport  # noqa: E402
import port_description as evidence  # noqa: E402
import port_exercise_ledger as storage  # noqa: E402
import r8_current_observation as r8_observation  # noqa: E402
import r8_probe_runner  # noqa: E402
import r8_root_session  # noqa: E402

HOST = "192.168.0.251"
FINGERPRINT = "SHA256:UJulVmfAMmHcUctvJrlGzBZR7I7uN8/TWNeJIs25yks"
SOURCE = Path(__file__).resolve()
SOURCE_SHA256 = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
MAX_SECONDS = 900
CONFIG_MODE_WARNING = "Warning: 1 user(s) already in config mode."


class Rejected(RuntimeError):
    """A pending R8 operation or its observed restore boundary is not exact."""


def _recognized_phase_shape(
    phases: list[tuple[Path, bytes, tuple[int, int]]],
) -> bool:
    return (
        (
            len(phases) == 23
            and phases[-1][0].name == "empty-vlan-phase-22-command_11_intent.json"
        )
        or (
            len(phases) == 29
            and phases[-1][0].name == "empty-vlan-phase-28-command_14_intent.json"
        )
        or (
            len(phases) == 35
            and phases[-1][0].name == "empty-vlan-phase-34-command_17_intent.json"
        )
    )


def unchanged_sources() -> None:
    if hashlib.sha256(SOURCE.read_bytes()).hexdigest() != SOURCE_SHA256:
        raise Rejected("restorer source drift")
    r8_probe_runner.unchanged_sources()
    trunk_transport.unchanged_sources()
    if evidence.digest(cycle.SOURCE_MANIFEST) != cycle.SOURCE_DIGEST:
        raise Rejected("R8 cycle source manifest drift")


def _read_private(
    path: Path, *, canonical: bool = True
) -> tuple[dict[str, Any], bytes, tuple[int, int]]:
    try:
        raw, identity = storage.read_file(path)
        value = storage.decode(raw) if canonical else json.loads(raw)
        if type(value) is not dict:
            raise Rejected("private R8 recovery object required")
    except (OSError, storage.Rejected, UnicodeError, json.JSONDecodeError) as error:
        raise Rejected("private R8 recovery receipt rejected") from error
    return value, raw, identity


def _verify_chain(
    pending: dict[str, Any],
    pending_raw: bytes,
    runtime: Path,
) -> tuple[
    list[tuple[Path, bytes, tuple[int, int]]], list[tuple[Path, bytes, tuple[int, int]]]
]:
    operation_id = pending["operation_id"]
    phase_paths = sorted(runtime.glob("empty-vlan-phase-*.json"))
    recovery_paths = sorted(runtime.glob("empty-vlan-recovery-*.json"))
    previous = storage.digest(pending_raw)

    def read_rows(
        paths: list[Path], expected_previous: str, *, phase: bool
    ) -> tuple[list[tuple[Path, bytes, tuple[int, int]]], str]:
        rows = []
        last = expected_previous
        for index, path in enumerate(paths):
            record, raw, identity = _read_private(path)
            expected_prefix = "empty-vlan-phase-" if phase else "empty-vlan-recovery-"
            name_parts = (
                path.name.removesuffix(".json")
                .removeprefix(expected_prefix)
                .split("-", 1)
            )
            if (
                len(name_parts) != 2
                or name_parts[0] != f"{index:02d}"
                or record.get("operation_id") != operation_id
                or record.get("index") != index
                or record.get("prev_digest") != last
                or record.get("phase") != name_parts[1]
                or record.get("evidence_sha256")
                != evidence.digest(record.get("evidence"))
            ):
                raise Rejected("pending R8 record chain mismatch")
            last = storage.digest(raw)
            rows.append((path, raw, identity))
        return rows, last

    phases, previous = read_rows(phase_paths, previous, phase=True)
    recoveries, _ = read_rows(recovery_paths, previous, phase=False)
    phase_shape = _recognized_phase_shape(phases)
    if (
        not phase_shape
        or pending.get("commands")
        != [*trunk_plan.R8_FULL_FORWARD, *trunk_plan.R8_FULL_INVERSE]
        or len(recoveries) != 2
        or recoveries[0][0].name != "empty-vlan-recovery-00-observed.json"
        or recoveries[1][0].name != "empty-vlan-recovery-01-inverse_intent.json"
    ):
        raise Rejected("pending R8 operation is not the recognized failed boundary")
    return phases, recoveries


def load_pending(pending_path: Path, preflight_path: Path) -> dict[str, Any]:
    if (
        pending_path != pending_path.resolve()
        or pending_path.parent.name != "brocade-persistence-ledger"
    ):
        raise Rejected("canonical Brocade pending path required")
    pending, pending_raw, pending_identity = _read_private(pending_path)
    unsigned = {key: value for key, value in pending.items() if key != "operation_id"}
    if (
        pending.get("schema") != 4
        or pending.get("operation") != cycle.CycleProfile.R8_FULL_TRUNK.value
        or pending.get("host") != HOST
        or pending.get("fingerprint") != FINGERPRINT
        or pending.get("writer") != "caller_supplied_transport"
        or pending.get("operation_id") != storage.digest(storage.canonical(unsigned))
        or storage.hashes(pending.get("binding"), cycle.BINDING_KEYS)
        != pending.get("binding")
        or pending["binding"].get("source_binding_sha256") != cycle.SOURCE_DIGEST
    ):
        raise Rejected("pending R8 operation identity or source binding differs")
    runtime = Path(pending.get("runtime", ""))
    storage.private_directory(runtime)
    if runtime.parent != pending_path.parent.parent:
        raise Rejected("pending R8 runtime escaped its private parent")
    if not preflight_path.is_absolute() or preflight_path != preflight_path.resolve():
        raise Rejected("canonical preflight receipt path required")
    preflight, preflight_raw, preflight_identity = _read_private(
        preflight_path, canonical=False
    )
    if (
        hashlib.sha256(preflight_raw).hexdigest()
        != pending["binding"]["native_recovery_proof_sha256"]
        or preflight.get("schema") != 2
        or preflight.get("configuration_write_attempted") is not False
        or preflight.get("independent_rescue_currently_verified") is not True
    ):
        raise Rejected("preflight receipt is not bound to the pending R8 operation")
    observation = preflight.get("current_observation")
    if type(observation) is not dict:
        raise Rejected("bound R8 starting observation required")
    baseline, startup = evidence.evidence_config(observation, host_observation.PORT)
    baseline_hash = evidence.configuration_hash(baseline)
    if (
        baseline != startup
        or baseline_hash != trunk_plan.R8_BASELINE_SHA256
        or pending["binding"]["baseline_running_sha256"] != baseline_hash
        or pending["binding"]["baseline_startup_sha256"] != baseline_hash
    ):
        raise Rejected("pending R8 baseline binding differs")
    phases, recoveries = _verify_chain(pending, pending_raw, runtime)
    recorded = recoveries[0][0]
    record, _, _ = _read_private(recorded)
    recovery = record["evidence"]
    original_observation = recovery["observation"]
    original_running, original_startup = evidence.evidence_config(
        original_observation, host_observation.PORT
    )
    original = trunk_observation.classify_r8_full_trunk_observation(
        baseline, original_running, original_startup
    )
    selected = trunk_plan.build_r8_full_trunk_plan(baseline, startup)
    forward_states = trunk_plan._states(
        trunk_plan.R8_FULL_FORWARD, selected.initial_state
    )
    boundary = recovery.get("boundary_index")
    inverse = trunk_plan.r8_full_inverse_commands(original.state)
    if (
        type(boundary) is not int
        or not 0 <= boundary < len(forward_states)
        or forward_states[boundary] != original.state
        or recovery.get("inverse_commands") != list(inverse)
        or record.get("phase") != "observed"
    ):
        raise Rejected("recorded R8 recovery state and exact inverse disagree")
    inverse_intent, _, _ = _read_private(recoveries[1][0])
    intent = inverse_intent["evidence"]
    if (
        inverse_intent.get("phase") != "inverse_intent"
        or intent.get("index") != 0
        or intent.get("command") != inverse[0]
        or intent.get("expected_state_sha256")
        != evidence.digest((original.state.vlans, original.state.native))
    ):
        raise Rejected("existing inverse intent differs from recognized recovery plan")
    return {
        "pending": pending,
        "pending_raw": pending_raw,
        "pending_identity": pending_identity,
        "preflight": preflight,
        "preflight_raw": preflight_raw,
        "preflight_identity": preflight_identity,
        "runtime": runtime,
        "baseline": baseline,
        "startup": startup,
        "initial_state": selected.initial_state,
        "recorded_state": original.state,
        "boundary": boundary,
        "inverse": inverse,
        "baseline_vlan_tables": original_observation["r8_vlan_baseline_tables"],
        "phase_files": phases,
        "recovery_files": recoveries,
    }


def validate_observation(
    payload: dict[str, Any], context: dict[str, Any], state: Any
) -> None:
    running, startup = evidence.evidence_config(payload, host_observation.PORT)
    observed = trunk_observation.classify_r8_full_trunk_observation(
        context["baseline"], running, startup
    )
    _validate_vlan_membership(
        trunk_observation.require_r8_vlan_capture(payload),
        context["baseline_vlan_tables"],
        observed.state,
        context["initial_state"],
    )
    operational_state = observed.state
    primary_tagged = any(
        trunk_plan.R8_PRIMARY_PORT in ports for _, ports in operational_state.vlans
    )
    if (
        trunk_plan.R8_PRIMARY_PORT not in operational_state.native
        and not primary_tagged
    ):
        operational_state = replace(
            operational_state,
            native=(*operational_state.native, trunk_plan.R8_PRIMARY_PORT),
        )
    trunk_observation.require_r8_full_trunk_operational_state(
        payload["responses"]["show interfaces brief"], operational_state
    )
    if observed.state != state:
        raise Rejected("fresh R8 recovery state differs from the exact inverse step")


def _validate_vlan_membership(
    observed: dict[str, str],
    baseline: dict[str, str],
    state: Any,
    initial_state: Any,
) -> None:
    vlan_ids = {1, 132, *(vlan for vlan, _ in trunk_plan.VLANS)}
    if set(observed) != {str(vlan) for vlan in vlan_ids} or set(baseline) != {
        str(vlan) for vlan in vlan_ids
    }:
        raise Rejected("complete R8 VLAN table readbacks required")
    before = {
        vlan: trunk_observation.parse_vlan(baseline[str(vlan)], vlan, total=6)
        for vlan in vlan_ids
    }
    current = {
        vlan: trunk_observation.parse_vlan(observed[str(vlan)], vlan, total=6)
        for vlan in vlan_ids
    }
    primary = trunk_observation._port(trunk_plan.R8_PRIMARY_PORT)
    native_ports = {trunk_observation._port(port) for port in state.native}
    primary_tagged = any(
        trunk_plan.R8_PRIMARY_PORT in ports for _, ports in state.vlans
    )
    expected_vlan1 = replace(
        before[1],
        untagged=(
            before[1].untagged
            if primary in native_ports or primary_tagged
            else tuple(sorted((*before[1].untagged, primary)))
        ),
        dual_mode=tuple(port for port in before[1].dual_mode if port in native_ports),
    )
    if expected_vlan1 != current[1] or before[132] != current[132]:
        raise Rejected("R8 VLAN1 or VLAN132 membership drift")
    initial_tagged = dict(initial_state.vlans)
    expected_tagged = dict(state.vlans)
    for vlan, _ in trunk_plan.VLANS:
        expected_initial = tuple(
            trunk_observation._port(port) for port in initial_tagged[vlan]
        )
        if before[vlan].tagged != expected_initial:
            raise Rejected("R8 baseline VLAN table differs from configuration")
        expected = replace(
            before[vlan],
            tagged=tuple(
                trunk_observation._port(port) for port in expected_tagged[vlan]
            ),
        )
        if current[vlan] != expected:
            raise Rejected("R8 VLAN table membership drift")


def _remaining_inverse(state: Any, context: dict[str, Any]) -> tuple[str, ...]:
    restore_states = trunk_plan._states(context["inverse"], context["recorded_state"])
    if state not in restore_states:
        raise Rejected("fresh R8 state is outside the recorded restore path")
    return trunk_plan.r8_full_inverse_commands(state)


class RecoveryTransport(trunk_transport.R8FullTrunkRecoveryTransport):
    """Use the pinned transport and admit only the one observed config warning."""

    _capture_filename = "r8-pending-restore-received.raw"

    def __init__(self, console: Any, observed_state: Any, deadline: float) -> None:
        self.deadline = deadline
        super().__init__(console, observed_state)

    def _read_mode(self, prompt: str) -> str:
        boundary = re.compile(r"(?:^|\n)" + prompt + r" *$")
        raw = ""
        try:
            while time.monotonic() < self.deadline:
                if self._console.channel.recv_ready():
                    chunk = self._console.channel.recv(65536)
                    if not chunk:
                        break
                    raw += chunk.decode("ascii", errors="strict")
                    if len(raw) > 65536:
                        raise trunk_transport.Rejected("R8 restore mode capture limit")
                    if raw.endswith("\r"):
                        if self._console.channel.recv_ready():
                            continue
                        if self._console.channel.closed:
                            raise trunk_transport.Rejected(
                                "incomplete R8 restore mode control"
                            )
                        time.sleep(min(0.01, max(0, self.deadline - time.monotonic())))
                        continue
                    text = str(base_transport._syntax.normalized(raw))
                    if boundary.search(text):
                        if self._console.channel.recv_ready():
                            continue
                        time.sleep(min(0.05, max(0, self.deadline - time.monotonic())))
                        if self._console.channel.recv_ready():
                            continue
                        return text
                    if re.search(
                        r"(?:^|\n)(?:SSH@)?headwater(?:\([^\r\n]*\))?[>#][^\r\n]*$",
                        text,
                    ):
                        raise trunk_transport.Rejected("R8 restore unexpected mode")
                elif self._console.channel.closed:
                    break
                else:
                    time.sleep(min(0.01, max(0, self.deadline - time.monotonic())))
            raise TimeoutError("R8 pending restore transport deadline expired")
        finally:
            self._console.save(raw)

    def send(self, index: int, command: str, before_send: Any) -> dict[str, str]:
        if self._failed:
            raise trunk_transport.Rejected("R8 restore transport failed")
        try:
            if (
                self._active
                or type(index) is not int
                or index != self._index
                or index >= len(self._commands)
                or command != self._commands[index]
                or not callable(before_send)
                or time.monotonic() >= self.deadline
            ):
                raise trunk_transport.Rejected("fixed R8 restore command required")
            self._active = True
            trunk_transport.unchanged_sources()
            if time.monotonic() >= self.deadline:
                raise TimeoutError("R8 pending restore deadline expired before prompt")
            self._console.channel.sendall("\r")
            prompt = self._read_mode(self._modes[index])
            if re.fullmatch(r"\n" + self._modes[index] + r" *", prompt) is None:
                raise trunk_transport.Rejected("fresh R8 restore prompt required")
            trunk_transport.unchanged_sources()
            result = before_send()
            if result is not None or time.monotonic() >= self.deadline:
                raise trunk_transport.Rejected("R8 restore intent exceeded deadline")
            trunk_transport.unchanged_sources()
            if time.monotonic() >= self.deadline:
                raise TimeoutError("R8 pending restore deadline expired before command")
            self._console.channel.sendall(self._commands[index] + "\r")
            response = self._read_mode(self._modes[index + 1])
            self._validate_response(index, response)
            raw = self._console.raw
            self._index += 1
            return {
                "response_body": raw,
                "response_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
            }
        except BaseException:
            self._failed = True
            raise
        finally:
            self._active = False
            if self._failed or self._index == len(self._commands):
                self._console.capture.close()

    def _validate_response(self, index: int, response: str) -> None:
        trunk_transport.unchanged_sources()
        if index != 0:
            super()._validate_response(index, response)
            return
        normalized = response.replace("\r\n", "\n").replace("\r", "\n")
        lines = [line for line in normalized.split("\n") if line]
        if (
            len(lines) not in (2, 3)
            or lines[0] != self._commands[index]
            or not re.fullmatch(self._modes[index + 1], lines[-1])
            or (len(lines) == 3 and lines[1] != CONFIG_MODE_WARNING)
        ):
            raise trunk_transport.Rejected("R8 restore config-mode response differs")


def _append(
    runtime: Path,
    index: int,
    previous: str,
    operation_id: str,
    phase: str,
    data: dict[str, Any],
) -> str:
    row = {
        "schema": 1,
        "operation_id": operation_id,
        "index": index,
        "phase": phase,
        "prev_digest": previous,
        "evidence_sha256": evidence.digest(data),
        "evidence": data,
        "restorer_source_sha256": SOURCE_SHA256,
    }
    path = runtime / f"r8-restore-{index:02d}-{phase}.json"
    storage.exclusive_write(path, storage.canonical(row))
    return storage.digest(path.read_bytes())


def _credential(username: str) -> str:
    env = os.environ.copy()
    env.update(
        {
            "DISPLAY": ":0",
            "DBUS_SESSION_BUS_ADDRESS": "unix:path=/run/user/1000/bus",
        }
    )
    result = subprocess.run(
        [
            "secret-tool",
            "lookup",
            "service",
            "brocade",
            "host",
            HOST,
            "username",
            username,
        ],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        timeout=5,
        check=False,
        env=env,
    )
    if result.returncode or result.stderr:
        raise Rejected("required Brocade credential unavailable")
    value = result.stdout.decode("ascii").rstrip("\n")
    if not value:
        raise Rejected("required Brocade credential unavailable")
    return value


def restore(pending_path: Path, preflight_path: Path, pin: Path) -> dict[str, Any]:
    unchanged_sources()
    if not pin.is_absolute() or pin != pin.resolve():
        raise Rejected("canonical Brocade host-key pin required")
    context = load_pending(pending_path, preflight_path)
    parent = pending_path.parent.parent
    runtime = Path(tempfile.mkdtemp(prefix="r8-pending-restore-", dir=parent))
    os.chmod(runtime, 0o700)
    root_runtime = runtime / "root"
    audit_runtime = runtime / "audit"
    root_runtime.mkdir(mode=0o700)
    audit_runtime.mkdir(mode=0o700)
    deadline = time.monotonic() + MAX_SECONDS
    operation_id = context["pending"]["operation_id"]
    original_last = context["recovery_files"][-1]
    previous = storage.digest(original_last[1])
    new_index = len(context["recovery_files"])
    root_password = _credential("root")
    audit_password = _credential("homelab_audit")

    def observe() -> dict[str, Any]:
        unchanged_sources()
        if time.monotonic() >= deadline:
            raise TimeoutError("R8 pending restore deadline expired")
        return r8_observation.observe(
            pin,
            audit_runtime,
            context["startup"],
            lambda: audit_password,
            deadline=deadline,
        )

    def current_sources() -> None:
        if time.monotonic() >= deadline:
            raise TimeoutError("R8 pending restore deadline expired before write")
        unchanged_sources()
        context["guard"].guard()

    ledger_parent = pending_path.parent.parent
    with storage.locked_exercise(ledger_parent, runtime) as guard:
        context["guard"] = guard
        guard.directories[context["runtime"]] = storage.private_directory(
            context["runtime"]
        )
        for path, raw, identity in (
            (pending_path, context["pending_raw"], context["pending_identity"]),
            (preflight_path, context["preflight_raw"], context["preflight_identity"]),
            *context["phase_files"],
            *context["recovery_files"],
        ):
            guard.files[path] = (raw, identity)
        guard.guard()
        first = observe()
        running, startup = evidence.evidence_config(first, host_observation.PORT)
        current = trunk_observation.classify_r8_full_trunk_observation(
            context["baseline"], running, startup
        ).state
        validate_observation(first, context, current)
        context["inverse"] = _remaining_inverse(current, context)
        context["recorded_state"] = current
        running, startup = evidence.evidence_config(first, host_observation.PORT)
        initial_hash = evidence.configuration_hash(running)
        previous = _append(
            runtime,
            new_index,
            previous,
            operation_id,
            "observed",
            {
                "observed_at": first["observed_at"],
                "running_sha256": initial_hash,
                "startup_sha256": evidence.configuration_hash(startup),
                "state_sha256": evidence.digest(
                    (context["recorded_state"].vlans, context["recorded_state"].native)
                ),
                "observation": first,
                "inverse_commands": list(context["inverse"]),
            },
        )
        new_index += 1
        forward_states = trunk_plan._states(
            context["inverse"], context["recorded_state"]
        )
        with r8_root_session.root_console_session(
            pin, root_runtime, lambda: root_password, deadline=deadline
        ) as console:
            writer = RecoveryTransport(console, context["recorded_state"], deadline)
            try:
                for index, command in enumerate(context["inverse"]):
                    before = observe()
                    validate_observation(before, context, forward_states[index])
                    current_sources()

                    def before_send() -> None:
                        nonlocal previous, new_index
                        current_sources()
                        previous = _append(
                            runtime,
                            new_index,
                            previous,
                            operation_id,
                            "inverse_intent",
                            {
                                "index": index,
                                "command": command,
                                "observed_at": before["observed_at"],
                                "state_sha256": evidence.digest(
                                    (
                                        forward_states[index].vlans,
                                        forward_states[index].native,
                                    )
                                ),
                                "observation": before,
                            },
                        )
                        new_index += 1
                        current_sources()

                    ack = writer.send(index, command, before_send)
                    after = observe()
                    validate_observation(after, context, forward_states[index + 1])
                    running_after, startup_after = evidence.evidence_config(
                        after, host_observation.PORT
                    )
                    previous = _append(
                        runtime,
                        new_index,
                        previous,
                        operation_id,
                        "inverse_observed",
                        {
                            "index": index,
                            "command": command,
                            "acknowledgement": ack,
                            "observed_at": after["observed_at"],
                            "running_sha256": evidence.configuration_hash(
                                running_after
                            ),
                            "startup_sha256": evidence.configuration_hash(
                                startup_after
                            ),
                            "state_sha256": evidence.digest(
                                (
                                    forward_states[index + 1].vlans,
                                    forward_states[index + 1].native,
                                )
                            ),
                            "observation": after,
                        },
                    )
                    new_index += 1
            finally:
                writer.close()
        final = observe()
        validate_observation(final, context, context["initial_state"])
        running, startup = evidence.evidence_config(final, host_observation.PORT)
        running_hash = evidence.configuration_hash(running)
        startup_hash = evidence.configuration_hash(startup)
        if (
            running_hash != trunk_plan.R8_BASELINE_SHA256
            or startup_hash != trunk_plan.R8_BASELINE_SHA256
        ):
            raise Rejected("R8 pending restore did not reach exact baseline")
        previous = _append(
            runtime,
            new_index,
            previous,
            operation_id,
            "restored",
            {
                "observed_at": final["observed_at"],
                "running_sha256": running_hash,
                "startup_sha256": startup_hash,
                "pending_retained": True,
                "observation": final,
            },
        )
        guard.guard()
        if storage.read_file(pending_path) != (
            context["pending_raw"],
            context["pending_identity"],
        ):
            raise Rejected("pending custody changed during R8 restore")
    return {
        "status": "restored_pending_retained",
        "operation_id": operation_id,
        "running_sha256": running_hash,
        "startup_sha256": startup_hash,
        "runtime": str(runtime),
        "pending_retained": True,
        "restoration_chain_sha256": previous,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pending", type=Path, required=True)
    parser.add_argument("--preflight", type=Path, required=True)
    parser.add_argument("--pin", type=Path, required=True)
    parser.add_argument("--plan", action="store_true")
    parser.add_argument("--restore", action="store_true")
    args = parser.parse_args()
    if args.plan == args.restore:
        parser.error("select exactly one of --plan or --restore")
    try:
        unchanged_sources()
        context = load_pending(args.pending, args.preflight)
        if args.plan:
            print(
                json.dumps(
                    {
                        "status": "pending_restore_plan_valid",
                        "operation_id": context["pending"]["operation_id"],
                        "boundary_index": context["boundary"],
                        "commands": list(context["inverse"]),
                        "pending_retained": True,
                    }
                )
            )
            return 0
        print(json.dumps(restore(args.pending, args.preflight, args.pin)))
        return 0
    except (Exception, KeyboardInterrupt) as error:
        print(
            json.dumps(
                {
                    "status": "pending_restore_failed",
                    "exception_type": type(error).__name__,
                    "pending_retained": True,
                }
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
