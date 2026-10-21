#!/usr/bin/env python3
"""Observe the fixed SCREEN window or perform bounded fixed serial reads."""

import argparse
import base64
from datetime import datetime, timezone
import fcntl
import hashlib
from importlib.util import module_from_spec, spec_from_file_location
import json
import os
from pathlib import Path
import platform
import re
import signal
import stat
import subprocess
import tempfile
import time

OWNER_PATH = Path(__file__).with_name("inspect-pikvm-serial.py").resolve()
OWNER_SHA256 = "6e1ffbd8acee89f5c9b53c325b3a0a6d7e5d98c69106c241d9ca18d09de9015d"
BINARY_SHA256 = "37ddde69ebad045aa1b71bb902c9a33ad1de6a26ae8a65e1b146d9d808af15c9"
SESSION = "78187.m7-brocade-console"
SCREEN_DIRECTORY = Path("/tmp/screen-root")
TITLE = "ttyUSB0"
DURATION = 10.0
VERSION_DURATION = 40.0
CONFIGURATION_DURATION = 120.0
CONFIGURATION_PAGER_LIMIT = 32
CURRENT_CONFIGURATION_SHA256 = (
    "97997daab378af8467dcb05244f2f9c03b2df33c694d373c1dc4a891cb4bbb3b"
)
PAGER = b"--More--, next page: Space, next line: Return key, quit: Control-c"
PAGER_LIMIT = 4
POE_ROWS = (
    "PoE Info: Resetting module in slot 1....completed.",
    "PoE Error: Device 0 failed to start on PoE module.",
    "PoE Error: Device 1 failed to start on PoE module.",
    "Resetting module in slot 1 again to recover from dev fault",
    "PoE Info: Hard Resetting in slot 1....",
)
MAX_BYTES = 1024 * 1024
LOCK_PATH = Path("/tmp/pikvm-screen-capture.lock")
PENDING_PATH = Path("/tmp/pikvm-screen-capture.pending.json")
# Observed kernel socket inode; distinct from the filesystem session socket inode.
EXPECTED_SOCKET_KERNEL_INODE = 493094
INFO = re.compile(
    r"\(([1-9][0-9]*),([1-9][0-9]*)\)/\(80,24\)\+100 \+(?:\(\+\))?flow"
    r"( log)? \{([A-Z!() ]+)\} 0\(" + re.escape(TITLE) + r"\)\n?"
)


DENIED = re.compile(
    r"(?:not authorized|access denied|permission denied|insufficient privilege|not allowed|command authorization failed)",
    re.I,
)


class Rejected(Exception):
    """Fixed owner, logging state or capture custody was not established."""


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def owner_module():
    if digest(OWNER_PATH) != OWNER_SHA256:
        raise Rejected("serial inspector source drift")
    spec = spec_from_file_location("capture_serial_owner", OWNER_PATH)
    if spec is None or spec.loader is None:
        raise Rejected("serial inspector unavailable")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse_info(raw):
    if len(raw) > 2048:
        raise Rejected("oversized SCREEN info")
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError as error:
        raise Rejected("non-ASCII SCREEN info") from error
    match = INFO.fullmatch(text)
    if match is None or int(match[1]) > 81 or int(match[2]) > 24:
        raise Rejected("incomplete or unexpected window0 info")
    # SCREEN reports width + 1 while the last-column character awaits wrapping.
    # Modem observations and cursor position can change with incoming output.
    return bool(match[3])


def process_starttime(pid):
    raw = Path(f"/proc/{pid}/stat").read_text()
    return int(raw[raw.rfind(")") + 1 :].split()[19])


def private_json(path, value):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(value, stream)
        stream.flush()
        os.fsync(stream.fileno())
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


