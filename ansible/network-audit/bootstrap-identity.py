#!/usr/bin/env python3
"""Pinned identity preflight and admitted, unpersisted account bootstrap."""

import argparse
from contextlib import contextmanager
from datetime import datetime
from zoneinfo import ZoneInfo
import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import stat
import sys
import tempfile
import threading
import time

from importlib.util import module_from_spec, spec_from_file_location

HOST = "192.168.0.251"
USER = "homelab_audit"
FINGERPRINT = "SHA256:UJulVmfAMmHcUctvJrlGzBZR7I7uN8/TWNeJIs25yks"
RELEASE = "08.0.30uT7f3"


def _timeout(deadline, maximum):
    if deadline is None:
        return maximum
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("operation deadline expired")
    return min(maximum, remaining)


def _bounded_channel_request(channel, transport, request, deadline):
    timeout = _timeout(deadline, 10)
    expired = threading.Event()

    def interrupt():
        expired.set()
        channel.close()
        try:
            transport.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass

    timer = threading.Timer(timeout, interrupt)
    timer.daemon = True
    timer.start()
    try:
        request()
    except Exception as exc:
        if expired.is_set():
            raise TimeoutError(
                "operation deadline expired during SSH channel setup"
            ) from exc
        raise
    finally:
        timer.cancel()
    if expired.is_set():
        raise TimeoutError("operation deadline expired during SSH channel setup")


COMMANDS = ("show version", "show running-config", "show configuration")
CONFIGURE = "configure terminal"
UNAVAILABLE = re.compile(
    r"configure terminal\nInvalid input -> configure terminal\n"
    r"Type \? for a list\n(?:SSH@)?headwater#"
)
PROMPT = re.compile(r"(?:^|\n)(?:SSH@)?headwater([>#])\s*$")
CONFIG_PROMPT = re.compile(r"(?:^|\n)(?:SSH@)?headwater\(config[^\r\n()]*\)#\s*$")
ANY_PROMPT = re.compile(PROMPT.pattern + "|" + CONFIG_PROMPT.pattern)
DENIED = re.compile(
    r"(?:not authorized|access denied|permission denied|insufficient privilege|"
    r"not allowed|command authorization failed)",
    re.I,
)
ERROR = re.compile(
    r"(?:^|\n)\s*%|invalid (?:input|command)|unknown command|not authorized|access denied|error:",
    re.I,
)


class Rejected(Exception):
    """An expected preflight gate failed; details must remain private."""


