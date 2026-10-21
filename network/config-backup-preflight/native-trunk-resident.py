#!/usr/bin/env python3
"""Bounded unsaved R8 runner; live admission remains false until qualification passes."""

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
from importlib import import_module
from importlib.util import module_from_spec, spec_from_file_location
import json
import os
from pathlib import Path
import re
import select
import secrets
import signal
import subprocess
import sys
import tempfile
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ansible/network-jobs"))
SOURCE_PINS = {
    "ansible/network-jobs/active40g_observation.py": "e42f35946342611becfd48a2f265eb08bd0fb9b69b48b0f6df8ba66832180e2e",
    "ansible/network-audit/bootstrap-identity.py": "9040bc7551266f7a55d1ba46cf080edeca31b1161ac6663e16db3a29d5ed13e2",
    "ansible/network-audit/capture.py": "f2534d3e46490894e7af821e70192469064b9ef71d58ba825a23f77ea0c26e51",
    "ansible/network-audit/run-audit.py": "1d23b99a219b7bc586b75f3676d663a62e2ecce6b338b7a8a86c2e7c840f0635",
    "ansible/network-jobs/bond_vlan_membership.py": "0227d540b9247e570d4a8f7bef062c6590e392b7d3a030fa7a97d236fd2a4b3d",
    "ansible/network-jobs/collect-port-evidence.py": "255e6c9244e82e9d9294b3c246db21a393b53af4e54166a29e7579904af1e8c1",
    "ansible/network-jobs/exercise_observation.py": "ed2140104ada5b13d1e5b5d6876bb10f60b6c6dd768fb6e333194d2bde3d7c79",
    "ansible/network-jobs/empty_vlan_transport.py": "63d24f43b9741971c86b53696629292f1b0bdbfff402c6cf9bdb77f2e832c79c",
    "ansible/network-jobs/inspect-port-syntax.py": "070e0beadf0651620cbf3e862dc6e269d3464692e825783588a968f1acd740fb",
    "ansible/network-jobs/native_trunk_observation.py": "d091fa393427f775bb80a052fe08f85bbe6808bddc3cabf02b1cbf0da682cdb3",
    "ansible/network-jobs/native_trunk_plan.py": "f3ed46c01844752a95023cbf4f21e9fda4469ed47b2edc78afc92a711aae03ea",
    "ansible/network-jobs/native_trunk_serial_plan.py": "3641f63faed456ceb74bf5542109846bb4a68b86f6571b9d439dfe1e8c827fb0",
    "ansible/network-jobs/native_trunk_transport.py": "d11314cbc21f6ca25054b31a53ee488283353d41bf43a4ed2dd3209f67a4c171",
    "ansible/network-jobs/r8_probe_admission.py": "4dde38282113bc59e32f5ee430f7b5fc8f610825cfb1cd8d1eaeadd87093a133",
    "ansible/network-jobs/r8_root_session.py": "554aa2278c2debdbf811806a8e01b5f2a4105394122d2502948300af532a6714",
    "ansible/network-jobs/r8_current_observation.py": "f8d37be9045e58eeb4d4c8f5dc0db902561409151831d61a01f1e7f208adf521",
    "ansible/network-jobs/r8_probe_runner.py": "387e4a75bcd436201ee82c47eee479dae9af6e4816205143bbd8454ddf4ee5e0",
    "ansible/network-jobs/r8_pending_restorer.py": "91d8df655a7ec117d3cb53dd6c5b22bcbafd0341b5c3d3babe8f0e61b0e28821",
    "ansible/network-jobs/r8_guest_acceptance.py": "d25765cce6406120fe628d6d64a30c32f165bbce49c411ffd3077bf4ef5881f2",
    "ansible/network-jobs/r8_guest_producer.py": "a2a25c190bc19555b0cf991ac1ed009d99ae5cd7da72b614b0b19b15f3c9da5e",
    "ansible/network-jobs/r8_guest_generator.py": "93a5eef438f754b3792d26b3bd0112227ff9df5f89672b8263b9476ee20003dd",
    "ansible/network-jobs/r8_guest_parent.py": "04323e709bd81f4b10420dc8f9ae94e82469b6a553730ef0f24c33234136d6ae",
    "ansible/network-jobs/writer_account.py": "f34145b733956d02efb5ebd71ad8d67eb22fc14c5ec041a02b9be801c79c6970",
    "ansible/network-jobs/port_description.py": "6ddbe2c29a1af384e3a0e25902ce2e35affdee81898f5761b29a82aa32441f84",
    "ansible/network-jobs/port_exercise.py": "7c76c76265b800d7b987029311a77a5bc3fe8cc3601c684fa41844bcce74186c",
    "ansible/network-jobs/port_exercise_ledger.py": "03866be805d4855a61084b6de3752f5d6eaae7d5afdfa64d4652270e924c49e3",
    "ansible/network-jobs/port_writer.py": "892dab2b7ab444a69f3858ac2a166661c5695f126a07a55e126d159c568fa503",
    "ansible/network-jobs/standby_native_membership.py": "433018925dfaf6f463707d28551a95f2ff5100b4d5e797d8664ec0e7d1cfaa9e",
    "ansible/network-jobs/standby_native_observation.py": "7a4f235be04d7e52c00afed5dae58a4de4d39fd09ee86579d1e10071665a4a1a",
    "ansible/network-jobs/standby_native_transport.py": "cab439fe1d46ee589f372033c8b8267dc4cc02ef76e5355938ec865ff80ebd6a",
    "ansible/network-jobs/trunk_link_admission.py": "c34855318bcfc313be6ed7b858a5c73b0749b48eb3944bcf9ef3fd6e41709a4c",
    "ansible/network-jobs/trunk_observation.py": "52eb5af27937a1ecb8fe85f083bb971071fec9d5ec45cb2f69e903e204bf27b1",
    "ansible/network-jobs/trunk_plan.py": "ca8820a59b3891e8d1264b5ff6d5ba5971e8fba735d215e6eb7af33e16c12817",
    "ansible/network-jobs/trunk_step.py": "6f956ab42ac703095276873ba95c83353ea73dd209f03cd1d1223a998ed9c611",
    "ansible/network-jobs/trunk_writer.py": "694def29754f93b5c239d8cb0f77b9d0c240199f7c8c63dc12631bfe45080df9",
    "network/config-backup-preflight/inspect-pikvm-serial.py": "6e1ffbd8acee89f5c9b53c325b3a0a6d7e5d98c69106c241d9ca18d09de9015d",
    "network/config-backup-preflight/pikvm-screen-capture.py": "5998be264a5a93f99b33c6969051de2ac7b14ce83482bbd0615287a278e4f4c1",
}
SELF_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def verify_sources():
    if hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != SELF_SHA256:
        raise RuntimeError("resident source changed after load")
    for relative, wanted in SOURCE_PINS.items():
        if hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() != wanted:
            raise RuntimeError("resident dependency drift: " + relative)


verify_sources()

observation = import_module("native_trunk_observation")
native = import_module("native_trunk_plan")
host_observation = import_module("active40g_observation")
plan = import_module("native_trunk_serial_plan")
r8_probe = import_module("r8_probe_runner")
r8_root_session = import_module("r8_root_session")
r8_observation = import_module("r8_current_observation")
r8_guest_parent = import_module("r8_guest_parent")

HELPER = Path(__file__).with_name("pikvm-screen-capture.py")
HELPER_SHA256 = "5998be264a5a93f99b33c6969051de2ac7b14ce83482bbd0615287a278e4f4c1"
EXECUTION_QUALIFIED = False
LIVE_ADMISSION = False
R8_LIVE_RUNTIME = None
TOTAL_SECONDS = 1800
CLEANUP_RESERVE = 20
INVERSE_RESERVE = 600
VALIDATOR_SECONDS = 5
PROOF_SECONDS = 230
R8_PROOF_SECONDS = 212
R8_DEADLINE_SLACK = 2
COMMAND_SECONDS = 20
READ_SECONDS = 120
OBSERVE_SECONDS = 50
READS = {
    "running": "show running-config",
    "startup": "show configuration",
    "brief": "show interfaces brief",
    "span": "show span vlan 1",
    **{f"vlan{vlan}": f"show vlan {vlan}" for vlan in (1, 10, 20, 30, 40, 132)},
}