class Controller:
    def __init__(self):
        self.source_sha256 = digest(Path(__file__))
        self.owner = owner_module()
        self.queries = []

    def command(self, operation, path=None):
        if operation == "info" and path is None:
            suffix = ["-Q", "info"]
        elif operation == "template" and isinstance(path, OwnedFile):
            path.verify()
            suffix = ["-X", "logfile", str(path.path)]
        elif operation == "probe" and path is None:
            suffix = ["-X", "stuff", "\x03"]
        elif operation == "version" and path is None:
            suffix = ["-X", "stuff", "show version\r"]
        elif operation == "running" and path is None:
            suffix = ["-X", "stuff", "show running-config\r"]
        elif operation == "startup" and path is None:
            suffix = ["-X", "stuff", "show configuration\r"]
        elif operation == "page" and path is None:
            suffix = ["-X", "stuff", " "]
        elif operation in ("on", "off") and path is None:
            suffix = ["-X", "log", operation]
        else:
            raise Rejected("unsupported SCREEN operation")
        argv = [self.owner.EXE, "-S", SESSION, "-p", "0", *suffix]
        attempt = {
            "operation": operation,
            "argv": argv,
            "outcome": "attempted",
            "attempted_at": datetime.now(timezone.utc).isoformat(),
        }
        self.queries.append(attempt)
        try:
            result = subprocess.run(
                argv,
                env={"SCREENDIR": str(SCREEN_DIRECTORY), "PATH": "/usr/bin:/bin"},
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=2,
                check=False,
                shell=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            attempt["outcome"] = type(error).__name__
            if isinstance(error, subprocess.TimeoutExpired):
                for key, value in (("stdout", error.stdout), ("stderr", error.stderr)):
                    raw = value.encode() if isinstance(value, str) else value or b""
                    attempt[key + "_base64"] = base64.b64encode(raw).decode("ascii")
            raise
        attempt.update(
            {
                "outcome": "returned",
                "returncode": result.returncode,
                "stdout_base64": base64.b64encode(result.stdout).decode("ascii"),
                "stderr_base64": base64.b64encode(result.stderr).decode("ascii"),
            }
        )
        if result.returncode or result.stderr or len(result.stdout) > 2048:
            raise Rejected("SCREEN command failed")
        return result.stdout

    def state(self):
        owner = self.owner
        if (
            os.getuid() != 0
            or platform.machine() != owner.MACHINE
            or platform.release() != owner.KERNEL
        ):
            raise Rejected("unexpected root PiKVM context")
        if (
            digest(Path(__file__)) != self.source_sha256
            or digest(OWNER_PATH) != OWNER_SHA256
            or digest(Path(owner.EXE)) != BINARY_SHA256
        ):
            raise Rejected("source or installed binary drift")
        before = owner.snapshot()
        directory = SCREEN_DIRECTORY.lstat()
        socket = (SCREEN_DIRECTORY / SESSION).lstat()
        if (
            not stat.S_ISDIR(directory.st_mode)
            or directory.st_uid != 0
            or stat.S_IMODE(directory.st_mode) != 0o700
        ):
            raise Rejected("SCREEN directory custody mismatch")
        if (
            not stat.S_ISSOCK(socket.st_mode)
            or socket.st_uid != 0
            or socket.st_nlink != 1
            or stat.S_IMODE(socket.st_mode) != 0o600
        ):
            raise Rejected("SCREEN session is not the fixed detached session")
        serial = owner.inspect()
        descriptors = {}
        for entry in (owner.PROC / "fd").iterdir():
            info = entry.stat()
            descriptors[entry.name] = (
                os.readlink(entry),
                info.st_dev,
                info.st_ino,
                stat.S_IFMT(info.st_mode),
            )
        logging = parse_info(self.command("info"))
        after_descriptors = {}
        for entry in (owner.PROC / "fd").iterdir():
            info = entry.stat()
            after_descriptors[entry.name] = (
                os.readlink(entry),
                info.st_dev,
                info.st_ino,
                stat.S_IFMT(info.st_mode),
            )
        after_socket = (SCREEN_DIRECTORY / SESSION).lstat()
        if (
            owner.snapshot() != before
            or after_descriptors != descriptors
            or (
                after_socket.st_dev,
                after_socket.st_ino,
                stat.S_IMODE(after_socket.st_mode),
            )
            != (socket.st_dev, socket.st_ino, 0o600)
        ):
            raise Rejected("owner or descriptors changed during state query")
        return {
            "owner": before,
            "settings": serial["settings"],
            "directory": (directory.st_dev, directory.st_ino),
            "socket": (socket.st_dev, socket.st_ino),
            "fds": descriptors,
            "logging": logging,
        }


def initial(state):
    expected = {
        "0": "/dev/null",
        "1": "/dev/null",
        "2": "/dev/null",
        "3": f"socket:[{EXPECTED_SOCKET_KERNEL_INODE}]",
        "4": "/dev/ttyUSB0",
    }
    kinds = {
        "0": stat.S_IFCHR,
        "1": stat.S_IFCHR,
        "2": stat.S_IFCHR,
        "3": stat.S_IFSOCK,
        "4": stat.S_IFCHR,
    }
    if (
        state["logging"]
        or {key: value[3] for key, value in state["fds"].items()} != kinds
        or {key: value[0] for key, value in state["fds"].items()} != expected
    ):
        raise Rejected("initial logging is on or unexpected owner descriptors exist")


def compare(before, current, owned):
    for key in ("owner", "settings", "directory", "socket"):
        if before[key] != current[key]:
            raise Rejected("owner, settings or session changed")
    baseline = current["fds"].copy()
    matches = []
    for key, value in list(baseline.items()):
        if owned is not None and value[1:3] == owned.identity:
            if value[0] != str(owned.path) or value[3] != stat.S_IFREG:
                raise Rejected("capture descriptor custody mismatch")
            matches.append(key)
            del baseline[key]
    if baseline != before["fds"] or len(matches) > 1:
        raise Rejected("unexpected or changed owner descriptor")
    return bool(matches)


class OwnedFile:
    def __init__(self, runtime):
        self.path = runtime / "window-output.log"
        info = runtime.lstat()
        self.directory = (info.st_dev, info.st_ino)
        fd = os.open(
            self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
        )
        try:
            info = os.fstat(fd)
            self.identity = (info.st_dev, info.st_ino)
        finally:
            os.close(fd)
        self.prefix = b""
        self.verify()

    def verify(self):
        directory = self.path.parent.lstat()
        info = self.path.lstat()
        if (
            (directory.st_dev, directory.st_ino) != self.directory
            or not stat.S_ISDIR(directory.st_mode)
            or directory.st_uid != os.getuid()
            or stat.S_IMODE(directory.st_mode) != 0o700
        ):
            raise Rejected("capture directory custody mismatch")
        if (
            (info.st_dev, info.st_ino) != self.identity
            or not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or info.st_nlink != 1
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_size > MAX_BYTES
        ):
            raise Rejected("capture file custody or size mismatch")
        return info

    def read_prefix(self):
        before = self.verify()
        fd = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            opened = os.fstat(fd)

            def custody(item):
                return (
                    item.st_dev,
                    item.st_ino,
                    item.st_mode,
                    item.st_uid,
                    item.st_nlink,
                )

            if (
                custody(opened) != custody(before)
                or opened.st_size < before.st_size
                or opened.st_size > MAX_BYTES
            ):
                raise Rejected("append-prefix opening custody or size changed")
            size = opened.st_size
            if size < len(self.prefix):
                raise Rejected("capture prefix shrank")
            data = b""
            while len(data) < size:
                chunk = os.pread(fd, size - len(data), len(data))
                if not chunk:
                    raise Rejected("capture shortened during prefix read")
                data += chunk
            after = os.fstat(fd)
            current = self.verify()
            checks = (
                ("descriptor-custody", lambda: custody(after) != custody(opened)),
                ("path-custody", lambda: custody(current) != custody(opened)),
                ("descriptor-shrink", lambda: after.st_size < size),
                ("path-shrink", lambda: current.st_size < after.st_size),
                ("descriptor-byte-limit", lambda: after.st_size > MAX_BYTES),
                (
                    "same-size-mtime-change",
                    lambda: (
                        after.st_size == size
                        and after.st_mtime_ns != opened.st_mtime_ns
                    ),
                ),
                ("prefix-reread-mismatch", lambda: os.pread(fd, size, 0) != data),
                ("accepted-prefix-mismatch", lambda: not data.startswith(self.prefix)),
            )
            for clause, rejected in checks:
                if rejected():

                    def metadata(item):
                        return {
                            "device": item.st_dev,
                            "inode": item.st_ino,
                            "mode": item.st_mode,
                            "uid": item.st_uid,
                            "nlink": item.st_nlink,
                            "size": item.st_size,
                            "mtime_ns": item.st_mtime_ns,
                        }

                    diagnostic = {
                        "clause": clause,
                        "opened": metadata(opened),
                        "after": metadata(after),
                        "current": metadata(current),
                        "read_bytes": len(data),
                        "accepted_prefix_bytes": len(self.prefix),
                    }
                    raise Rejected(
                        "capture prefix rewrite, shrink or custody change: "
                        + json.dumps(diagnostic, sort_keys=True)
                    )
            self.prefix = data
            return data
        finally:
            os.close(fd)

    def read(self):
        before = self.verify()
        fd = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            opened = os.fstat(fd)
            if (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns) != (
                before.st_dev,
                before.st_ino,
                before.st_size,
                before.st_mtime_ns,
            ):
                raise Rejected("capture changed while opening")
            with os.fdopen(fd, "rb", closefd=False) as stream:
                data = stream.read(MAX_BYTES + 1)
            after = self.verify()
            if len(data) != before.st_size or (after.st_size, after.st_mtime_ns) != (
                before.st_size,
                before.st_mtime_ns,
            ):
                raise Rejected("capture changed while reading")
            return data
        finally:
            os.close(fd)


def classify_prompt(data):
    # This is a log suffix observation, not proof of freshness or cancellation.
    last = data.replace(b"\r\n", b"\n").split(b"\n")[-1]
    if last == b"headwater>":
        return "unprivileged-prompt"
    if last == b"headwater#":
        return "privileged-prompt"
    if last in (b"Username:", b"login:", b"Login:"):
        return "login-prompt"
    if last in (b"Password:", b"password:"):
        return "password-prompt"
    return "unknown"


def qualified_lines(data):
    text = data.decode("ascii")
    text = text.replace("\r\n", "\n").replace("\n\r", "\n").replace("\r", "\n")
    if any(ord(char) < 32 and char not in "\n\t" or ord(char) == 127 for char in text):
        raise Rejected("unexpected response control")
    lines = []
    for line in text.split("\n"):
        line = line.rstrip(" \t")
        if line in POE_ROWS:
            continue
        if line.startswith("headwater#") and line[len("headwater#") :] in POE_ROWS:
            line = "headwater#"
        if line:
            lines.append(line)
    return lines


def cancellation_prompt(data):
    return qualified_lines(data) == ["^C", "headwater#"]


def invalid_version_line(line):
    return bool(DENIED.search(line)) or bool(
        re.search(
            r"(?:Invalid (?:input|command)|Unknown command|Access denied|Error:|Username:|Password:|headwater[>(#]|^(?:PoE |Resetting module))",
            line,
            re.I,
        )
    )


def without_known_noise(data):
    rows = b"|".join(re.escape(row.encode("ascii")) for row in POE_ROWS)
    newline = rb"(?:\r\n|\n\r|\n|\r)"
    # Exact complete asynchronous rows may follow a pager with a line separator.
    pager_noise = (
        re.escape(PAGER)
        + rb"(?:"
        + newline
        + rb"?(?:"
        + rows
        + rb")"
        + newline
        + rb")+"
    )
    data = re.sub(pager_noise, lambda match: PAGER, data)
    pattern = (
        rb"(?:^|(?<=\n)|(?<=\r)|(?<=headwater#)|(?<=Control-c))"
        + rb"(?:"
        + rows
        + rb")(?:\r\n|\n\r|\n|\r)"
    )
    return re.sub(pattern, b"", data)


def strip_version_prompt_noise(data):
    marker = b"headwater#"
    position = data.rfind(marker)
    if position < 0:
        return data
    end = position + len(marker)
    tail = data[end:]
    if not tail:
        return data
    try:
        text = tail.decode("ascii")
    except UnicodeDecodeError as error:
        raise Rejected("non-ASCII output after version prompt") from error
    text = re.sub(r"^(?:\r\n|\n\r|\r|\n)+", "", text)
    terminated = text.endswith(("\r", "\n"))
    lines = re.split(r"\r\n|\n\r|\r|\n", text)
    if terminated:
        lines = lines[:-1]
    known = set(POE_ROWS)
    for index, line in enumerate(lines):
        if line in known:
            continue
        if (
            index == len(lines) - 1
            and not terminated
            and any(row.startswith(line) for row in POE_ROWS)
        ):
            continue
        raise Rejected("unexpected output after version prompt")
    return data[:end]


def version_progress(data, spaces):
    data = without_known_noise(data)
    erased = PAGER + b"\x08 \x08" * len(PAGER)
    consumed = data.count(erased)
    if consumed > spaces or consumed > PAGER_LIMIT:
        raise Rejected("unexpected pager chronology")
    cleaned = data.replace(erased, b"")
    if cleaned.endswith(PAGER):
        if cleaned.count(PAGER) != 1:
            raise Rejected("unexpected pager count")
        prefix = qualified_lines(cleaned[: -len(PAGER)])
        if (
            not prefix
            or prefix[0] != "show version"
            or prefix.count("show version") != 1
            or any(invalid_version_line(line) for line in prefix)
        ):
            raise Rejected("pager prefix echo, denial or error")
        # One dispatch for each fully observed pager; wait for its exact erasure.
        return "page" if consumed == spaces else "wait"
    if b"--More--" in cleaned or b"\x08" in cleaned:
        # A split pager/erasure is unresolved and cannot authorize input.
        return "wait"
    cleaned = strip_version_prompt_noise(cleaned)
    lines = qualified_lines(cleaned)
    if any(
        re.search(
            r"(?:Invalid (?:input|command)|Unknown command|Access denied|Error:|Username:|Password:|headwater>|headwater\()",
            line,
            re.I,
        )
        for line in lines
    ):
        raise Rejected("version response denial or changed prompt")
    if not lines or lines[-1] != "headwater#":
        return "wait"
    if any(invalid_version_line(line) for line in lines[:-1]):
        raise Rejected("unmatched diagnostic or unexpected prompt in version")
    if (
        lines[0] != "show version"
        or lines.count("show version") != 1
        or len(lines) < 5
        or re.findall(r"\bSW:\s+Version\s+(\S+)", "\n".join(lines)) != ["08.0.30uT7f3"]
        or re.findall(
            r"^UNIT 1: SL 1: (ICX\d+-\S+) POE.*Management Module$",
            "\n".join(lines),
            re.M,
        )
        != ["ICX6610-48P"]
        or not re.fullmatch(
            r'[ \t]*The system\s*:\s*started=(?:cold start|warm start(?:\t reloaded=by "reload")?)',
            lines[-2],
        )
    ):
        raise Rejected("incomplete or wrong version boundary")
    return "complete"


def configuration_progress(data, operation, spaces):
    command = {"running": "show running-config", "startup": "show configuration"}[
        operation
    ]
    data = without_known_noise(data)
    erased = PAGER + b"\x08 \x08" * len(PAGER)
    consumed = data.count(erased)
    if consumed > spaces or consumed > CONFIGURATION_PAGER_LIMIT:
        raise Rejected("configuration pager chronology")
    cleaned = data.replace(erased, b"")
    if cleaned.endswith(PAGER):
        if cleaned.count(PAGER) != 1:
            raise Rejected("configuration pager count")
        lines = qualified_lines(cleaned[: -len(PAGER)])
        if (
            not lines
            or lines[0] != command
            or any(
                invalid_version_line(line)
                or line == "end"
                or line.lstrip(" \t").startswith("%")
                for line in lines[1:]
            )
        ):
            raise Rejected("configuration pager echo, prompt or error")
        return ("page" if consumed == spaces else "wait"), ()
    if b"--More--" in cleaned or b"\x08" in cleaned:
        return "wait", ()
    marker = b"headwater#"
    position = cleaned.rfind(marker)
    if position >= 0:
        end = position + len(marker)
        tail = cleaned[end:]
        if tail and any(row.encode("ascii").startswith(tail) for row in POE_ROWS):
            # A known asynchronous row is incomplete; prove the preceding response
            # before waiting within the caller's original read deadline.
            progress, _ = configuration_progress(cleaned[:end], operation, spaces)
            if progress == "complete":
                return "wait", ()
    lines = qualified_lines(cleaned)
    if any(
        re.search(
            r"(?:Invalid (?:input|command)|Unknown command|Access denied|Error:|Username:|Password:|headwater>|headwater\()",
            line,
            re.I,
        )
        or DENIED.search(line)
        or line.lstrip(" \t").startswith("%")
        for line in lines
    ):
        raise Rejected("configuration denial or changed prompt")
    if not lines or lines[-1] != "headwater#":
        return "wait", ()
    if lines[0] != command or any(invalid_version_line(line) for line in lines[1:-1]):
        raise Rejected("configuration echo, diagnostic or unexpected prompt")
    body = tuple(lines[1:-1])
    start = [
        index
        for index, line in enumerate(body)
        if re.fullmatch(r"(?:ver|version) 08\.0\.30uT7f3", line)
    ]
    if len(start) != 1 or not body or body[-1] != "end":
        raise Rejected("configuration version or end boundary")
    for line in body[: start[0]]:
        if not re.fullmatch(
            r"(?:Current configuration:.*|Startup configuration:.*|Startup-config data location is flash memory|!|\d+ bytes)",
            line,
        ):
            raise Rejected("unrecognized configuration header")
    canonical = body[start[0] :]
    if "end" in canonical[:-1]:
        raise Rejected("early configuration end")
    return "complete", canonical


def canonical_hash(lines):
    return hashlib.sha256(("\n".join(lines) + "\n").encode("ascii")).hexdigest()


def guarded_input(
    controller, before, owned, evidence, operation, interrupted, deadline
):
    if interrupted() or time.monotonic() >= deadline:
        raise Rejected("input interrupted or deadline expired")
    current = controller.state()
    evidence["last_observed_state"] = current
    if not compare(before, current, owned) or not current["logging"]:
        raise Rejected("input logger ownership lost")
    owned.verify()
    if interrupted() or time.monotonic() >= deadline:
        raise Rejected("input interrupted or expired after guard")
    attempt = {
        "operation": operation,
        "input_hex": {
            "probe": "03",
            "version": "73686f772076657273696f6e0d",
            "page": "20",
            "running": b"show running-config\r".hex(),
            "startup": b"show configuration\r".hex(),
        }[operation],
        "attempted_at": datetime.now(timezone.utc).isoformat(),
    }
    evidence["serial_input_attempts"].append(attempt)
    if operation == "probe":
        evidence["probe_attempted"] = True
        evidence["probe_input_hex"] = "03"
        evidence["probe_attempted_at"] = attempt["attempted_at"]
    controller.command(operation)
    attempt["dispatch_returned_at"] = datetime.now(timezone.utc).isoformat()


def checkpoint(controller, before, owned, evidence, interrupted, deadline):
    if interrupted() or time.monotonic() >= deadline:
        raise Rejected("prefix observation interrupted or expired")
    current = controller.state()
    evidence["last_observed_state"] = current
    if not current["logging"] or not compare(before, current, owned):
        raise Rejected("prefix observation logger not owned")
    data = owned.read_prefix()
    current = controller.state()
    evidence["last_observed_state"] = current
    if not current["logging"] or not compare(before, current, owned):
        raise Rejected("prefix observation logger ownership changed")
    evidence["append_prefix_observations"].append(
        {
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "logging_verified_on": True,
        }
    )
    if interrupted() or time.monotonic() >= deadline:
        raise Rejected("prefix observation interrupted or expired")
    return data


def qualify_cancel(controller, before, owned, evidence, interrupted, deadline):
    guarded_input(controller, before, owned, evidence, "probe", interrupted, deadline)
    evidence["probe_attempted"] = True
    evidence["probe_input_hex"] = "03"
    evidence["probe_dispatch_returned_at"] = datetime.now(timezone.utc).isoformat()
    while True:
        time.sleep(0.1)
        data = checkpoint(controller, before, owned, evidence, interrupted, deadline)
        if cancellation_prompt(data):
            break
    evidence["empty_privileged_prompt_observed"] = True
    evidence["cancellation_verified"] = True
    evidence["prompt_freshness_verified"] = True
    evidence["qualified_cancel_bytes"] = len(data)
    evidence["qualified_cancel_sha256"] = hashlib.sha256(data).hexdigest()
    return data


def fixed_version(controller, before, owned, evidence, interrupted, deadline):
    data = qualify_cancel(controller, before, owned, evidence, interrupted, deadline)
    offset = len(data)
    guarded_input(controller, before, owned, evidence, "version", interrupted, deadline)
    spaces = 0
    while True:
        time.sleep(0.1)
        data = checkpoint(controller, before, owned, evidence, interrupted, deadline)
        progress = version_progress(data[offset:], spaces)
        if progress == "complete":
            evidence["version_response_complete"] = True
            evidence["show_version_complete"] = True
            evidence["version_response_offset"] = offset
            evidence["version_response_bytes"] = len(data) - offset
            evidence["version_response_sha256"] = hashlib.sha256(
                data[offset:]
            ).hexdigest()
            return
        if progress == "page":
            if spaces >= PAGER_LIMIT:
                raise Rejected("fixed pager limit reached")
            # Record intent before dispatch; uncertainty terminates, never retries.
            spaces += 1
            evidence["pager_space_attempts"] = spaces
            guarded_input(
                controller, before, owned, evidence, "page", interrupted, deadline
            )


def fixed_configurations(controller, before, owned, evidence, interrupted, deadline):
    data = qualify_cancel(controller, before, owned, evidence, interrupted, deadline)
    for operation, command in (
        ("running", "show running-config"),
        ("startup", "show configuration"),
    ):
        offset = len(data)
        guarded_input(
            controller, before, owned, evidence, operation, interrupted, deadline
        )
        spaces = 0
        while True:
            time.sleep(0.1)
            data = checkpoint(
                controller, before, owned, evidence, interrupted, deadline
            )
            progress, canonical = configuration_progress(
                data[offset:], operation, spaces
            )
            if progress == "complete":
                digest = canonical_hash(canonical)
                evidence["configuration_responses"].append(
                    {
                        "operation": operation,
                        "command": command,
                        "offset": offset,
                        "bytes": len(data) - offset,
                        "raw_sha256": hashlib.sha256(data[offset:]).hexdigest(),
                        "canonical_lines": canonical,
                        "canonical_sha256": digest,
                        "expected_current_sha256": CURRENT_CONFIGURATION_SHA256,
                        "matches_current_baseline": digest
                        == CURRENT_CONFIGURATION_SHA256,
                        "pager_space_attempts": spaces,
                        "completed_at": datetime.now(timezone.utc).isoformat(),
                    }
                )
                break
            if progress == "page":
                if spaces >= CONFIGURATION_PAGER_LIMIT:
                    raise Rejected("configuration pager limit")
                spaces += 1
                guarded_input(
                    controller, before, owned, evidence, "page", interrupted, deadline
                )
    evidence["configurations_complete"] = True


def lifecycle(
    controller,
    runtime,
    interrupted=lambda: False,
    duration=DURATION,
    probe=False,
    show_version=False,
    configurations=False,
):
    evidence = {
        "mode": "configurations"
        if configurations
        else "show-version"
        if show_version
        else "probe-prompt"
        if probe
        else "capture",
        "serial_input_attempts": [],
        "append_prefix_observations": [],
        "continuous_logging_required": show_version or configurations,
        "configurations_complete": False,
        "configuration_responses": [],
        "canonicalization_authority": "source-bound frozen helper configuration_progress",
        "controller_independent_canonicalization_verified": False,
        "buffer_flush_latency_verified": False,
        "empty_privileged_prompt_observed": False,
        "version_response_complete": False,
        "show_version_complete": False,
        "external_concurrent_input_absent_verified": False,
        "configuration_write_admitted": False,
        "probe_attempted": False,
        "cancellation_verified": False,
        "prompt_freshness_verified": False,
        "prompt_classification": "unknown",
        "prompts_observed": [],
        "started_at": datetime.now(timezone.utc).isoformat(),
        "runtime_retained": True,
        "runtime": str(runtime),
        "source_sha256": digest(Path(__file__)),
        "owner_source_sha256": OWNER_SHA256,
        "expected_installed_binary_sha256": BINARY_SHA256,
        "capture_scope": "SCREEN window-output log; possible SCREEN timestamp metadata",
        "prior_template_restored": False,
        "prior_template_observed": False,
        "raw_uart_byte_fidelity_verified": False,
        "command_stream_complete": False,
        "serial_control_verified": False,
        "independent_rescue_verified": False,
        "restore_verified": False,
        "task_complete": False,
        "atomic_state_ownership_verified": False,
        "capture_succeeded": False,
        "cleanup_complete": False,
        "cleanup_scope": "logging OFF, owned capture FD closed, original owner/settings/session unchanged; private artifacts retained",
        "logfile_adoption_verified": False,
        "enabled_intent": False,
        "configured_deadline_seconds": CONFIGURATION_DURATION
        if configurations
        else VERSION_DURATION
        if show_version
        else DURATION,
        "deadline_includes_command_cleanup_overhead": False,
        "hard_filesystem_size_cap_verified": False,
        "observed_size_rejection_limit": MAX_BYTES,
    }
    before = None
    owned = None
    try:
        before = controller.state()
        initial(before)
        evidence["before"] = before
        owned = OwnedFile(runtime)
        evidence["attempted_logfile_template"] = str(owned.path)
        evidence["owned_capture_identity"] = owned.identity
        evidence["owned_directory_identity"] = owned.directory
        if interrupted():
            raise Rejected("capture interrupted before template adoption")
        compare(before, controller.state(), None)
        controller.command("template", owned)
        compare(before, controller.state(), None)
        deadline = time.monotonic() + (
            min(duration, CONFIGURATION_DURATION)
            if configurations
            else min(duration, VERSION_DURATION)
            if show_version
            else min(duration, DURATION)
        )
        evidence["deadline_started_at"] = datetime.now(timezone.utc).isoformat()
        evidence["deadline_monotonic"] = deadline
        if interrupted():
            raise Rejected("capture interrupted before logging on")
        evidence["enabled_intent"] = True
        controller.command("on")
        while True:
            current = controller.state()
            evidence["last_observed_state"] = current
            if not compare(before, current, owned) or not current["logging"]:
                raise Rejected("logging did not retain the owned file")
            owned.verify()
            evidence["logfile_adoption_verified"] = True
            evidence.setdefault(
                "verified_logging_on_observed_at",
                datetime.now(timezone.utc).isoformat(),
            )
            if interrupted():
                raise Rejected("capture interrupted")
            if configurations:
                fixed_configurations(
                    controller, before, owned, evidence, interrupted, deadline
                )
                break
            if show_version:
                fixed_version(
                    controller, before, owned, evidence, interrupted, deadline
                )
                break
            if probe and not evidence["probe_attempted"]:
                if time.monotonic() >= deadline:
                    raise Rejected("probe deadline expired before input")
                guarded = controller.state()
                if not compare(before, guarded, owned) or not guarded["logging"]:
                    raise Rejected("probe logger ownership lost before input")
                owned.verify()
                if interrupted() or time.monotonic() >= deadline:
                    raise Rejected("probe interrupted or expired before input")
                evidence["probe_attempted"] = True
                evidence["probe_input_hex"] = "03"
                evidence["probe_attempted_at"] = datetime.now(timezone.utc).isoformat()
                controller.command("probe")
                evidence["probe_dispatch_returned_at"] = datetime.now(
                    timezone.utc
                ).isoformat()
            if time.monotonic() >= deadline:
                break
            time.sleep(0.05)
    except Exception as error:
        evidence["failure"] = type(error).__name__ + ": " + str(error)
    finally:
        if before is not None:
            try:
                current = controller.state()
                evidence["last_observed_state"] = current
                matching = compare(before, current, owned)
                if current["logging"] or matching:
                    if not evidence["enabled_intent"] or not matching or owned is None:
                        raise Rejected("cannot stop an unowned logger")
                    controller.command("off")
                    current = controller.state()
                    evidence["last_observed_state"] = current
                    matching = compare(before, current, owned)
                if current["logging"] or matching:
                    raise Rejected("logging off or descriptor closure unproved")
                evidence["after"] = current
                evidence["verified_logging_off_observed_at"] = datetime.now(
                    timezone.utc
                ).isoformat()
                evidence["cleanup_complete"] = True
                if owned is not None:
                    data = owned.read()
                    if not data.startswith(owned.prefix):
                        raise Rejected("final capture prefix changed")
                    evidence["log_base64"] = base64.b64encode(data).decode("ascii")
                    evidence["log_bytes"] = len(data)
                    evidence["log_sha256"] = hashlib.sha256(data).hexdigest()
                    if configurations and evidence["configurations_complete"]:
                        evidence["configurations_complete"] = False
                        records = evidence["configuration_responses"]
                        for index, record in enumerate(records):
                            end = (
                                records[index + 1]["offset"]
                                if index + 1 < len(records)
                                else len(data)
                            )
                            segment = data[record["offset"] : end]
                            progress, canonical = configuration_progress(
                                segment,
                                record["operation"],
                                record["pager_space_attempts"],
                            )
                            if (
                                progress != "complete"
                                or canonical_hash(canonical)
                                != record["canonical_sha256"]
                            ):
                                raise Rejected("final flushed configuration changed")
                            record["bytes"] = len(segment)
                            record["raw_sha256"] = hashlib.sha256(segment).hexdigest()
                        evidence["configurations_complete"] = True
                    if show_version and evidence["show_version_complete"]:
                        offset = evidence["version_response_offset"]
                        evidence["show_version_complete"] = False
                        evidence["version_response_complete"] = False
                        if (
                            version_progress(
                                data[offset:], evidence.get("pager_space_attempts", 0)
                            )
                            != "complete"
                        ):
                            evidence["show_version_complete"] = False
                            evidence["version_response_complete"] = False
                            raise Rejected("final flushed version boundary changed")
                        evidence["show_version_complete"] = True
                        evidence["version_response_complete"] = True
                        evidence["version_response_bytes"] = len(data) - offset
                        evidence["version_response_sha256"] = hashlib.sha256(
                            data[offset:]
                        ).hexdigest()
                    if probe:
                        evidence["prompt_classification"] = classify_prompt(data)
                        evidence["prompts_observed"] = sorted(
                            {
                                classify_prompt(line)
                                for line in data.replace(b"\r\n", b"\n").split(b"\n")
                            }
                            - {"unknown"}
                        )
                evidence["capture_succeeded"] = "failure" not in evidence
            except Exception as error:
                evidence["cleanup_failure"] = type(error).__name__ + ": " + str(error)
        evidence["queries"] = controller.queries
        evidence["completed_at"] = datetime.now(timezone.utc).isoformat()
        try:
            private_json(runtime / "evidence.json", evidence)
        except Exception as error:
            raise Rejected(
                f"receipt_written=false; retained private runtime: {runtime}"
            ) from error
    return evidence


def capture_lock():
    fd = os.open(
        LOCK_PATH, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600
    )
    try:
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != 0
            or info.st_nlink != 1
            or stat.S_IMODE(info.st_mode) != 0o600
        ):
            raise Rejected("capture lock custody mismatch")
        linked = LOCK_PATH.lstat()
        if (linked.st_dev, linked.st_ino) != (info.st_dev, info.st_ino):
            raise Rejected("capture lock path changed")
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if PENDING_PATH.exists() or PENDING_PATH.is_symlink():
            raise Rejected("pending SCREEN capture requires independent reconciliation")
        return fd
    except Exception:
        os.close(fd)
        raise


