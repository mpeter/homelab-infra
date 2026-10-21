"""Private audit observations during an unsaved, fixed-port exercise.

This library grants no admission and makes no configuration changes. Startup
must match the caller's canonical anchor; the orchestrator classifies running
changes. No CLI or credential storage is provided.
"""

from collections.abc import Callable
from datetime import datetime, timezone
import hashlib
import json
from inspect import iscoroutine
from importlib.util import module_from_spec, spec_from_file_location
import os
from pathlib import Path
import re
import stat
import time
from typing import Any

_BASE = Path(__file__).resolve().parent
SOURCE_PATHS = {
    "collector": _BASE / "collect-port-evidence.py",
    "bootstrap": _BASE.parent / "network-audit/bootstrap-identity.py",
    "capture": _BASE.parent / "network-audit/capture.py",
    "launcher": _BASE.parent / "network-audit/run-audit.py",
    "engine": _BASE / "port_description.py",
    "observation": Path(__file__).resolve(),
}
SOURCE_SHA256 = {
    "collector": "255e6c9244e82e9d9294b3c246db21a393b53af4e54166a29e7579904af1e8c1",
    "bootstrap": "9040bc7551266f7a55d1ba46cf080edeca31b1161ac6663e16db3a29d5ed13e2",
    "capture": "f2534d3e46490894e7af821e70192469064b9ef71d58ba825a23f77ea0c26e51",
    "launcher": "1d23b99a219b7bc586b75f3676d663a62e2ecce6b338b7a8a86c2e7c840f0635",
    "engine": "6ddbe2c29a1af384e3a0e25902ce2e35affdee81898f5761b29a82aa32441f84",
    "observation": hashlib.sha256(SOURCE_PATHS["observation"].read_bytes()).hexdigest(),
}
PORT = "1/1/47"


class Rejected(ValueError):
    """An observation boundary failed; private evidence may remain."""


def unchanged_sources() -> None:
    for name, path in SOURCE_PATHS.items():
        if hashlib.sha256(path.read_bytes()).hexdigest() != SOURCE_SHA256[name]:
            raise Rejected("observation source drift")


def _load(name: str, path: Path) -> Any:
    spec = spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise Rejected("observation dependency unavailable")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


unchanged_sources()
# This collector owns its separately loaded bootstrap module. Specializing its
# Console does not mutate the ordinary collector or any other session's globals.
collector = _load("exercise_observation_collector", SOURCE_PATHS["collector"])
engine = _load("exercise_observation_engine", SOURCE_PATHS["engine"])
bootstrap = collector.bootstrap
COMMANDS = (*collector.COMMANDS, f"show interfaces ethernet {PORT}")


def _private_path(path: Path, *, directory: bool) -> None:
    if not isinstance(path, Path) or not path.is_absolute() or path != path.resolve():
        raise Rejected("private path must be absolute without symlinks")
    if any(component.is_symlink() for component in (path, *path.parents)):
        raise Rejected("private path symlink")
    info = path.stat()
    if (
        info.st_uid != os.getuid()
        or stat.S_IMODE(info.st_mode) != (0o700 if directory else 0o600)
        or not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))
        or (not directory and info.st_nlink != 1)
    ):
        raise Rejected("unsafe private path")
    if directory and path.is_relative_to(_BASE.parents[1]):
        raise Rejected("runtime inside checkout")


def _audit(lines: tuple[str, ...]) -> None:
    accounts = [
        line for line in lines if re.match(r"username homelab_audit\b", line.lstrip())
    ]
    if (
        len(accounts) != 1
        or re.fullmatch(
            r"username homelab_audit privilege 5 password \S[^\r\n]*", accounts[0]
        )
        is None
    ):
        raise Rejected("persisted privilege-5 audit account required")


class _AuditInput:
    def __init__(self, provider: Callable[[], str]):
        self.provider = provider
        self.password: str | None = None

    def __getitem__(self, key: str) -> str:
        if key != "audit_password":
            raise Rejected("audit identity required")
        if self.password is None:
            unchanged_sources()
            password = self.provider()
            if iscoroutine(password):
                password.close()
            if (
                not isinstance(password, str)
                or re.fullmatch(r"[A-Za-z0-9]{32,48}", password) is None
            ):
                raise Rejected("audit credential shape")
            unchanged_sources()
            self.password = password
        return self.password


