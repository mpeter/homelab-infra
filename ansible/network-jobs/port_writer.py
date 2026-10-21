"""Fixed writer transport for ICX6610-48P 08.0.30uT7f3 at 192.168.0.251.

This library supplies a pinned SSH session and one unsaved description attempt.
It does not admit an exercise, establish a baseline, hold a ledger lock, prove
recovery, or accept a preview. The caller must establish those prerequisites
before opening the session and durably record intent before the leaf is sent.
No account creation, persistence, retries, or recovery commands are provided.
"""

import base64
from collections.abc import Callable, Iterator
from contextlib import contextmanager
import hashlib
from importlib import import_module
from inspect import iscoroutine
from importlib.util import module_from_spec, spec_from_file_location
import os
from pathlib import Path
import re
import socket
import stat
import tempfile
import threading
import time
from typing import Any

HOST = "192.168.0.251"
USER = "homelab_writer"
FINGERPRINT = "SHA256:UJulVmfAMmHcUctvJrlGzBZR7I7uN8/TWNeJIs25yks"
PORT = "1/1/47"
DESCRIPTION = "homelab-description-exercise"
_BASE = Path(__file__).resolve().parent
_SOURCES = {
    _BASE
    / "inspect-port-syntax.py": "070e0beadf0651620cbf3e862dc6e269d3464692e825783588a968f1acd740fb",
    _BASE
    / "collect-port-evidence.py": "255e6c9244e82e9d9294b3c246db21a393b53af4e54166a29e7579904af1e8c1",
    _BASE.parent
    / "network-audit/bootstrap-identity.py": "9040bc7551266f7a55d1ba46cf080edeca31b1161ac6663e16db3a29d5ed13e2",
    _BASE.parent
    / "network-audit/capture.py": "f2534d3e46490894e7af821e70192469064b9ef71d58ba825a23f77ea0c26e51",
    _BASE.parent
    / "network-audit/run-audit.py": "1d23b99a219b7bc586b75f3676d663a62e2ecce6b338b7a8a86c2e7c840f0635",
    Path(__file__).resolve(): hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
}


class Rejected(Exception):
    """A fixed transport boundary failed; no recovery is attempted."""


def unchanged_sources() -> None:
    for path, expected in _SOURCES.items():
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise Rejected("writer source drift")


def _remaining_timeout(deadline: float | None, maximum: float) -> float:
    if deadline is None:
        return maximum
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("R8 operation deadline expired")
    return min(maximum, remaining)


def _bounded_channel_request(
    channel: Any, transport: Any, request: Callable[[], None], deadline: float | None
) -> None:
    timeout = _remaining_timeout(deadline, 10)
    expired = threading.Event()

    def interrupt() -> None:
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
                "R8 operation deadline expired during SSH channel setup"
            ) from exc
        raise
    finally:
        timer.cancel()
    if expired.is_set():
        raise TimeoutError("R8 operation deadline expired during SSH channel setup")


unchanged_sources()
_SPEC = spec_from_file_location("writer_syntax", _BASE / "inspect-port-syntax.py")
if _SPEC is None or _SPEC.loader is None:
    raise Rejected("syntax helper unavailable")
_syntax = module_from_spec(_SPEC)
_SPEC.loader.exec_module(_syntax)


def _private_path(path: Path, *, directory: bool) -> None:
    if not path.is_absolute() or path != path.resolve():
        raise Rejected("private path must be absolute without symlinks")
    for component in (path, *path.parents):
        if component.is_symlink():
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


class _CaptureChannel:
    def __init__(self, channel: Any, capture: Any):
        self._channel = channel
        self._capture = capture

    @property
    def closed(self) -> bool:
        return bool(self._channel.closed)

    def recv_ready(self) -> bool:
        return bool(self._channel.recv_ready())

    def recv(self, size: int) -> bytes:
        data: bytes = self._channel.recv(size)
        self._capture.write(data)
        self._capture.flush()
        return data

    def sendall(self, value: str) -> None:
        self._channel.sendall(value)


class _Console:
    def __init__(self, channel: _CaptureChannel):
        self.channel = channel

    def save(self, raw: str) -> None:
        # recv captures bytes before decoding or boundary validation can fail.
        pass


def _challenge(console: _Console, pattern: str, deadline: float | None = None) -> str:
    raw = ""
    deadline = min(
        time.monotonic() + 20,
        deadline if deadline is not None else float("inf"),
    )
    while time.monotonic() < deadline:
        if console.channel.recv_ready():
            data = console.channel.recv(65536)
            if not data:
                break
            raw += data.decode("ascii", errors="strict")
            if len(raw) > 65536:
                raise Rejected("enable capture limit")
            if raw.endswith("\r"):
                continue
            text = _syntax.normalized(raw)
            if re.fullmatch(pattern, text):
                if console.channel.recv_ready():
                    continue
                time.sleep(0.05)
                if not console.channel.recv_ready():
                    return text
            elif re.search(r"(?:[>#]|User Name:|Password:) *$", text):
                raise Rejected("enable boundary")
        elif console.channel.closed:
            break
        else:
            time.sleep(0.01)
    raise Rejected("incomplete enable response")


