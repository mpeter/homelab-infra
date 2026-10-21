#!/usr/bin/env python3
"""Invoke the frozen fixed PiKVM capture helper; save all evidence privately."""

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import selectors
import shlex
import stat
import subprocess
import tempfile
import time

HELPER_SHA256 = "5998be264a5a93f99b33c6969051de2ac7b14ce83482bbd0615287a278e4f4c1"
SERIAL_SHA256 = "6e1ffbd8acee89f5c9b53c325b3a0a6d7e5d98c69106c241d9ca18d09de9015d"
PIN_SHA256 = "5787aa88eef74b418d0c3c1db6b68ce1acd5ec7cdb566f9dd0d9da36112bec08"
DIRECTORY = Path(__file__).resolve().parent
REPOSITORY = DIRECTORY.parents[1]
PIN = REPOSITORY / "inventory/local/brocade-ee-2026-10-06/pikvm-known-hosts"
ARTIFACT_PARENT = (
    REPOSITORY / "inventory/local/pikvm-screen-capture-invocations-2026-10-09"
)
MAX_OUTPUT = 16 * 1024 * 1024
SSH_DEADLINE = 165

# Fixed remote code receives source bytes through stdin, never shell interpolation.
REMOTE_SOURCE = r"""
import base64, datetime, hashlib, json, os, pathlib, stat, subprocess, sys, tempfile, time
UID = 0
HELPER_SHA = "5998be264a5a93f99b33c6969051de2ac7b14ce83482bbd0615287a278e4f4c1"
SERIAL_SHA = "6e1ffbd8acee89f5c9b53c325b3a0a6d7e5d98c69106c241d9ca18d09de9015d"
LIMIT = 6 * 1024 * 1024
PENDING = pathlib.Path("/tmp/pikvm-screen-capture.pending.json")
class Rejected(Exception): pass

def emit(value):
    print(json.dumps(value), flush=True)

def directory(path):
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != UID or stat.S_IMODE(info.st_mode) != 0o700:
        raise Rejected("private directory custody mismatch")
    return info.st_dev, info.st_ino

def read(path, limit=LIMIT, parent_identity=None):
    if parent_identity is not None and directory(path.parent) != parent_identity:
        raise Rejected("private directory replaced")
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_uid != UID or before.st_nlink != 1 or stat.S_IMODE(before.st_mode) != 0o600 or before.st_size > limit:
        raise Rejected("private file custody or size mismatch")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        opened = os.fstat(fd)
        key = lambda item: (item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns, item.st_mode, item.st_uid, item.st_nlink)
        if key(opened) != key(before): raise Rejected("opened file changed")
        with os.fdopen(fd, "rb", closefd=False) as stream: data = stream.read(limit + 1)
        after = path.lstat()
        if key(after) != key(before) or len(data) != before.st_size:
            raise Rejected("file changed during collection")
        if parent_identity is not None and directory(path.parent) != parent_identity:
            raise Rejected("private directory changed during collection")
        return {"path": str(path), "identity": [before.st_dev, before.st_ino],
                "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                "base64": base64.b64encode(data).decode("ascii")}
    finally: os.close(fd)

def write(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data); stream.flush(); os.fsync(stream.fileno())

def runtime(path):
    value = pathlib.Path(path)
    if value.parent != pathlib.Path("/tmp") or not value.name.startswith(("pikvm-screen-check-", "pikvm-screen-capture-")):
        raise Rejected("unexpected helper runtime")
    identity = directory(value)
    records = []
    for name in ("runner.json", "evidence.json", "runner-failure.json", "window-output.log"):
        item = value / name
        if item.exists() or item.is_symlink():
            records.append(read(item, 1024 * 1024 if name.endswith(".log") else LIMIT, identity))
    return {"path": str(value), "identity": identity, "files": records}

def pending():
    if not (PENDING.exists() or PENDING.is_symlink()): return None
    record = read(PENDING, 16384)
    parsed = json.loads(base64.b64decode(record["base64"]))
    result = {"marker": record}
    if isinstance(parsed, dict) and isinstance(parsed.get("private_runtime"), str):
        result["runtime"] = runtime(parsed["private_runtime"])
    return result

def run(helper, mode):
    argv = [sys.executable, str(helper), "--" + mode]
    started = datetime.datetime.now(datetime.timezone.utc).isoformat()
    emit({"event": "helper-starting", "mode": mode, "argv": argv})
    try:
        result = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, timeout=15 if mode == "check" else 138 if mode == "configurations" else 58 if mode == "show-version" else 35, check=False,
                                env={"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"})
    except subprocess.TimeoutExpired as error:
        emit({"event": "helper-timeout", "mode": mode,
              "stdout_base64": base64.b64encode(error.stdout or b"").decode("ascii"),
              "stderr_base64": base64.b64encode(error.stderr or b"").decode("ascii")})
        raise
    record = {"event": "helper-result", "mode": mode, "returncode": result.returncode,
              "stdout_base64": base64.b64encode(result.stdout).decode("ascii"),
              "stderr_base64": base64.b64encode(result.stderr).decode("ascii")}
    emit(record)
    if len(result.stdout) > 16384 or result.stderr:
        raise Rejected("unexpected helper output")
    summary = json.loads(result.stdout)
    if not isinstance(summary, dict): raise Rejected("helper summary is not an object")
    emit({"event": "helper-handles", "mode": mode, "summary": summary})
    collected = runtime(summary["private_runtime"]) if "private_runtime" in summary else None
    emit({"event": "runtime-collected", "mode": mode, "runtime": collected})
    return result.returncode, summary, collected, started

def verify_configurations(evidence, data):
    # Raw-to-canonical semantics remain the reviewed source-bound helper's authority.
    # This controller checks custody/hash bindings; root rederivation is separate.
    records = evidence.get("configuration_responses", [])
    if (evidence.get("configurations_complete") is not True or len(records) != 2
        or evidence.get("continuous_logging_required") is not True
        or evidence.get("configuration_write_admitted") is not False
        or evidence.get("external_concurrent_input_absent_verified") is not False
        or evidence.get("empty_privileged_prompt_observed") is not True
        or evidence.get("canonicalization_authority") != "source-bound frozen helper configuration_progress"
        or evidence.get("controller_independent_canonicalization_verified") is not False):
        raise Rejected("configuration acceptance or ownership claim mismatch")
    expected_inputs = ["probe"]
    offset = evidence.get("qualified_cancel_bytes")
    if type(offset) is not int or offset <= 0 or evidence.get("qualified_cancel_sha256") != hashlib.sha256(data[:offset]).hexdigest():
        raise Rejected("configuration cancellation prefix mismatch")
    for record, operation, command in zip(records, ("running", "startup"), ("show running-config", "show configuration"), strict=True):
        size = record.get("bytes")
        pages = record.get("pager_space_attempts")
        lines = record.get("canonical_lines")
        if (record.get("operation") != operation or record.get("command") != command
            or record.get("offset") != offset or type(size) is not int or size <= 0 or offset+size > len(data)
            or type(pages) is not int or pages < 0 or pages > 32 or not isinstance(lines, list)
            or not lines or any(not isinstance(line, str) for line in lines)):
            raise Rejected("configuration record or pager chronology mismatch")
        segment = data[offset:offset+size]
        canonical = ("\n".join(lines) + "\n").encode("ascii")
        digest = hashlib.sha256(canonical).hexdigest()
        expected = "97997daab378af8467dcb05244f2f9c03b2df33c694d373c1dc4a891cb4bbb3b"
        if (record.get("raw_sha256") != hashlib.sha256(segment).hexdigest()
            or record.get("canonical_sha256") != digest or record.get("expected_current_sha256") != expected
            or record.get("matches_current_baseline") is not (digest == expected)
            or lines[0] not in ("ver 08.0.30uT7f3", "version 08.0.30uT7f3")
            or lines[-1] != "end" or "end" in lines[:-1]):
            raise Rejected("configuration canonical or raw binding mismatch")
        expected_inputs += [operation] + ["page"] * pages
        offset += size
    if offset != len(data): raise Rejected("configuration trailing bytes unbound")
    attempts = evidence.get("serial_input_attempts", [])
    if [item.get("operation") for item in attempts] != expected_inputs:
        raise Rejected("fixed configuration input order mismatch")
    values = {"probe": "03", "running": b"show running-config\r".hex(), "startup": b"show configuration\r".hex(), "page": "20"}
    previous = ""
    for item in attempts:
        if (item.get("input_hex") != values[item["operation"]] or not isinstance(item.get("attempted_at"), str)
            or not isinstance(item.get("dispatch_returned_at"), str) or item["attempted_at"] < previous
            or item["dispatch_returned_at"] < item["attempted_at"]):
            raise Rejected("configuration input timing or byte mismatch")
        previous = item["dispatch_returned_at"]
    commands = [item.get("operation") for item in evidence.get("queries", []) if item.get("operation") != "info"]
    if commands != ["template", "on", *expected_inputs, "off"]:
        raise Rejected("configuration logger or input chronology mismatch")
    observations = evidence.get("append_prefix_observations", [])
    size = 0
    if not observations: raise Rejected("configuration prefix observations absent")
    for item in observations:
        if (item.get("logging_verified_on") is not True or type(item.get("bytes")) is not int
            or item["bytes"] < size or item["bytes"] > len(data)
            or item.get("sha256") != hashlib.sha256(data[:item["bytes"]]).hexdigest()):
            raise Rejected("configuration append prefix mismatch")
        size = item["bytes"]

def verify_version(evidence, data):
    attempts = evidence.get("serial_input_attempts", [])
    operations = [item.get("operation") for item in attempts]
    if (operations[:2] != ["probe", "version"] or operations[2:] != ["page"] * len(operations[2:])
        or len(operations) > 6 or evidence.get("pager_space_attempts", 0) != len(operations) - 2
        or evidence.get("empty_privileged_prompt_observed") is not True
        or evidence.get("show_version_complete") is not True or evidence.get("version_response_complete") is not True
        or evidence.get("external_concurrent_input_absent_verified") is not False
        or evidence.get("configuration_write_admitted") is not False):
        raise Rejected("fixed version chronology or acceptance mismatch")
    commands = [item.get("operation") for item in evidence.get("queries", []) if item.get("operation") != "info"]
    if commands != ["template", "on", *operations, "off"]:
        raise Rejected("intermediate logger toggle or input chronology mismatch")
    observations = evidence.get("append_prefix_observations", [])
    if evidence.get("continuous_logging_required") is not True or not observations:
        raise Rejected("continuous logging observation missing")
    size = 0
    for item in observations:
        if (item.get("logging_verified_on") is not True or type(item.get("bytes")) is not int
            or item["bytes"] < size or item["bytes"] > len(data)
            or item.get("sha256") != hashlib.sha256(data[:item["bytes"]]).hexdigest()):
            raise Rejected("append-prefix receipt mismatch")
        size = item["bytes"]
    previous = ""
    for item in attempts:
        if (item.get("input_hex") != {"probe": "03", "version": "73686f772076657273696f6e0d", "page": "20"}[item["operation"]]
            or not isinstance(item.get("attempted_at"), str) or not isinstance(item.get("dispatch_returned_at"), str)
            or item["attempted_at"] < previous or item["dispatch_returned_at"] < item["attempted_at"]):
            raise Rejected("fixed version input receipt mismatch")
        previous = item["dispatch_returned_at"]
    offset = evidence.get("version_response_offset")
    if (type(offset) is not int or offset <= 0 or offset >= len(data)
        or evidence.get("qualified_cancel_bytes") != offset
        or evidence.get("qualified_cancel_sha256") != hashlib.sha256(data[:offset]).hexdigest()
        or evidence.get("version_response_bytes") != len(data) - offset
        or evidence.get("version_response_sha256") != hashlib.sha256(data[offset:]).hexdigest()):
        raise Rejected("version response byte binding mismatch")

def verify_receipt(mode, summary, collected, started):
    files = {pathlib.Path(item["path"]).name: item for item in collected["files"]}
    if "evidence.json" not in files: raise Rejected("missing evidence receipt")
    evidence = json.loads(base64.b64decode(files["evidence.json"]["base64"], validate=True))
    if not isinstance(evidence, dict) or evidence.get("source_sha256") != HELPER_SHA:
        raise Rejected("evidence source mismatch")
    if mode == "check":
        if evidence.get("fixed_owner_checked") is not True or evidence.get("capture_admitted") is not False or evidence.get("state", {}).get("owner", [None])[0] != 5441045:
            raise Rejected("invalid check receipt")
        return
    if not all(name in files for name in ("runner.json", "window-output.log")):
        raise Rejected("missing capture receipts")
    qualified_cancel = mode in ("show-version", "configurations")
    if (evidence.get("mode") != mode
        or evidence.get("cancellation_verified") is not qualified_cancel
        or evidence.get("prompt_freshness_verified") is not qualified_cancel):
        raise Rejected("probe mode or unsupported cancellation claim")
    if mode in ("probe-prompt", "show-version", "configurations") and (evidence.get("probe_attempted") is not True or evidence.get("probe_input_hex") != "03" or not evidence.get("probe_dispatch_returned_at")):
        raise Rejected("missing fixed probe receipt")
    if mode == "capture" and evidence.get("probe_attempted") is not False:
        raise Rejected("passive capture input claim")
    if (evidence.get("owner_source_sha256") != SERIAL_SHA
        or evidence.get("capture_succeeded") is not True or evidence.get("cleanup_complete") is not True
        or evidence.get("expected_installed_binary_sha256") != "37ddde69ebad045aa1b71bb902c9a33ad1de6a26ae8a65e1b146d9d808af15c9"
        or evidence.get("before", {}).get("owner", [None])[0] != 5441045
        or evidence.get("after", {}).get("owner", [None])[0] != 5441045):
        raise Rejected("capture state/source binding mismatch")
    before, after = evidence.get("before", {}), evidence.get("after", {})
    keys = {"owner", "settings", "directory", "socket", "fds", "logging"}
    if (set(before) != keys or set(after) != keys or before != after or before["logging"] is not False
        or evidence.get("owned_capture_identity") != files["window-output.log"]["identity"]
        or evidence.get("owned_directory_identity") != list(collected["identity"])
        or evidence.get("runtime") != collected["path"]
        or evidence.get("attempted_logfile_template") != files["window-output.log"]["path"]
        or evidence.get("logfile_adoption_verified") is not True):
        raise Rejected("capture state or inode custody mismatch")
    for key in ("prior_template_restored", "prior_template_observed", "raw_uart_byte_fidelity_verified",
                "command_stream_complete", "serial_control_verified", "independent_rescue_verified", "restore_verified", "task_complete"):
        if evidence.get(key) is not False: raise Rejected("unsupported capture claim")
    begin = datetime.datetime.fromisoformat(evidence["started_at"])
    end = datetime.datetime.fromisoformat(evidence["completed_at"])
    if begin < datetime.datetime.fromisoformat(started) or end < begin or end > datetime.datetime.now(datetime.timezone.utc):
        raise Rejected("stale capture receipt")
    runner = json.loads(base64.b64decode(files["runner.json"]["base64"], validate=True))
    if (runner.get("source_sha256") != HELPER_SHA or type(runner.get("pid")) is not int
        or runner["pid"] != summary.get("runner_pid") or type(runner.get("starttime")) is not int or runner["starttime"] <= 0):
        raise Rejected("runner receipt mismatch")
    proc = pathlib.Path("/proc") / str(runner["pid"]) / "stat"
    try:
        raw = proc.read_text()
        current_start = int(raw[raw.rfind(")") + 1:].split()[19])
    except FileNotFoundError: current_start = None
    if current_start == runner["starttime"]: raise Rejected("runner epoch still present")
    emit({"event": "runner-terminal-verified", "runner_pid": runner["pid"],
          "runner_starttime": runner["starttime"], "runner_epoch_absent": True})
    if mode == "configurations":
        verify_configurations(evidence, base64.b64decode(evidence["log_base64"], validate=True))
    if mode == "show-version":
        verify_version(evidence, base64.b64decode(evidence["log_base64"], validate=True))
    logfile = files["window-output.log"]
    data = base64.b64decode(evidence["log_base64"], validate=True)
    if len(data) != evidence.get("log_bytes") or len(data) != logfile["bytes"] or hashlib.sha256(data).hexdigest() != evidence.get("log_sha256") or evidence["log_sha256"] != logfile["sha256"]:
        raise Rejected("logfile/receipt byte hash mismatch")

def main():
    stage = None
    sources = {}
    clean = False
    result = {"event": "complete", "operation_complete": False, "source_stage_removed": False,
              "runtime_retained": True, "restore_verified": False}
    try:
        if os.getuid() != UID: raise Rejected("remote process is not root")
        os.umask(0o077)
        payload = json.loads(sys.stdin.buffer.read(128 * 1024 + 1))
        if set(payload) != {"mode", "helper_base64", "serial_base64"} or payload["mode"] not in ("check", "capture", "probe-prompt", "show-version", "configurations"):
            raise Rejected("unsupported invocation payload")
        decoded = {}
        for name, key, expected in (("pikvm-screen-capture.py", "helper_base64", HELPER_SHA),
                                    ("inspect-pikvm-serial.py", "serial_base64", SERIAL_SHA)):
            data = base64.b64decode(payload[key], validate=True)
            if hashlib.sha256(data).hexdigest() != expected: raise Rejected("frozen source mismatch")
            decoded[name] = data
        stage = pathlib.Path(tempfile.mkdtemp(prefix="pikvm-screen-source-", dir="/tmp"))
        stage.chmod(0o700); stage_identity = directory(stage)
        result["source_stage"] = str(stage)
        emit({"event": "source-stage-created", "source_stage": str(stage), "identity": stage_identity})
        for name, data in decoded.items():
            write(stage / name, data)
            sources[name] = read(stage / name, 128 * 1024, stage_identity)
        emit({"event": "sources-staged", "sources": sources})
        helper = stage / "pikvm-screen-capture.py"
        code, check, check_runtime, check_started = run(helper, "check")
        if code != 0 or check.get("fixed_owner_checked") is not True or check.get("capture_admitted") is not False or check_runtime is None:
            raise Rejected("fresh helper check failed")
        verify_receipt("check", check, check_runtime, check_started)
        if payload["mode"] == "check":
            clean = True
            result["operation_complete"] = True
        else:
            if PENDING.exists() or PENDING.is_symlink(): raise Rejected("pending capture interlock")
            for name, original in sources.items():
                if read(stage / name, 128 * 1024, stage_identity) != original:
                    raise Rejected("source changed after fresh check")
            code, capture, captured_runtime, capture_started = run(helper, payload["mode"])
            result["capture_summary"] = capture
            clean = (code == 0 and capture.get("runner_terminal") is True
                     and capture.get("runner_exit_status") == 0
                     and capture.get("operation_complete") is True
                     and capture.get("cleanup_complete") is True
                     and capture.get("pending_retained") is False
                     and captured_runtime is not None
                     and not (PENDING.exists() or PENDING.is_symlink()))
            if clean: verify_receipt(payload["mode"], capture, captured_runtime, capture_started)
            result["operation_complete"] = clean
        if clean:
            # Verify all sources before removing either. Runtime/log remain intact.
            if set(item.name for item in stage.iterdir()) != set(sources):
                raise Rejected("unexpected source stage entries")
            for name, original in sources.items():
                current = read(stage / name, 128 * 1024, stage_identity)
                if current != original: raise Rejected("staged source changed before cleanup")
            for name in sources: (stage / name).unlink()
            stage.rmdir()
            result["source_stage_removed"] = True
    except Exception as error:
        result["exception_type"] = type(error).__name__
        result["operation_complete"] = False
        try: result["pending"] = pending()
        except Exception as custody_error: result["pending_collection_failure"] = type(custody_error).__name__
    emit(result)
    return 0 if result["operation_complete"] and result["source_stage_removed"] else 2
if __name__ == "__main__": sys.exit(main())
"""