def cleaned(raw: str) -> str:
    text = re.sub(r"\x1b\[[0-9;]*m", "", raw)
    rendered = []
    for row in text.split("\n"):
        cells: list[str] = []
        cursor = 0
        for char in row:
            if char == "\r":
                cursor = 0
            elif char == "\x08":
                cursor = max(0, cursor - 1)
            elif char == "\t":
                stop = (cursor // 8 + 1) * 8
                while cursor < stop:
                    if cursor == len(cells):
                        cells.append(" ")
                    else:
                        cells[cursor] = " "
                    cursor += 1
            elif ord(char) < 32:
                raise Rejected("terminal control")
            else:
                if cursor == len(cells):
                    cells.append(char)
                else:
                    cells[cursor] = char
                cursor += 1
        rendered.append("".join(cells).replace("--More--", "").rstrip())
    return "\n".join(rendered)


class Console:
    def __init__(self, channel, password: str, runtime: Path):
        self.channel = channel
        self.password = password
        self.runtime = runtime
        self.sequence = 0

    def read(self, boundary, allow_errors=False, deadline=None):
        deadline = min(
            time.monotonic() + 20,
            deadline if deadline is not None else float("inf"),
        )
        raw = ""
        pages = 0
        while time.monotonic() < deadline:
            if self.channel.recv_ready():
                data = self.channel.recv(65536)
                if not data:
                    break
                chunk = data.decode("ascii", errors="strict")
                raw += chunk
                if len(raw) > 8 * 1024 * 1024:
                    raise Rejected("capture limit")
                # Handle a pager token split between SSH reads exactly once.
                new_pages = raw.count("--More--")
                if new_pages > pages:
                    if new_pages > 128:
                        raise Rejected("pager limit")
                    self.channel.sendall(" " * (new_pages - pages))
                    pages = new_pages
                try:
                    text = cleaned(raw)
                except Rejected:
                    self.save(raw)
                    raise
                if boundary.search(text):
                    self.save(raw)
                    if ERROR.search(text) and not allow_errors:
                        raise Rejected("device rejected command")
                    return text
            elif self.channel.closed:
                break
            else:
                time.sleep(0.01)
        self.save(raw)
        raise Rejected("incomplete response")

    def save(self, raw):
        self.sequence += 1
        path = self.runtime / f"capture-{self.sequence:02}.txt"
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w") as output:
            output.write(raw)

    def enable(self, username="root", deadline=None):
        if username not in ("root", USER):
            raise Rejected("enable identity boundary")
        initial = self.read(PROMPT, deadline=deadline)
        matched = PROMPT.search(initial)
        if matched is not None and matched.group(1) == "#" and username == USER:
            return
        if matched is None or matched.group(1) != ">":
            raise Rejected("unexpected initial privilege")
        self.channel.sendall("enable\r")
        self.read(re.compile(r"User Name:\s*$"), deadline=deadline)
        self.channel.sendall(username + "\r")
        self.read(re.compile(r"Password:\s*$"), deadline=deadline)
        self.channel.sendall(self.password + "\r")
        enabled = self.read(PROMPT, deadline=deadline)
        matched = PROMPT.search(enabled)
        if matched is None or matched.group(1) != "#":
            raise Rejected("enable failed")

    def command(self, command, audit=False, deadline=None):
        if command not in COMMANDS:
            raise Rejected("command outside preflight")
        self.channel.sendall(command + "\r")
        text = self.read(PROMPT, deadline=deadline)
        lines = text.strip().splitlines()
        matched = PROMPT.fullmatch(lines[-1])
        if (
            lines[0].strip() != command
            or matched is None
            or (matched.group(1) != "#" and not audit)
        ):
            raise Rejected("command boundary")
        return "\n".join(lines[1:-1])

    def configure(self, command):
        if command != f"no username {USER}" and not re.fullmatch(
            rf"username {USER} privilege 5 password [A-Za-z0-9]{{32,48}}", command
        ):
            raise Rejected("write command boundary")
        self.channel.sendall(CONFIGURE + "\r")
        entered = self.read(ANY_PROMPT)
        if not CONFIG_PROMPT.search(entered):
            raise Rejected("configuration entry failed")
        try:
            self.channel.sendall(command + "\r")
            response = self.read(ANY_PROMPT)
            if not CONFIG_PROMPT.search(response):
                raise Rejected("configuration command boundary")
        finally:
            self.channel.sendall("exit\r")
            exited = self.read(PROMPT)
            if not exited.rstrip().endswith("#"):
                raise Rejected("configuration exit failed")

    def deny_configuration(self, *, root_control: bool):
        self.channel.sendall(CONFIGURE + "\r")
        response = self.read(ANY_PROMPT, allow_errors=True)
        if CONFIG_PROMPT.search(response):
            self.channel.sendall("exit\r")
            self.read(PROMPT)
            raise Rejected("audit entered configuration")
        lines = response.strip().splitlines()
        prompt = PROMPT.fullmatch(lines[-1])
        unavailable = (
            root_control and UNAVAILABLE.fullmatch(response.strip()) is not None
        )
        if (
            lines[0].strip() != CONFIGURE
            or prompt is None
            or prompt.group(1) != "#"
            or not (DENIED.search(response) or unavailable)
        ):
            raise Rejected("configuration denial unproven")


def configuration(text: str) -> tuple[str, ...]:
    if ERROR.search(text):
        raise Rejected("configuration error")
    lines = tuple(line.rstrip() for line in text.splitlines() if line.strip())
    start = [
        i
        for i, line in enumerate(lines)
        if re.fullmatch(r"(?:ver|version) " + re.escape(RELEASE), line)
    ]
    if len(start) != 1 or not lines or lines[-1] != "end":
        raise Rejected("configuration boundary")
    for line in lines[: start[0]]:
        if not re.fullmatch(
            r"(?:Current configuration:.*|Startup configuration:.*|"
            r"Startup-config data location is flash memory|!|\d+ bytes)",
            line,
        ):
            raise Rejected("unrecognized configuration header")
    result = lines[start[0] :]
    if "end" in result[:-1]:
        raise Rejected("early configuration end")
    return result


def baseline(version: str, running: str, startup: str):
    if ERROR.search(version) or not re.search(
        r"\bSW:\s+Version\s+" + re.escape(RELEASE) + r"(?=\s|$)", version
    ):
        raise Rejected("release boundary")
    if not re.search(r"\bICX6610-48P(?=\s|$)", version):
        raise Rejected("model boundary")
    current = configuration(running)
    if current != configuration(startup):
        raise Rejected("unsaved differences")
    accounts = [line for line in current if line.lstrip().startswith("username ")]
    if len(accounts) != 1 or not re.match(r"username root\s", accounts[0]):
        raise Rejected("account conflict")
    if any(
        re.match(r"(?:privilege|aaa authorization)\b", line.lstrip())
        for line in current
    ):
        raise Rejected("privilege override")
    for method in ("login", "enable"):
        matching = [
            line
            for line in current
            if re.match(rf"aaa authentication {method}\b", line.lstrip())
        ]
        if matching != [f"aaa authentication {method} default local"]:
            raise Rejected("local AAA missing or conflicting")
    return current


def account_delta(before: tuple[str, ...], after: tuple[str, ...]):
    """Verify one exact privilege-5 account insertion without revealing its value."""
    additions = [line for line in after if line not in before]
    if len(additions) != 1 or not re.fullmatch(
        r"username homelab_audit privilege 5 password \S[^\r\n]*", additions[0]
    ):
        raise Rejected("account delta")
    if tuple(line for line in after if line != additions[0]) != before:
        raise Rejected("unrelated delta")


def paths(env):
    spec = spec_from_file_location(
        "audit_launcher", Path(__file__).with_name("run-audit.py")
    )
    if spec is None or spec.loader is None:
        raise Rejected("launcher unavailable")
    launcher = module_from_spec(spec)
    spec.loader.exec_module(launcher)
    pin = Path(env.get("BROCADE_KNOWN_HOSTS", ""))
    parent = Path(env.get("BROCADE_RUNTIME_PRIVATE", ""))
    launcher.private_path(pin)
    launcher.private_path(parent, directory=True)
    checkout = Path(__file__).resolve().parents[2]
    if parent.is_relative_to(checkout):
        raise Rejected("runtime inside checkout")
    return pin, Path(tempfile.mkdtemp(prefix="brocade-preflight-", dir=parent))


def admission(env, now=None):
    if env.get("BROCADE_BOOTSTRAP_ADMITTED") != "yes":
        raise Rejected("bootstrap not admitted")
    if env.get("BROCADE_ROOT_RESCUE_VERIFIED") != "yes":
        raise Rejected("root rescue attestation missing")
    if not re.fullmatch(
        r"[0-9a-f]{64}", env.get("BROCADE_BOOTSTRAP_BASELINE_SHA256", "")
    ):
        raise Rejected("recovered baseline hash missing")
    local = (now or datetime.now(ZoneInfo("America/New_York"))).astimezone(
        ZoneInfo("America/New_York")
    )
    if not (local.hour >= 23 or local.hour < 3):
        raise Rejected("outside bootstrap maintenance window")


def recovered_baseline(before, env):
    digest = hashlib.sha256(("\n".join(before) + "\n").encode()).hexdigest()
    if digest != env.get("BROCADE_BOOTSTRAP_BASELINE_SHA256"):
        raise Rejected("recovered baseline hash mismatch")


def credential_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise Rejected("duplicate credential field")
        result[key] = value
    return result


def credentials(mode):
    payload = json.loads(sys.stdin.read(8193), object_pairs_hook=credential_object)
    keys = {"root_password", "audit_password"} if mode == "apply" else {"root_password"}
    if not isinstance(payload, dict) or set(payload) != keys:
        raise Rejected("credential shape")
    password = payload["root_password"]
    if (
        not isinstance(password, str)
        or not password
        or len(password) > 256
        or any(ord(c) < 32 or ord(c) > 126 for c in password)
    ):
        raise Rejected("credential shape")
    if mode == "apply" and (
        not isinstance(payload["audit_password"], str)
        or not re.fullmatch(r"[A-Za-z0-9]{32,48}", payload["audit_password"])
    ):
        raise Rejected("audit credential shape")
    return payload


@contextmanager
def session(pin, runtime, user="root", payload=None, mode="preflight", deadline=None):
    import paramiko

    lines = pin.read_text().splitlines()
    if len(lines) != 1:
        raise Rejected("pin count")
    entry = paramiko.hostkeys.HostKeyEntry.from_line(lines[0])
    if (
        entry is None
        or entry.hostnames != [HOST]
        or entry.key is None
        or entry.key.get_name() != "ssh-rsa"
    ):
        raise Rejected("pin shape")
    fingerprint = "SHA256:" + base64.b64encode(
        hashlib.sha256(entry.key.asbytes()).digest()
    ).decode().rstrip("=")
    if fingerprint != FINGERPRINT:
        raise Rejected("unaccepted pin")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    client.load_host_keys(str(pin))
    try:
        with socket.create_connection(
            (HOST, 22), timeout=_timeout(deadline, 10)
        ) as sock:
            with paramiko.Transport(sock) as transport:
                transport.start_client(timeout=_timeout(deadline, 10))
                if transport.get_remote_server_key() != entry.key:
                    raise Rejected("host key mismatch")
                # No credential input or authentication precedes the pinned handshake.
                if payload is None:
                    payload = credentials(mode)
                password = payload[
                    "root_password" if user == "root" else "audit_password"
                ]
                transport.auth_timeout = _timeout(deadline, 10)
                transport.auth_password(user, password, fallback=False)
                channel = transport.open_session(timeout=_timeout(deadline, 10))
                channel.settimeout(_timeout(deadline, 10))
                _bounded_channel_request(
                    channel,
                    transport,
                    lambda: channel.get_pty(term="vt100", width=160, height=24),
                    deadline,
                )
                _bounded_channel_request(
                    channel, transport, channel.invoke_shell, deadline
                )
                capture_dir = Path(tempfile.mkdtemp(prefix=f"{user}-", dir=runtime))
                console = Console(channel, password, capture_dir)
                try:
                    if user == "root":
                        console.enable(deadline=deadline)
                    else:
                        console.enable(username=USER, deadline=deadline)
                    yield console, payload
                finally:
                    channel.close()
    finally:
        client.close()


def inspect(console, audit=False):
    return [console.command(command, audit=audit) for command in COMMANDS]


def preflight(pin, runtime):
    with session(pin, runtime) as (console, _):
        baseline(*inspect(console))


def private_json(path, value):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as output:
        json.dump(value, output)


def baseline_file(env):
    path = Path(env.get("BROCADE_BOOTSTRAP_BASELINE", ""))
    spec = spec_from_file_location(
        "audit_launcher", Path(__file__).with_name("run-audit.py")
    )
    if spec is None or spec.loader is None:
        raise Rejected("launcher unavailable")
    launcher = module_from_spec(spec)
    spec.loader.exec_module(launcher)
    launcher.private_path(path)
    data = json.loads(path.read_text())
    if (
        not isinstance(data, dict)
        or set(data) != {"host", "version", "running", "startup"}
        or data["host"] != HOST
        or not isinstance(data["version"], str)
        or not isinstance(data["running"], list)
        or not isinstance(data["startup"], list)
        or not all(
            isinstance(line, str) and "\n" not in line and "\r" not in line
            for line in data["running"] + data["startup"]
        )
    ):
        raise Rejected("baseline shape")
    before = baseline(
        data["version"], "\n".join(data["running"]), "\n".join(data["startup"])
    )
    if list(before) != data["running"] or list(before) != data["startup"]:
        raise Rejected("baseline noncanonical")
    return before


def readback(console, before, account_present):
    version, running, startup = inspect(console)
    baseline(version, "\n".join(before), startup)
    current = configuration(running)
    if account_present:
        account_delta(before, current)
    elif current != before:
        raise Rejected("rollback running mismatch")
    return current


def rollback(pin, runtime, payload, before):
    with session(pin, runtime, payload=payload) as (console, _):
        version, running, startup = inspect(console)
        baseline(version, "\n".join(before), startup)
        current = configuration(running)
        if current != before:
            account_delta(before, current)
            console.configure(f"no username {USER}")
        readback(console, before, account_present=False)
    with session(pin, runtime, payload=payload) as (console, _):
        readback(console, before, account_present=False)
    private_json(runtime / "rollback.json", {"verified": True, "persisted": False})


def apply(pin, runtime, env):
    attempted = False
    before = None
    payload = None
    try:
        with session(pin, runtime, mode="apply") as (console, payload):
            responses = inspect(console)
            before = baseline(*responses)
            recovered_baseline(before, env)
            private_json(
                runtime / "before.json",
                {
                    "host": HOST,
                    "version": responses[0],
                    "running": before,
                    "startup": before,
                },
            )
            admission(env)
            attempted = True
            console.configure(
                f"username {USER} privilege 5 password {payload['audit_password']}"
            )
            expected = readback(console, before, account_present=True)
        with session(pin, runtime, user=USER, payload=payload) as (console, _):
            version, running, startup = inspect(console, audit=True)
            baseline(version, "\n".join(before), startup)
            if configuration(running) != expected:
                raise Rejected("audit capture mismatch")
            console.deny_configuration(root_control=True)
        with session(pin, runtime, payload=payload) as (console, _):
            if readback(console, before, account_present=True) != expected:
                raise Rejected("root capture mismatch")
        private_json(
            runtime / "acceptance.json", {"verified": True, "persisted": False}
        )
    except BaseException:
        if attempted and before is not None and payload is not None:
            try:
                rollback(pin, runtime, payload, before)
            except BaseException as error:
                raise Rejected(
                    "automatic rollback failed; recovery uncertain"
                ) from error
            raise Rejected("apply failed; automatic rollback verified") from None
        raise


def explicit_rollback(pin, runtime, env):
    before = baseline_file(env)
    recovered_baseline(before, env)
    with session(pin, runtime, mode="rollback") as (_, payload):
        pass
    admission(env)
    try:
        rollback(pin, runtime, payload, before)
    except BaseException as error:
        raise Rejected("rollback failed; recovery uncertain") from error


def sync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


@contextmanager
def mutation_guard(env, runtime: Path):
    """Serialize mutating CLI routes; trusted apply/rollback callers own admission."""
    spec = spec_from_file_location(
        "audit_launcher", Path(__file__).with_name("run-audit.py")
    )
    if spec is None or spec.loader is None:
        raise Rejected("launcher unavailable")
    launcher = module_from_spec(spec)
    spec.loader.exec_module(launcher)
    parent = Path(env.get("BROCADE_RUNTIME_PRIVATE", ""))
    launcher.private_path(parent, directory=True)
    launcher.private_path(runtime, directory=True)
    if parent.is_relative_to(Path(__file__).resolve().parents[2]):
        raise Rejected("stable private parent inside checkout")
    if runtime.parent != parent:
        raise Rejected("runtime outside stable private parent")
    ledger = parent / "brocade-persistence-ledger"
    if not os.path.lexists(ledger):
        ledger.mkdir(mode=0o700)
        sync_directory(parent)
    launcher.private_path(ledger, directory=True)
    lock = ledger / "lock"
    fd = os.open(lock, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_nlink != 1
        ):
            raise Rejected("unsafe ledger lock")
        sync_directory(ledger)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise Rejected("another persistence workflow holds the lock") from error
        if os.path.lexists(ledger / "pending.json"):
            raise Rejected("pending ledger blocks bootstrap mutation")
        yield
    finally:
        os.close(fd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--apply", action="store_true")
    modes.add_argument("--rollback", action="store_true")
    args = parser.parse_args()
    os.umask(0o077)
    stage = "private-inputs"
    runtime = None
    try:
        if args.apply or args.rollback:
            stage = "write-admission"
            admission(os.environ)
        pin, runtime = paths(os.environ)
        stage = (
            "apply"
            if args.apply
            else "rollback"
            if args.rollback
            else "read-only-preflight"
        )
        if args.apply or args.rollback:
            with mutation_guard(os.environ, runtime):
                if args.apply:
                    apply(pin, runtime, os.environ)
                else:
                    explicit_rollback(pin, runtime, os.environ)
        else:
            preflight(pin, runtime)
    except Exception as error:
        # Transport exceptions and configuration responses can carry secrets.
        if runtime is not None:
            try:
                fd = os.open(
                    runtime / "failure.json",
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    0o600,
                )
                with os.fdopen(fd, "w") as output:
                    json.dump(
                        {
                            "stage": stage,
                            "exception_type": type(error).__name__,
                            "gate": str(error) if isinstance(error, Rejected) else None,
                        },
                        output,
                    )
            except (OSError, TypeError, ValueError):
                # Diagnostic storage failure must not expose the original exception.
                pass
        gate = str(error) if isinstance(error, Rejected) else "private diagnostics"
        print(
            f"Rejected at {stage}: {gate}; private runtime: {runtime}.", file=sys.stderr
        )
        return 2
    print(f"{stage} passed; private runtime: {runtime}. No configuration persisted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