def clear_pending(identity):
    info = PENDING_PATH.lstat()
    if (
        (info.st_dev, info.st_ino) != identity
        or not stat.S_ISREG(info.st_mode)
        or info.st_uid != 0
        or info.st_nlink != 1
        or stat.S_IMODE(info.st_mode) != 0o600
    ):
        raise Rejected("pending marker custody changed")
    PENDING_PATH.unlink()


def launch_capture(probe=False, show_version=False, configurations=False):
    # The detached local child survives launcher/SSH loss and owns the deadline.
    lock = capture_lock()
    runtime = Path(tempfile.mkdtemp(prefix="pikvm-screen-capture-", dir="/tmp"))
    runtime.chmod(0o700)
    private_json(
        PENDING_PATH,
        {
            "private_runtime": str(runtime),
            "source_sha256": digest(Path(__file__)),
            "cleanup_verified": False,
        },
    )
    pending_info = PENDING_PATH.lstat()
    pending_identity = (pending_info.st_dev, pending_info.st_ino)
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
            private_json(
                runtime / "runner.json",
                {
                    "pid": os.getpid(),
                    "starttime": process_starttime(os.getpid()),
                    "source_sha256": digest(Path(__file__)),
                },
            )
            result = lifecycle(
                Controller(),
                runtime,
                lambda: interrupted[0],
                duration=CONFIGURATION_DURATION
                if configurations
                else VERSION_DURATION
                if show_version
                else DURATION,
                probe=probe,
                show_version=show_version,
                configurations=configurations,
            )
            if result["cleanup_complete"]:
                clear_pending(pending_identity)
            os._exit(0)
        except BaseException as error:
            try:
                private_json(
                    runtime / "runner-failure.json",
                    {
                        "exception_type": type(error).__name__,
                        "runtime_retained": True,
                        "cleanup_complete": False,
                        "capture_succeeded": False,
                        "source_sha256": digest(Path(__file__)),
                    },
                )
            except BaseException:
                pass
            os._exit(2)
    os.close(lock)
    deadline = (
        time.monotonic()
        + (
            CONFIGURATION_DURATION
            if configurations
            else VERSION_DURATION
            if show_version
            else DURATION
        )
        + 15
    )
    while time.monotonic() < deadline:
        waited, status = os.waitpid(pid, os.WNOHANG)
        if waited:
            receipt = runtime / "evidence.json"
            result = json.loads(receipt.read_text()) if receipt.exists() else {}
            return {
                "private_runtime": str(runtime),
                "runner_pid": pid,
                "runner_terminal": True,
                "runner_exit_status": status,
                "receipt_written": receipt.exists(),
                "capture_succeeded": result.get("capture_succeeded", False),
                "cleanup_complete": result.get("cleanup_complete", False),
                "pending_retained": PENDING_PATH.exists(),
                "operation_complete": status == 0
                and not PENDING_PATH.exists()
                and result.get("capture_succeeded", False)
                and result.get("cleanup_complete", False),
            }
        time.sleep(0.05)
    return {
        "private_runtime": str(runtime),
        "runner_pid": pid,
        "runner_terminal": False,
        "receipt_written": False,
        "pending_retained": PENDING_PATH.exists(),
        "operation_complete": False,
        "capture_succeeded": False,
        "cleanup_complete": False,
    }


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
        if args.check:
            runtime = Path(tempfile.mkdtemp(prefix="pikvm-screen-check-", dir="/tmp"))
            runtime.chmod(0o700)
            controller = None
            evidence = {
                "source_sha256": digest(Path(__file__)),
                "capture_admitted": False,
                "runtime_retained": True,
                "restore_verified": False,
            }
            try:
                controller = Controller()
                state = controller.state()
                initial(state)
                evidence["state"] = state
                evidence["fixed_owner_checked"] = True
            except Exception as error:
                evidence["exception_type"] = type(error).__name__
                evidence["fixed_owner_checked"] = False
            evidence["queries"] = controller.queries if controller is not None else []
            private_json(runtime / "evidence.json", evidence)
            print(
                json.dumps(
                    {
                        "fixed_owner_checked": evidence["fixed_owner_checked"],
                        "private_runtime": str(runtime),
                        "capture_admitted": False,
                        "restore_verified": False,
                    }
                )
            )
            return 0 if evidence["fixed_owner_checked"] else 2
        result = (
            launch_capture(configurations=True)
            if args.configurations
            else launch_capture(show_version=True)
            if args.show_version
            else launch_capture(probe=True)
            if args.probe_prompt
            else launch_capture()
        )
        print(json.dumps(result))
        return 0 if result["operation_complete"] else 2
    except Exception as error:
        print(
            json.dumps(
                {"capture_succeeded": False, "exception_type": type(error).__name__}
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
