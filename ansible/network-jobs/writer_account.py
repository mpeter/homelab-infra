"""One temporary writer-account attempt on the pinned ICX6610-48P 08.0.30uT7f3.

The caller owns the canonical exclusive lock, pending journal, fresh baseline,
recovery gates, and durable intent. This library admits no exercise or live
acceptance and provides no CLI, save, retry, automatic inverse, or recovery.
Failures leave state uncertain; even failed reads remain in private raw captures.
"""

import hashlib
import os
import re
import tempfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from importlib.util import module_from_spec, spec_from_file_location
from inspect import iscoroutine, iscoroutinefunction
from pathlib import Path
from typing import Any

_BASE = Path(__file__).resolve().parent
_WRITER_PATH = _BASE / "port_writer.py"
_WRITER_SHA256 = "892dab2b7ab444a69f3858ac2a166661c5695f126a07a55e126d159c568fa503"
if hashlib.sha256(_WRITER_PATH.read_bytes()).hexdigest() != _WRITER_SHA256:
    raise RuntimeError("account transport dependency drift")
_SPEC = spec_from_file_location("account_writer_transport", _WRITER_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("account transport dependency unavailable")
_transport = module_from_spec(_SPEC)
_SPEC.loader.exec_module(_transport)
Rejected = _transport.Rejected
HOST = _transport.HOST
FINGERPRINT = _transport.FINGERPRINT
USER = "homelab_writer"
ROOT = "root"
_SOURCES = {
    **_transport._SOURCES,
    _WRITER_PATH: _WRITER_SHA256,
    Path(__file__).resolve(): hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
}
_syntax = _transport._syntax


def unchanged_sources() -> None:
    for path, expected in _SOURCES.items():
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise Rejected("account transport source drift")


def _enable_root(console: Any, password: str, deadline: float | None = None) -> None:
    # Root must demonstrate its own enable challenge, even after SSH auth.
    _transport._challenge(console, r"\n?(?:SSH@)?headwater> *", deadline)
    unchanged_sources()
    console.channel.sendall("enable\r")
    _transport._challenge(console, r"enable\nUser Name: *", deadline)
    unchanged_sources()
    console.channel.sendall(ROOT + "\r")
    _transport._challenge(console, ROOT + r"\nPassword: *", deadline)
    unchanged_sources()
    console.channel.sendall(password + "\r")
    _transport._challenge(console, r"\n(?:SSH@)?headwater# *", deadline)


class WriterAccount:
    """One unsaved account leaf; durable intent must synchronously return None."""

    def __init__(self, console: Any):
        self._console = console
        self._attempted = False
        self._closed = False

    def create_writer(self, password: str, before_send: Callable[[], object]) -> None:
        if (
            not isinstance(password, str)
            or re.fullmatch(r"[A-Za-z0-9]{32,48}", password) is None
        ):
            raise Rejected("writer password shape")
        self._attempt(f"username {USER} privilege 4 password {password}", before_send)

    def remove_writer(self, before_send: Callable[[], object]) -> None:
        self._attempt("no username " + USER, before_send)

    def _transition(self, command: str, prompt: str) -> None:
        unchanged_sources()
        _syntax.transition(self._console, command, prompt)

    def _attempt(self, command: str, before_send: Callable[[], object]) -> None:
        if self._closed or self._attempted:
            raise Rejected("account session already used or closed")
        self._attempted = True
        if not callable(before_send) or iscoroutinefunction(before_send):
            raise Rejected("synchronous durable intent callback required")
        self._transition("configure terminal", _syntax.CONFIG)
        unchanged_sources()
        result = before_send()
        if result is not None:
            if iscoroutine(result):
                result.close()
            raise Rejected("durable intent callback must return None synchronously")
        unchanged_sources()
        self._console.channel.sendall(command + "\r")
        response = _syntax.read_mode(self._console, _syntax.CONFIG)
        if (
            re.fullmatch(re.escape(command) + "\n" + _syntax.CONFIG + r" *", response)
            is None
        ):
            raise Rejected("account leaf echo boundary")
        self._transition("exit", _syntax.EXEC)


@contextmanager
def account_session(
    pin: Path,
    runtime: Path,
    credential_provider: Callable[[], str],
    deadline: float | None = None,
) -> Iterator[WriterAccount]:
    """Read only the root password, lazily after exact pin and remote handshake.

    The provider must return a single printable ASCII password. Received bytes
    are captured before decoding in an exclusive owner-only file outside checkout.
    The caller must hold all admission gates for the entire context.
    """
    unchanged_sources()
    _transport._private_path(pin, directory=False)
    _transport._private_path(runtime, directory=True)
    paramiko = _transport.import_module("paramiko")
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
    fingerprint = "SHA256:" + _transport.base64.b64encode(
        hashlib.sha256(entry.key.asbytes()).digest()
    ).decode().rstrip("=")
    if fingerprint != FINGERPRINT:
        raise Rejected("unaccepted pin")
    with (
        _transport.socket.create_connection(
            (HOST, 22), timeout=_transport._remaining_timeout(deadline, 10)
        ) as sock,
        paramiko.Transport(sock) as transport,
    ):
        transport.start_client(timeout=_transport._remaining_timeout(deadline, 10))
        if transport.get_remote_server_key() != entry.key:
            raise Rejected("host key mismatch")
        unchanged_sources()
        password = credential_provider()
        if (
            not isinstance(password, str)
            or not password
            or len(password) > 256
            or any(ord(char) < 32 or ord(char) > 126 for char in password)
        ):
            if iscoroutine(password):
                password.close()
            raise Rejected("root credential shape")
        unchanged_sources()
        transport.auth_timeout = _transport._remaining_timeout(deadline, 10)
        transport.auth_password(ROOT, password, fallback=False)
        channel = transport.open_session(
            timeout=_transport._remaining_timeout(deadline, 10)
        )
        account = None
        try:
            channel.settimeout(_transport._remaining_timeout(deadline, 10))
            channel.get_pty(term="vt100", width=160, height=24)
            capture_dir = Path(
                tempfile.mkdtemp(prefix="homelab-writer-account-", dir=runtime)
            )
            fd = os.open(
                capture_dir / "received.raw",
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
            )
            with os.fdopen(fd, "wb") as capture:
                console = _transport._Console(
                    _transport._CaptureChannel(channel, capture)
                )
                channel.invoke_shell()
                _enable_root(console, password, deadline)
                account = WriterAccount(console)
                yield account
        finally:
            if account is not None:
                account._closed = True
            channel.close()