def _sync(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class _WireChannel:
    def __init__(self, channel: Any, runtime: Path):
        self.channel = channel
        self.fd = os.open(
            runtime / "received.raw",
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
        )

    def __getattr__(self, name: str) -> Any:
        return getattr(self.channel, name)

    def recv(self, size: int) -> bytes:
        data: bytes = self.channel.recv(size)
        remaining = memoryview(data)
        while remaining:
            count = os.write(self.fd, remaining)
            if count <= 0:
                raise OSError("wire capture incomplete")
            remaining = remaining[count:]
        return data

    def close_capture(self) -> None:
        os.close(self.fd)


_BaseConsole: Any = bootstrap.Console


class _Console(_BaseConsole):
    def __init__(self, channel: Any, password: str, runtime: Path):
        self.wire = _WireChannel(channel, runtime)
        super().__init__(self.wire, password, runtime)

    def read(
        self,
        boundary: Any,
        allow_errors: bool = False,
        *,
        deadline: float | None = None,
    ) -> str:
        """Drain queued bytes and require a quiet, complete terminal boundary."""
        unchanged_sources()
        raw = ""
        pages = 0
        deadline = min(
            time.monotonic() + 20,
            deadline if deadline is not None else float("inf"),
        )
        last_received: float | None = None
        pager = collector.capture.PAGER
        erased = pager + "\x08 \x08" * len(pager)
        try:
            while time.monotonic() < deadline:
                if self.channel.recv_ready():
                    data = self.channel.recv(65536)
                    if not data:
                        break
                    raw += data.decode("ascii", errors="strict")
                    last_received = time.monotonic()
                    if len(raw) > 8 * 1024 * 1024:
                        raise Rejected("capture limit")
                    new_pages = raw.count("--More--")
                    if new_pages > pages:
                        if new_pages > 128:
                            raise Rejected("pager limit")
                        for marker in re.finditer(re.escape("--More--"), raw):
                            prefix = bootstrap.cleaned(
                                raw[: marker.start()].replace(erased, "")
                            )
                            if any(
                                bootstrap.ANY_PROMPT.fullmatch(line)
                                or re.fullmatch(r"(?:User Name:|Password:)\s*", line)
                                for line in prefix.splitlines()
                            ):
                                raise Rejected("pager after terminal boundary")
                        self.channel.sendall(" " * (new_pages - pages))
                        pages = new_pages
                    # Never decide at the first prompt: another queued chunk may
                    # contain an error, a second prompt, or a partial boundary.
                    continue
                if (
                    last_received is not None
                    and time.monotonic() - last_received >= 0.05
                ):
                    completed = raw.replace(erased, "")
                    pending = next(
                        (
                            size
                            for size in range(len(erased) - 1, 0, -1)
                            if completed.endswith(erased[:size])
                        ),
                        0,
                    )
                    consumed = collector.capture.consumed_pagers(
                        completed[:-pending] if pending else completed
                    )
                    if not allow_errors and (
                        bootstrap.ERROR.search(consumed)
                        or bootstrap.DENIED.search(consumed)
                    ):
                        raise Rejected("raw command error")
                    # A final CR may be the first byte of a fragmented CRLF.
                    # Validate internal controls now, and wait for its LF before
                    # deciding whether a complete terminal boundary exists.
                    checked = consumed[:-1] if consumed.endswith("\r") else consumed
                    if re.search(r"\r(?!\n)|[\x08\x7f]", checked):
                        raise Rejected("terminal overwrite or control")
                    # A page prompt and its exact erasure may arrive separately.
                    # This prefix is only provisional: it cannot complete a read.
                    if pending:
                        if any(
                            bootstrap.ANY_PROMPT.fullmatch(line)
                            or re.fullmatch(r"(?:User Name:|Password:)\s*", line)
                            for line in bootstrap.cleaned(consumed).splitlines()
                        ):
                            raise Rejected("pager after terminal boundary")
                        time.sleep(0.005)
                        continue
                    if consumed.endswith("\r"):
                        time.sleep(0.005)
                        continue
                    text = bootstrap.cleaned(consumed)
                    match = boundary.search(text)
                    lines = text.splitlines()
                    terminals = [
                        bool(
                            bootstrap.ANY_PROMPT.fullmatch(line)
                            or re.fullmatch(r"(?:User Name:|Password:)\s*", line)
                        )
                        for line in lines
                    ]
                    if any(terminals[:-1]):
                        raise Rejected("observation terminal boundary")
                    if match is None:
                        if any(terminals):
                            raise Rejected("observation terminal boundary")
                        # Silence in an ordinary body is not command completion.
                        # Keep waiting for the expected boundary within deadline.
                        time.sleep(0.005)
                        continue
                    if match.end() != len(text):
                        raise Rejected("observation terminal boundary")
                    if not allow_errors and (
                        bootstrap.ERROR.search(text) or bootstrap.DENIED.search(text)
                    ):
                        raise Rejected("device rejected command")
                    return text
                if self.channel.closed:
                    break
                time.sleep(0.005)
            raise Rejected("incomplete response")
        finally:
            if raw:
                self.save(raw)
            unchanged_sources()


# A session-local subclass is created below so failure before session yield still
# closes the private file descriptor, without shared mutable session bookkeeping.
def observe(
    pin: Path,
    runtime: Path,
    expected_startup: tuple[str, ...],
    credential_provider: Callable[[], str],
) -> dict[str, Any]:
    """Read six fixed commands as homelab_audit after the accepted handshake."""
    unchanged_sources()
    _private_path(pin, directory=False)
    _private_path(runtime, directory=True)
    if (
        not callable(credential_provider)
        or type(expected_startup) is not tuple
        or not all(isinstance(line, str) for line in expected_startup)
    ):
        raise Rejected("canonical startup anchor required")
    if engine.configuration("\n".join(expected_startup)) != expected_startup:
        raise Rejected("canonical startup anchor required")
    _audit(expected_startup)
    if (runtime / "evidence.json").exists() or (runtime / "evidence.json").is_symlink():
        raise Rejected("evidence already exists")
    started = datetime.now(timezone.utc).isoformat()
    consoles: list[Any] = []

    class Console(_Console):
        def __init__(self, channel: Any, password: str, capture_runtime: Path):
            super().__init__(channel, password, capture_runtime)
            consoles.append(self)

    # The private bootstrap module is loaded per invocation, preserving concurrent
    # callers and the exact reviewed transport implementation.
    session_bootstrap = _load("exercise_observation_session", SOURCE_PATHS["bootstrap"])
    session_bootstrap.Console = Console
    unchanged_sources()
    try:
        with session_bootstrap.session(
            pin, runtime, user=bootstrap.USER, payload=_AuditInput(credential_provider)
        ) as (console, _):
            responses = []
            for command in COMMANDS:
                unchanged_sources()
                responses.append(collector.read_command(console, command, PORT))
                unchanged_sources()
                if len(responses) == 3:
                    collector.capture.validate(responses)
                    running = engine.configuration(responses[1])
                    startup = engine.configuration(responses[2])
                    _audit(running)
                    _audit(startup)
                    if startup != expected_startup:
                        raise Rejected("startup anchor changed")
            evidence = {
                "schema": 1,
                "observed_at": started,
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "host": bootstrap.HOST,
                "model": "ICX6610-48P",
                "release": bootstrap.RELEASE,
                "identity": bootstrap.USER,
                "accepted_host_key_fingerprint": bootstrap.FINGERPRINT,
                "selected_port": PORT,
                "commands": list(COMMANDS),
                "expected_execution_environment_sha256": collector.EE_DIGEST,
                "source_sha256": {
                    name: SOURCE_SHA256[name] for name in collector.SOURCE_PATHS
                },
                "observation_source_sha256": dict(SOURCE_SHA256),
                "captures_directory": str(console.runtime),
                "raw_capture_sha256": {
                    path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                    for path in sorted(console.runtime.glob("capture-*.txt"))
                },
                "wire_capture": {
                    "path": str(console.runtime / "received.raw"),
                    "sha256": hashlib.sha256(
                        (console.runtime / "received.raw").read_bytes()
                    ).hexdigest(),
                },
                "responses": dict(zip(COMMANDS, responses, strict=True)),
                "terminal_boundaries_complete": True,
                "operational_parsing_complete": False,
                "reserved_use_reviewed": False,
                "unused_port_verified": False,
                "ready": False,
                "admitted": False,
                "apply_allowed": False,
                "task_7_4_complete": False,
            }
            engine.evidence_config(evidence, PORT)
            for path in (*sorted(console.runtime.iterdir()), console.runtime):
                _sync(path)
            unchanged_sources()
            fd = os.open(
                runtime / "evidence.json",
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
            )
            with os.fdopen(fd, "w") as output:
                json.dump(evidence, output)
                output.flush()
                os.fsync(output.fileno())
            _sync(runtime)
            return evidence
    finally:
        for console in consoles:
            console.wire.close_capture()