def _enable(console: _Console, password: str, deadline: float | None = None) -> None:
    initial = _challenge(console, r"\n?(?:SSH@)?headwater[>#] *", deadline)
    if initial.rstrip().endswith("#"):
        return
    unchanged_sources()
    console.channel.sendall("enable\r")
    _challenge(console, r"enable\nUser Name: *", deadline)
    unchanged_sources()
    console.channel.sendall(USER + "\r")
    _challenge(console, USER + r"\nPassword: *", deadline)
    unchanged_sources()
    console.channel.sendall(password + "\r")
    _challenge(console, r"\n(?:SSH@)?headwater# *", deadline)


class PortWriter:
    """One fixed set or clear attempt; failures leave state uncertain for the caller.

    The durable intent callback must complete synchronously and return None.
    """

    def __init__(self, console: _Console):
        self._console = console
        self._attempted = False
        self._closed = False

    def set_description(self, before_send: Callable[[], object]) -> None:
        self._attempt("port-name " + DESCRIPTION, before_send)

    def clear_description(self, before_send: Callable[[], object]) -> None:
        self._attempt("no port-name", before_send)

    def _transition(self, command: str, prompt: str) -> None:
        unchanged_sources()
        _syntax.transition(self._console, command, prompt)

    def _attempt(self, command: str, before_send: Callable[[], object]) -> None:
        if self._closed or self._attempted:
            raise Rejected("writer session already used or closed")
        self._attempted = True
        if not callable(before_send):
            raise Rejected("durable intent callback required")
        self._transition("configure terminal", _syntax.CONFIG)
        self._transition("interface ethernet " + PORT, _syntax.INTERFACE)
        unchanged_sources()
        result = before_send()
        if result is not None:
            if iscoroutine(result):
                result.close()
            raise Rejected("durable intent callback must return None synchronously")
        unchanged_sources()
        self._console.channel.sendall(command + "\r")
        response = _syntax.read_mode(self._console, _syntax.INTERFACE)
        if (
            re.fullmatch(
                re.escape(command) + "\n" + _syntax.INTERFACE + r" *", response
            )
            is None
        ):
            raise Rejected("leaf echo boundary")
        self._transition("exit", _syntax.CONFIG)
        self._transition("exit", _syntax.EXEC)


@contextmanager
def writer_session(
    pin: Path,
    runtime: Path,
    credential_provider: Callable[[], str],
    deadline: float | None = None,
) -> Iterator[PortWriter]:
    """Authenticate only homelab_writer after the accepted RSA handshake.

    The credential provider is called once after host verification and must
    return only the writer password, never a root/audit credential mapping.
    Captured bytes remain in an exclusive private file beneath runtime.
    """
    unchanged_sources()
    _private_path(pin, directory=False)
    _private_path(runtime, directory=True)
    paramiko = import_module("paramiko")

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
    with socket.create_connection(
        (HOST, 22), timeout=_remaining_timeout(deadline, 10)
    ) as sock:
        with paramiko.Transport(sock) as transport:
            transport.start_client(timeout=_remaining_timeout(deadline, 10))
            if transport.get_remote_server_key() != entry.key:
                raise Rejected("host key mismatch")
            password = credential_provider()
            if (
                not isinstance(password, str)
                or not password
                or len(password) > 256
                or any(ord(char) < 32 or ord(char) > 126 for char in password)
            ):
                raise Rejected("writer credential shape")
            transport.auth_timeout = _remaining_timeout(deadline, 10)
            transport.auth_password(USER, password, fallback=False)
            channel = transport.open_session(timeout=_remaining_timeout(deadline, 10))
            writer = None
            try:
                channel.settimeout(_remaining_timeout(deadline, 10))
                _bounded_channel_request(
                    channel,
                    transport,
                    lambda: channel.get_pty(term="vt100", width=160, height=24),
                    deadline,
                )
                capture_dir = Path(
                    tempfile.mkdtemp(prefix="homelab-writer-", dir=runtime)
                )
                fd = os.open(
                    capture_dir / "received.raw",
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    0o600,
                )
                with os.fdopen(fd, "wb") as capture:
                    console = _Console(_CaptureChannel(channel, capture))
                    _bounded_channel_request(
                        channel, transport, channel.invoke_shell, deadline
                    )
                    _enable(console, password, deadline)
                    writer = PortWriter(console)
                    yield writer
            finally:
                if writer is not None:
                    writer._closed = True
                channel.close()
