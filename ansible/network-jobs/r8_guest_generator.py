"""Own the fixed, selector-free R8 Fedora traffic process."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
from typing import Any

ROOT = Path(__file__).resolve().parent / "r8-guest-traffic"
RUNNER = ROOT / "run.py"
OUTPUT_LIMIT = 65536
SOURCE_PINS = {
    "run.py": "b5ac5df0451a7a3a42a913880fbcc290975999fbba8a07ebfeaf6dcd03781ae3",
    "guest.py": "35d1db4cc432273f63f5c28284c401b78b0570e20160e549cedda0398b78636b",
    "required-host-known_hosts": "1b176280226f3c5bf476cb8a833d6cd9dbfab70b2ea74c4dc4ff4889cbfb12f0",
}


def unchanged_sources() -> None:
    for name, expected in SOURCE_PINS.items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
            raise Rejected("R8 guest runner dependency drift: " + name)


def collect_network(deadline: float) -> tuple[dict[str, Any], dict[str, Any]]:
    """Collect the fixed Fedora route, gateway, WAN and raw DNS proof."""
    unchanged_sources()
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("Fedora network probe deadline expired")
    try:
        process = subprocess.Popen(
            [sys.executable, "-I", str(RUNNER), "--probe"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            close_fds=True,
            start_new_session=True,
        )
    except OSError as error:
        raise Rejected("Fedora network probe could not start") from error
    try:
        stdout, stderr = process.communicate(timeout=min(25, remaining))
    except subprocess.TimeoutExpired as error:
        os.killpg(process.pid, signal.SIGKILL)
        process.communicate()
        raise TimeoutError("Fedora network probe deadline expired") from error
    if (
        process.returncode != 0
        or stderr
        or len(stdout) > OUTPUT_LIMIT
        or time.monotonic() >= deadline
    ):
        raise Rejected("Fedora network probe failed its bounded contract")
    record = json.loads(stdout)
    if type(record) is not dict or set(record) != {"fedora", "dns"}:
        raise Rejected("Fedora network probe evidence shape differs")
    unchanged_sources()
    return record["fedora"], record["dns"]


class Rejected(RuntimeError):
    """The fixed R8 traffic runner or its evidence failed its contract."""


def _private_json(path: Path) -> dict[str, Any] | None:
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except FileNotFoundError:
        return None
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.geteuid()
            or info.st_mode & 0o077
            or info.st_nlink != 1
            or not 0 < info.st_size <= OUTPUT_LIMIT
        ):
            raise Rejected("private guest runner evidence shape")
        raw = stream.read(OUTPUT_LIMIT + 1)
        if len(raw) != info.st_size:
            raise Rejected("private guest runner evidence changed")
    value = json.loads(raw)
    if type(value) is not dict:
        raise Rejected("guest runner JSON object required")
    return value


class FiniteGuestGenerator:
    """Run one pinned remote ping and reap only its owned process group."""

    def __init__(self) -> None:
        self._directory: Path | None = None
        self._output: Path | None = None
        self._process: subprocess.Popen[bytes] | None = None

    def start(self, deadline: float) -> None:
        if self._process is not None:
            raise Rejected("guest generator already started")
        if time.monotonic() >= deadline:
            raise TimeoutError("guest generator start deadline expired")
        unchanged_sources()
        directory = Path(tempfile.mkdtemp(prefix="r8-guest-"))
        os.chmod(directory, 0o700)
        output = directory / "output"
        self._directory, self._output = directory, output
        self._process = subprocess.Popen(
            [sys.executable, "-I", str(RUNNER), "--output", str(output)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )

    def readiness(self, deadline: float) -> dict[str, Any]:
        if self._output is None or self._process is None:
            raise Rejected("guest generator was not started")
        path = self._output / "readiness.json"
        while time.monotonic() < deadline:
            record = _private_json(path)
            if record is not None:
                if record.get("status") != "traffic_started":
                    raise Rejected("guest traffic readiness record differs")
                return record
            if self._process.poll() is not None:
                raise Rejected("guest traffic exited before readiness")
            time.sleep(min(0.1, max(0, deadline - time.monotonic())))
        raise TimeoutError("guest traffic readiness deadline expired")

    def active(self, deadline: float) -> bool:
        if time.monotonic() >= deadline:
            raise TimeoutError("guest traffic active check deadline expired")
        if self._process is None:
            raise Rejected("guest generator was not started")
        return self._process.poll() is None

    def hold(self, deadline: float, start: float, offsets: list[float]) -> None:
        if len(offsets) != 2 or time.monotonic() >= deadline:
            raise Rejected("guest held-window bounds required")
        end = start + 4.0
        while time.time() < end:
            if time.monotonic() >= deadline:
                raise TimeoutError("guest held-window deadline expired")
            if self._process is None or self._process.poll() is not None:
                raise Rejected("guest traffic ended during held window")
            time.sleep(min(0.1, end - time.time()))

    def finish(self, deadline: float) -> dict[str, Any]:
        if self._process is None or self._output is None:
            raise Rejected("guest generator was not started")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("guest traffic completion deadline expired")
        try:
            self._process.wait(timeout=remaining)
        except subprocess.TimeoutExpired as error:
            raise TimeoutError("guest traffic completion deadline expired") from error
        result = _private_json(self._output / "result.json")
        if result is None:
            raise Rejected("guest traffic terminal evidence missing")
        return result

    def stop(self, timeout: float) -> None:
        process = self._process
        if process is not None and process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=min(timeout, 0.5))
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=max(0.1, timeout - 0.5))
            except ProcessLookupError:
                process.wait(timeout=timeout)
        if process is not None and process.poll() is None:
            raise TimeoutError("owned guest traffic process was not reaped")
        if self._directory is not None:
            shutil.rmtree(self._directory)
        self._process = None
        self._output = None
        self._directory = None