class Rejected(Exception):
    """Source, pin, transport or remote custody did not pass."""


def private_write(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def bound_read(path, expected, private=False):
    before = path.lstat()
    if (
        not stat.S_ISREG(before.st_mode)
        or before.st_nlink != 1
        or before.st_uid != os.getuid()
        or before.st_size > 128 * 1024
        or (private and stat.S_IMODE(before.st_mode) != 0o600)
    ):
        raise Rejected("local source or pin custody mismatch")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        with os.fdopen(fd, "rb", closefd=False) as stream:
            data = stream.read(128 * 1024 + 1)
        after = path.lstat()

        def key(item):
            return (
                item.st_dev,
                item.st_ino,
                item.st_size,
                item.st_mtime_ns,
                item.st_mode,
                item.st_uid,
                item.st_nlink,
            )

        if (
            key(before) != key(info)
            or key(before) != key(after)
            or len(data) != before.st_size
            or hashlib.sha256(data).hexdigest() != expected
        ):
            raise Rejected("local source or pin drift")
        return data
    finally:
        os.close(fd)


def ssh_argv():
    return [
        "ssh",
        "-F",
        "/dev/null",
        "-T",
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        "UserKnownHostsFile=" + str(PIN),
        "-o",
        "GlobalKnownHostsFile=/dev/null",
        "-o",
        "ConnectTimeout=8",
        "-o",
        "ControlMaster=no",
        "-o",
        "ControlPath=none",
        "root@192.168.0.250",
        "python3 -c " + shlex.quote(REMOTE_SOURCE),
    ]


def transport(argv, payload):
    process = subprocess.Popen(
        argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    output = {"stdout": bytearray(), "stderr": bytearray()}
    reason = None
    try:
        assert (
            process.stdin is not None
            and process.stdout is not None
            and process.stderr is not None
        )
        deadline = time.monotonic() + SSH_DEADLINE
        offset = 0
        with selectors.DefaultSelector() as selector:
            os.set_blocking(process.stdin.fileno(), False)
            selector.register(process.stdin, selectors.EVENT_WRITE, "stdin")
            for name, stream in (
                ("stdout", process.stdout),
                ("stderr", process.stderr),
            ):
                selector.register(stream, selectors.EVENT_READ, name)
            while selector.get_map():
                if time.monotonic() >= deadline:
                    raise Rejected("SSH controller deadline exceeded")
                for key, _ in selector.select(0.05):
                    if key.data == "stdin":
                        offset += os.write(
                            key.fileobj.fileno(), payload[offset : offset + 8192]
                        )
                        if offset == len(payload):
                            selector.unregister(key.fileobj)
                            process.stdin.close()
                        continue
                    data = os.read(key.fileobj.fileno(), 65536)
                    if not data:
                        selector.unregister(key.fileobj)
                    else:
                        remaining = MAX_OUTPUT - sum(
                            len(value) for value in output.values()
                        )
                        output[key.data].extend(data[:remaining])
                        if len(data) > remaining:
                            raise Rejected("SSH output size limit exceeded")
        process.wait(timeout=2)
    except Exception as error:
        reason = type(error).__name__ + ": " + str(error)
        for cleanup in (process.kill, lambda: process.wait(timeout=2)):
            try:
                cleanup()
            except Exception as cleanup_error:
                reason += "; cleanup: " + type(cleanup_error).__name__
    finally:
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream is not None and not stream.closed:
                try:
                    stream.close()
                except OSError as error:
                    reason = (reason or "") + "; close: " + type(error).__name__
    return process.returncode, bytes(output["stdout"]), bytes(output["stderr"]), reason


def verify_configurations(evidence, data):
    # Raw-to-canonical semantics remain the reviewed source-bound helper's authority.
    # This controller checks custody/hash bindings; root rederivation is separate.
    records = evidence.get("configuration_responses", [])
    if (
        evidence.get("configurations_complete") is not True
        or len(records) != 2
        or evidence.get("continuous_logging_required") is not True
        or evidence.get("configuration_write_admitted") is not False
        or evidence.get("external_concurrent_input_absent_verified") is not False
        or evidence.get("empty_privileged_prompt_observed") is not True
        or evidence.get("cancellation_verified") is not True
        or evidence.get("prompt_freshness_verified") is not True
        or evidence.get("canonicalization_authority")
        != "source-bound frozen helper configuration_progress"
        or evidence.get("controller_independent_canonicalization_verified") is not False
    ):
        raise Rejected("configuration acceptance or ownership claim mismatch")
    expected_inputs = ["probe"]
    offset = evidence.get("qualified_cancel_bytes")
    if (
        type(offset) is not int
        or offset <= 0
        or evidence.get("qualified_cancel_sha256")
        != hashlib.sha256(data[:offset]).hexdigest()
    ):
        raise Rejected("configuration cancellation prefix mismatch")
    for record, operation, command in zip(
        records,
        ("running", "startup"),
        ("show running-config", "show configuration"),
        strict=True,
    ):
        size = record.get("bytes")
        pages = record.get("pager_space_attempts")
        lines = record.get("canonical_lines")
        if (
            record.get("operation") != operation
            or record.get("command") != command
            or record.get("offset") != offset
            or type(size) is not int
            or size <= 0
            or offset + size > len(data)
            or type(pages) is not int
            or pages < 0
            or pages > 32
            or not isinstance(lines, list)
            or not lines
            or any(not isinstance(line, str) for line in lines)
        ):
            raise Rejected("configuration record or pager chronology mismatch")
        segment = data[offset : offset + size]
        canonical = ("\n".join(lines) + "\n").encode("ascii")
        digest = hashlib.sha256(canonical).hexdigest()
        expected = "97997daab378af8467dcb05244f2f9c03b2df33c694d373c1dc4a891cb4bbb3b"
        if (
            record.get("raw_sha256") != hashlib.sha256(segment).hexdigest()
            or record.get("canonical_sha256") != digest
            or record.get("expected_current_sha256") != expected
            or record.get("matches_current_baseline") is not (digest == expected)
            or lines[0] not in ("ver 08.0.30uT7f3", "version 08.0.30uT7f3")
            or lines[-1] != "end"
            or "end" in lines[:-1]
        ):
            raise Rejected("configuration canonical or raw binding mismatch")
        expected_inputs += [operation] + ["page"] * pages
        offset += size
    if offset != len(data):
        raise Rejected("configuration trailing bytes unbound")
    attempts = evidence.get("serial_input_attempts", [])
    if [item.get("operation") for item in attempts] != expected_inputs:
        raise Rejected("fixed configuration input order mismatch")
    values = {
        "probe": "03",
        "running": b"show running-config\r".hex(),
        "startup": b"show configuration\r".hex(),
        "page": "20",
    }
    previous = ""
    for item in attempts:
        if (
            item.get("input_hex") != values[item["operation"]]
            or not isinstance(item.get("attempted_at"), str)
            or not isinstance(item.get("dispatch_returned_at"), str)
            or item["attempted_at"] < previous
            or item["dispatch_returned_at"] < item["attempted_at"]
        ):
            raise Rejected("configuration input timing or byte mismatch")
        previous = item["dispatch_returned_at"]
    commands = [
        item.get("operation")
        for item in evidence.get("queries", [])
        if item.get("operation") != "info"
    ]
    if commands != ["template", "on", *expected_inputs, "off"]:
        raise Rejected("configuration logger or input chronology mismatch")
    observations = evidence.get("append_prefix_observations", [])
    size = 0
    if not observations:
        raise Rejected("configuration prefix observations absent")
    for item in observations:
        if (
            item.get("logging_verified_on") is not True
            or type(item.get("bytes")) is not int
            or item["bytes"] < size
            or item["bytes"] > len(data)
            or item.get("sha256") != hashlib.sha256(data[: item["bytes"]]).hexdigest()
        ):
            raise Rejected("configuration append prefix mismatch")
        size = item["bytes"]


def verify_version(evidence, data):
    attempts = evidence.get("serial_input_attempts", [])
    operations = [item.get("operation") for item in attempts]
    if (
        operations[:2] != ["probe", "version"]
        or operations[2:] != ["page"] * len(operations[2:])
        or len(operations) > 6
        or evidence.get("pager_space_attempts", 0) != len(operations) - 2
        or evidence.get("empty_privileged_prompt_observed") is not True
        or evidence.get("cancellation_verified") is not True
        or evidence.get("prompt_freshness_verified") is not True
        or evidence.get("show_version_complete") is not True
        or evidence.get("version_response_complete") is not True
        or evidence.get("external_concurrent_input_absent_verified") is not False
        or evidence.get("configuration_write_admitted") is not False
    ):
        raise Rejected("fixed version chronology or acceptance mismatch")
    commands = [
        item.get("operation")
        for item in evidence.get("queries", [])
        if item.get("operation") != "info"
    ]
    if commands != ["template", "on", *operations, "off"]:
        raise Rejected("intermediate logger toggle or input chronology mismatch")
    observations = evidence.get("append_prefix_observations", [])
    if evidence.get("continuous_logging_required") is not True or not observations:
        raise Rejected("continuous logging observation missing")
    size = 0
    for item in observations:
        if (
            item.get("logging_verified_on") is not True
            or type(item.get("bytes")) is not int
            or item["bytes"] < size
            or item["bytes"] > len(data)
            or item.get("sha256") != hashlib.sha256(data[: item["bytes"]]).hexdigest()
        ):
            raise Rejected("append-prefix receipt mismatch")
        size = item["bytes"]
    previous = ""
    for item in attempts:
        if (
            item.get("input_hex")
            != {"probe": "03", "version": "73686f772076657273696f6e0d", "page": "20"}[
                item["operation"]
            ]
            or not isinstance(item.get("attempted_at"), str)
            or not isinstance(item.get("dispatch_returned_at"), str)
            or item["attempted_at"] < previous
            or item["dispatch_returned_at"] < item["attempted_at"]
        ):
            raise Rejected("fixed version input receipt mismatch")
        previous = item["dispatch_returned_at"]
    offset = evidence.get("version_response_offset")
    if (
        type(offset) is not int
        or offset <= 0
        or offset >= len(data)
        or evidence.get("qualified_cancel_bytes") != offset
        or evidence.get("qualified_cancel_sha256")
        != hashlib.sha256(data[:offset]).hexdigest()
        or evidence.get("version_response_bytes") != len(data) - offset
        or evidence.get("version_response_sha256")
        != hashlib.sha256(data[offset:]).hexdigest()
    ):
        raise Rejected("version response byte binding mismatch")


def validate_events(events, mode):
    expected = [
        "source-stage-created",
        "sources-staged",
        "helper-starting",
        "helper-result",
        "helper-handles",
        "runtime-collected",
    ]
    if mode != "check":
        expected += [
            "helper-starting",
            "helper-result",
            "helper-handles",
            "runtime-collected",
            "runner-terminal-verified",
        ]
    expected += ["complete"]
    if [item.get("event") for item in events] != expected:
        raise Rejected("missing, duplicate or out-of-sequence remote receipts")
    stage = events[0]["source_stage"]
    path = Path(stage)
    if path.parent != Path("/tmp") or not path.name.startswith("pikvm-screen-source-"):
        raise Rejected("unexpected remote source stage")
    sources = events[1]["sources"]
    if set(sources) != {"pikvm-screen-capture.py", "inspect-pikvm-serial.py"}:
        raise Rejected("unexpected staged sources")
    for name, expected_hash in (
        ("pikvm-screen-capture.py", HELPER_SHA256),
        ("inspect-pikvm-serial.py", SERIAL_SHA256),
    ):
        record = sources[name]
        raw = base64.b64decode(record["base64"], validate=True)
        if (
            record["path"] != str(path / name)
            or hashlib.sha256(raw).hexdigest() != expected_hash
            or record["sha256"] != expected_hash
            or record["bytes"] != len(raw)
        ):
            raise Rejected("staged source receipt mismatch")
    for offset, phase in ((2, "check"), (6, mode))[: 1 if mode == "check" else 2]:
        start, result, handles, collected = events[offset : offset + 4]
        if any(
            item.get("mode") != phase for item in (start, result, handles, collected)
        ):
            raise Rejected("helper receipt mode mismatch")
        if len(start["argv"]) != 3 or start["argv"][1:] != [
            str(path / "pikvm-screen-capture.py"),
            "--" + phase,
        ]:
            raise Rejected("helper invocation receipt mismatch")
        summary = json.loads(base64.b64decode(result["stdout_base64"], validate=True))
        if (
            result["returncode"] != 0
            or base64.b64decode(result["stderr_base64"], validate=True)
            or summary != handles["summary"]
        ):
            raise Rejected("helper result/handle mismatch")
        runtime = collected["runtime"]
        if runtime["path"] != summary.get("private_runtime"):
            raise Rejected("runtime receipt mismatch")
        files = {}
        for record in runtime["files"]:
            raw = base64.b64decode(record["base64"], validate=True)
            if (
                Path(record["path"]).parent != Path(runtime["path"])
                or len(raw) != record["bytes"]
                or hashlib.sha256(raw).hexdigest() != record["sha256"]
            ):
                raise Rejected("runtime file receipt mismatch")
            files[Path(record["path"]).name] = raw
        evidence = json.loads(files["evidence.json"])
        if evidence.get("source_sha256") != HELPER_SHA256:
            raise Rejected("runtime source mismatch")
        if phase == "check" and (
            evidence.get("fixed_owner_checked") is not True
            or summary.get("fixed_owner_checked") is not True
        ):
            raise Rejected("check receipt rejected")
        if phase != "check":
            if (
                evidence.get("mode") != phase
                or evidence.get("cancellation_verified")
                is not (phase in ("show-version", "configurations"))
                or evidence.get("prompt_freshness_verified")
                is not (phase in ("show-version", "configurations"))
            ):
                raise Rejected("probe mode or cancellation mismatch")
            if phase in ("probe-prompt", "show-version", "configurations") and (
                evidence.get("probe_attempted") is not True
                or evidence.get("probe_input_hex") != "03"
                or not evidence.get("probe_dispatch_returned_at")
            ):
                raise Rejected("fixed probe receipt mismatch")
            if phase == "capture" and evidence.get("probe_attempted") is not False:
                raise Rejected("passive capture input mismatch")
            if phase == "configurations":
                verify_configurations(evidence, files["window-output.log"])
            if phase == "show-version":
                verify_version(evidence, files["window-output.log"])
            runner = json.loads(files["runner.json"])
            terminal = events[-2]
            if (
                summary.get("operation_complete") is not True
                or summary.get("cleanup_complete") is not True
                or summary.get("runner_terminal") is not True
                or summary.get("runner_exit_status") != 0
                or summary.get("pending_retained") is not False
                or runner.get("source_sha256") != HELPER_SHA256
                or runner.get("pid") != summary.get("runner_pid")
                or terminal.get("runner_pid") != runner.get("pid")
                or terminal.get("runner_starttime") != runner.get("starttime")
                or terminal.get("runner_epoch_absent") is not True
                or evidence.get("cleanup_complete") is not True
                or evidence.get("owner_source_sha256") != SERIAL_SHA256
                or evidence.get("log_bytes") != len(files["window-output.log"])
                or base64.b64decode(evidence["log_base64"], validate=True)
                != files["window-output.log"]
                or evidence.get("log_sha256")
                != hashlib.sha256(files["window-output.log"]).hexdigest()
            ):
                raise Rejected("capture receipt binding mismatch")
    final = events[-1]
    if (
        final.get("source_stage") != stage
        or final.get("operation_complete") is not True
        or final.get("source_stage_removed") is not True
    ):
        raise Rejected("remote cleanup receipt mismatch")


def invoke(mode):
    if mode not in (
        "check",
        "capture",
        "probe-prompt",
        "show-version",
        "configurations",
    ):
        raise Rejected("unsupported invocation mode")
    helper = bound_read(DIRECTORY / "pikvm-screen-capture.py", HELPER_SHA256)
    serial = bound_read(DIRECTORY / "inspect-pikvm-serial.py", SERIAL_SHA256)
    pin = bound_read(PIN, PIN_SHA256, private=True)
    ARTIFACT_PARENT.mkdir(mode=0o700, exist_ok=True)
    parent = ARTIFACT_PARENT.lstat()
    if (
        not stat.S_ISDIR(parent.st_mode)
        or parent.st_uid != os.getuid()
        or stat.S_IMODE(parent.st_mode) != 0o700
    ):
        raise Rejected("private artifact parent custody mismatch")
    artifact = Path(tempfile.mkdtemp(prefix="invoke-", dir=ARTIFACT_PARENT))
    artifact.chmod(0o700)
    argv = ssh_argv()
    payload = json.dumps(
        {
            "mode": mode,
            "helper_base64": base64.b64encode(helper).decode("ascii"),
            "serial_base64": base64.b64encode(serial).decode("ascii"),
        }
    ).encode()
    for name, data in (
        ("helper.py", helper),
        ("serial.py", serial),
        ("remote-controller.py", REMOTE_SOURCE.encode()),
        ("known_hosts", pin),
        ("payload.json", payload),
        ("argv.json", json.dumps(argv).encode()),
    ):
        private_write(artifact / name, data)
    receipt = {
        "mode": mode,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "controller_source_sha256": hashlib.sha256(
            Path(__file__).read_bytes()
        ).hexdigest(),
        "helper_sha256": HELPER_SHA256,
        "serial_sha256": SERIAL_SHA256,
        "pin_sha256": PIN_SHA256,
        "private_artifact": str(artifact),
        "operation_complete": False,
        "source_stage_removed": False,
        "restore_verified": False,
    }
    try:
        bound_read(PIN, PIN_SHA256, private=True)
        code, stdout, stderr, failure = transport(argv, payload)
        receipt.update({"ssh_returncode": code, "transport_failure": failure})
        events = []
        for line in stdout.splitlines():
            try:
                value = json.loads(line)
                if isinstance(value, dict):
                    events.append(value)
                else:
                    receipt["incomplete_transport_record"] = True
            except (ValueError, UnicodeDecodeError):
                receipt["incomplete_transport_record"] = True
        for event in events:
            stage = event.get("source_stage")
            if (
                isinstance(stage, str)
                and Path(stage).parent == Path("/tmp")
                and Path(stage).name.startswith("pikvm-screen-source-")
            ):
                receipt["remote_source_stage"] = stage
            if event.get("event") == "helper-handles":
                summary = event.get("summary", {})
                if isinstance(summary, dict):
                    path = summary.get("private_runtime")
                    if (
                        isinstance(path, str)
                        and Path(path).parent == Path("/tmp")
                        and Path(path).name.startswith(
                            ("pikvm-screen-check-", "pikvm-screen-capture-")
                        )
                    ):
                        receipt["private_runtime"] = path
                    for key in ("runner_pid", "runner_exit_status"):
                        if type(summary.get(key)) is int:
                            receipt[key] = summary[key]
                    for key in ("runner_terminal", "pending_retained"):
                        if type(summary.get(key)) is bool:
                            receipt[key] = summary[key]
            if (
                event.get("event") == "runner-terminal-verified"
                and type(event.get("runner_starttime")) is int
            ):
                receipt["runner_starttime"] = event["runner_starttime"]
        final = events[-1] if events else {}
        pending = final.get("pending", {})
        if isinstance(pending, dict) and isinstance(pending.get("runtime"), dict):
            pending_runtime = pending["runtime"]
            path = pending_runtime.get("path")
            if (
                isinstance(path, str)
                and Path(path).parent == Path("/tmp")
                and Path(path).name.startswith("pikvm-screen-capture-")
            ):
                receipt["pending_private_runtime"] = path
                for item in pending_runtime.get("files", []):
                    if Path(item.get("path", "")).name == "runner.json":
                        try:
                            runner = json.loads(
                                base64.b64decode(item["base64"], validate=True)
                            )
                            if runner.get("source_sha256") == HELPER_SHA256:
                                for key in ("pid", "starttime"):
                                    if type(runner.get(key)) is int and runner[key] > 0:
                                        receipt["pending_runner_" + key] = runner[key]
                        except (ValueError, KeyError, UnicodeDecodeError):
                            receipt["pending_handle_parse_failed"] = True
        if final.get("operation_complete") is True:
            validate_events(events, mode)
            receipt["source_stage_removed"] = final.get("source_stage_removed") is True
        private_write(artifact / "ssh.stdout", stdout)
        private_write(artifact / "ssh.stderr", stderr)
        private_write(artifact / "remote-events.json", json.dumps(events).encode())
        receipt["operation_complete"] = (
            code == 0
            and failure is None
            and not stderr
            and not receipt.get("incomplete_transport_record")
            and final.get("event") == "complete"
            and final.get("operation_complete") is True
            and final.get("source_stage_removed") is True
        )
    except Exception as error:
        receipt["exception_type"] = type(error).__name__
        receipt["operation_complete"] = False
    receipt["completed_at"] = datetime.now(timezone.utc).isoformat()
    try:
        private_write(artifact / "receipt.json", json.dumps(receipt).encode())
        receipt["receipt_written"] = True
    except Exception as error:
        receipt["operation_complete"] = False
        receipt["receipt_written"] = False
        receipt["receipt_persistence_failure"] = type(error).__name__
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--check", action="store_true")
    action.add_argument("--capture", action="store_true")
    action.add_argument("--probe-prompt", action="store_true")
    action.add_argument("--show-version", action="store_true")
    action.add_argument("--configurations", action="store_true")
    args = parser.parse_args()
    try:
        result = invoke(
            "configurations"
            if args.configurations
            else "show-version"
            if args.show_version
            else "probe-prompt"
            if args.probe_prompt
            else "capture"
            if args.capture
            else "check"
        )
    except Exception as error:
        print(
            json.dumps(
                {"operation_complete": False, "exception_type": type(error).__name__}
            )
        )
        return 2
    # Raw terminal output, source bodies and complete remote receipts stay private.
    allowed = (
        "operation_complete",
        "private_artifact",
        "remote_source_stage",
        "source_stage_removed",
        "private_runtime",
        "runner_pid",
        "pending_private_runtime",
        "pending_runner_pid",
        "pending_runner_starttime",
        "runner_starttime",
        "receipt_written",
        "runner_terminal",
        "runner_exit_status",
        "pending_retained",
        "restore_verified",
    )
    print(json.dumps({key: result[key] for key in allowed if key in result}))
    return 0 if result["operation_complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