class R8OperationBudget:
    """Reserve bounded time for both proofs, inverse restoration, and cleanup."""

    def __init__(self, started: float | None = None):
        self.started = time.monotonic() if started is None else started
        self.deadline = self.started + TOTAL_SECONDS
        self.phase = "forward"
        self.guest_proofs = 0

    @property
    def observation_deadline(self) -> float:
        return {
            "forward": self.deadline
            - INVERSE_RESERVE
            - R8_PROOF_SECONDS
            - CLEANUP_RESERVE
            - R8_DEADLINE_SLACK,
            "held": self.deadline
            - INVERSE_RESERVE
            - R8_PROOF_SECONDS
            - CLEANUP_RESERVE
            - R8_DEADLINE_SLACK,
            "inverse": self.deadline - R8_PROOF_SECONDS - CLEANUP_RESERVE,
            "restored": self.deadline - CLEANUP_RESERVE,
            "recovery": self.deadline - CLEANUP_RESERVE,
            "cleanup": self.deadline,
        }[self.phase]

    @property
    def guest_proof_deadline(self) -> float:
        return self.observation_deadline - 2

    def check(self) -> None:
        if time.monotonic() >= self.observation_deadline:
            raise TimeoutError("R8 operation phase deadline expired")

    def before_forward_send(self) -> None:
        self.check()
        if self.observation_deadline - time.monotonic() < 20:
            raise TimeoutError(
                "R8 forward command cannot finish before inverse reserve"
            )

    def begin_inverse(self, emergency: bool = False) -> None:
        if self.phase in ("inverse", "recovery"):
            return
        if self.phase not in ("forward", "held"):
            raise RuntimeError("R8 inverse phase transition")
        cutoff = self.deadline - INVERSE_RESERVE - R8_PROOF_SECONDS - CLEANUP_RESERVE
        if time.monotonic() > cutoff:
            if not emergency:
                raise TimeoutError("R8 inverse reserve no longer available")
            self.phase = "recovery"
        else:
            self.phase = "inverse"

    def before_inverse_send(self) -> None:
        self.check()
        if self.observation_deadline - time.monotonic() < 20:
            raise TimeoutError("R8 inverse command cannot finish before proof reserve")

    def begin_guest_proof(self) -> None:
        if self.guest_proofs == 0:
            self.check()
            held_cutoff = (
                self.deadline
                - INVERSE_RESERVE
                - 2 * R8_PROOF_SECONDS
                - CLEANUP_RESERVE
                - R8_DEADLINE_SLACK
            )
            if time.monotonic() >= held_cutoff:
                raise TimeoutError("R8 held proof cannot finish before inverse reserve")
            self.phase = "held"
        elif self.guest_proofs == 1:
            if self.phase != "inverse":
                raise RuntimeError("R8 restored proof requires inverse phase")
            self.check()
            self.phase = "restored"
        else:
            raise RuntimeError("unexpected R8 guest proof count")
        self.guest_proofs += 1

    def begin_cleanup(self) -> None:
        self.check()
        if self.phase != "restored" or self.guest_proofs != 2:
            raise RuntimeError("R8 cleanup requires both guest proofs")
        self.phase = "cleanup"


def read_echo_response(raw, command):
    """Reconstruct only a fixed read echo interrupted by exact known rows."""
    if command not in READS.values():
        return raw
    data = capture.without_known_noise(raw)
    expected = command.encode("ascii")
    cursor = matched = 0
    interrupted = False
    while cursor < len(data):
        if matched < len(expected) and data[cursor] == expected[matched]:
            cursor += 1
            matched += 1
            continue
        if matched == len(expected) and data[cursor : cursor + 1] in (b"\r", b"\n"):
            return expected + data[cursor:] if interrupted else raw
        if not matched:
            return raw
        remaining = data[cursor:]
        for row in capture.POE_ROWS:
            row = row.encode("ascii")
            if row.startswith(remaining):
                return None
            if remaining.startswith(row):
                suffix = remaining[len(row) :]
                if not suffix:
                    return None
                newline = re.match(rb"\r\n|\n\r|\r|\n", suffix)
                if newline is None:
                    return raw
                cursor += len(row) + newline.end()
                interrupted = True
                break
        else:
            return raw
    return None if interrupted else raw


def helper_module() -> Any:
    if hashlib.sha256(HELPER.read_bytes()).hexdigest() != HELPER_SHA256:
        raise RuntimeError("frozen serial helper drift")
    spec = spec_from_file_location("native_resident_capture", HELPER)
    if spec is None or spec.loader is None:
        raise RuntimeError("frozen serial helper unavailable")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


capture = helper_module()
Rejected = capture.Rejected


class CarrierRejected(Exception):
    """Exact configuration/membership proved; only primary carrier has failed."""


class GuestProofRejected(Exception):
    """Parent validated a rejection with actual restored or never-selected host proof."""


class Controller:
    """One additional fixed-index operation; no caller-supplied input string."""

    def __init__(self):
        self.base = capture.Controller()
        self.owner = self.base.owner

    def state(self):
        return self.base.state()

    def command(self, operation, path=None):
        return self.base.command(operation, path)

    def dispatch(self, command_index, steps=None, read=False):
        if type(command_index) is not int or command_index < 0:
            raise Rejected("fixed command index required")
        if read:
            commands = tuple(READS.values())
        elif steps is plan.FORWARD or steps is plan.INVERSE:
            commands = tuple(step.command for step in steps)
        elif steps is not None and plan.fixed_sequence(steps):
            commands = tuple(step.command for step in steps)
        else:
            raise Rejected("fixed serial sequence required")
        if command_index >= len(commands):
            raise Rejected("fixed command index out of range")
        result = subprocess.run(
            [
                self.owner.EXE,
                "-S",
                capture.SESSION,
                "-p",
                "0",
                "-X",
                "stuff",
                commands[command_index] + "\r",
            ],
            env={"SCREENDIR": str(capture.SCREEN_DIRECTORY), "PATH": "/usr/bin:/bin"},
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=2,
            check=False,
            shell=False,
        )
        if result.returncode or result.stderr or len(result.stdout) > 2048:
            raise Rejected("fixed SCREEN dispatch uncertain")


def validate_guest_binding(validator, state, cutoff):
    """Bound the trusted parent's artifact validator; retain no callback output."""
    remaining = min(VALIDATOR_SECONDS, cutoff - time.monotonic())
    if remaining <= 0 or not callable(validator):
        raise Rejected("bounded parent validator required")
    read_fd, write_fd = os.pipe()
    pid = os.fork()
    if pid == 0:
        try:
            os.close(read_fd)
            os.setsid()
            result = validator(state)
            if type(result) is not str or re.fullmatch(r"[0-9a-f]{64}", result) is None:
                os._exit(1)
            os.write(write_fd, result.encode("ascii"))
            os._exit(0)
        except GuestProofRejected:
            os.write(write_fd, b"rejected-restored")
            os._exit(1)
        except BaseException as error:
            # Only a fixed reason taxonomy crosses the child boundary.
            reason = "observer-error"
            if isinstance(error, host_observation.Rejected):
                reason = {
                    "sampled active40G baseline drift": "baseline-drift",
                    "active40G transition counters drift outside acknowledged changes": "transition-counters",
                }.get(str(error), "invalid-telemetry")
            elif isinstance(error, Rejected) and str(error) == "host sample freshness":
                reason = "sample-freshness"
            try:
                os.write(
                    write_fd, json.dumps({"host_rejection_reason": reason}).encode()
                )
            finally:
                os._exit(1)
    os.close(write_fd)
    try:
        if not select.select([read_fd], [], [], remaining)[0]:
            raise Rejected("parent guest validator deadline expired")
        result = os.read(read_fd, 65)
        if result == b"rejected-restored":
            raise GuestProofRejected("parent validated restored-host proof rejection")
        if len(result) != 64 or re.fullmatch(rb"[0-9a-f]{64}", result) is None:
            raise Rejected("validated exact guest qualification binding required")
        if time.monotonic() >= cutoff:
            raise Rejected("guest validator exceeded forward cutoff")
        return result.decode("ascii")
    finally:
        os.close(read_fd)
        try:
            os.killpg(pid, signal.SIGKILL)
        except ProcessLookupError:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        os.waitpid(pid, 0)


def active_port_change(steps, index):
    """Count only active-port membership/native deltas in the exact fixed model."""
    if steps == plan.FORWARD:
        initial = native.State()
    else:
        initial = next(
            native.expected_state(completed)
            for completed in plan.ROLLBACK_BOUNDARIES
            if steps == plan.inverse_for(completed)
        )
    states = native._states(tuple(step.command for step in steps), initial)
    before, after = states[index : index + 2]
    port = "1/2/6"
    return (port in before.native) != (port in after.native) or any(
        (port in before.tagged(vlan)) != (port in after.tagged(vlan))
        for vlan, _ in native.VLANS
    )


