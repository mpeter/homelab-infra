"""Offline fixed serial dispatch, cleanup, deadlines and detached-child fixtures."""

from importlib.util import module_from_spec, spec_from_file_location
from datetime import datetime, timezone
import json
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

PATH = Path(__file__).with_name("native-trunk-resident.py")
spec = spec_from_file_location("resident_candidate", PATH)
assert spec is not None and spec.loader is not None
resident = module_from_spec(spec)
spec.loader.exec_module(resident)


def test_pve_credential_descriptor_is_bounded_and_not_echoed() -> None:
    read_fd, write_fd = os.pipe()
    try:
        os.write(write_fd, b"credential-value\n")
    finally:
        os.close(write_fd)
    assert resident.pve_credential_from_fd(read_fd) == "credential-value"

    read_fd, write_fd = os.pipe()
    try:
        os.write(write_fd, b"bad\nvalue")
    finally:
        os.close(write_fd)
    with pytest.raises(resident.Rejected, match="descriptor rejected"):
        resident.pve_credential_from_fd(read_fd)


def test_r8_operation_budget_preserves_both_proofs_inverse_and_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = [0.0]
    monkeypatch.setattr(resident.time, "monotonic", lambda: clock[0])
    budget = resident.R8OperationBudget()

    clock[0] = (
        budget.deadline
        - resident.INVERSE_RESERVE
        - 2 * resident.R8_PROOF_SECONDS
        - resident.CLEANUP_RESERVE
        - resident.R8_DEADLINE_SLACK
        - 1
    )
    budget.begin_guest_proof()
    clock[0] = (
        budget.deadline
        - resident.INVERSE_RESERVE
        - resident.R8_PROOF_SECONDS
        - resident.CLEANUP_RESERVE
        - 1
    )
    budget.begin_inverse()

    clock[0] = (
        budget.deadline - resident.R8_PROOF_SECONDS - resident.CLEANUP_RESERVE - 1
    )
    budget.begin_guest_proof()
    clock[0] = budget.deadline - resident.CLEANUP_RESERVE - 1
    budget.begin_cleanup()
    budget.check()

    clock[0] = budget.deadline
    with pytest.raises(TimeoutError, match="phase deadline"):
        budget.check()


def test_r8_operation_budget_rejects_forward_when_held_proof_reserve_is_gone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = [0.0]
    monkeypatch.setattr(resident.time, "monotonic", lambda: clock[0])
    budget = resident.R8OperationBudget()
    clock[0] = (
        budget.deadline
        - resident.INVERSE_RESERVE
        - 2 * resident.R8_PROOF_SECONDS
        - resident.CLEANUP_RESERVE
    )
    with pytest.raises(TimeoutError, match="held proof"):
        budget.begin_guest_proof()


def test_r8_inverse_start_cutoff_is_not_reapplied_during_restoration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = [0.0]
    monkeypatch.setattr(resident.time, "monotonic", lambda: clock[0])
    budget = resident.R8OperationBudget()
    inverse_start_cutoff = (
        budget.deadline
        - resident.INVERSE_RESERVE
        - resident.R8_PROOF_SECONDS
        - resident.CLEANUP_RESERVE
    )

    clock[0] = inverse_start_cutoff - 1
    budget.begin_inverse()
    clock[0] = inverse_start_cutoff + 1
    budget.begin_inverse()
    budget.before_inverse_send()
    assert budget.phase == "inverse"


def test_r8_forward_timeout_uses_the_reserved_emergency_inverse_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = [0.0]
    monkeypatch.setattr(resident.time, "monotonic", lambda: clock[0])
    budget = resident.R8OperationBudget()
    inverse_start_cutoff = (
        budget.deadline
        - resident.INVERSE_RESERVE
        - resident.R8_PROOF_SECONDS
        - resident.CLEANUP_RESERVE
    )

    clock[0] = inverse_start_cutoff
    budget.begin_inverse()
    assert budget.phase == "inverse"

    emergency = resident.R8OperationBudget()
    clock[0] = (
        emergency.deadline
        - resident.INVERSE_RESERVE
        - resident.R8_PROOF_SECONDS
        - resident.CLEANUP_RESERVE
        + 1
    )
    emergency.begin_inverse(emergency=True)
    emergency.before_inverse_send()
    assert emergency.phase == "recovery"


def test_r8_preflight_requires_fresh_current_structured_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed = datetime.now(timezone.utc)
    from test_native_trunk_observation import operational, r8_fixture, tables
    from test_port_description import VERSION

    config = r8_fixture()
    cycle = resident.r8_probe.admission.cycle
    monkeypatch.setattr(
        cycle.native_trunk_plan,
        "R8_BASELINE_SHA256",
        cycle.evidence.configuration_hash(config),
    )
    state = (
        resident.r8_probe.admission.cycle.native_trunk_plan.build_r8_full_trunk_plan(
            config, config
        ).initial_state
    )
    observer = resident.r8_observation
    brief_rows = []
    for line in operational(state).splitlines():
        row = line.split()
        if row and row[0] == "1/2/2":
            line = " ".join(
                [*row[:1], "Down", "None", "None", "None", "None", *row[6:]]
            )
        brief_rows.append(line)
    brief = "\n".join(brief_rows)
    observation = {
        "schema": 1,
        "observed_at": observed.isoformat(),
        "completed_at": observed.isoformat(),
        "host": observer.base.bootstrap.HOST,
        "model": "ICX6610-48P",
        "release": observer.base.bootstrap.RELEASE,
        "identity": "homelab_audit",
        "accepted_host_key_fingerprint": observer.base.bootstrap.FINGERPRINT,
        "selected_port": observer.base.PORT,
        "commands": list(observer.base.COMMANDS),
        "expected_execution_environment_sha256": observer.base.collector.EE_DIGEST,
        "source_sha256": dict(observer.base.collector.SOURCE_SHA256),
        "observation_source_sha256": dict(observer.SOURCE_SHA256),
        "raw_capture_sha256": {
            f"capture-{index:02}.txt": "a" * 64
            for index in range(1, len(observer.base.COMMANDS) + 1)
        },
        "responses": {
            "show version": VERSION,
            "show running-config": "\n".join(config),
            "show configuration": "\n".join(config),
            "show interfaces brief": brief,
            "show mac-address": "MAC-Address Port Type Index VLAN",
            f"show interfaces ethernet {observer.base.PORT}": "Port 1/1/47",
        },
        "terminal_boundaries_complete": True,
        "r8_vlan_commands": list(observer.COMMANDS),
        "r8_vlan_tables": {str(vlan): table for vlan, table in tables(state).items()},
        "r8_vlan_capture_sha256": {command: "b" * 64 for command in observer.COMMANDS},
        "r8_vlan_raw_capture_sha256": {
            f"capture-{index:02}.txt": "c" * 64
            for index in range(
                len(observer.base.COMMANDS) + 1,
                len(observer.base.COMMANDS) + len(observer.COMMANDS) + 1,
            )
        },
    }
    receipt = {
        "schema": 2,
        "current_observation": observation,
        "configuration_write_attempted": False,
        "independent_rescue_currently_verified": True,
        "pve_parent_readonly_preflight": {
            "passed": True,
            "active_member": "nic5",
            "usb_management_gateway": "10.72.10.1",
        },
    }
    path = tmp_path / "r8-preflight.json"

    def write(value: dict[str, object]) -> None:
        path.write_text(json.dumps(value))
        path.chmod(0o600)

    write(receipt)
    accepted, digest, raw = resident.validate_r8_preflight(path, now=observed)
    assert accepted == receipt
    assert digest == hashlib.sha256(raw).hexdigest()

    write(
        {
            "schema": 1,
            "observed_at": observed.isoformat(),
            "running_sha256": cycle.native_trunk_plan.R8_BASELINE_SHA256,
            "startup_sha256": cycle.native_trunk_plan.R8_BASELINE_SHA256,
            "six_vlan_tables_semantically_accepted": True,
        }
    )
    with pytest.raises(resident.Rejected, match="current-source R8 observation"):
        resident.validate_r8_preflight(path, now=observed)

    write(receipt)
    naive_observation = {
        **observation,
        "observed_at": observed.replace(tzinfo=None).isoformat(),
    }
    write({**receipt, "current_observation": naive_observation})
    with pytest.raises(resident.Rejected, match="timezone-aware"):
        resident.validate_r8_preflight(path, now=observed)

    write(receipt)
    write({**receipt, "independent_rescue_currently_verified": False})
    with pytest.raises(resident.Rejected, match="structured R8 preflight"):
        resident.validate_r8_preflight(path, now=observed)

    drifted = {**observation, "observation_source_sha256": {"old": "source"}}
    write({**receipt, "current_observation": drifted})
    with pytest.raises(resident.Rejected, match="observation binding mismatch"):
        resident.validate_r8_preflight(path, now=observed)

    changed_tables = dict(observation["r8_vlan_tables"])
    changed_tables["20"] = "PORT-VLAN 20, Name LAB-SERVICES, unexpected members"
    write(
        {
            **receipt,
            "current_observation": {**observation, "r8_vlan_tables": changed_tables},
        }
    )
    with pytest.raises(resident.Rejected, match="semantic admission"):
        resident.validate_r8_preflight(path, now=observed)


def test_read_offset_preserves_split_diagnostic_without_accepting_a_read():
    row = resident.capture.POE_ROWS[0].encode("ascii")
    prefix = b"show running-config\nend\nheadwater#"
    for split in range(1, len(row) + 1):
        before = prefix + row[:split]
        offset = resident.read_offset(before)
        assert offset == len(prefix)
        after = before + row[split:] + b"\n\r"
        assert resident.capture.configuration_progress(
            after[offset:], "startup", 0
        ) == ("wait", ())
        assert resident.capture.configuration_progress(
            after[offset:] + b"show configuration\nver 08.0.30uT7f3\nend\nheadwater#",
            "startup",
            0,
        ) == ("complete", ("ver 08.0.30uT7f3", "end"))
        with pytest.raises(resident.capture.Rejected):
            resident.capture.configuration_progress(
                after[offset:] + b"Access denied\nheadwater#", "startup", 0
            )


@pytest.mark.parametrize(
    "tail", [b"", b"PoE Error: unknown", b"Access denied", b"show configuration"]
)
def test_read_offset_does_not_rewind_unrecognized_output(tail):
    raw = b"headwater#" + tail
    assert resident.read_offset(raw) == len(raw)


# Derived from the 123-artifact held-7 failure: brief offset 48365,
# recovery read offset 50492, with an erased pager and a partial interface row.
FAILED_BRIEF = (
    b"show interfaces brief\r\n\r\n\r"
    b"Port       Link    State   Dupl Speed Trunk Tag Pvid Pri MAC             Name\n\r"
    + resident.capture.PAGER
    + b"\x08 \x08" * len(resident.capture.PAGER)
    + b"1/1/45     Down    None    None None  None  No  1    0   748"
)


FAILED_RUNNING_ECHO = (
    b"show running-conPoE Info: Resetting module in slot 1....completed.\n\r"
    b"PoE Error: Device 0 failed to start on Po"
)


def test_actual_state13_partial_read_echo_waits_without_qualification():
    with pytest.raises(resident.capture.Rejected, match="denial or changed prompt"):
        resident.capture.configuration_progress(FAILED_RUNNING_ECHO, "running", 0)
    assert (
        resident.read_echo_response(FAILED_RUNNING_ECHO, "show running-config") is None
    )
    complete = (
        FAILED_RUNNING_ECHO + b"E module.\n\r"
        b"PoE Error: Device 1 failed to start on PoE module.\n\r"
        b"fig\r\nver 08.0.30uT7f3\r\nend\r\nheadwater#"
    )
    response = resident.read_echo_response(complete, "show running-config")
    assert resident.capture.configuration_progress(response, "running", 0) == (
        "complete",
        ("ver 08.0.30uT7f3", "end"),
    )


def test_runner_waits_for_actual_partial_echo_before_full_read(runner, monkeypatch):
    remainder = b"E module.\n\rfig\r\nver 08.0.30uT7f3\r\nend\r\nheadwater#"

    def append(raw):
        with runner.owned.path.open("ab") as stream:
            stream.write(raw)

    def dispatch(index, steps=None, read=False):
        assert read and tuple(resident.READS)[index] == "running"
        append(FAILED_RUNNING_ECHO)

    sleeps = []

    def receive_remainder(duration):
        sleeps.append(duration)
        assert len(sleeps) == 1
        append(remainder)

    monkeypatch.setattr(runner.controller, "dispatch", dispatch)
    monkeypatch.setattr(resident.time, "sleep", receive_remainder)
    assert runner.read("running", runner.deadline) == ("ver 08.0.30uT7f3", "end")
    assert sleeps == [0.1]
    assert runner.pending_read is None


