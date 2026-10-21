#!/usr/bin/env python3
"""Inspect fixed ICX port-name help without executing a port setting."""

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
from importlib.util import module_from_spec, spec_from_file_location
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import time

COLLECTOR_PATH = Path(__file__).with_name("collect-port-evidence.py").resolve()
SPEC = spec_from_file_location("port_syntax_collector", COLLECTOR_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("collector unavailable")
collector = module_from_spec(SPEC)
SPEC.loader.exec_module(collector)
bootstrap = collector.bootstrap
Rejected = collector.Rejected
SOURCE_PATHS = {**collector.SOURCE_PATHS, "inspector": Path(__file__).resolve()}
SOURCE_SHA256 = {
    name: hashlib.sha256(path.read_bytes()).hexdigest()
    for name, path in SOURCE_PATHS.items()
}
BASELINE_SHA256 = "97997daab378af8467dcb05244f2f9c03b2df33c694d373c1dc4a891cb4bbb3b"
PORT = "1/1/47"
EXEC = r"(?:SSH@)?headwater#"
CONFIG = r"(?:SSH@)?headwater\(config\)#"
INTERFACE = r"(?:SSH@)?headwater\(config-if-e1000-1/1/47\)#"
HELP_COMMANDS = ("port-name ?", "no port-name ?")


def unchanged_sources():
    collector.unchanged_sources()
    if any(
        hashlib.sha256(path.read_bytes()).hexdigest() != SOURCE_SHA256[name]
        for name, path in SOURCE_PATHS.items()
    ):
        raise Rejected("inspector source drift")


def credentials():
    try:
        raw = sys.stdin.read(8193)
        if len(raw) > 8192:
            raise Rejected("credential size")
        payload = json.loads(raw, object_pairs_hook=bootstrap.credential_object)
    except (ValueError, UnicodeError) as error:
        raise Rejected("credential shape") from error
    if not isinstance(payload, dict) or set(payload) != {"root_password"}:
        raise Rejected("credential shape")
    password = payload["root_password"]
    if (
        not isinstance(password, str)
        or not password
        or len(password) > 256
        or any(ord(char) < 32 or ord(char) > 126 for char in password)
    ):
        raise Rejected("credential shape")
    return payload


class RootInput:
    """Read the single stdin credential only after the pinned handshake."""

    def __init__(self):
        self.payload = None

    def __getitem__(self, key):
        if key != "root_password":
            raise Rejected("credential key")
        if self.payload is None:
            self.payload = credentials()
        return self.payload[key]


def launcher():
    spec = spec_from_file_location(
        "syntax_launcher", collector.SOURCE_PATHS["launcher"]
    )
    if spec is None or spec.loader is None:
        raise Rejected("launcher unavailable")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    unchanged_sources()
    return module


def private_path(path, *, directory=False):
    module = launcher()
    try:
        module.private_path(path, directory=directory)
    except module.PrerequisiteError as error:
        raise Rejected("unsafe private path") from error


def paths(env):
    unchanged_sources()
    validate = private_path
    pin = Path(env.get("BROCADE_KNOWN_HOSTS", ""))
    parent = Path(env.get("BROCADE_RUNTIME_PRIVATE", ""))
    validate(pin)
    validate(parent, directory=True)
    if pin.stat().st_nlink != 1:
        raise Rejected("hardlinked pin")
    if parent.is_relative_to(Path(__file__).resolve().parents[2]):
        raise Rejected("runtime inside checkout")
    return pin, Path(tempfile.mkdtemp(prefix="brocade-port-syntax-", dir=parent))


@contextmanager
def locked_ledger(env, runtime):
    validate = private_path
    parent = Path(env.get("BROCADE_RUNTIME_PRIVATE", ""))
    validate(parent, directory=True)
    validate(runtime, directory=True)
    if runtime.parent != parent or parent.is_relative_to(
        Path(__file__).resolve().parents[2]
    ):
        raise Rejected("runtime outside stable private parent")
    ledger = parent / "brocade-persistence-ledger"
    validate(ledger, directory=True)
    lock = ledger / "lock"
    validate(lock)
    fd = os.open(lock, os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_nlink != 1
            or (info.st_dev, info.st_ino) != (lock.stat().st_dev, lock.stat().st_ino)
        ):
            raise Rejected("unsafe ledger lock")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise Rejected("another workflow holds the lock") from error
        if os.path.lexists(ledger / "pending.json"):
            raise Rejected("pending persistence blocks syntax inspection")
        yield
    finally:
        os.close(fd)


def baseline(console):
    responses = [
        collector.read_command(console, command, PORT) for command in bootstrap.COMMANDS
    ]
    current = collector.baseline(*responses)
    digest = hashlib.sha256(("\n".join(current) + "\n").encode()).hexdigest()
    if digest != BASELINE_SHA256:
        raise Rejected("canonical baseline drift")
    return current


def normalized(raw, *, clearing=False):
    if bootstrap.DENIED.search(raw) or bootstrap.ERROR.search(raw):
        raise Rejected("raw mode response error")
    # Ctrl-C may erase the retained buffer with complete BS-space-BS triplets.
    if clearing:
        erased = re.match(r"(?:\x08 \x08)+", raw)
        if erased is not None:
            if len(erased.group()) > 13 * 3:
                raise Rejected("clear erase limit")
            raw = raw[erased.end() :]
    if (
        re.search(r"\r(?!\n)", raw)
        or re.search(r"[\x00-\x08\x0b-\x1f\x7f]", raw.replace("\r\n", "\n"))
        or "--More--" in raw
    ):
        raise Rejected("mode response control or pager")
    text = bootstrap.cleaned(raw)
    if bootstrap.DENIED.search(text) or bootstrap.ERROR.search(text):
        raise Rejected("mode response error")
    return text


def read_mode(console, prompt, *, retained="", clearing=False):
    boundary = re.compile(r"(?:^|\n)" + prompt + re.escape(retained) + r" *$")
    deadline = time.monotonic() + 20
    raw = ""
    try:
        while time.monotonic() < deadline:
            if console.channel.recv_ready():
                chunk = console.channel.recv(65536)
                if not chunk:
                    break
                raw += chunk.decode("ascii", errors="strict")
                if len(raw) > 65536:
                    raise Rejected("mode capture limit")
                # CRLF and complete erase triplets can span transport chunks.
                if raw.endswith("\r") or (clearing and raw.endswith(("\x08", "\x08 "))):
                    if console.channel.recv_ready():
                        continue
                    # A lone backspace also ends a complete triplet; normalize it
                    # before deciding whether more bytes are required.
                    if raw.endswith("\r") or not raw.endswith("\x08 \x08"):
                        if console.channel.closed:
                            raise Rejected("incomplete mode control")
                        time.sleep(0.01)
                        continue
                text = normalized(raw, clearing=clearing)
                if boundary.search(text):
                    if console.channel.recv_ready():
                        continue
                    time.sleep(0.05)
                    if console.channel.recv_ready():
                        continue
                    return text
                tail = text.split("\n")[-1]
                prompt_match = re.match(prompt, tail)
                if prompt_match is not None and retained.startswith(
                    tail[prompt_match.end() :]
                ):
                    continue
                if re.search(
                    r"(?:^|\n)(?:SSH@)?headwater(?:\([^\r\n]*\))?[>#][^\r\n]*$", text
                ):
                    raise Rejected("unexpected mode or retained buffer")
            elif console.channel.closed:
                break
            else:
                time.sleep(0.01)
        raise Rejected("incomplete mode response")
    finally:
        console.save(raw)


def transition(console, command, prompt):
    allowed = {
        ("configure terminal", CONFIG),
        ("interface ethernet " + PORT, INTERFACE),
        ("exit", CONFIG),
        ("exit", EXEC),
    }
    if (command, prompt) not in allowed:
        raise Rejected("mode command boundary")
    unchanged_sources()
    console.channel.sendall(command + "\r")
    response = read_mode(console, prompt)
    lines = response.strip().splitlines()
    if len(lines) != 2 or lines[0] != command or re.fullmatch(prompt, lines[1]) is None:
        raise Rejected("mode echo boundary")


def help_query(console, command):
    if command not in HELP_COMMANDS:
        raise Rejected("help command boundary")
    unchanged_sources()
    # No carriage return: '?' requests help and the buffer remains unexecuted.
    console.channel.sendall(command)
    retained = command[:-1].rstrip()
    response = read_mode(console, INTERFACE, retained=retained)
    lines = response.strip().splitlines()
    if (
        len(lines) < 3
        or lines[0] not in (command, command[:-1].rstrip())
        or any(
            re.search(r"(?:SSH@)?headwater(?:\([^\r\n]*\))?[>#]", line)
            for line in lines[1:-1]
        )
        or not "\n".join(lines[1:-1]).strip()
    ):
        raise Rejected("help echo or body boundary")
    console.channel.sendall("\x03")
    cleared = read_mode(console, INTERFACE, clearing=True)
    # A fresh newline and empty prompt prove cancellation; retained input fails.
    if not re.fullmatch(r"(?:\^C)?\n" + INTERFACE + r" *", cleared):
        raise Rejected("empty fresh interface prompt required")
    return "\n".join(lines[1:-1])


def inspect(pin, runtime, env):
    unchanged_sources()
    with locked_ledger(env, runtime):
        with bootstrap.session(pin, runtime, user="root", payload=RootInput()) as (
            console,
            _,
        ):
            before = baseline(console)
            transition(console, "configure terminal", CONFIG)
            transition(console, "interface ethernet " + PORT, INTERFACE)
            help_text = {
                command: help_query(console, command) for command in HELP_COMMANDS
            }
            transition(console, "exit", CONFIG)
            transition(console, "exit", EXEC)
            after = baseline(console)
            if after != before:
                raise Rejected("configuration changed")
            unchanged_sources()
            bootstrap.private_json(
                runtime / "syntax-evidence.json",
                {
                    "schema": 1,
                    "observed_at": datetime.now(timezone.utc).isoformat(),
                    "host": bootstrap.HOST,
                    "model": "ICX6610-48P",
                    "release": bootstrap.RELEASE,
                    "selected_port": PORT,
                    "identity": "root",
                    "canonical_baseline_sha256": BASELINE_SHA256,
                    "help": help_text,
                    "source_sha256": SOURCE_SHA256,
                    "expected_execution_environment_sha256": collector.EE_DIGEST,
                    "raw_capture_sha256": {
                        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                        for path in sorted(console.runtime.glob("capture-*.txt"))
                    },
                    "configuration_mutation_absent": True,
                    "serializer_proven": False,
                    "task_7_4_complete": False,
                },
            )
    return {
        "syntax_help_available": True,
        "configuration_mutation_absent": True,
        "serializer_proven": False,
        "task_7_4_complete": False,
        "private_runtime": str(runtime),
    }


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    os.umask(0o077)
    runtime = None
    try:
        pin, runtime = paths(os.environ)
        result = inspect(pin, runtime, os.environ)
    except Exception as error:
        if runtime is not None:
            try:
                bootstrap.private_json(
                    runtime / "failure.json",
                    {
                        "exception_type": type(error).__name__,
                        "gate": str(error) if isinstance(error, Rejected) else None,
                    },
                )
            except OSError:
                pass
        print(
            f"Port syntax inspection rejected; private runtime: {runtime}.",
            file=sys.stderr,
        )
        return 2
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