def validate_host_binding(observer, baseline, cutoff, *, acknowledged_active_changes=0):
    """Bound a fixed read-only observer and return its validated frozen snapshot."""
    remaining = min(VALIDATOR_SECONDS, cutoff - time.monotonic())
    if remaining <= 0 or not callable(observer):
        raise Rejected("bounded read-only active40G observer required")
    read_fd, write_fd = os.pipe()
    started = datetime.now(timezone.utc)
    pid = os.fork()
    if pid == 0:
        try:
            os.close(read_fd)
            os.setsid()
            sample = observer()
            stamp = datetime.fromisoformat(sample["sampled_at"])
            if not started <= stamp <= datetime.now(timezone.utc):
                raise Rejected("host sample freshness")
            frozen = host_observation.validate(
                sample,
                baseline,
                acknowledged_active_changes=acknowledged_active_changes,
            )
            raw = json.dumps(frozen, sort_keys=True, separators=(",", ":")).encode()
            if not 0 < len(raw) <= 16384:
                os._exit(1)
            os.write(write_fd, raw)
            os._exit(0)
        except BaseException as error:
            # Only a fixed reason taxonomy crosses the child boundary.
            reason = "observer-error"
            if isinstance(error, host_observation.Rejected):
                reason = {
                    "sampled active40G baseline drift": "baseline-drift",
                    "active40G transition counters drift outside acknowledged changes": "transition-counters",
                }.get(str(error), "invalid-telemetry")
            elif isinstance(error, Rejected) and str(error) == "host sample freshness":
                reason = "sample-freshness"
            try:
                os.write(
                    write_fd, json.dumps({"host_rejection_reason": reason}).encode()
                )
            finally:
                os._exit(1)
    os.close(write_fd)
    deadline = min(cutoff, time.monotonic() + remaining)
    raw = b""
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([read_fd], [], [], remaining)[0]:
                raise Rejected("active40G host observer deadline expired")
            chunk = os.read(read_fd, 16385)
            if not chunk:
                break
            raw += chunk
            if len(raw) > 16384:
                raise Rejected("active40G host observer evidence oversized")
        if not raw or time.monotonic() >= cutoff:
            raise Rejected("active40G host observer rejected or expired")
        result = json.loads(raw)
        reason = result.get("host_rejection_reason")
        if reason is not None:
            if reason not in (
                "observer-error",
                "baseline-drift",
                "transition-counters",
                "invalid-telemetry",
                "sample-freshness",
            ):
                raise Rejected("active40G host observer invalid rejection reason")
            raise Rejected("active40G host observer rejected: " + reason)
        return result
    finally:
        os.close(read_fd)
        try:
            os.killpg(pid, signal.SIGKILL)
        except ProcessLookupError:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        os.waitpid(pid, 0)


def read_offset(raw, expected_prompt=plan.FORWARD[0].before):
    """Keep a known asynchronous row intact after the expected mode prompt."""
    start = max(raw.rfind(b"\n") + 1, raw.rfind(b"\r") + 1)
    prompt = re.match(expected_prompt.encode("ascii"), raw[start:])
    if prompt:
        start += prompt.end()
    tail = raw[start:]
    if tail and any(row.encode("ascii").startswith(tail) for row in capture.POE_ROWS):
        return start
    return len(raw)


def current_exec_suffix(raw):
    lines = acknowledgement_lines(
        capture.without_known_noise(raw), plan.FORWARD[0].before
    )
    return bool(lines and lines[-1] == "headwater#")


def known_read_noise(operation, raw):
    if operation not in READS or not current_exec_suffix(raw):
        return False
    if capture.PAGER in raw or b"\x08" in raw:
        return False
    cleaned = raw
    removed = 0
    for row in capture.POE_ROWS:
        cleaned, count = re.subn(
            re.escape(row.encode("ascii")) + rb"(?:\r\n|\n\r|\n|\r)", b"", cleaned
        )
        removed += count
    lines = capture.qualified_lines(cleaned)
    return bool(
        removed
        and lines
        and lines[0] == READS[operation]
        and lines[-1] == "headwater#"
        and not any(
            capture.DENIED.search(line)
            or re.search(
                r"headwater[>(#]|Invalid (?:input|command)|Unknown command", line
            )
            for line in lines[1:-1]
        )
    )