@pytest.mark.parametrize("command", tuple(resident.READS.values()))
@pytest.mark.parametrize("row", resident.capture.POE_ROWS)
def test_fixed_read_echo_known_rows_at_every_split(command, row):
    body = b"\r\nbody\r\nheadwater#"
    for split in range(1, len(command) + 1):
        echo = command.encode()
        raw = echo[:split] + row.encode() + b"\n\r" + echo[split:] + body
        assert resident.read_echo_response(raw, command) == echo + body


@pytest.mark.parametrize(
    "suffix",
    [
        b"PoE Error: Device 2 failed to start on PoE module.\n\rfig\nend\nheadwater#",
        b"PoE Error: Device 0 failed to start on PoE module. extra\n\rfig\nend\nheadwater#",
        b"PoE Error: Device 0 failed to start on PoE module.\t\n\rfig\nend\nheadwater#",
        b"PoE Error: Device 0 failed to start on PoE module.\x00\n\rfig\nend\nheadwater#",
    ],
)
def test_read_echo_unknown_rows_and_controls_remain_rejected(suffix):
    raw = b"show running-con" + suffix
    assert resident.read_echo_response(raw, "show running-config") == raw
    with pytest.raises(resident.capture.Rejected):
        resident.capture.configuration_progress(raw, "running", 0)


def test_reconstructed_read_retains_prompt_echo_and_pager_checks():
    prefix = b"show running-con" + resident.capture.POE_ROWS[0].encode() + b"\n\r"
    for suffix in (
        b"fig\nver 08.0.30uT7f3\nend\nheadwater(config)#",
        b"figX\nver 08.0.30uT7f3\nend\nheadwater#",
    ):
        response = resident.read_echo_response(prefix + suffix, "show running-config")
        with pytest.raises(resident.capture.Rejected):
            resident.capture.configuration_progress(response, "running", 0)
    erased = resident.capture.PAGER + b"\x08 \x08" * len(resident.capture.PAGER)
    response = resident.read_echo_response(
        prefix + b"fig\n" + erased, "show running-config"
    )
    with pytest.raises(resident.capture.Rejected, match="pager chronology"):
        resident.capture.configuration_progress(response, "running", 0)
    mutation = (
        b"con"
        + resident.capture.POE_ROWS[0].encode()
        + b"\n\rfigure terminal\nheadwater(config)#"
    )
    assert resident.read_echo_response(mutation, "configure terminal") == mutation