class Runner:
    def __init__(
        self,
        controller,
        runtime,
        before,
        owned,
        interrupted,
        deadline,
        *,
        qualification=native.Qualification(native.QualificationMode.ALL_UP),
        host_observer=None,
    ):
        native.require_qualification_mode(qualification.mode)
        if qualification.mode is native.QualificationMode.PRIMARY_DOWN and not callable(
            host_observer
        ):
            raise Rejected("primary-down requires read-only active40G observer")
        self._qualification = qualification
        self._selected_mode = qualification.mode
        self.host_observer = host_observer
        self.host_baseline = None
        self.host_failure = None
        self.host_samples = 0
        self.acknowledged_active_changes = 0
        self.controller, self.runtime, self.before, self.owned = (
            controller,
            runtime,
            before,
            owned,
        )
        self.interrupted, self.deadline = interrupted, deadline
        self.events = 0
        self.unknown = False
        self.sequence = None
        self.next_index = 0
        self.pending_read = None
        self.last_read_exec_offset = None
        self.evidence: dict[str, Any] = {
            "serial_input_attempts": [],
            "append_prefix_observations": [],
        }

    @property
    def qualification(self):
        return self._qualification

    def sample_host(self, cutoff):
        if self.qualification.mode is native.QualificationMode.ALL_UP:
            return
        verify_sources()
        acknowledged = self.acknowledged_active_changes
        frozen = validate_host_binding(
            self.host_observer,
            self.host_baseline,
            cutoff,
            acknowledged_active_changes=acknowledged,
        )
        self.acknowledged_active_changes = 0
        self.host_baseline = frozen
        self.host_samples += 1
        self.event(
            "host-sample",
            {
                "sample": self.host_samples,
                "acknowledged_active_changes": acknowledged,
                "validated_state": frozen,
                "observed_at": datetime.now(timezone.utc).isoformat(),
                "sha256": hashlib.sha256(
                    json.dumps(frozen, sort_keys=True).encode()
                ).hexdigest(),
                "qualification_mode": self.qualification.mode.value,
                "continuous_monitoring": False,
            },
        )

    def guard(self, cutoff):
        if self.qualification.mode is not self._selected_mode:
            raise Rejected("qualification mode changed after selection")
        if self.interrupted() or time.monotonic() >= min(cutoff, self.deadline):
            raise Rejected("resident interrupted or absolute deadline expired")
        state = self.controller.state()
        if not capture.compare(self.before, state, self.owned) or not state["logging"]:
            raise Rejected("serial logging custody lost")
        self.owned.verify()
        if self.interrupted() or time.monotonic() >= min(cutoff, self.deadline):
            raise Rejected("resident expired after custody guard")

    def event(self, kind, payload):
        capture.private_json(
            self.runtime / f"event-{self.events:04d}-{kind}.json", payload
        )
        self.events += 1

    def checkpoint(self, cutoff):
        return capture.checkpoint(
            self.controller,
            self.before,
            self.owned,
            self.evidence,
            self.interrupted,
            min(cutoff, self.deadline),
        )

    def send(self, steps, index, cutoff):
        if self.pending_read is not None:
            raise Rejected("unresolved read boundary; no mutation dispatch")
        if self.unknown:
            raise Rejected("unknown serial outcome; no retry")
        if not plan.fixed_sequence(steps):
            raise Rejected("fixed serial sequence required")
        if self.sequence is None:
            self.sequence = steps
        if (
            steps != self.sequence
            or type(index) is not int
            or index != self.next_index
            or index >= len(steps)
        ):
            raise Rejected("fixed serial command order required")
        self.guard(cutoff)
        step = steps[index]
        offset = read_offset(self.checkpoint(cutoff), step.before)
        self.event(
            "intent",
            {
                "index": index,
                "step": asdict(step),
                "offset": offset,
                "at": datetime.now(timezone.utc).isoformat(),
            },
        )
        self.guard(cutoff)
        self.unknown = True
        self.controller.dispatch(index, steps=steps)
        response_deadline = min(cutoff, time.monotonic() + COMMAND_SECONDS)
        while True:
            raw = self.checkpoint(response_deadline)[offset:]
            lines = acknowledgement_lines(raw, step.after, command=step.command)
            if lines and re.fullmatch(step.after, lines[-1]):
                acknowledgement = None
                vlan = re.search(r"config-vlan-(\d+)", step.before)
                if step.command.startswith("tagged ethernet ") and vlan:
                    acknowledgement = f"Added tagged port(s) ethe {step.command.split()[2]} to port-vlan {vlan[1]}."
                elif step.command.startswith("no tagged ethernet ") and vlan:
                    acknowledgement = f"Deleted tagged port(s) to port-vlan {vlan[1]}."
                if lines[:-1] not in (
                    [step.command],
                    [step.command, acknowledgement]
                    if acknowledgement
                    else [step.command],
                ):
                    raise Rejected("unknown serial acknowledgement")
                self.event(
                    "ack",
                    {
                        "index": index,
                        "raw_sha256": hashlib.sha256(raw).hexdigest(),
                        "bytes": len(raw),
                    },
                )
                if active_port_change(steps, index):
                    self.acknowledged_active_changes += 1
                self.unknown = False
                self.next_index += 1
                return
            if lines and re.search(r"headwater.*[>#]$", lines[-1]):
                raise Rejected("unexpected serial prompt")
            time.sleep(0.1)

    def cancel_pending_read(self, cutoff):
        if self.pending_read is None:
            return
        operation, offset = self.pending_read
        response = read_echo_response(
            self.checkpoint(cutoff)[offset:], READS[operation]
        )
        if response is None:
            raise Rejected("unresolved read lacks known pager boundary")
        raw = capture.without_known_noise(response)
        first = re.split(rb"[\r\n]", raw, maxsplit=1)[0]
        if first != READS[operation].encode("ascii") or capture.PAGER not in raw:
            raise Rejected("unresolved read lacks known pager boundary")
        deadline = min(cutoff, self.deadline, time.monotonic() + COMMAND_SECONDS)
        offset = len(self.checkpoint(deadline))
        self.event("read-cancel-intent", {"operation": operation, "offset": offset})
        capture.guarded_input(
            self.controller,
            self.before,
            self.owned,
            self.evidence,
            "probe",
            self.interrupted,
            deadline,
        )
        while True:
            response = self.checkpoint(deadline)[offset:]
            cleaned = capture.without_known_noise(response)
            lines = [line for line in re.split(rb"\r\n|\n\r|\r|\n", cleaned) if line]
            if lines == [b"^C", b"headwater#"]:
                self.guard(deadline)
                self.event(
                    "read-cancel",
                    {
                        "operation": operation,
                        "raw_sha256": hashlib.sha256(response).hexdigest(),
                        "exact_exec_observed": True,
                    },
                )
                self.pending_read = None
                return
            time.sleep(0.1)

    def read(self, operation, cutoff):
        self.cancel_pending_read(cutoff)
        self.failed_read = None
        self.guard(cutoff)
        read_started = time.monotonic()
        deadline = min(cutoff, read_started + READ_SECONDS)
        offset = read_offset(self.checkpoint(deadline))
        self.event("read-intent", {"operation": operation, "offset": offset})
        self.guard(deadline)
        self.pending_read = (operation, offset)
        self.controller.dispatch(tuple(READS).index(operation), read=True)
        spaces = 0
        while True:
            raw = self.checkpoint(deadline)[offset:]
            response = read_echo_response(raw, READS[operation])
            if response is None:
                time.sleep(0.1)
                continue
            if operation in ("running", "startup"):
                progress, canonical = capture.configuration_progress(
                    response, operation, spaces
                )
                body = tuple(canonical)
            else:
                cleaned = capture.without_known_noise(response)
                erased = capture.PAGER + b"\x08 \x08" * len(capture.PAGER)
                consumed = cleaned.count(erased)
                if consumed > spaces or consumed > capture.CONFIGURATION_PAGER_LIMIT:
                    raise Rejected("read pager chronology")
                cleaned = cleaned.replace(erased, b"")
                progress, body = "wait", ()
                if cleaned.endswith(capture.PAGER):
                    progress = "page" if consumed == spaces else "wait"
                elif b"--More--" not in cleaned and b"\x08" not in cleaned:
                    lines = capture.qualified_lines(cleaned)
                    if lines and lines[-1] == "headwater#":
                        self.pending_read = None
                        if lines[0] != READS[operation] or any(
                            capture.DENIED.search(line)
                            or re.search(
                                r"headwater[>(#]|Invalid (?:input|command)|Unknown command",
                                line,
                            )
                            for line in lines[1:-1]
                        ):
                            self.failed_read = (operation, raw)
                            raise Rejected("read echo or prompt boundary")
                        progress, body = "complete", tuple(lines[1:-1])
            if progress == "complete":
                self.guard(deadline)
                self.event(
                    "read",
                    {
                        "operation": operation,
                        "elapsed_seconds": time.monotonic() - read_started,
                        "lines": body,
                        "raw_sha256": hashlib.sha256(raw).hexdigest(),
                    },
                )
                rows = b"|".join(
                    re.escape(row.encode("ascii")) for row in capture.POE_ROWS
                )
                terminal = re.search(rb"headwater#(?:[ \t\r\n]|" + rows + rb")*\Z", raw)
                if terminal is None:
                    raise Rejected("qualified read terminal boundary unavailable")
                self.last_read_exec_offset = offset + terminal.start()
                self.pending_read = None
                return body
            if progress == "page":
                if spaces >= capture.CONFIGURATION_PAGER_LIMIT:
                    raise Rejected("read pager limit")
                spaces += 1
                self.event("page-intent", {"operation": operation, "space": spaces})
                capture.guarded_input(
                    self.controller,
                    self.before,
                    self.owned,
                    self.evidence,
                    "page",
                    self.interrupted,
                    deadline,
                )
            time.sleep(0.1)

    def diagnostic_span(self, cutoff):
        if self.unknown:
            raise Rejected("unknown serial outcome; no diagnostic continuation")
        offset = len(self.checkpoint(cutoff))
        try:
            return self.read("span", cutoff)
        except Rejected as error:
            if str(error) != "read echo or prompt boundary":
                raise
            self.guard(cutoff)
            raw = self.checkpoint(cutoff)[offset:]
            cleaned = capture.without_known_noise(raw)
            erased = capture.PAGER + b"\x08 \x08" * len(capture.PAGER)
            if cleaned.count(erased) > capture.CONFIGURATION_PAGER_LIMIT:
                raise Rejected("failed diagnostic pager bound") from error
            lines = capture.qualified_lines(cleaned.replace(erased, b""))
            if not lines or lines[-1] != "headwater#":
                raise Rejected("failed diagnostic did not return exact EXEC") from error
            self.guard(cutoff)
            self.event(
                "diagnostic-failure",
                {
                    "operation": "span",
                    "failure": str(error),
                    "exact_exec_observed": True,
                    "raw_sha256": hashlib.sha256(raw).hexdigest(),
                    "span_parser_qualified": False,
                },
            )
            return None

    def observe_restored(self, baseline, startup, completed, cutoff, inverse=False):
        # Only verified gateway settling may refresh a read window within the fixed inverse budget.
        observation_cutoff = min(cutoff, time.monotonic() + OBSERVE_SECONDS)
        while True:
            try:
                return self.observe(
                    baseline, startup, completed, observation_cutoff, inverse
                )
            except (Rejected, observation.evidence.Rejected) as error:
                if self.unknown:
                    raise
                if (
                    str(error) == "fixed trunk carrier or speed required"
                    and getattr(self, "recovering", False)
                    and self.gateway_listening(completed, inverse)
                ):
                    self.guard(observation_cutoff)
                    current = self.checkpoint(observation_cutoff)
                    if self.last_read_exec_offset is None:
                        raise
                    fresh = current[self.last_read_exec_offset :]
                    if not current_exec_suffix(fresh) or acknowledgement_lines(
                        fresh, plan.FORWARD[0].before
                    ) != ["headwater#"]:
                        raise
                    if tuple(self.read("startup", observation_cutoff)) != tuple(
                        startup
                    ):
                        raise Rejected(
                            "startup changed during inverse gateway settling"
                        )
                    self.event(
                        "inverse-gateway-settle",
                        {
                            "completed": completed,
                            "inverse": inverse,
                            "cutoff": observation_cutoff,
                            "configuration_inputs": 0,
                        },
                    )
                    self.guard(observation_cutoff)
                    time.sleep(0.5)
                    observation_cutoff = min(cutoff, time.monotonic() + OBSERVE_SECONDS)
                    continue
                if str(error) != "read echo or prompt boundary" or getattr(
                    self, "postinverse_reobserved", False
                ):
                    raise
                failed = getattr(self, "failed_read", None)
                if failed is None or not known_read_noise(failed[0], failed[1]):
                    raise
                self.guard(observation_cutoff)
                current = self.checkpoint(observation_cutoff)
                if not current_exec_suffix(current):
                    raise
                self.postinverse_reobserved = True
                self.event(
                    "postinverse-read-noise",
                    {
                        "operation": failed[0],
                        "raw_sha256": hashlib.sha256(failed[1]).hexdigest(),
                        "reobserve_once": True,
                        "cutoff": observation_cutoff,
                    },
                )

    def gateway_listening(self, completed, inverse):
        brief = self.last_brief
        if (
            not brief.isascii()
            or re.search(r"[^\x20-\x7e\r\n\t]", brief)
            or re.search(r"\r(?!\n)", brief)
        ):
            return False
        rows = []
        gateways = 0
        for line in brief.splitlines():
            words = line.split()
            if words and words[0] == "1/3/1":
                gateways += 1
                if (
                    len(words) != 10
                    or words[1] != "Up"
                    or words[2] not in ("Listen", "Learn")
                    or words[3:5] != ["Full", "10G"]
                ):
                    return False
                words[2] = "Forward"
                line = " ".join(words)
            rows.append(line)
        if gateways != 1:
            return False
        # This validates the complete table and every other carrier, tag and PVID.
        if self.qualification.mode is native.QualificationMode.PRIMARY_DOWN:
            observation.require_operational_state(
                "\n".join(rows),
                completed=completed,
                inverse=inverse,
                qualification=self.qualification,
            )
        else:
            observation.require_recovery_operational_state(
                "\n".join(rows),
                completed=completed,
                inverse=inverse,
            )
        return True

    def observe(self, baseline, startup, completed, cutoff, inverse=False):
        observation_started = time.monotonic()
        cutoff = min(cutoff, observation_started + OBSERVE_SECONDS)
        running = self.read("running", cutoff)
        state = observation.classify_observation(baseline, running, startup)
        observation.require_state(state, completed=completed, inverse=inverse)
        brief = "\n".join(self.read("brief", cutoff))
        self.last_brief = brief
        tables = {
            vlan: "\n".join(self.read(f"vlan{vlan}", cutoff))
            for vlan in (1, 10, 20, 30, 40, 132)
        }
        observation.require_membership(
            tables,
            baseline_vlan1=self.baseline_tables[1],
            baseline_vlan132=self.baseline_tables[132],
            completed=completed,
            inverse=inverse,
        )
        recovery = getattr(self, "recovering", False)
        if self.qualification.mode is native.QualificationMode.PRIMARY_DOWN:
            try:
                observation.require_operational_state(
                    brief,
                    completed=completed,
                    inverse=inverse,
                    qualification=self.qualification,
                )
                self.sample_host(cutoff)
            except (Rejected, observation.evidence.Rejected) as error:
                # Invert only at an exact configuration/membership boundary with
                # restoration-safe switch links. Host drift never qualifies it.
                observation.require_recovery_operational_state(
                    brief,
                    completed=completed,
                    inverse=inverse,
                )
                self.host_failure = str(error)
                if not recovery:
                    raise CarrierRejected(
                        "primary-down sampled state drift: " + str(error)
                    ) from error
        elif recovery:
            observation.require_recovery_operational_state(
                brief, completed=completed, inverse=inverse
            )
            if any(
                line.split()[:2] == ["1/2/2", "Down"] for line in brief.splitlines()
            ):
                self.recovery_carrier_failed = True
        else:
            try:
                observation.require_operational_state(
                    brief, completed=completed, inverse=inverse
                )
            except observation.evidence.Rejected as error:
                observation.require_recovery_operational_state(
                    brief, completed=completed, inverse=inverse
                )
                self.guard(cutoff)
                raise CarrierRejected(
                    "primary carrier down at exact native state"
                ) from error
        self.guard(cutoff)
        self.event(
            "state",
            {
                "completed": completed,
                "inverse": inverse,
                "elapsed_seconds": time.monotonic() - observation_started,
                "cutoff": cutoff,
                "state": asdict(state),
            },
        )
        return state

    def wait_guest_proof(self, state, cutoff):
        self.guard(cutoff)
        if (
            cutoff - time.monotonic()
            < PROOF_SECONDS + OBSERVE_SECONDS + VALIDATOR_SECONDS
        ):
            # No held artifact has been published, so the fixed job cannot select a NIC.
            raise GuestProofRejected("insufficient forward budget before proof job")
        context = {
            "schema": 1,
            "qualification_mode": self.qualification.mode.value,
            "guest_proof_kind": "read-only-active40g"
            if self.qualification.mode is native.QualificationMode.PRIMARY_DOWN
            else "selected-standby",
            "host_baseline_sha256": hashlib.sha256(
                json.dumps(self.host_baseline, sort_keys=True).encode()
            ).hexdigest()
            if self.host_baseline is not None
            else None,
            "nonce": secrets.token_hex(32),
            "resident_sha256": SELF_SHA256,
            "runner": {
                "pid": os.getpid(),
                "starttime": capture.process_starttime(os.getpid()),
            },
            "state_sha256": hashlib.sha256(
                json.dumps(
                    asdict(state), sort_keys=True, separators=(",", ":")
                ).encode()
            ).hexdigest(),
            "state": json.loads(json.dumps(asdict(state))),
            "proof_seconds": PROOF_SECONDS,
            "proof_cutoff_monotonic": time.monotonic() + PROOF_SECONDS,
        }
        final_proof = (
            self.qualification.mode is native.QualificationMode.PRIMARY_DOWN
            and state.state == native.FINAL_STATE
        )
        if self.qualification.mode is native.QualificationMode.PRIMARY_DOWN:
            context["completed"] = len(native.FORWARD_COMMANDS) if final_proof else 7
        suffix = "-final" if final_proof else ""
        held_path = self.runtime / f"held-state{suffix}.json"
        capture.private_json(held_path, context)
        held_stat = held_path.lstat()
        proof_cutoff = min(cutoff, context["proof_cutoff_monotonic"])
        proof_path = self.runtime / f"guest-proof{suffix}.json"
        while time.monotonic() < proof_cutoff:
            self.guard(cutoff)
            try:
                fd = os.open(proof_path, os.O_RDONLY | os.O_NOFOLLOW)
            except FileNotFoundError:
                time.sleep(min(0.1, max(0, proof_cutoff - time.monotonic())))
                continue
            with os.fdopen(fd, "rb") as stream:
                info = os.fstat(stream.fileno())
                if (
                    not capture.stat.S_ISREG(info.st_mode)
                    or info.st_uid != os.geteuid()
                    or capture.stat.S_IMODE(info.st_mode) != 0o600
                    or info.st_nlink != 1
                    or not 0 < info.st_size <= 65536
                    or info.st_mtime_ns < held_stat.st_mtime_ns
                ):
                    raise Rejected("private guest proof custody or freshness differs")
                raw = stream.read(65537)
                after = os.fstat(stream.fileno())
                fields = (
                    "st_dev",
                    "st_ino",
                    "st_size",
                    "st_mtime_ns",
                    "st_ctime_ns",
                    "st_mode",
                    "st_uid",
                    "st_nlink",
                )
                if len(raw) != info.st_size or any(
                    getattr(info, field) != getattr(after, field) for field in fields
                ):
                    raise Rejected("guest proof changed during read")
            artifact = json.loads(raw)
            if (
                type(artifact) is not dict
                or set(artifact) != {"context", "proof"}
                or artifact["context"] != context
                or type(artifact["proof"]) is not dict
            ):
                raise Rejected("guest proof does not bind exact held runtime/state")
            if (
                self.qualification.mode is native.QualificationMode.PRIMARY_DOWN
                and artifact["proof"].get("kind") != "read-only-active40g"
            ):
                raise Rejected("primary-down requires read-only active40G guest proof")
            self.guard(cutoff)
            self.event(
                "guest-proof-arrived", {"sha256": hashlib.sha256(raw).hexdigest()}
            )
            return artifact
        # An elapsed watchdog is not evidence that the PVE selector restored nic0.
        raise Rejected("guest proof absent; selector restoration unresolved")

    def cycle(self, phase, validate_guest_proof):
        require_phase(phase)
        forward_cutoff = self.deadline - INVERSE_RESERVE - CLEANUP_RESERVE
        inverse_cutoff = self.deadline - CLEANUP_RESERVE
        capture.qualify_cancel(
            self.controller,
            self.before,
            self.owned,
            self.evidence,
            self.interrupted,
            forward_cutoff,
        )
        baseline = self.read("running", forward_cutoff)
        startup = self.read("startup", forward_cutoff)
        if self.qualification.mode is native.QualificationMode.PRIMARY_DOWN:
            native.build_plan(baseline, startup, qualification=self.qualification)
            self.sample_host(forward_cutoff)
        else:
            native.build_plan(baseline, startup)
        self.baseline_tables = {
            vlan: "\n".join(self.read(f"vlan{vlan}", forward_cutoff))
            for vlan in (1, 132)
        }
        self.observe(baseline, startup, 0, forward_cutoff)
        self.diagnostic_span(
            forward_cutoff
        )  # Diagnostic only; no qualified span parser.
        completed = 0
        guest_bound = False
        guest_proof_failure = None
        native_started = None
        forward_failure = None
        for index, step in enumerate(plan.FORWARD):
            self.send(plan.FORWARD, index, forward_cutoff)
            completed = step.completed
            if step.command == "dual-mode 1":
                native_started = time.monotonic()
            if step.observe:
                phase_cutoff = forward_cutoff
                if step.hold:
                    assert native_started is not None
                    phase_cutoff = min(
                        forward_cutoff, native_started + native.MAX_FORWARD_SECONDS
                    )
                    hold_started = time.monotonic()
                    self.event(
                        "native-hold",
                        {
                            "completed": completed,
                            "navigation_seconds": hold_started - native_started,
                        },
                    )
                    hold_end = hold_started + native.MIN_SETTLE_SECONDS
                    while time.monotonic() < hold_end:
                        self.guard(phase_cutoff)
                        time.sleep(max(0, min(0.1, hold_end - time.monotonic())))
                try:
                    state = self.observe(baseline, startup, completed, phase_cutoff)
                except CarrierRejected as error:
                    if self.unknown or completed not in plan.ROLLBACK_BOUNDARIES:
                        raise
                    self.guard(inverse_cutoff)
                    forward_failure = str(error)
                    self.event(
                        "forward-failure",
                        {"completed": completed, "failure": str(error)},
                    )
                    break
                self.guard(phase_cutoff)
                if step.hold:
                    assert native_started is not None
                    observation.require_settled_native_phase(
                        state,
                        self.last_brief,
                        completed=completed,
                        elapsed_seconds=time.monotonic() - native_started,
                        qualification=self.qualification,
                    )
                self.diagnostic_span(forward_cutoff)
                if completed == 7 or (
                    completed == len(native.FORWARD_COMMANDS)
                    and self.qualification.mode is native.QualificationMode.PRIMARY_DOWN
                ):
                    self.event(
                        "held-standby" if completed == 7 else "held-final-trunk",
                        {
                            "state": asdict(state),
                            "execution_qualified": False,
                            "live_admission": False,
                        },
                    )
                    if phase is plan.Phase.STANDBY_QUALIFICATION:
                        break
                    if phase is not plan.Phase.REMAINING_TRUNK:
                        raise Rejected("fixed phase required")
                    # Parent owns exact scope/freshness binding to an actual guest proof.
                    try:
                        guest_bound = False
                        artifact = self.wait_guest_proof(state, forward_cutoff)
                        state = self.observe(
                            baseline, startup, completed, forward_cutoff
                        )
                        proof = validate_guest_binding(
                            lambda current: validate_guest_proof(current, artifact),
                            state,
                            forward_cutoff,
                        )
                        try:
                            self.sample_host(forward_cutoff)
                        except Rejected as error:
                            self.host_failure = str(error)
                            raise CarrierRejected(
                                "post-proof sampled host drift"
                            ) from error
                    except CarrierRejected as error:
                        if self.unknown or completed not in plan.ROLLBACK_BOUNDARIES:
                            raise
                        self.guard(inverse_cutoff)
                        forward_failure = str(error)
                        self.event(
                            "forward-failure",
                            {"completed": completed, "failure": str(error)},
                        )
                        break
                    except GuestProofRejected as error:
                        self.guard(inverse_cutoff)
                        guest_proof_failure = str(error)
                        self.event("guest-proof-failure", {"failure": str(error)})
                        break
                    except Rejected as error:
                        if (
                            self.qualification.mode
                            is not native.QualificationMode.PRIMARY_DOWN
                        ):
                            raise
                        # This proof job is read-only: no selector restoration is
                        # unresolved. Reobserve exact switch state before inverse.
                        self.recovering = True
                        self.observe(baseline, startup, completed, inverse_cutoff)
                        self.host_failure = str(error)
                        guest_proof_failure = str(error)
                        self.event("guest-proof-failure", {"failure": str(error)})
                        break
                    guest_bound = (
                        self.qualification.mode
                        is not native.QualificationMode.PRIMARY_DOWN
                        or completed == len(native.FORWARD_COMMANDS)
                    )
                    self.event(
                        "guest-binding",
                        {
                            "completed": completed,
                            "sha256": proof,
                            "authority": "parent validator",
                            "fresh_proof_claimed": False,
                        },
                    )
        inverse = plan.inverse_for(completed)
        self.recovering = True
        inverse_cutoff = min(inverse_cutoff, time.monotonic() + INVERSE_RESERVE)
        self.sequence, self.next_index = inverse, 0
        for index, step in enumerate(inverse):
            self.send(inverse, index, inverse_cutoff)
            if step.observe:
                if completed in native.NATIVE_PHASE_ENDS:
                    self.observe_restored(baseline, startup, 0, inverse_cutoff)
                else:
                    self.observe_restored(
                        baseline, startup, step.completed, inverse_cutoff, inverse=True
                    )
                self.diagnostic_span(inverse_cutoff)
        verify_sources()
        final_startup = self.read("startup", inverse_cutoff)
        if final_startup != startup:
            raise Rejected("startup changed during unsaved serial cycle")
        if self.qualification.mode is native.QualificationMode.PRIMARY_DOWN:
            try:
                self.sample_host(inverse_cutoff)
            except Rejected as error:
                self.host_failure = str(error)
        self.event(
            "restored",
            {
                "baseline_sha256": observation.evidence.configuration_hash(baseline),
                "startup_unchanged": True,
            },
        )
        return {
            "qualification_mode": self.qualification.mode.value,
            "accepted_outcome": self.qualification.accepted_outcome
            if phase is plan.Phase.REMAINING_TRUNK
            and guest_bound
            and guest_proof_failure is None
            and forward_failure is None
            and self.host_failure is None
            and not getattr(self, "recovery_carrier_failed", False)
            else None,
            "host_samples": self.host_samples,
            "host_failure": self.host_failure,
            "continuous_monitoring": False,
            "primary_forwarding_qualified": False,
            "primary_redundancy_qualified": False,
            "restored": True,
            "execution_qualified": False,
            "live_admission": False,
            "span_parser_qualified": False,
            "guest_proof_authority_bound": guest_bound,
            "guest_proof_failure": guest_proof_failure,
            "forward_failure": forward_failure,
            "recovery_carrier_failed": getattr(self, "recovery_carrier_failed", False),
            "qualification_passed": phase is plan.Phase.REMAINING_TRUNK
            and guest_bound
            and guest_proof_failure is None
            and forward_failure is None
            and self.host_failure is None
            and not getattr(self, "recovery_carrier_failed", False),
        }


def acknowledgement_lines(raw, expected_prompt, *, command=None):
    lines = capture.qualified_lines(capture.without_known_noise(raw))
    for index, line in enumerate(lines):
        for row in capture.POE_ROWS:
            if line.endswith(row):
                prompt = line[: -len(row)]
                if re.fullmatch(expected_prompt, prompt):
                    lines[index] = prompt
                    break
    if command == "configure terminal" and not any(
        byte < 32 and byte not in (10, 13) or byte == 127 for byte in raw
    ):
        # Known asynchronous rows interrupted this echo on the actual device.
        # Remove only complete rows and accept only the exact recovered echo/prompt.
        rows = b"|".join(re.escape(row.encode("ascii")) for row in capture.POE_ROWS)
        recovered = re.sub(rb"(?:" + rows + rb")(?:\r\n|\n\r|\n|\r)", b"", raw)
        recovered_text = recovered.decode("ascii").replace("\r\n", "\n")
        recovered_text = recovered_text.replace("\n\r", "\n").replace("\r", "\n")
        recovered_lines = [line for line in recovered_text.split("\n") if line]
        if (
            len(recovered_lines) == 2
            and recovered_lines[0] == command
            and re.fullmatch(expected_prompt, recovered_lines[1])
        ):
            return recovered_lines
    return lines