@pytest.mark.parametrize("echo_noise", [False, True])
def test_failed_brief_requires_fresh_cancel_before_recovery_read(
    runner, monkeypatch, echo_noise
):
    chronology = []
    clock = [100.0]
    monkeypatch.setattr(resident.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(
        resident.time, "sleep", lambda n: clock.__setitem__(0, clock[0] + n)
    )
    monkeypatch.setattr(resident, "READ_SECONDS", 0.2)
    runner.deadline = 1000

    def append(raw):
        with runner.owned.path.open("ab") as stream:
            stream.write(raw)

    def dispatch(index, steps=None, read=False):
        assert read
        operation = tuple(resident.READS)[index]
        chronology.append(operation)
        if operation == "brief":
            prefix, pager, _ = FAILED_BRIEF.partition(resident.capture.PAGER)
            if echo_noise:
                prefix = prefix.replace(
                    b"show interfaces",
                    b"show inter"
                    + resident.capture.POE_ROWS[0].encode()
                    + b"\n\rfaces",
                )
            append(prefix + pager)
        else:
            append(b"show running-config\nver 08.0.30uT7f3\nend\nheadwater#")

    def cancel(operation, path=None):
        if operation == "page":
            chronology.append("page")
            append(FAILED_BRIEF.partition(resident.capture.PAGER)[2])
            return
        assert operation == "probe"
        chronology.append("cancel")
        append(b"^C\r\nheadwater#")

    monkeypatch.setattr(runner.controller, "dispatch", dispatch)
    monkeypatch.setattr(runner.controller, "command", cancel)
    with pytest.raises(resident.Rejected, match="expired"):
        runner.read("brief", 500)
    assert runner.pending_read == ("brief", 0)
    assert runner.read("running", 500) == ("ver 08.0.30uT7f3", "end")
    assert chronology == ["brief", "page", "cancel", "running"]
    assert runner.pending_read is None
    assert len(list(runner.runtime.glob("event-*-read-cancel.json"))) == 1


@pytest.mark.parametrize(
    "response",
    [
        b"",
        b"headwater#",
        b"^C\nheadwater(config)#",
        b"^C\nAccess denied\nheadwater#",
        b"^C\nheadwater# ",
        b"^C\nheadwater#\t",
        b"^C\nheadwater#\x00",
    ],
)
def test_failed_pager_cancel_never_dispatches_fresh_read(runner, monkeypatch, response):
    runner.owned.path.write_bytes(FAILED_BRIEF + b"headwater#")
    runner.pending_read = ("brief", 0)
    clock = [100.0]
    monkeypatch.setattr(resident.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(
        resident.time, "sleep", lambda n: clock.__setitem__(0, clock[0] + 10)
    )
    runner.deadline = 1000

    def cancel(operation, path=None):
        with runner.owned.path.open("ab") as stream:
            stream.write(response)

    monkeypatch.setattr(runner.controller, "command", cancel)
    with pytest.raises(resident.Rejected, match="expired"):
        runner.read("running", 500)
    assert runner.pending_read is not None
    assert not runner.controller.sent


@pytest.mark.parametrize(
    "raw",
    [
        b"show interfaces brief\npartial row",
        b"unknown command\n" + resident.capture.PAGER,
    ],
)
def test_unrecognized_pending_read_blocks_cancel_and_mutation(runner, monkeypatch, raw):
    runner.owned.path.write_bytes(raw)
    runner.pending_read = ("brief", 0)
    monkeypatch.setattr(
        runner.controller, "command", lambda *args: pytest.fail("cancel dispatched")
    )
    with pytest.raises(resident.Rejected, match="known pager"):
        runner.read("running", runner.deadline)
    with pytest.raises(resident.Rejected, match="unresolved read"):
        runner.send(resident.plan.FORWARD, 0, runner.deadline)
    assert not runner.controller.sent


class Controller:
    def __init__(self, runtime):
        self.runtime = runtime
        self.logging = False
        self.owned = None
        self.sent = []
        self.fail = False

    def state(self):
        fds = {}
        if self.logging:
            assert self.owned is not None
            info = self.owned.path.stat()
            fds["7"] = (
                str(self.owned.path),
                info.st_dev,
                info.st_ino,
                resident.capture.stat.S_IFREG,
            )
        return {
            "owner": "fixed",
            "settings": "fixed",
            "directory": "fixed",
            "socket": "fixed",
            "fds": fds,
            "logging": self.logging,
        }

    def command(self, operation, path=None):
        if operation == "template":
            self.owned = path
        elif operation == "on":
            self.logging = True
        elif operation == "off":
            self.logging = False
        else:
            raise AssertionError(operation)

    def dispatch(self, index, steps=None, read=False):
        self.sent.append((index, read))
        if self.fail:
            raise OSError("uncertain partial dispatch")
        assert not read
        step = steps[index]
        prompt = step.after.replace(r"(?:SSH@)?", "").replace("\\", "")
        assert self.owned is not None
        with self.owned.path.open("ab") as stream:
            stream.write((step.command + "\r\n" + prompt).encode())


@pytest.fixture
def runner(tmp_path):
    tmp_path.chmod(0o700)
    controller = Controller(tmp_path)
    before = controller.state()
    owned = resident.capture.OwnedFile(tmp_path)
    controller.owned, controller.logging = owned, True
    return resident.Runner(
        controller, tmp_path, before, owned, lambda: False, time.monotonic() + 1800
    )


def test_intent_is_durable_before_one_fixed_dispatch(runner, monkeypatch):
    dispatch = runner.controller.dispatch

    def checked(index, steps=None, read=False):
        events = list(runner.runtime.glob("event-*-intent.json"))
        assert len(events) == 1
        assert (
            json.loads(events[0].read_text())["step"]["command"] == "configure terminal"
        )
        assert events[0].stat().st_mode & 0o777 == 0o600
        dispatch(index, steps, read)

    monkeypatch.setattr(runner.controller, "dispatch", checked)
    runner.send(resident.plan.FORWARD, 0, runner.deadline)
    assert runner.controller.sent == [(0, False)]
    assert not runner.unknown
    assert len(list(runner.runtime.glob("event-*-ack.json"))) == 1


def test_failed_intent_prevents_dispatch(runner, monkeypatch):
    monkeypatch.setattr(
        runner, "event", lambda *args: (_ for _ in ()).throw(OSError("fsync failed"))
    )
    with pytest.raises(OSError):
        runner.send(resident.plan.FORWARD, 0, runner.deadline)
    assert not runner.controller.sent


def test_unknown_dispatch_is_permanent_and_retains_intent(runner):
    runner.controller.fail = True
    with pytest.raises(OSError):
        runner.send(resident.plan.FORWARD, 0, runner.deadline)
    with pytest.raises(resident.Rejected, match="no retry"):
        runner.send(resident.plan.FORWARD, 0, runner.deadline)
    assert runner.controller.sent == [(0, False)]
    assert runner.unknown
    assert len(list(runner.runtime.glob("event-*-intent.json"))) == 1


def test_expired_deadline_prevents_intent_and_dispatch(runner):
    with pytest.raises(resident.Rejected, match="deadline"):
        runner.send(resident.plan.FORWARD, 0, time.monotonic() - 1)
    assert not runner.controller.sent
    assert not list(runner.runtime.glob("event-*"))


def test_wrong_ack_stops_without_inverse(runner, monkeypatch):
    def wrong(index, steps=None, read=False):
        runner.controller.sent.append((index, read))
        runner.owned.path.write_bytes(
            b"configure terminal\r\nunknown body\r\nheadwater(config)#"
        )

    monkeypatch.setattr(runner.controller, "dispatch", wrong)
    with pytest.raises(resident.Rejected, match="acknowledgement"):
        runner.send(resident.plan.FORWARD, 0, runner.deadline)
    assert runner.unknown and runner.controller.sent == [(0, False)]


@pytest.mark.parametrize(
    "restored,unknown,clears",
    [(True, False, True), (False, True, False), (False, False, False)],
)
def test_cleanup_does_not_resolve_unknown_switch_state(
    tmp_path, monkeypatch, restored, unknown, clears
):
    tmp_path.chmod(0o700)
    controller = Controller(tmp_path)
    monkeypatch.setattr(resident.capture, "initial", lambda state: None)

    def cycle(self, phase, validator):
        self.unknown = unknown
        return {"restored": restored}

    monkeypatch.setattr(resident.Runner, "cycle", cycle)
    receipt = resident.lifecycle(
        controller, tmp_path, resident.plan.Phase.STANDBY_QUALIFICATION, None
    )
    assert receipt["cleanup_complete"] and not controller.logging
    assert receipt["pending_may_clear"] is clears
    assert json.loads((tmp_path / "receipt.json").read_text()) == receipt


def test_detached_child_survives_launcher_exit(tmp_path):
    # Launch a fake cycle in a separate interpreter; no SCREEN, SSH or network.
    script = """
from importlib.util import spec_from_file_location,module_from_spec
from pathlib import Path
import json,os,time
spec=spec_from_file_location('fixture', %r);m=module_from_spec(spec);spec.loader.exec_module(m)
r=Path(%r)
m.capture.PENDING_PATH=r/'pending.json'
m.capture.capture_lock=lambda:os.open(r/'lock',os.O_WRONLY|os.O_CREAT,0o600)
def cycle(*args, **kwargs):
 time.sleep(.2)
 (r/'child-finished').write_text(str(os.getpid()))
 return {'pending_may_clear':False}
m.lifecycle=cycle
m.Controller=lambda:None
m.tempfile.mkdtemp=lambda **kw:str(r/'child')
(r/'child').mkdir(mode=0o700)
print(json.dumps(m.launch_candidate(m.plan.Phase.STANDBY_QUALIFICATION,None)))
""" % (str(PATH), str(tmp_path))
    launcher = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, timeout=5
    )
    assert launcher.returncode == 0, launcher.stderr
    result = json.loads(launcher.stdout)
    until = time.monotonic() + 5
    while not (tmp_path / "child-finished").exists() and time.monotonic() < until:
        time.sleep(0.02)
    assert (tmp_path / "child-finished").read_text() == str(result["pid"])
    assert (tmp_path / "pending.json").exists()


def test_candidate_cli_is_preparation_only():
    result = subprocess.run(
        [sys.executable, str(PATH), "--check"],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0, result.stderr
    status = json.loads(result.stdout)
    assert not status["live_admission"] and not status["execution_qualified"]
    assert status["forward_commands"] == 41 and status["inverse_commands"] == 29
    assert resident.INVERSE_RESERVE + resident.CLEANUP_RESERVE < resident.TOTAL_SECONDS


def test_r8_cli_returns_failure_status_when_preflight_is_rejected():
    result = subprocess.run(
        [
            sys.executable,
            str(PATH),
            "--r8-full-trunk",
            "--pin",
            "/missing/brocade-known-hosts",
            "--preflight-receipt",
            "/missing/r8-preflight.json",
        ],
        input="{}\n",
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 2
    assert json.loads(result.stdout)["status"] == "r8_full_trunk_failed"


def test_successful_command_cannot_be_repeated_or_skipped(runner):
    runner.send(resident.plan.FORWARD, 0, runner.deadline)
    for index in (0, 2):
        with pytest.raises(resident.Rejected, match="order"):
            runner.send(resident.plan.FORWARD, index, runner.deadline)
    assert runner.controller.sent == [(0, False)]


def test_forward_cutoff_reserves_inverse_and_cleanup(runner, monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(resident.time, "monotonic", lambda: clock[0])
    runner.deadline = 100.0 + resident.TOTAL_SECONDS
    cutoff = runner.deadline - resident.INVERSE_RESERVE - resident.CLEANUP_RESERVE
    clock[0] = cutoff
    with pytest.raises(resident.Rejected, match="deadline"):
        runner.send(resident.plan.FORWARD, 0, cutoff)
    assert (
        runner.deadline - clock[0]
        == resident.INVERSE_RESERVE + resident.CLEANUP_RESERVE
    )
    assert not runner.controller.sent


@pytest.mark.parametrize("phase", list(resident.plan.Phase))
@pytest.mark.parametrize("diagnostic_failure", (False, True))
def test_fixed_cycle_boundary_guest_binding_and_original_reserve(
    runner, monkeypatch, phase, diagnostic_failure
):
    clock = [100.0]
    monkeypatch.setattr(resident.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(
        resident.time,
        "sleep",
        lambda duration: clock.__setitem__(0, clock[0] + duration),
    )
    runner.deadline = 100 + resident.TOTAL_SECONDS
    guarded_times = []
    original_guard = runner.guard

    def recorded_guard(cutoff):
        guarded_times.append((clock[0], cutoff))
        original_guard(cutoff)

    monkeypatch.setattr(runner, "guard", recorded_guard)
    monkeypatch.setattr(
        resident.capture, "qualify_cancel", lambda *args: b"^C\r\nheadwater#"
    )
    monkeypatch.setattr(resident.native, "build_plan", lambda *args: None)
    runner.last_brief = ""
    chronology = []
    monkeypatch.setattr(
        resident.observation,
        "require_settled_native_phase",
        lambda *args, **kwargs: chronology.append("settled"),
    )

    failed_span = False

    def read(operation, cutoff):
        nonlocal failed_span
        if operation == "span":
            chronology.append("span")
            if diagnostic_failure and "settled" in chronology and not failed_span:
                failed_span = True
                with runner.owned.path.open("ab") as stream:
                    stream.write(
                        b"lot 1....completed.\r\nshow span vlan 1\r\nheadwater#"
                    )
                raise resident.Rejected("read echo or prompt boundary")
        return ("baseline",)

    monkeypatch.setattr(runner, "read", read)
    observations = []

    def observe(baseline, startup, completed, cutoff, inverse=False):
        chronology.append("semantic")
        observations.append((completed, inverse, clock[0], cutoff))
        return resident.observation.Observation(
            resident.native.expected_state(completed, inverse=inverse), "a", "b", "a"
        )

    monkeypatch.setattr(runner, "observe", observe)
    binding = []

    def validator(state, artifact):
        assert artifact == {"prepared": True}
        assert state.state == resident.native.expected_state(7)
        assert not any(
            "1/2/2" in json.loads(p.read_text())["step"]["command"]
            for p in runner.runtime.glob("event-*-intent.json")
        )
        binding.append(state)
        return "a" * 64

    monkeypatch.setattr(
        runner, "wait_guest_proof", lambda state, cutoff: {"prepared": True}
    )
    result = runner.cycle(phase, validator)
    assert result["restored"]
    assert failed_span is diagnostic_failure
    assert len(list(runner.runtime.glob("event-*-diagnostic-failure.json"))) == int(
        diagnostic_failure
    )
    for index, item in enumerate(chronology):
        if item == "settled":
            assert chronology[index - 1] == "semantic"
            assert chronology[index + 1] == "span"
    assert runner.deadline == 100 + resident.TOTAL_SECONDS
    held = [o for o in observations if o[0] == 7 and not o[1]]
    assert held[0][2] >= 100 + resident.native.MIN_SETTLE_SECONDS
    assert any(
        now < 100 + resident.native.MIN_SETTLE_SECONDS
        and cutoff == 100 + resident.native.MAX_FORWARD_SECONDS
        for now, cutoff in guarded_times
    )
    intents = [
        json.loads(p.read_text())
        for p in sorted(runner.runtime.glob("event-*-intent.json"))
    ]
    commands = [p["step"]["command"] for p in intents]
    if phase is resident.plan.Phase.STANDBY_QUALIFICATION:
        assert not binding
        assert not any("1/2/2" in c or "1/3/1" in c for c in commands)
        assert commands == [
            s.command for s in resident.plan.FORWARD[: resident.plan.STANDBY_END]
        ] + [s.command for s in resident.plan.inverse_for(7)]
    else:
        assert len(list(runner.runtime.glob("event-*-guest-binding.json"))) == 1
        assert commands == [s.command for s in resident.plan.FORWARD] + [
            s.command for s in resident.plan.INVERSE
        ]
    assert all(
        o[3] <= runner.deadline - resident.INVERSE_RESERVE - resident.CLEANUP_RESERVE
        for o in observations
        if not o[1] and o[0] != 0
    )


def test_invalid_guest_binding_prevents_primary_and_preserves_known_state(
    runner, monkeypatch
):
    monkeypatch.setattr(resident.capture, "qualify_cancel", lambda *args: b"")
    monkeypatch.setattr(resident.native, "build_plan", lambda *args: None)
    runner.last_brief = ""
    monkeypatch.setattr(
        resident.observation,
        "require_settled_native_phase",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(resident.native, "MIN_SETTLE_SECONDS", 0)
    monkeypatch.setattr(runner, "read", lambda operation, cutoff: ())
    monkeypatch.setattr(
        runner,
        "observe",
        lambda *args, **kw: resident.observation.Observation(
            resident.native.expected_state(7), "a", "b", "a"
        ),
    )
    monkeypatch.setattr(runner, "wait_guest_proof", lambda state, cutoff: {})
    with pytest.raises(resident.Rejected, match="guest qualification"):
        runner.cycle(resident.plan.Phase.REMAINING_TRUNK, lambda state, artifact: None)
    intents = [
        json.loads(p.read_text())["step"]["command"]
        for p in runner.runtime.glob("event-*-intent.json")
    ]
    assert not any("1/2/2" in c or "1/3/1" in c for c in intents)
    assert len(intents) == resident.plan.STANDBY_END
    assert not runner.unknown


def test_dependency_drift_fails_before_lifecycle_dispatch(tmp_path, monkeypatch):
    key = next(iter(resident.SOURCE_PINS))
    monkeypatch.setitem(resident.SOURCE_PINS, key, "0" * 64)
    controller = Controller(tmp_path)
    with pytest.raises(RuntimeError, match="dependency drift"):
        resident.lifecycle(
            controller, tmp_path, resident.plan.Phase.STANDBY_QUALIFICATION, None
        )
    assert not controller.sent and not controller.logging


def test_invalid_phase_rejects_before_logging_or_serial(tmp_path):
    controller = Controller(tmp_path)
    with pytest.raises(resident.Rejected, match="phase"):
        resident.lifecycle(controller, tmp_path, "arbitrary", None)
    assert not controller.logging and not controller.sent
    assert not list(tmp_path.iterdir())


def test_blocking_validator_is_killed_before_recovery_reserve(monkeypatch):
    monkeypatch.setattr(resident, "VALIDATOR_SECONDS", 0.1)
    started = time.monotonic()

    def blocked(state):
        time.sleep(60)
        return "a" * 64

    cutoff = started + 5
    with pytest.raises(resident.Rejected, match="validator deadline"):
        resident.validate_guest_binding(blocked, None, cutoff)
    assert time.monotonic() - started < 2


def test_validator_hash_contract_and_failure():
    assert (
        resident.validate_guest_binding(
            lambda state: "a" * 64, None, time.monotonic() + 2
        )
        == "a" * 64
    )
    with pytest.raises(resident.Rejected, match="qualification"):
        resident.validate_guest_binding(
            lambda state: "not a hash", None, time.monotonic() + 2
        )


def test_late_native_observation_cannot_authorize_primary(runner, monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(resident.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(
        resident.time,
        "sleep",
        lambda duration: clock.__setitem__(0, clock[0] + duration),
    )
    monkeypatch.setattr(resident.capture, "qualify_cancel", lambda *args: b"")
    monkeypatch.setattr(resident.native, "build_plan", lambda *args: None)
    monkeypatch.setattr(runner, "read", lambda operation, cutoff: ())
    runner.deadline = 100 + resident.TOTAL_SECONDS

    def delayed(baseline, startup, completed, cutoff, inverse=False):
        if completed == 7:
            assert cutoff == 100 + resident.native.MAX_FORWARD_SECONDS
            clock[0] = cutoff + 1
        return resident.observation.Observation(
            resident.native.expected_state(completed), "a", "b", "a"
        )

    monkeypatch.setattr(runner, "observe", delayed)
    with pytest.raises(resident.Rejected, match="deadline"):
        runner.cycle(resident.plan.Phase.REMAINING_TRUNK, lambda state: "a" * 64)
    commands = [
        json.loads(p.read_text())["step"]["command"]
        for p in runner.runtime.glob("event-*-intent.json")
    ]
    assert len(commands) == resident.plan.STANDBY_END
    assert not any("1/2/2" in command for command in commands)


def test_import_time_source_manifest_is_fully_pinned():
    guest_generator = resident.r8_probe.guest_producer.r8_guest_generator
    cycle_sources = resident.plan.base.cycle.SOURCE_PATHS
    resident_path = (
        resident.ROOT / "network/config-backup-preflight/native-trunk-resident.py"
    ).resolve()
    assert cycle_sources["native_trunk_resident"].resolve() == resident_path
    assert (
        hashlib.sha256(resident_path.read_bytes()).hexdigest() == resident.SELF_SHA256
    )
    required = {
        str(path.resolve().relative_to(resident.ROOT))
        for name, path in cycle_sources.items()
        if name != "native_trunk_resident"
    }
    dynamically_bound = {"ansible/network-jobs/empty_vlan_cycle.py"}
    guest_artifacts = {
        "ansible/network-jobs/r8-guest-traffic/run.py",
        "ansible/network-jobs/r8-guest-traffic/guest.py",
        "ansible/network-jobs/r8-guest-traffic/required-host-known_hosts",
    }
    assert required - dynamically_bound - guest_artifacts <= resident.SOURCE_PINS.keys()
    guest_root = resident.ROOT / "ansible/network-jobs/r8-guest-traffic"
    guest_artifact_pins = {
        "run.py": "run.py",
        "guest.py": "guest.py",
        "required-host-known_hosts": "required-host-known_hosts",
    }
    for name, pin_name in guest_artifact_pins.items():
        assert (
            hashlib.sha256((guest_root / name).read_bytes()).hexdigest()
            == guest_generator.SOURCE_PINS[pin_name]
        )
    cycle_path = resident.ROOT / "ansible/network-jobs/empty_vlan_cycle.py"
    assert (
        hashlib.sha256(cycle_path.read_bytes()).hexdigest()
        == (resident.plan.base.cycle.SOURCE_MANIFEST["empty_vlan_cycle"])
    )


def test_exact_pinned_stage_imports_without_repository_fallback(tmp_path):
    for relative in resident.SOURCE_PINS:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((resident.ROOT / relative).read_bytes())
    for name, source in resident.plan.base.cycle.SOURCE_PATHS.items():
        if name == "native_trunk_resident":
            continue
        relative = source.resolve().relative_to(resident.ROOT)
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
    staged = tmp_path / PATH.relative_to(resident.ROOT)
    staged.write_bytes(PATH.read_bytes())
    result = subprocess.run(
        [sys.executable, "-I", str(staged), "--check"],
        cwd=tmp_path,
        capture_output=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stderr.decode()
    report = json.loads(result.stdout)
    assert report["live_admission"] is False
    assert report["execution_qualified"] is False


@pytest.mark.parametrize("outer_cutoff,expected", [(1000, 150), (130, 130)])
def test_semantic_observation_has_shared_budget_and_retains_all_gates(
    runner, monkeypatch, outer_cutoff, expected
):
    clock = [100.0]
    monkeypatch.setattr(resident.time, "monotonic", lambda: clock[0])
    runner.baseline_tables = {1: "one", 132: "legacy"}
    state = resident.observation.Observation(
        resident.native.expected_state(7), "a", "b", "a"
    )
    monkeypatch.setattr(
        resident.observation, "classify_observation", lambda *args: state
    )
    calls = []
    for name in ("require_state", "require_operational_state", "require_membership"):
        monkeypatch.setattr(
            resident.observation,
            name,
            lambda *args, _name=name, **kwargs: calls.append(_name),
        )
    reads = []

    def read(operation, cutoff):
        reads.append((operation, cutoff))
        clock[0] += 1
        return (operation,)

    monkeypatch.setattr(runner, "read", read)
    assert runner.observe((), (), 7, outer_cutoff) == state
    assert reads == [
        (op, expected)
        for op in (
            "running",
            "brief",
            "vlan1",
            "vlan10",
            "vlan20",
            "vlan30",
            "vlan40",
            "vlan132",
        )
    ]
    assert calls == ["require_state", "require_membership", "require_operational_state"]
    event = json.loads(next(runner.runtime.glob("event-*-state.json")).read_text())
    assert event["elapsed_seconds"] == 8
    assert event["cutoff"] == expected


def test_semantic_observation_rejects_late_final_table(runner, monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(resident.time, "monotonic", lambda: clock[0])
    runner.baseline_tables = {1: "one", 132: "legacy"}
    state = resident.observation.Observation(
        resident.native.expected_state(7), "a", "b", "a"
    )
    monkeypatch.setattr(
        resident.observation, "classify_observation", lambda *args: state
    )
    for name in ("require_state", "require_operational_state", "require_membership"):
        monkeypatch.setattr(resident.observation, name, lambda *args, **kwargs: None)

    def read(operation, cutoff):
        if operation == "vlan132":
            clock[0] = cutoff + 0.01
        return (operation,)

    monkeypatch.setattr(runner, "read", read)
    with pytest.raises(resident.Rejected, match="deadline"):
        runner.observe((), (), 7, 1000)
    assert not list(runner.runtime.glob("event-*-state.json"))


def test_actual_read_records_elapsed_and_rejects_late_response(runner, monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(resident.time, "monotonic", lambda: clock[0])

    def dispatch(index, steps=None, read=False):
        assert read and resident.READS["vlan10"] == "show vlan 10"
        clock[0] += 2.5
        with runner.owned.path.open("ab") as out:
            out.write(b"show vlan 10\r\nNo such VLAN\r\nheadwater#")

    monkeypatch.setattr(runner.controller, "dispatch", dispatch)
    assert runner.read("vlan10", 110) == ("No such VLAN",)
    event = json.loads(next(runner.runtime.glob("event-*-read.json")).read_text())
    assert event["elapsed_seconds"] == 2.5
    with pytest.raises(resident.Rejected, match="expired"):
        runner.read("vlan10", 104)
    assert len(list(runner.runtime.glob("event-*-read.json"))) == 1


@pytest.mark.parametrize("index", range(len(resident.plan.inverse_for(7))))
def test_exact_known_noise_attached_to_expected_inverse_prompt(runner, index):
    steps = resident.plan.inverse_for(7)
    step = steps[index]
    prompt = step.after.replace(r"(?:SSH@)?", "").replace("\\", "")
    raw = (
        step.command + "\r\n\r" + prompt + resident.capture.POE_ROWS[0] + "\n\r"
    ).encode()
    assert resident.acknowledgement_lines(raw, step.after) == [step.command, prompt]


def test_attached_noise_does_not_accept_wrong_mode_or_partial_noise():
    expected = resident.plan.inverse_for(7)[0].after
    row = resident.capture.POE_ROWS[0]
    for suffix in (row[:-1], row + "extra", "Unknown asynchronous output"):
        raw = ("configure terminal\r\nheadwater(config)#" + suffix).encode()
        assert resident.acknowledgement_lines(raw, expected)[-1] != "headwater(config)#"
    wrong = ("configure terminal\r\nheadwater(config-vlan-10)#" + row).encode()
    assert resident.acknowledgement_lines(wrong, expected)[-1] != "headwater(config)#"


def test_actual_config_prompt_attached_noise_completes_one_send(runner, monkeypatch):
    original_dispatch = runner.controller.dispatch

    def dispatch(index, steps=None, read=False):
        original_dispatch(index, steps=steps, read=read)
        with runner.owned.path.open("ab") as stream:
            stream.write((resident.capture.POE_ROWS[0] + "\n\r").encode())

    monkeypatch.setattr(runner.controller, "dispatch", dispatch)
    steps = resident.plan.inverse_for(7)
    runner.send(steps, 0, time.monotonic() + 5)
    assert runner.next_index == 1
    assert runner.unknown is False
    assert runner.controller.sent == [(0, False)]


def test_actual_span_pre_echo_fragment_is_unqualified_diagnostic(runner, monkeypatch):
    def dispatch(index, steps=None, read=False):
        assert read and resident.READS["span"] == list(resident.READS.values())[index]
        with runner.owned.path.open("ab") as stream:
            stream.write(
                b"lot 1....completed.\r\nshow span vlan 1\r\nSTP instance owned by VLAN 1\r\nheadwater#"
            )

    monkeypatch.setattr(runner.controller, "dispatch", dispatch)
    assert runner.diagnostic_span(time.monotonic() + 5) is None
    event = json.loads(
        next(runner.runtime.glob("event-*-diagnostic-failure.json")).read_text()
    )
    assert event["exact_exec_observed"] is True
    assert event["span_parser_qualified"] is False
    assert runner.unknown is False


@pytest.mark.parametrize(
    "suffix", (b"headwater(config)#", b"login:", resident.capture.PAGER, b"unknown")
)
def test_failed_diagnostic_requires_latest_exact_exec(runner, monkeypatch, suffix):
    def read(operation, cutoff):
        with runner.owned.path.open("ab") as stream:
            stream.write(b"headwater#\r\n" + suffix)
        raise resident.Rejected("read echo or prompt boundary")

    monkeypatch.setattr(runner, "read", read)
    with pytest.raises(resident.Rejected, match="exact EXEC"):
        runner.diagnostic_span(time.monotonic() + 5)
    assert not list(runner.runtime.glob("event-*-diagnostic-failure.json"))


@pytest.mark.parametrize(
    "failure",
    (
        "serial logging custody lost",
        "prefix observation interrupted or expired",
        "capture prefix rewrite, shrink or custody change",
    ),
)
def test_core_diagnostic_guard_failures_remain_terminal(runner, monkeypatch, failure):
    def read(operation, cutoff):
        raise resident.Rejected(failure)

    monkeypatch.setattr(runner, "read", read)
    with pytest.raises(resident.Rejected, match=failure):
        runner.diagnostic_span(time.monotonic() + 5)
    assert not list(runner.runtime.glob("event-*-diagnostic-failure.json"))


def test_unknown_command_forbids_diagnostic_continuation(runner):
    runner.unknown = True
    with pytest.raises(resident.Rejected, match="unknown serial outcome"):
        runner.diagnostic_span(time.monotonic() + 5)
    assert not runner.controller.sent


def test_rendezvous_publishes_unique_runtime_and_accepts_only_bound_private_artifact(
    runner, monkeypatch
):
    state = resident.observation.Observation(
        resident.native.expected_state(7), "a", "b", "a"
    )
    slept = []

    def deliver(duration):
        slept.append(duration)
        context = json.loads((runner.runtime / "held-state.json").read_text())
        assert context["runner"]["pid"] == resident.os.getpid()
        assert context["runner"]["starttime"] == resident.capture.process_starttime(
            resident.os.getpid()
        )
        assert context["resident_sha256"] == resident.SELF_SHA256
        assert len(context["nonce"]) == 64
        resident.capture.private_json(
            runner.runtime / "guest-proof.json",
            {"context": context, "proof": {"status": "passed"}},
        )

    monkeypatch.setattr(resident.time, "sleep", deliver)
    result = runner.wait_guest_proof(state, resident.time.monotonic() + 1000)
    assert result["proof"]["status"] == "passed"
    assert len(slept) == 1


@pytest.mark.parametrize(
    "defect", ["nonce", "mode", "symlink", "oversize", "older", "keys"]
)
def test_rendezvous_rejects_stale_or_unowned_artifact(runner, monkeypatch, defect):
    state = resident.observation.Observation(
        resident.native.expected_state(7), "a", "b", "a"
    )

    def deliver(duration):
        held = runner.runtime / "held-state.json"
        context = json.loads(held.read_text())
        if defect == "nonce":
            context["nonce"] = "0" * 64
        artifact = {"context": context, "proof": {}}
        if defect == "keys":
            artifact["extra"] = True
        path = runner.runtime / "guest-proof.json"
        resident.capture.private_json(path, artifact)
        if defect == "mode":
            path.chmod(0o644)
        if defect == "symlink":
            target = runner.runtime / "other.json"
            path.rename(target)
            path.symlink_to(target)
        if defect == "oversize":
            path.write_bytes(b"x" * 65537)
        if defect == "older":
            resident.os.utime(path, ns=(1, 1))

    monkeypatch.setattr(resident.time, "sleep", deliver)
    with pytest.raises((resident.Rejected, OSError)):
        runner.wait_guest_proof(state, resident.time.monotonic() + 1000)


def test_rendezvous_timeout_is_unresolved_and_does_not_assume_watchdog_restore(
    runner, monkeypatch
):
    clock = [100.0]
    monkeypatch.setattr(resident.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(
        resident.time,
        "sleep",
        lambda duration: clock.__setitem__(0, clock[0] + duration),
    )
    runner.deadline = 1900
    state = resident.observation.Observation(
        resident.native.expected_state(7), "a", "b", "a"
    )
    with pytest.raises(resident.Rejected, match="restoration unresolved") as error:
        runner.wait_guest_proof(state, 1280)
    assert not isinstance(error.value, resident.GuestProofRejected)
    assert clock[0] == pytest.approx(100 + resident.PROOF_SECONDS)


def test_insufficient_proof_budget_rejects_before_publishing_job_authority(runner):
    state = resident.observation.Observation(
        resident.native.expected_state(7), "a", "b", "a"
    )
    with pytest.raises(resident.GuestProofRejected, match="insufficient"):
        runner.wait_guest_proof(state, resident.time.monotonic() + 100)
    assert not (runner.runtime / "held-state.json").exists()


def test_validated_restored_host_rejection_reaches_exact_standby_inverse(
    runner, monkeypatch
):
    runner.last_brief = ""
    monkeypatch.setattr(resident.capture, "qualify_cancel", lambda *args: b"")
    monkeypatch.setattr(resident.native, "build_plan", lambda *args: None)
    monkeypatch.setattr(resident.native, "MIN_SETTLE_SECONDS", 0)
    monkeypatch.setattr(
        resident.observation, "require_settled_native_phase", lambda *args, **kw: None
    )
    monkeypatch.setattr(runner, "read", lambda *args: ())
    observations = []

    def observe(baseline, startup, completed, cutoff, inverse=False):
        observations.append(completed)
        return resident.observation.Observation(
            resident.native.expected_state(completed), "a", "b", "a"
        )

    monkeypatch.setattr(runner, "observe", observe)
    monkeypatch.setattr(runner, "wait_guest_proof", lambda *args: {"proof": "restored"})

    def reject(state, artifact):
        assert artifact == {"proof": "restored"}
        raise resident.GuestProofRejected(
            "actual selector terminal/restored host rejected"
        )

    result = runner.cycle(resident.plan.Phase.REMAINING_TRUNK, reject)
    commands = [
        json.loads(p.read_text())["step"]["command"]
        for p in sorted(runner.runtime.glob("event-*-intent.json"))
    ]
    assert commands == [
        s.command for s in resident.plan.FORWARD[: resident.plan.STANDBY_END]
    ] + [s.command for s in resident.plan.inverse_for(7)]
    assert observations == [0, 7, 7, 0]
    assert result["restored"] and result["guest_proof_failure"]
    assert (
        not result["guest_proof_authority_bound"] and not result["qualification_passed"]
    )


def test_post_proof_semantic_failure_preserves_pending_and_prevents_inverse(
    runner, monkeypatch
):
    runner.last_brief = ""
    monkeypatch.setattr(resident.capture, "qualify_cancel", lambda *args: b"")
    monkeypatch.setattr(resident.native, "build_plan", lambda *args: None)
    monkeypatch.setattr(resident.native, "MIN_SETTLE_SECONDS", 0)
    monkeypatch.setattr(
        resident.observation, "require_settled_native_phase", lambda *args, **kw: None
    )
    monkeypatch.setattr(runner, "read", lambda *args: ())
    monkeypatch.setattr(runner, "wait_guest_proof", lambda *args: {})
    count = [0]

    def observe(*args, **kw):
        count[0] += 1
        if count[0] == 3:
            raise resident.Rejected("fresh semantic drift")
        return resident.observation.Observation(
            resident.native.expected_state(7), "a", "b", "a"
        )

    monkeypatch.setattr(runner, "observe", observe)
    with pytest.raises(resident.Rejected, match="fresh semantic drift"):
        runner.cycle(resident.plan.Phase.REMAINING_TRUNK, lambda *args: "a" * 64)
    assert (
        len(list(runner.runtime.glob("event-*-intent.json")))
        == resident.plan.STANDBY_END
    )


# Actual V2 postinverse VLAN30 echo: only the read was interrupted by PoE output.
READ_NOISE = (
    b"show vlan 3Resetting module in slot 1 again to recover from dev fault\n\r"
    b"PoE Info: Hard Resetting in slot 1....\n\r0\r\n\r"
    b"Error - port-vlan 30 does not exist.\n\rheadwater#"
)


def test_actual_postinverse_noise_is_evidence_for_one_fresh_read_only():
    assert resident.known_read_noise("vlan30", READ_NOISE)


@pytest.mark.parametrize(
    "raw",
    [
        READ_NOISE.replace(b"dev fault", b"unknown fault"),
        READ_NOISE.replace(b"headwater#", b"headwater(config)#"),
        READ_NOISE + b"\nlogin:",
        READ_NOISE + resident.capture.PAGER,
        b"show vlan 30\nError - port-vlan 30 does not exist.\nheadwater#",
    ],
)
def test_unqualified_read_failure_cannot_authorize_reobservation(raw):
    assert not resident.known_read_noise("vlan30", raw)


def test_postinverse_reobserve_retains_original_cutoff_and_is_once(monkeypatch):
    runner = object.__new__(resident.Runner)
    runner.unknown = False
    calls = []
    monkeypatch.setattr(resident.time, "monotonic", lambda: 100)
    runner.guard = lambda cutoff: calls.append(("guard", cutoff))
    runner.checkpoint = lambda cutoff: READ_NOISE
    runner.event = lambda *args: None

    def observe(*args):
        calls.append(("observe", args[3]))
        if sum(item[0] == "observe" for item in calls) == 1:
            runner.failed_read = ("vlan30", READ_NOISE)
            raise resident.Rejected("read echo or prompt boundary")
        return "strictly-verified-baseline"

    runner.observe = observe
    assert runner.observe_restored((), (), 0, 130) == "strictly-verified-baseline"
    assert [item[1] for item in calls if item[0] == "observe"] == [130, 130]


def test_second_read_failure_and_unknown_configuration_stay_terminal():
    runner = object.__new__(resident.Runner)
    runner.unknown = False
    runner.guard = lambda cutoff: None
    runner.checkpoint = lambda cutoff: READ_NOISE
    runner.event = lambda *args: None
    calls = []

    def reject(*args):
        calls.append(args)
        runner.failed_read = ("vlan30", READ_NOISE)
        raise resident.Rejected("read echo or prompt boundary")

    runner.observe = reject
    with pytest.raises(resident.Rejected):
        runner.observe_restored((), (), 0, time.monotonic() + 50)
    assert len(calls) == 2
    runner.postinverse_reobserved = False
    runner.unknown = True
    calls.clear()
    with pytest.raises(resident.Rejected):
        runner.observe_restored((), (), 0, time.monotonic() + 50)
    assert len(calls) == 1


def prepare_cycle(runner, monkeypatch):
    runner.last_brief = ""
    monkeypatch.setattr(resident.capture, "qualify_cancel", lambda *args: b"")
    monkeypatch.setattr(resident.native, "build_plan", lambda *args: None)
    monkeypatch.setattr(resident.native, "MIN_SETTLE_SECONDS", 0)
    monkeypatch.setattr(
        resident.observation, "require_settled_native_phase", lambda *args, **kw: None
    )
    monkeypatch.setattr(runner, "read", lambda *args: ())
    monkeypatch.setattr(runner, "diagnostic_span", lambda *args: None)
    monkeypatch.setattr(runner, "wait_guest_proof", lambda *args: {})
    monkeypatch.setattr(resident, "validate_guest_binding", lambda *args: "a" * 64)


@pytest.mark.parametrize("completed", (7, 13, 19, 35))
def test_acknowledged_carrier_failure_uses_exact_bounded_inverse(
    runner, monkeypatch, completed
):
    prepare_cycle(runner, monkeypatch)
    observations = []

    def observe(baseline, startup, current, cutoff, inverse=False):
        observations.append((current, inverse))
        if current == completed and not getattr(runner, "recovering", False):
            raise resident.CarrierRejected("primary carrier down at exact native state")
        return resident.observation.Observation(
            resident.native.expected_state(current, inverse=inverse), "a", "b", "a"
        )

    monkeypatch.setattr(runner, "observe", observe)
    result = runner.cycle(resident.plan.Phase.REMAINING_TRUNK, lambda *args: "a" * 64)
    boundary = next(
        i + 1
        for i, step in enumerate(resident.plan.FORWARD)
        if step.completed == completed and step.observe
    )
    commands = [
        json.loads(p.read_text())["step"]["command"]
        for p in sorted(runner.runtime.glob("event-*-intent.json"))
    ]
    assert commands == [s.command for s in resident.plan.FORWARD[:boundary]] + [
        s.command for s in resident.plan.inverse_for(completed)
    ]
    assert result["restored"] and result["forward_failure"]
    assert not result["qualification_passed"]
    assert not result["execution_qualified"] and not result["live_admission"]
    assert not runner.unknown
    assert observations[-1] == ((23, True) if completed == 35 else (0, False))
    assert list(runner.runtime.glob("event-*-restored.json"))


def test_unknown_command_at_primary_boundary_never_replays_inverse(runner, monkeypatch):
    prepare_cycle(runner, monkeypatch)
    monkeypatch.setattr(
        runner,
        "observe",
        lambda *args, **kw: resident.observation.Observation(
            resident.native.expected_state(7), "a", "b", "a"
        ),
    )
    dispatch = runner.controller.dispatch

    def fail(index, steps=None, read=False):
        if (
            steps is resident.plan.FORWARD
            and steps[index].command == "dual-mode 1"
            and steps[index].completed == 12
        ):
            runner.controller.sent.append((index, read))
            raise OSError("partial primary dispatch")
        dispatch(index, steps, read)

    monkeypatch.setattr(runner.controller, "dispatch", fail)
    with pytest.raises(OSError, match="partial"):
        runner.cycle(resident.plan.Phase.REMAINING_TRUNK, lambda *args: "a" * 64)
    assert runner.unknown
    commands = [
        json.loads(p.read_text())["step"]["command"]
        for p in runner.runtime.glob("event-*-intent.json")
    ]
    assert not any(command.startswith("no ") for command in commands)
    assert not list(runner.runtime.glob("event-*-restored.json"))


def test_actual_primary_down_row_requires_exact_configuration_and_membership(
    runner, monkeypatch
):
    from test_native_trunk_observation import BASELINE, operational, running, tables
    from test_bond_vlan_membership import AFTER1, AFTER132

    state = resident.native.expected_state(13)
    runner.baseline_tables = {1: AFTER1, 132: AFTER132}
    responses = {
        "running": running(state, BASELINE),
        **{
            f"vlan{vlan}": tuple(text.splitlines())
            for vlan, text in tables(state).items()
        },
    }
    rows = []
    for line in operational(state).splitlines():
        words = line.split()
        if words and words[0] == "1/2/2":
            words[1:5] = ["Down", "None", "None", "None"]
            line = " ".join(words)
        rows.append(line)
    responses["brief"] = tuple(rows)
    monkeypatch.setattr(runner, "read", lambda op, cutoff: responses[op])
    monkeypatch.setattr(
        resident.observation,
        "classify_observation",
        lambda baseline, current, startup: resident.observation._classify_observation(
            baseline,
            current,
            startup,
            baseline_sha256=resident.observation.evidence.configuration_hash(baseline),
        ),
    )
    with pytest.raises(resident.CarrierRejected):
        runner.observe(BASELINE, BASELINE, 13, runner.deadline)
    responses["vlan10"] = ("unknown membership",)
    with pytest.raises(resident.observation.evidence.Rejected):
        runner.observe(BASELINE, BASELINE, 13, runner.deadline)
    responses["vlan10"] = tuple(tables(state)[10].splitlines())
    responses["running"] = (
        *responses["running"][:-1],
        "unexpected configuration",
        "end",
    )
    with pytest.raises(resident.observation.evidence.Rejected):
        runner.observe(BASELINE, BASELINE, 13, runner.deadline)
    runner.recovering = True
    responses["running"] = BASELINE
    responses.update(
        {
            f"vlan{vlan}": tuple(text.splitlines())
            for vlan, text in tables(resident.native.State()).items()
        }
    )
    responses["brief"] = tuple(line.replace("Yes 1", "No 1") for line in rows)
    restored = runner.observe(BASELINE, BASELINE, 0, runner.deadline)
    assert runner.recovery_carrier_failed
    assert restored.state == resident.native.State()
    assert (
        restored.running_sha256 == restored.startup_sha256 == restored.baseline_sha256
    )


def test_post_guest_primary_down_reaches_inverse_with_real_semantic_guards(
    runner, monkeypatch
):
    from test_native_trunk_observation import BASELINE, operational, running, tables
    from test_bond_vlan_membership import AFTER1, AFTER132

    prepare_cycle(runner, monkeypatch)
    actual_observe = resident.Runner.observe.__get__(runner)
    monkeypatch.setattr(
        resident.observation,
        "classify_observation",
        lambda baseline, current, startup: resident.observation._classify_observation(
            baseline,
            current,
            startup,
            baseline_sha256=resident.observation.evidence.configuration_hash(baseline),
        ),
    )
    observations = []
    down = [False]
    current = [resident.native.State()]

    def read(operation, cutoff):
        if operation == "startup":
            return BASELINE
        if operation == "running":
            return running(current[0], BASELINE)
        if operation == "brief":
            rows = []
            for line in operational(current[0]).splitlines():
                words = line.split()
                if down[0] and words and words[0] == "1/2/2":
                    words[1:5] = ["Down", "None", "None", "None"]
                    line = " ".join(words)
                rows.append(line)
            return tuple(rows)
        return tuple(tables(current[0])[int(operation[4:])].splitlines())

    def observe(baseline, startup, completed, cutoff, inverse=False):
        observations.append(completed)
        current[0] = resident.native.expected_state(completed, inverse=inverse)
        if observations == [0, 7, 7]:
            down[0] = True
        return actual_observe(baseline, startup, completed, cutoff, inverse)

    monkeypatch.setattr(runner, "read", read)
    monkeypatch.setattr(runner, "observe", observe)
    result = runner.cycle(resident.plan.Phase.REMAINING_TRUNK, lambda *args: "a" * 64)
    commands = [
        json.loads(p.read_text())["step"]["command"]
        for p in sorted(runner.runtime.glob("event-*-intent.json"))
    ]
    assert commands == [
        s.command for s in resident.plan.FORWARD[: resident.plan.STANDBY_END]
    ] + [s.command for s in resident.plan.inverse_for(7)]
    assert observations == [0, 7, 7, 0]
    assert (
        result["restored"]
        and result["forward_failure"]
        and result["recovery_carrier_failed"]
    )
    assert (
        not result["qualification_passed"] and not result["guest_proof_authority_bound"]
    )
    assert not runner.unknown
    assert not any("1/2/2" in command for command in commands)
    for vlan, expected in ((1, AFTER1), (132, AFTER132)):
        assert resident.observation.parse_vlan(
            runner.baseline_tables[vlan], vlan, total=2
        ) == resident.observation.parse_vlan(expected, vlan, total=2)


def degraded_runner(runner, monkeypatch):
    from test_active40g_observation import sample

    result = resident.Runner(
        runner.controller,
        runner.runtime,
        runner.before,
        runner.owned,
        runner.interrupted,
        runner.deadline,
        qualification=resident.native.Qualification(
            resident.native.QualificationMode.PRIMARY_DOWN
        ),
        host_observer=sample,
    )
    monkeypatch.setattr(
        resident,
        "validate_host_binding",
        lambda observer, baseline, cutoff, **kwargs: resident.host_observation.validate(
            observer(), baseline, **kwargs
        ),
    )
    return result


def prepare_degraded_cycle(runner, monkeypatch):
    from test_native_trunk_observation import BASELINE, primary_down, running, tables

    prepare_cycle(runner, monkeypatch)
    monkeypatch.setattr(resident.native, "build_plan", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        resident.observation,
        "classify_observation",
        lambda baseline, current, startup: resident.observation._classify_observation(
            baseline,
            current,
            startup,
            baseline_sha256=resident.observation.evidence.configuration_hash(baseline),
        ),
    )
    current = [resident.native.State()]
    original = resident.Runner.observe.__get__(runner)

    def read(operation, cutoff):
        if operation == "startup":
            return BASELINE
        if operation == "running":
            return running(current[0], BASELINE)
        if operation == "brief":
            return tuple(primary_down(current[0]).splitlines())
        return tuple(tables(current[0])[int(operation[4:])].splitlines())

    def observe(baseline, startup, completed, cutoff, inverse=False):
        current[0] = resident.native.expected_state(completed, inverse=inverse)
        return original(baseline, startup, completed, cutoff, inverse)

    monkeypatch.setattr(runner, "read", read)
    monkeypatch.setattr(runner, "observe", observe)


def test_primary_down_full_cycle_is_distinct_and_always_inverts(runner, monkeypatch):
    runner = degraded_runner(runner, monkeypatch)
    prepare_degraded_cycle(runner, monkeypatch)
    result = runner.cycle(resident.plan.Phase.REMAINING_TRUNK, lambda *args: "a" * 64)
    commands = [
        json.loads(p.read_text())["step"]["command"]
        for p in sorted(runner.runtime.glob("event-*-intent.json"))
    ]
    assert commands == [
        step.command for step in (*resident.plan.FORWARD, *resident.plan.INVERSE)
    ]
    assert result["restored"] and result["qualification_passed"]
    assert result["accepted_outcome"] == "primary-down-active40g-native-trunk-qualified"
    assert (
        result["qualification_mode"] == "primary-down" and result["host_samples"] >= 8
    )
    assert (
        not result["continuous_monitoring"]
        and not result["primary_forwarding_qualified"]
    )
    assert (
        not result["primary_redundancy_qualified"] and not result["execution_qualified"]
    )
    assert not result["live_admission"]
    samples = [
        json.loads(path.read_text())
        for path in runner.runtime.glob("event-*-host-sample.json")
    ]
    assert len(samples) == result["host_samples"]
    assert all(sample["validated_state"]["active"] == "nic5" for sample in samples)
    assert all(
        sample["validated_state"]["primary_counters"]["carrier"] == "0"
        for sample in samples
    )


@pytest.mark.parametrize("failure", ["carrier", "active", "counter", "timeout"])
def test_degraded_drift_at_exact_boundary_inverts_and_keeps_pending(
    runner, monkeypatch, failure
):
    from test_active40g_observation import sample

    runner = degraded_runner(runner, monkeypatch)
    prepare_degraded_cycle(runner, monkeypatch)
    calls = [0]

    def host():
        calls[0] += 1
        result = sample()
        if calls[0] >= 3:
            if failure == "carrier":
                result["members"]["nic0"]["carrier"] = "1"
            elif failure == "active":
                result["active"] = "nic0"
            elif failure == "counter":
                result["members"]["nic0"]["carrier_changes"] = "7"
            else:
                raise resident.Rejected("host sample timeout")
        return result

    def bounded(observer, baseline, cutoff, **kwargs):
        try:
            return resident.host_observation.validate(observer(), baseline, **kwargs)
        except resident.host_observation.Rejected as error:
            raise resident.Rejected(str(error)) from error

    runner.host_observer = host
    monkeypatch.setattr(resident, "validate_host_binding", bounded)
    monkeypatch.setattr(resident.capture, "initial", lambda state: None)
    monkeypatch.setattr(resident, "Runner", lambda *args, **kwargs: runner)
    monkeypatch.setattr(resident.capture, "OwnedFile", lambda runtime: runner.owned)
    runner.controller.logging = False
    receipt = resident.lifecycle(
        runner.controller,
        runner.runtime,
        resident.plan.Phase.REMAINING_TRUNK,
        None,
        qualification=runner.qualification,
        host_observer=host,
    )
    commands = [
        json.loads(p.read_text())["step"]["command"]
        for p in sorted(runner.runtime.glob("event-*-intent.json"))
    ]
    assert commands == [
        step.command for step in resident.plan.FORWARD[: resident.plan.STANDBY_END]
    ] + [step.command for step in resident.plan.inverse_for(7)]
    assert (
        receipt["restored"] and receipt["cleanup_complete"] and receipt["host_failure"]
    )
    assert not receipt["pending_may_clear"] and not receipt["qualification_passed"]
    assert receipt["accepted_outcome"] is None


def test_primary_down_missing_read_only_observer_rejects_before_logging(runner):
    with pytest.raises(resident.Rejected, match="read-only active40G observer"):
        resident.lifecycle(
            runner.controller,
            runner.runtime,
            resident.plan.Phase.REMAINING_TRUNK,
            None,
            qualification=resident.native.Qualification(
                resident.native.QualificationMode.PRIMARY_DOWN
            ),
        )
    assert not runner.controller.sent


def test_runner_mode_cannot_be_changed_after_selection(runner):
    with pytest.raises(AttributeError):
        runner.qualification = resident.native.Qualification(
            resident.native.QualificationMode.PRIMARY_DOWN
        )
    runner._qualification = resident.native.Qualification(
        resident.native.QualificationMode.PRIMARY_DOWN
    )
    with pytest.raises(resident.Rejected, match="mode changed"):
        runner.guard(runner.deadline)


def test_read_only_host_binding_is_fresh_bounded_and_rejects_drift():
    from test_active40g_observation import sample

    baseline = resident.validate_host_binding(sample, None, time.monotonic() + 10)
    assert baseline["active"] == "nic5"
    resident.validate_host_binding(sample, baseline, time.monotonic() + 10)

    def stale():
        result = sample()
        result["sampled_at"] = "2026-01-01T00:00:00+00:00"
        return result

    with pytest.raises(resident.Rejected, match="rejected"):
        resident.validate_host_binding(stale, baseline, time.monotonic() + 10)


def test_read_only_host_binding_timeout_kills_child(monkeypatch):
    monkeypatch.setattr(resident, "VALIDATOR_SECONDS", 0.05)
    with pytest.raises(resident.Rejected, match="deadline expired"):
        resident.validate_host_binding(
            lambda: time.sleep(1), None, time.monotonic() + 10
        )


@pytest.mark.parametrize("kind", ["read-only-active40g", "selected-standby", None])
def test_degraded_rendezvous_binds_mode_and_rejects_selector_proof(
    runner, monkeypatch, kind
):
    runner = degraded_runner(runner, monkeypatch)
    runner.host_baseline = {"active": "nic5"}
    state = resident.observation.Observation(
        resident.native.expected_state(7), "a", "b", "a"
    )

    def deliver(duration):
        context = json.loads((runner.runtime / "held-state.json").read_text())
        assert context["qualification_mode"] == "primary-down"
        assert context["guest_proof_kind"] == "read-only-active40g"
        assert context["host_baseline_sha256"] is not None
        resident.capture.private_json(
            runner.runtime / "guest-proof.json",
            {
                "context": context,
                "proof": {"kind": kind},
            },
        )

    monkeypatch.setattr(resident.time, "sleep", deliver)
    if kind == "read-only-active40g":
        assert (
            runner.wait_guest_proof(state, time.monotonic() + 1000)["proof"]["kind"]
            == kind
        )
    else:
        with pytest.raises(resident.Rejected, match="read-only active40G guest proof"):
            runner.wait_guest_proof(state, time.monotonic() + 1000)


def test_degraded_read_only_proof_timeout_inverts_without_selector_assumption(
    runner, monkeypatch
):
    runner = degraded_runner(runner, monkeypatch)
    prepare_degraded_cycle(runner, monkeypatch)

    def absent(*args):
        raise resident.Rejected("read-only guest proof absent")

    monkeypatch.setattr(runner, "wait_guest_proof", absent)
    result = runner.cycle(resident.plan.Phase.REMAINING_TRUNK, lambda *args: "a" * 64)
    commands = [
        json.loads(p.read_text())["step"]["command"]
        for p in sorted(runner.runtime.glob("event-*-intent.json"))
    ]
    assert commands == [
        step.command for step in resident.plan.FORWARD[: resident.plan.STANDBY_END]
    ] + [step.command for step in resident.plan.inverse_for(7)]
    assert (
        result["restored"] and result["host_failure"] == "read-only guest proof absent"
    )
    assert not result["qualification_passed"] and result["accepted_outcome"] is None


def test_degraded_sources_are_pinned_before_observing_host(runner, monkeypatch):
    runner = degraded_runner(runner, monkeypatch)
    monkeypatch.setitem(
        resident.SOURCE_PINS, "ansible/network-jobs/active40g_observation.py", "0" * 64
    )
    with pytest.raises(RuntimeError, match="resident dependency drift"):
        runner.sample_host(runner.deadline)
    assert runner.host_samples == 0 and not runner.controller.sent


@pytest.mark.parametrize("observer_gone", [False, True])
def test_primary_down_requires_final_guest_proof_and_inverts_on_rejection(
    runner, monkeypatch, observer_gone
):
    runner = degraded_runner(runner, monkeypatch)
    prepare_degraded_cycle(runner, monkeypatch)
    held = []

    def proof(state, cutoff):
        held.append(state.state)
        if state.state == resident.native.FINAL_STATE:
            if observer_gone:

                def missing_observer():
                    raise resident.Rejected("workstation observer disappeared")

                runner.host_observer = missing_observer
            raise resident.Rejected("final trunk guest proof absent")
        return {"proof": {"kind": "read-only-active40g"}}

    monkeypatch.setattr(runner, "wait_guest_proof", proof)
    result = runner.cycle(resident.plan.Phase.REMAINING_TRUNK, lambda *args: "a" * 64)
    assert held == [
        resident.native.expected_state(7),
        resident.native.FINAL_STATE,
    ]
    assert result["restored"] and not result["qualification_passed"]
    assert result["accepted_outcome"] is None
    assert result["guest_proof_failure"] == "final trunk guest proof absent"
    commands = [
        json.loads(p.read_text())["step"]["command"]
        for p in sorted(runner.runtime.glob("event-*-intent.json"))
    ]
    assert commands == [
        step.command for step in (*resident.plan.FORWARD, *resident.plan.INVERSE)
    ]


def test_final_rendezvous_cannot_reuse_standby_proof(runner, monkeypatch):
    runner = degraded_runner(runner, monkeypatch)
    runner.host_baseline = {"active": "nic5"}
    state = resident.observation.Observation(resident.native.FINAL_STATE, "a", "b", "a")
    resident.capture.private_json(runner.runtime / "guest-proof.json", {"old": True})

    def deliver(duration):
        context = json.loads((runner.runtime / "held-state-final.json").read_text())
        assert context["completed"] == len(resident.native.FORWARD_COMMANDS)
        resident.capture.private_json(
            runner.runtime / "guest-proof-final.json",
            {"context": context, "proof": {"kind": "read-only-active40g"}},
        )

    monkeypatch.setattr(resident.time, "sleep", deliver)
    artifact = runner.wait_guest_proof(state, time.monotonic() + 1000)
    assert artifact["context"]["completed"] == len(resident.native.FORWARD_COMMANDS)
    assert not (runner.runtime / "held-state.json").exists()


def test_active_port_budget_matches_only_modeled_membership_changes():
    for steps in (resident.plan.FORWARD, resident.plan.INVERSE):
        counted = [
            step.command
            for index, step in enumerate(steps)
            if resident.active_port_change(steps, index)
        ]
        assert counted == (
            ["tagged ethernet 1/2/6", "dual-mode 1"] + ["tagged ethernet 1/2/6"] * 3
            if steps == resident.plan.FORWARD
            else [
                "no vlan 40",
                "no vlan 30",
                "no vlan 20",
                "no dual-mode 1",
                "no tagged ethernet 1/2/6",
            ]
        )


def test_ack_budget_is_consumed_before_held_samples(runner, monkeypatch):
    from test_active40g_observation import transition_sample

    runner = degraded_runner(runner, monkeypatch)
    current = [transition_sample(35, 40, 41)]
    runner.host_observer = lambda: current[0]
    runner.sample_host(runner.deadline)
    runner.acknowledged_active_changes = 2
    current[0] = transition_sample(36, 41, 42)
    runner.sample_host(runner.deadline)
    assert runner.acknowledged_active_changes == 0
    runner.sample_host(runner.deadline)
    current[0] = transition_sample(37, 42, 43)
    with pytest.raises(
        resident.host_observation.Rejected, match="transition counters drift"
    ):
        runner.sample_host(runner.deadline)
    assert runner.host_samples == 3


def test_host_child_reports_bounded_counter_rejection_reason():
    from test_active40g_observation import transition_sample

    before = resident.validate_host_binding(
        lambda: transition_sample(35, 40, 41), None, time.monotonic() + 10
    )
    with pytest.raises(resident.Rejected, match="rejected: transition-counters"):
        resident.validate_host_binding(
            lambda: transition_sample(36, 41, 42), before, time.monotonic() + 10
        )
    after = resident.validate_host_binding(
        lambda: transition_sample(36, 41, 42),
        before,
        time.monotonic() + 10,
        acknowledged_active_changes=2,
    )
    resident.validate_host_binding(
        lambda: transition_sample(36, 41, 42), after, time.monotonic() + 10
    )


def test_host_child_never_propagates_raw_observer_error():
    def failed():
        raise RuntimeError("private sentinel must not leave child")

    with pytest.raises(resident.Rejected, match="rejected: observer-error") as error:
        resident.validate_host_binding(failed, None, time.monotonic() + 10)
    assert "private sentinel" not in str(error.value)


def test_counter_budget_increments_only_after_active_mutation_ack(runner):
    for index, step in enumerate(resident.plan.FORWARD):
        before = runner.acknowledged_active_changes
        runner.send(resident.plan.FORWARD, index, runner.deadline)
        assert runner.acknowledged_active_changes == before + int(
            resident.active_port_change(resident.plan.FORWARD, index)
        )
    assert runner.acknowledged_active_changes == 5


def test_uncertain_active_dispatch_cannot_earn_counter_budget(runner):
    for index in range(2):
        runner.send(resident.plan.FORWARD, index, runner.deadline)
    assert resident.plan.FORWARD[2].command == "tagged ethernet 1/2/6"
    runner.controller.fail = True
    with pytest.raises(OSError):
        runner.send(resident.plan.FORWARD, 2, runner.deadline)
    assert runner.unknown and runner.acknowledged_active_changes == 0


INTERRUPTED_CONFIGURE_ECHO = (
    b"conPoE Info: Resetting module in slot 1....completed.\n\r"
    b"PoE Error: Device 0 failed to start on PoE module.\n\r"
    b"PoE Error: Device 1 failed to start on PoE module.\n\r"
    b"figure terminal\r\n\rheadwater(config)#"
)


@pytest.mark.parametrize("split", range(1, len(resident.capture.POE_ROWS[0]) + 1))
def test_actual_completed19_ack_preserves_diagnostic_checkpoint_boundary(
    runner, monkeypatch, split
):
    row = resident.capture.POE_ROWS[0].encode("ascii")
    before = b"headwater#" + row[:split]
    runner.owned.path.write_bytes(before)
    runner.sequence = resident.plan.FORWARD
    runner.next_index = 24

    def dispatch(index, steps=None, read=False):
        assert index == 24 and steps == resident.plan.FORWARD and not read
        runner.controller.sent.append((index, read))
        with runner.owned.path.open("ab") as stream:
            stream.write(
                row[split:]
                + b"\n\r"
                + resident.capture.POE_ROWS[1].encode("ascii")
                + b"\n\r"
                + resident.capture.POE_ROWS[2].encode("ascii")
                + b"\n\r"
                + b"configure terminal\r\n\rheadwater(config)#"
            )

    monkeypatch.setattr(runner.controller, "dispatch", dispatch)
    runner.send(resident.plan.FORWARD, 24, runner.deadline)
    intent = json.loads(next(runner.runtime.glob("event-*-intent.json")).read_text())
    assert intent["offset"] == len(b"headwater#")
    assert runner.controller.sent == [(24, False)]
    assert runner.next_index == 25 and not runner.unknown
    assert runner.acknowledged_active_changes == 0
    assert len(list(runner.runtime.glob("event-*-ack.json"))) == 1


@pytest.mark.parametrize(
    "suffix", [b"unknown row", b"PoE Error: unknown", b"Access denied"]
)
def test_split_ack_boundary_still_rejects_unknown_output(runner, monkeypatch, suffix):
    runner.owned.path.write_bytes(b"headwater#P")
    runner.sequence = resident.plan.FORWARD
    runner.next_index = 24

    def dispatch(index, steps=None, read=False):
        runner.controller.sent.append((index, read))
        with runner.owned.path.open("ab") as stream:
            stream.write(
                resident.capture.POE_ROWS[0].encode("ascii")[1:]
                + b"\n\r"
                + suffix
                + b"\nconfigure terminal\r\nheadwater(config)#"
            )

    monkeypatch.setattr(runner.controller, "dispatch", dispatch)
    with pytest.raises(resident.Rejected):
        runner.send(resident.plan.FORWARD, 24, runner.deadline)
    assert runner.controller.sent == [(24, False)]
    assert runner.next_index == 24 and runner.unknown
    assert not list(runner.runtime.glob("event-*-ack.json"))


def test_observed_known_poe_interrupting_configure_echo_completes_one_send(
    runner, monkeypatch
):
    def dispatch(index, steps=None, read=False):
        assert index == 0 and steps == resident.plan.FORWARD and not read
        runner.controller.sent.append((index, read))
        with runner.owned.path.open("ab") as stream:
            stream.write(INTERRUPTED_CONFIGURE_ECHO)

    monkeypatch.setattr(runner.controller, "dispatch", dispatch)
    runner.send(resident.plan.FORWARD, 0, runner.deadline)
    assert runner.controller.sent == [(0, False)]
    assert runner.next_index == 1 and not runner.unknown
    assert runner.acknowledged_active_changes == 0
    assert len(list(runner.runtime.glob("event-*-ack.json"))) == 1


@pytest.mark.parametrize("split", range(1, len("configure terminal")))
@pytest.mark.parametrize("row", resident.capture.POE_ROWS)
def test_only_exact_configure_echo_recovered_across_complete_known_poe(split, row):
    command = "configure terminal"
    raw = (
        command[:split] + row + "\n\r" + command[split:] + "\r\nheadwater(config)#"
    ).encode()
    assert resident.acknowledgement_lines(
        raw, resident.plan.FORWARD[0].after, command=command
    ) == [command, "headwater(config)#"]


@pytest.mark.parametrize(
    "raw",
    [
        INTERRUPTED_CONFIGURE_ECHO.replace(b"slot 1", b"slot 2"),
        INTERRUPTED_CONFIGURE_ECHO.replace(b"completed.", b"completed.extra"),
        INTERRUPTED_CONFIGURE_ECHO.replace(
            b"figure terminal", b"figure terminal extra"
        ),
        INTERRUPTED_CONFIGURE_ECHO.replace(b"figure terminal", b"figure termina"),
        INTERRUPTED_CONFIGURE_ECHO.replace(
            b"figure terminal", b"figure terminal\nunknown row"
        ),
        INTERRUPTED_CONFIGURE_ECHO.replace(
            b"headwater(config)#", b"headwater(config-vlan-10)#"
        ),
        INTERRUPTED_CONFIGURE_ECHO.replace(b"headwater(config)#", b"headwater#"),
        INTERRUPTED_CONFIGURE_ECHO.replace(b"....completed.\n\r", b"....completed."),
        INTERRUPTED_CONFIGURE_ECHO.replace(b"conPoE", b"con\tPoE"),
        INTERRUPTED_CONFIGURE_ECHO.replace(b"figure terminal", b"figure terminal "),
        INTERRUPTED_CONFIGURE_ECHO + b" ",
        INTERRUPTED_CONFIGURE_ECHO + b"\n" + resident.capture.POE_ROWS[0].encode(),
        INTERRUPTED_CONFIGURE_ECHO
        + b"\n"
        + resident.capture.POE_ROWS[0].encode()
        + b" \n",
    ],
)
def test_interrupted_configure_echo_rejects_unknown_rows_mismatch_or_boundaries(raw):
    assert resident.acknowledgement_lines(
        raw, resident.plan.FORWARD[0].after, command="configure terminal"
    ) != ["configure terminal", "headwater(config)#"]


@pytest.mark.parametrize("control", [b"\x00", b"\x08", b"\x1b", b"\x7f"])
def test_interrupted_configure_echo_rejects_controls(control):
    with pytest.raises(resident.capture.Rejected, match="control"):
        resident.acknowledgement_lines(
            INTERRUPTED_CONFIGURE_ECHO.replace(b"conPoE", b"con" + control + b"PoE"),
            resident.plan.FORWARD[0].after,
            command="configure terminal",
        )


def test_poe_echo_reconstruction_is_not_admitted_for_mutation_commands():
    raw = b"dual-PoE Info: Resetting module in slot 1....completed.\n\rmode 1\r\nheadwater(config-if-e40000-1/2/6)#"
    assert resident.acknowledgement_lines(
        raw, resident.plan.FORWARD[5].after, command="dual-mode 1"
    ) != ["dual-mode 1", "headwater(config-if-e40000-1/2/6)#"]


@pytest.fixture
def inverse_gateway_reads(runner, monkeypatch):
    from test_native_trunk_observation import BASELINE, primary_down, running, tables
    from test_bond_vlan_membership import AFTER1, AFTER132

    runner = degraded_runner(runner, monkeypatch)
    runner.recovering = True
    runner.baseline_tables = {1: AFTER1, 132: AFTER132}
    monkeypatch.setattr(runner, "sample_host", lambda cutoff: None)
    monkeypatch.setattr(runner, "checkpoint", lambda cutoff: b"headwater#")
    runner.last_read_exec_offset = 0
    monkeypatch.setattr(
        resident.observation,
        "classify_observation",
        lambda baseline, current, startup: resident.observation._classify_observation(
            baseline,
            current,
            startup,
            baseline_sha256=resident.observation.evidence.configuration_hash(baseline),
        ),
    )
    options = {
        "completed": 10,
        "reads": [],
        "brief_count": 0,
        "mutation": None,
        "transient": "Listen",
    }

    def read(operation, cutoff):
        options["reads"].append((operation, cutoff))
        state = resident.native.expected_state(options["completed"], inverse=True)
        mutation = options["mutation"]
        if operation == "running":
            value = running(state, BASELINE)
            return (
                (*value[:-1], "hostname foreign", "end")
                if mutation == "configuration"
                else value
            )
        if operation == "startup":
            return (
                (*BASELINE[:-1], "hostname foreign", "end")
                if mutation == "startup"
                else BASELINE
            )
        if operation == "brief":
            options["brief_count"] += 1
            text = primary_down(state)
            transients = options.get("transients", (options["transient"],))
            if options["brief_count"] <= len(transients) or mutation == "timeout":
                text = "\n".join(
                    line.replace(
                        "Forward",
                        transients[
                            min(options["brief_count"] - 1, len(transients) - 1)
                        ],
                    )
                    if line.split() and line.split()[0] == "1/3/1"
                    else line
                    for line in text.splitlines()
                )
            if mutation == "active_listen":
                text = "\n".join(
                    line.replace("Forward", "Listen")
                    if line.split() and line.split()[0] == "1/2/6"
                    else line
                    for line in text.splitlines()
                )
            if mutation in ("gateway_blocked", "gateway_unknown", "gateway_down"):
                replacements = {
                    "gateway_blocked": ("Listen", "Blocked"),
                    "gateway_unknown": ("Listen", "Unknown"),
                    "gateway_down": ("Up      Listen", "Down    Listen"),
                }
                if mutation == "gateway_down":
                    changed = []
                    for line in text.splitlines():
                        words = line.split()
                        if words and words[0] == "1/3/1":
                            words[1] = "Down"
                            line = " ".join(words)
                        changed.append(line)
                    text = "\n".join(changed)
                else:
                    text = text.replace(*replacements[mutation])
            return tuple(text.splitlines())
        value = tables(state)[int(operation[4:])]
        return (
            ("foreign membership",)
            if mutation == "membership" and operation == "vlan132"
            else tuple(value.splitlines())
        )

    monkeypatch.setattr(runner, "read", read)
    return runner, options, BASELINE


@pytest.mark.parametrize("completed", [10, 16, 23])
@pytest.mark.parametrize("transient", ["Listen", "Learn"])
def test_inverse_gateway_listen_settles_with_full_strict_readback(
    inverse_gateway_reads, monkeypatch, completed, transient
):
    runner, options, baseline = inverse_gateway_reads
    options["completed"] = completed
    options["transient"] = transient
    monkeypatch.setattr(resident.time, "sleep", lambda duration: None)
    cutoff = time.monotonic() + 30
    observed = runner.observe_restored(
        baseline, baseline, completed, cutoff, inverse=True
    )
    assert observed.state == resident.native.expected_state(completed, inverse=True)
    assert options["brief_count"] == 2
    assert [op for op, _ in options["reads"]].count("running") == 2
    assert [op for op, _ in options["reads"]].count("startup") == 1
    assert {limit for _, limit in options["reads"]} == {cutoff}
    assert not runner.controller.sent
    assert "Listen" not in runner.last_brief
    events = list(runner.runtime.glob("event-*-inverse-gateway-settle.json"))
    assert (
        len(events) == 1
        and json.loads(events[0].read_bytes())["configuration_inputs"] == 0
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "configuration",
        "startup",
        "membership",
        "active_listen",
        "gateway_blocked",
        "gateway_unknown",
        "gateway_down",
        "unknown",
        "not_recovering",
        "changed_prompt",
    ],
)
def test_inverse_gateway_wait_does_not_admit_other_uncertainty(
    inverse_gateway_reads, monkeypatch, mutation
):
    runner, options, baseline = inverse_gateway_reads
    options["mutation"] = mutation
    if mutation == "unknown":
        runner.unknown = True
    if mutation == "not_recovering":
        runner.recovering = False
    if mutation == "changed_prompt":
        monkeypatch.setattr(runner, "checkpoint", lambda cutoff: b"headwater(config)#")
    with pytest.raises((resident.Rejected, resident.observation.evidence.Rejected)):
        runner.observe_restored(
            baseline, baseline, 10, time.monotonic() + 30, inverse=True
        )
    assert options["brief_count"] <= 1
    assert not runner.controller.sent


def test_inverse_gateway_wait_cannot_extend_original_deadline(
    inverse_gateway_reads, monkeypatch
):
    runner, options, baseline = inverse_gateway_reads
    options["mutation"] = "timeout"
    clock = [time.monotonic()]
    monkeypatch.setattr(resident.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(
        resident.time, "sleep", lambda duration: clock.__setitem__(0, clock[0] + 10)
    )
    cutoff = clock[0] + 5
    with pytest.raises(resident.Rejected, match="deadline expired"):
        runner.observe_restored(baseline, baseline, 10, cutoff, inverse=True)
    assert {limit for _, limit in options["reads"]} == {cutoff}
    assert not runner.controller.sent


def test_primary_down_full_cycle_restores_after_gateway_listen(runner, monkeypatch):
    runner = degraded_runner(runner, monkeypatch)
    prepare_degraded_cycle(runner, monkeypatch)
    runner.last_read_exec_offset = 0
    read = runner.read
    recovery_briefs = []

    def listening_read(operation, cutoff):
        value = read(operation, cutoff)
        runner.last_read_exec_offset = runner.checkpoint(cutoff).rfind(b"headwater#")
        if operation == "brief" and getattr(runner, "recovering", False):
            recovery_briefs.append(cutoff)
            if len(recovery_briefs) <= 2:
                return tuple(
                    line.replace(
                        "Forward", ("Listen", "Learn")[len(recovery_briefs) - 1]
                    )
                    if line.split() and line.split()[0] == "1/3/1"
                    else line
                    for line in value
                )
        return value

    monkeypatch.setattr(runner, "read", listening_read)
    monkeypatch.setattr(resident.time, "sleep", lambda duration: None)
    result = runner.cycle(resident.plan.Phase.REMAINING_TRUNK, lambda *args: "a" * 64)
    commands = [
        json.loads(p.read_text())["step"]["command"]
        for p in sorted(runner.runtime.glob("event-*-intent.json"))
    ]
    assert commands == [
        step.command for step in (*resident.plan.FORWARD, *resident.plan.INVERSE)
    ]
    assert result["restored"] and result["qualification_passed"]
    assert result["accepted_outcome"] == "primary-down-active40g-native-trunk-qualified"
    assert not result["forward_failure"] and not runner.unknown
    assert len(list(runner.runtime.glob("event-*-inverse-gateway-settle.json"))) == 2
    assert recovery_briefs[0] < recovery_briefs[1] < recovery_briefs[2]
    assert all(
        cutoff <= runner.deadline - resident.CLEANUP_RESERVE
        for cutoff in recovery_briefs
    )


@pytest.mark.parametrize(
    "fresh", [b"headwater#", b"headwater#\x08", b"headwater#\nforeign#\nheadwater#"]
)
def test_inverse_gateway_prompt_check_uses_qualified_read_boundary(
    inverse_gateway_reads, monkeypatch, fresh
):
    runner, options, baseline = inverse_gateway_reads
    historical = FAILED_BRIEF + b"\nheadwater#\n"
    raw = historical + fresh
    runner.last_read_exec_offset = len(historical)
    monkeypatch.setattr(runner, "checkpoint", lambda cutoff: raw)
    monkeypatch.setattr(resident.time, "sleep", lambda duration: None)
    with pytest.raises(resident.Rejected, match="unexpected response control"):
        resident.current_exec_suffix(raw)
    if fresh == b"headwater#":
        observed = runner.observe_restored(
            baseline, baseline, 10, time.monotonic() + 30, inverse=True
        )
        assert observed.state == resident.native.expected_state(10, inverse=True)
        assert not runner.controller.sent
    else:
        with pytest.raises((resident.Rejected, resident.observation.evidence.Rejected)):
            runner.observe_restored(
                baseline, baseline, 10, time.monotonic() + 30, inverse=True
            )
        assert not runner.controller.sent


@pytest.mark.parametrize(
    "noise", [b"", resident.capture.POE_ROWS[0].encode("ascii") + b"\n\r"]
)
def test_paginated_read_records_actual_exec_boundary_with_known_trailing_noise(
    runner, monkeypatch, noise
):
    with runner.owned.path.open("ab") as stream:
        stream.write(FAILED_BRIEF + b"\nheadwater#")

    def dispatch(index, steps=None, read=False):
        assert read
        with runner.owned.path.open("ab") as stream:
            stream.write(b"show vlan 10\r\nbody\r\n" + resident.capture.PAGER)

    def page(*args, **kwargs):
        with runner.owned.path.open("ab") as stream:
            stream.write(
                b"\x08 \x08" * len(resident.capture.PAGER)
                + b"tail\r\nheadwater#"
                + noise
            )

    monkeypatch.setattr(runner.controller, "dispatch", dispatch)
    monkeypatch.setattr(resident.capture, "guarded_input", page)
    assert runner.read("vlan10", time.monotonic() + 30) == ("body", "tail")
    raw = runner.owned.path.read_bytes()
    assert raw[runner.last_read_exec_offset :] == b"headwater#" + noise
    assert resident.current_exec_suffix(raw[runner.last_read_exec_offset :])
    with pytest.raises(resident.Rejected, match="unexpected response control"):
        resident.current_exec_suffix(raw)


@pytest.fixture
def timed_inverse_gateway_reads(inverse_gateway_reads, monkeypatch):
    runner, options, baseline = inverse_gateway_reads
    clock = [100.0]
    runner.deadline = 1900.0
    options["transients"] = ("Listen", "Learn")
    costs = {"running": 4.0, "brief": 9.0, "startup": 4.0}
    read = runner.read
    host_cutoffs = []
    monkeypatch.setattr(resident.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(
        resident.time, "sleep", lambda seconds: clock.__setitem__(0, clock[0] + seconds)
    )

    def advance(seconds, cutoff):
        clock[0] = min(clock[0] + seconds, cutoff)
        runner.guard(cutoff)

    def timed_read(operation, cutoff):
        runner.guard(cutoff)
        result = read(operation, cutoff)
        advance(costs.get(operation, 0.5), cutoff)
        return result

    def host_sample(cutoff):
        host_cutoffs.append(cutoff)
        advance(4.0, cutoff)

    monkeypatch.setattr(runner, "read", timed_read)
    monkeypatch.setattr(runner, "sample_host", host_sample)
    return runner, options, baseline, clock, costs, host_cutoffs


def test_inverse_gateway_retries_complete_beyond_one_observation_window(
    timed_inverse_gateway_reads,
):
    runner, options, baseline, clock, _, host_cutoffs = timed_inverse_gateway_reads
    outer = clock[0] + resident.INVERSE_RESERVE
    observed = runner.observe_restored(baseline, baseline, 10, outer, inverse=True)
    assert observed.state == resident.native.expected_state(10, inverse=True)
    assert clock[0] - 100.0 == 61.0 > resident.OBSERVE_SECONDS
    assert options["brief_count"] == 3
    attempt_cutoffs = [
        limit for operation, limit in options["reads"] if operation == "running"
    ]
    assert attempt_cutoffs == [150.0, 170.5, 191.0]
    assert host_cutoffs == [attempt_cutoffs[-1]]
    assert all(limit <= outer for _, limit in options["reads"])
    assert [operation for operation, _ in options["reads"]].count("startup") == 2
    assert not runner.controller.sent and not runner.unknown


def test_inverse_gateway_retries_never_renew_outer_cutoff(timed_inverse_gateway_reads):
    runner, options, baseline, clock, _, host_cutoffs = timed_inverse_gateway_reads
    options["mutation"] = "timeout"
    outer = clock[0] + 60.0
    with pytest.raises(resident.Rejected, match="deadline expired"):
        runner.observe_restored(baseline, baseline, 10, outer, inverse=True)
    assert clock[0] == outer
    assert all(limit <= outer for _, limit in options["reads"])
    assert not host_cutoffs and not runner.controller.sent


def test_inverse_gateway_single_attempt_timeout_is_terminal(
    timed_inverse_gateway_reads,
):
    runner, options, baseline, clock, costs, host_cutoffs = timed_inverse_gateway_reads
    costs["running"] = resident.OBSERVE_SECONDS + 1
    with pytest.raises(resident.Rejected, match="deadline expired"):
        runner.observe_restored(baseline, baseline, 10, clock[0] + 600, inverse=True)
    assert clock[0] == 150.0
    assert options["reads"] == [("running", 150.0)]
    assert not host_cutoffs and not runner.controller.sent


@pytest.mark.parametrize("forward_failure", [False, True])
def test_inverse_budget_is_fixed_once_at_first_dispatch(
    runner, monkeypatch, forward_failure
):
    prepare_cycle(runner, monkeypatch)
    clock = [100.0]
    runner.deadline = clock[0] + resident.TOTAL_SECONDS
    monkeypatch.setattr(resident.time, "monotonic", lambda: clock[0])
    records = []
    send = runner.send

    def recorded_send(steps, index, cutoff):
        records.append((steps is resident.plan.FORWARD, index, clock[0], cutoff))
        send(steps, index, cutoff)
        clock[0] += 1.0

    def observe(baseline, startup, completed, cutoff, inverse=False):
        if (
            forward_failure
            and completed == 7
            and not getattr(runner, "recovering", False)
        ):
            clock[0] = runner.deadline - 100
            raise resident.CarrierRejected("primary carrier down at exact native state")
        return resident.observation.Observation(
            resident.native.expected_state(completed, inverse=inverse), "a", "b", "a"
        )

    monkeypatch.setattr(runner, "send", recorded_send)
    monkeypatch.setattr(runner, "observe", observe)
    result = runner.cycle(resident.plan.Phase.REMAINING_TRUNK, lambda *args: "a" * 64)
    inverse = [record for record in records if not record[0]]
    expected = min(
        runner.deadline - resident.CLEANUP_RESERVE,
        inverse[0][2] + resident.INVERSE_RESERVE,
    )
    assert {record[3] for record in inverse} == {expected}
    assert all(
        record[3]
        == runner.deadline - resident.INVERSE_RESERVE - resident.CLEANUP_RESERVE
        for record in records
        if record[0]
    )
    assert result["restored"] and not runner.unknown