def require_phase(phase):
    if (
        phase is not plan.Phase.STANDBY_QUALIFICATION
        and phase is not plan.Phase.REMAINING_TRUNK
    ):
        raise Rejected("fixed phase required")


def lifecycle(
    controller,
    runtime,
    phase,
    validator,
    interrupted=lambda: False,
    *,
    qualification=native.Qualification(native.QualificationMode.ALL_UP),
    host_observer=None,
):
    require_phase(phase)
    native.require_qualification_mode(qualification.mode)
    if qualification.mode is native.QualificationMode.PRIMARY_DOWN and not callable(
        host_observer
    ):
        raise Rejected("primary-down requires read-only active40G observer")
    verify_sources()
    deadline = time.monotonic() + TOTAL_SECONDS
    before, owned, enabled, runner = None, None, False, None
    receipt: dict[str, Any] = {
        "qualification_mode": qualification.mode.value,
        "restored": False,
        "cleanup_complete": False,
        "execution_qualified": False,
        "live_admission": False,
    }
    try:
        before = controller.state()
        capture.initial(before)
        owned = capture.OwnedFile(runtime)
        capture.compare(before, controller.state(), None)
        controller.command("template", owned)
        capture.compare(before, controller.state(), None)
        if (
            interrupted()
            or time.monotonic() >= deadline - INVERSE_RESERVE - CLEANUP_RESERVE
        ):
            raise Rejected("expired before logging adoption")
        enabled = True
        controller.command("on")
        runner = Runner(
            controller,
            runtime,
            before,
            owned,
            interrupted,
            deadline,
            qualification=qualification,
            host_observer=host_observer,
        )
        receipt.update(runner.cycle(phase, validator))
    except Exception as error:
        receipt["failure"] = type(error).__name__ + ": " + str(error)
    finally:
        receipt["unknown_command"] = runner.unknown if runner else False
        if before is not None:
            try:
                if time.monotonic() >= deadline:
                    raise Rejected("absolute deadline exhausted before cleanup")
                current = controller.state()
                matching = capture.compare(before, current, owned)
                if current["logging"] or matching:
                    if not enabled or not matching or owned is None:
                        raise Rejected("cannot stop unowned logging")
                    controller.command("off")
                    current = controller.state()
                if current["logging"] or capture.compare(before, current, owned):
                    raise Rejected("logging closure unproved")
                receipt["cleanup_complete"] = True
                if owned is not None:
                    owned.read()
            except Exception as error:
                receipt["cleanup_failure"] = type(error).__name__ + ": " + str(error)
        receipt["pending_may_clear"] = bool(
            receipt["restored"]
            and receipt["cleanup_complete"]
            and not receipt["unknown_command"]
            and "failure" not in receipt
            and not receipt.get("host_failure")
        )
        capture.private_json(runtime / "receipt.json", receipt)
    return receipt


def run_r8_probe_candidate(guarded, baseline, observe, console, admit, binding):
    """Run the current-source auxiliary R8 probe through strict transport and admission."""
    verify_sources()
    return r8_probe.run_and_admit(
        guarded,
        baseline,
        observe,
        console,
        admit,
        binding,
    )


def run_r8_full_trunk_candidate(
    guarded,
    baseline,
    observe,
    console,
    admit,
    binding,
    held_guest_proof,
    guest_policy,
    r8_recovery_session=None,
    operation_budget=None,
):
    """Run current-source tag restoration against the accepted R8 saved trunk."""
    verify_sources()
    return r8_probe.run_and_admit_full_trunk(
        guarded,
        baseline,
        observe,
        console,
        admit,
        binding,
        held_guest_proof,
        guest_policy,
        r8_recovery_session,
        operation_budget,
    )


def run_r8_full_trunk_session_candidate(
    guarded,
    baseline,
    observe,
    admit,
    binding,
    held_guest_proof,
    guest_policy,
    recovery_observe,
    pin,
    runtime,
    credential_provider,
    operation_budget=None,
):
    """Run the source-pinned R8 caller with distinct root SSH sessions."""
    verify_sources()
    return r8_root_session.run_full_trunk_candidate(
        guarded,
        baseline,
        observe,
        admit,
        binding,
        held_guest_proof,
        guest_policy,
        recovery_observe,
        pin,
        runtime,
        credential_provider,
        operation_budget,
    )


def run_r8_full_trunk_audited_candidate(
    guarded,
    baseline,
    admit,
    binding,
    audit_pin,
    audit_runtime,
    audit_credential_provider,
    root_pin,
    root_runtime,
    root_credential_provider,
    pve_credential_provider=None,
    operation_budget=None,
):
    """Bind current-source R8 guest proof, audit reads and root writes."""
    verify_sources()

    guest_parent_options = (
        {"pve_credential_provider": pve_credential_provider}
        if pve_credential_provider is not None
        else {}
    )
    held_guest_proof, guest_policy = r8_guest_parent.R8GuestParent(
        audit_pin,
        audit_runtime,
        baseline,
        audit_credential_provider,
        **guest_parent_options,
    ).prepare(
        deadline=(
            operation_budget.observation_deadline
            if operation_budget is not None
            else None
        )
    )
    if operation_budget is not None:
        operation_budget.check()

    def observe():
        options = {}
        if operation_budget is not None:
            operation_budget.check()
            options["deadline"] = operation_budget.observation_deadline
        result = r8_observation.observe(
            audit_pin,
            audit_runtime,
            baseline,
            audit_credential_provider,
            **options,
        )
        if operation_budget is not None:
            operation_budget.check()
        return result

    def recovery_observe(_recovery_console):
        return observe

    return run_r8_full_trunk_session_candidate(
        guarded,
        baseline,
        observe,
        admit,
        binding,
        held_guest_proof,
        guest_policy,
        recovery_observe,
        root_pin,
        root_runtime,
        root_credential_provider,
        operation_budget,
    )


def validate_r8_preflight(path, now=None):
    """Require fresh, semantically checked current-source evidence before R8 writes."""
    r8_observation.base._private_path(path, directory=False)
    raw = path.read_bytes()
    receipt = json.loads(
        raw, object_pairs_hook=r8_probe.admission.cycle.storage.unique_object
    )
    pve = receipt.get("pve_parent_readonly_preflight")
    observation = receipt.get("current_observation")
    if (
        receipt.get("schema") != 2
        or not isinstance(observation, dict)
        or not isinstance(observation.get("observed_at"), str)
    ):
        raise Rejected("current-source R8 observation required")
    try:
        observed = datetime.fromisoformat(
            observation["observed_at"].replace("Z", "+00:00")
        )
    except ValueError as error:
        raise Rejected("current-source R8 observation timestamp required") from error
    if observed.tzinfo is None:
        raise Rejected("timezone-aware current-source R8 observation required")
    age = ((now or datetime.now(timezone.utc)) - observed).total_seconds()
    if (
        receipt.get("configuration_write_attempted") is not False
        or receipt.get("independent_rescue_currently_verified") is not True
        or type(pve) is not dict
        or pve.get("passed") is not True
        or pve.get("active_member") != "nic5"
        or pve.get("usb_management_gateway") != "10.72.10.1"
        or not 0 <= age < 600
    ):
        raise Rejected("fresh structured R8 preflight receipt required")
    r8_observation.unchanged_sources()
    try:
        baseline, startup = r8_observation.base.engine.evidence_config(
            observation, r8_observation.base.PORT
        )
        cycle = r8_probe.admission.cycle
        expected_hash = cycle.native_trunk_plan.R8_BASELINE_SHA256
        if (
            cycle.evidence.configuration_hash(baseline) != expected_hash
            or cycle.evidence.configuration_hash(startup) != expected_hash
        ):
            raise Rejected(
                "live running/startup state differs from accepted R8 baseline"
            )
        tables = r8_observation.trunk.require_r8_vlan_capture(observation)
        plan = cycle.native_trunk_plan.build_r8_full_trunk_plan(baseline, startup)
        state = r8_observation.trunk.classify_r8_full_trunk_observation(
            baseline, baseline, startup
        )
        r8_observation.trunk.require_r8_full_trunk_membership(
            tables, tables, state.state, plan.initial_state
        )
        r8_observation.trunk.require_r8_full_trunk_operational_state(
            observation["responses"]["show interfaces brief"], state.state
        )
        if observation.get("observation_source_sha256") != r8_observation.SOURCE_SHA256:
            raise Rejected("current-source R8 observation binding mismatch")
    except (KeyError, TypeError, ValueError) as error:
        raise Rejected(
            "current-source R8 observation failed semantic admission"
        ) from error
    return receipt, hashlib.sha256(raw).hexdigest(), raw


def _r8_startup_anchor(pin, runtime, audit_credential_provider, deadline=None):
    base = r8_observation.base
    payload = base._AuditInput(audit_credential_provider)
    options = {"deadline": deadline} if deadline is not None else {}
    with base.bootstrap.session(
        pin,
        runtime,
        user=base.bootstrap.USER,
        payload=payload,
        **options,
    ) as (console, _):
        raw = console.command("show configuration", audit=True, **options)
    return base.engine.configuration(raw)


def run_r8_full_trunk_live(pin, preflight_path, pve_credential_provider=None):
    """Execute one explicit, unsaved R8 qualification under durable custody."""
    global R8_LIVE_RUNTIME
    started = time.monotonic()
    budget = R8OperationBudget(started)
    verify_sources()
    preflight, preflight_sha256, preflight_raw = validate_r8_preflight(preflight_path)
    r8_observation.base._private_path(pin, directory=False)

    parent = Path.home() / ".cache/agent-scratch/m7-r8-live"
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    r8_probe.admission.cycle.storage.private_directory(parent)
    runtime = Path(tempfile.mkdtemp(prefix="r8-full-trunk-", dir=parent))
    R8_LIVE_RUNTIME = runtime
    runtime.chmod(0o700)
    audit_runtime = runtime / "audit"
    root_runtime = runtime / "root"
    audit_runtime.mkdir(mode=0o700)
    root_runtime.mkdir(mode=0o700)
    credentials = {"values": None}

    def credential(name):
        if credentials["values"] is None:
            credentials["values"] = r8_observation.base.bootstrap.credentials("apply")
        return credentials["values"][name + "_password"]

    def audit_credential_provider():
        return credential("audit")

    def root_credential_provider():
        return credential("root")

    def admit():
        verify_sources()
        budget.check()
        current = preflight_path.read_bytes()
        if current != preflight_raw:
            raise Rejected("R8 preflight receipt changed during operation")

    with r8_probe.admission.cycle.storage.locked_exercise(parent, runtime) as guarded:
        if os.path.lexists(guarded.pending):
            raise Rejected("pending R8 operation blocks qualification")
        budget.check()
        startup = _r8_startup_anchor(
            pin,
            audit_runtime,
            audit_credential_provider,
            deadline=budget.observation_deadline,
        )
        budget.check()
        if r8_observation.base.engine.configuration_hash(startup) != (
            r8_probe.admission.cycle.native_trunk_plan.R8_BASELINE_SHA256
        ):
            raise Rejected("live startup differs from accepted R8 baseline")
        observation = r8_observation.observe(
            pin,
            audit_runtime,
            startup,
            audit_credential_provider,
            deadline=budget.observation_deadline,
        )
        baseline, observed_startup = r8_probe.admission.cycle.evidence.evidence_config(
            observation, r8_observation.base.PORT
        )
        if (
            baseline != startup
            or observed_startup != startup
            or r8_observation.base.engine.configuration_hash(baseline)
            != r8_probe.admission.cycle.native_trunk_plan.R8_BASELINE_SHA256
        ):
            raise Rejected(
                "live running/startup state differs from accepted R8 baseline"
            )

        cycle = r8_probe.admission.cycle
        binding = {
            "baseline_running_sha256": cycle.evidence.configuration_hash(baseline),
            "baseline_startup_sha256": cycle.evidence.configuration_hash(startup),
            "source_binding_sha256": cycle.SOURCE_DIGEST,
            "execution_environment_sha256": cycle.evidence.EE_DIGEST,
            "preview_sha256": cycle.r8_full_trunk_preview_digest(baseline),
            "native_recovery_proof_sha256": preflight_sha256,
        }
        budget.check()
        result = run_r8_full_trunk_audited_candidate(
            guarded=guarded,
            baseline=baseline,
            admit=admit,
            binding=binding,
            audit_pin=pin,
            audit_runtime=audit_runtime,
            audit_credential_provider=audit_credential_provider,
            root_pin=pin,
            root_runtime=root_runtime,
            root_credential_provider=root_credential_provider,
            pve_credential_provider=pve_credential_provider,
            operation_budget=budget,
        )
    return {
        "status": "r8_full_trunk_unsaved_cycle_passed",
        "result": result,
        "runtime": str(runtime),
        "preflight_sha256": preflight_sha256,
        "preflight_observed_at": preflight["observed_at"],
        "elapsed_seconds": time.monotonic() - started,
        "total_seconds": TOTAL_SECONDS,
        "inverse_reserve_seconds": INVERSE_RESERVE,
        "cleanup_reserve_seconds": CLEANUP_RESERVE,
        "task_complete": False,
    }


def pve_credential_from_fd(fd):
    """Read one bounded PVE credential from a caller-owned private descriptor."""
    raw = os.read(fd, 258)
    os.close(fd)
    if raw.endswith(b"\n"):
        raw = raw[:-1]
    if not raw or len(raw) > 256 or any(byte < 33 or byte > 126 for byte in raw):
        raise Rejected("PVE credential descriptor rejected")
    return raw.decode("ascii")


def launch_candidate(
    phase,
    validator,
    *,
    qualification=native.Qualification(native.QualificationMode.ALL_UP),
    host_observer=None,
):
    """Detached candidate entry point for offline qualification; CLI does not admit it."""
    require_phase(phase)
    native.require_qualification_mode(qualification.mode)
    if qualification.mode is native.QualificationMode.PRIMARY_DOWN and not callable(
        host_observer
    ):
        raise Rejected("primary-down requires read-only active40G observer")
    verify_sources()
    lock = capture.capture_lock()
    runtime = Path(tempfile.mkdtemp(prefix="native-trunk-resident-", dir="/tmp"))
    runtime.chmod(0o700)
    capture.private_json(
        capture.PENDING_PATH,
        {
            "runtime": str(runtime),
            "qualification_mode": qualification.mode.value,
            "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "switch_state_resolved": False,
        },
    )
    info = capture.PENDING_PATH.lstat()
    identity = info.st_dev, info.st_ino
    pid = os.fork()
    if pid == 0:
        try:
            os.setsid()
            interrupted = [False]

            def stop(signum, frame):
                interrupted[0] = True

            for signum in (signal.SIGHUP, signal.SIGTERM, signal.SIGINT):
                signal.signal(signum, stop)
            null = os.open("/dev/null", os.O_RDWR)
            for fd in (0, 1, 2):
                os.dup2(null, fd)
            if null > 2:
                os.close(null)
            capture.private_json(
                runtime / "runner.json",
                {
                    "pid": os.getpid(),
                    "starttime": capture.process_starttime(os.getpid()),
                },
            )
            receipt = lifecycle(
                Controller(),
                runtime,
                phase,
                validator,
                lambda: interrupted[0],
                qualification=qualification,
                host_observer=host_observer,
            )
            if receipt["pending_may_clear"]:
                capture.clear_pending(identity)
            os._exit(0)
        except BaseException as error:
            try:
                capture.private_json(
                    runtime / "runner-failure.json",
                    {"exception_type": type(error).__name__, "pending_retained": True},
                )
            finally:
                os._exit(1)
    os.close(lock)
    return {
        "pid": pid,
        "runtime": str(runtime),
        "execution_qualified": False,
        "live_admission": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--r8-full-trunk", action="store_true")
    parser.add_argument("--pin", type=Path)
    parser.add_argument("--preflight-receipt", type=Path)
    parser.add_argument("--pve-credential-fd", type=int)
    args = parser.parse_args()
    if args.r8_full_trunk:
        if args.pin is None or args.preflight_receipt is None:
            parser.error("--r8-full-trunk requires --pin and --preflight-receipt")
        try:
            pve_credential_provider = None
            if args.pve_credential_fd is not None:
                pve_credential = pve_credential_from_fd(args.pve_credential_fd)

                def pve_credential_provider():
                    return pve_credential

            print(
                json.dumps(
                    run_r8_full_trunk_live(
                        args.pin,
                        args.preflight_receipt,
                        pve_credential_provider=pve_credential_provider,
                    )
                )
            )
        except (Exception, KeyboardInterrupt) as error:
            print(
                json.dumps(
                    {
                        "status": "r8_full_trunk_failed",
                        "exception_type": type(error).__name__,
                        "pending_retained": bool(
                            R8_LIVE_RUNTIME is not None
                            and os.path.lexists(
                                Path.home()
                                / ".cache/agent-scratch/m7-r8-live"
                                / "brocade-persistence-ledger"
                                / "pending.json"
                            )
                        ),
                        "runtime": (
                            str(R8_LIVE_RUNTIME)
                            if R8_LIVE_RUNTIME is not None
                            else None
                        ),
                        "task_complete": False,
                    }
                )
            )
            return 2
        return 0
    print(
        json.dumps(
            {
                "execution_qualified": False,
                "live_admission": False,
                "forward_commands": len(plan.FORWARD),
                "inverse_commands": len(plan.INVERSE),
                "guest_binding": "parent validator required",
                "total_seconds": TOTAL_SECONDS,
                "inverse_reserve": INVERSE_RESERVE,
                "cleanup_reserve": CLEANUP_RESERVE,
            }
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
