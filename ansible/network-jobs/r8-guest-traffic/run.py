"""Strict SSH runner for one finite guest traffic process."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import select
import subprocess
import time

ROOT = Path(__file__).resolve().parent
GUEST_SHA256 = "35d1db4cc432273f63f5c28284c401b78b0570e20160e549cedda0398b78636b"
KNOWN_HOSTS_SHA256 = "1b176280226f3c5bf476cb8a833d6cd9dbfab70b2ea74c4dc4ff4889cbfb12f0"


def private_write(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def budget(seconds):
    if type(seconds) is not int or not 1 <= seconds <= 130:
        raise RuntimeError("SSH deadline must be between 1 and 130 seconds")
    return time.monotonic() + seconds


def ssh_argv(operation=""):
    return [
        "ssh",
        "-F",
        "/dev/null",
        "-T",
        "-i",
        str(Path.home() / ".ssh/id_ed25519"),
        "-o",
        "BatchMode=yes",
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        "UserKnownHostsFile=" + str(ROOT / "required-host-known_hosts"),
        "-o",
        "GlobalKnownHostsFile=/dev/null",
        "-o",
        "ConnectTimeout=5",
        "-o",
        "ConnectionAttempts=1",
        "-o",
        "ServerAliveInterval=2",
        "-o",
        "ServerAliveCountMax=1",
        "mpeter@192.168.0.114",
        "python3 -I -" + (" " + operation if operation else ""),
    ]


def launch(output):
    source = (ROOT / "guest.py").read_bytes()
    if (
        hashlib.sha256(source).hexdigest() != GUEST_SHA256
        or hashlib.sha256((ROOT / "required-host-known_hosts").read_bytes()).hexdigest()
        != KNOWN_HOSTS_SHA256
    ):
        raise RuntimeError("reviewed source or host key binding differs")
    output.mkdir(mode=0o700)
    deadline = budget(130)
    process = subprocess.Popen(
        ssh_argv(),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    stdout, stderr, pending = bytearray(), bytearray(), bytearray()
    ready, terminal, failure = None, None, None
    try:
        if process.stdin is None or process.stdout is None or process.stderr is None:
            raise RuntimeError("SSH pipes unavailable")
        process.stdin.write(source)
        process.stdin.close()
        streams = {process.stdout.fileno(): "stdout", process.stderr.fileno(): "stderr"}
        while streams:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError("SSH runner deadline expired")
            readable, _, _ = select.select(list(streams), [], [], min(remaining, 0.2))
            for fd in readable:
                chunk = os.read(fd, 8192)
                if not chunk:
                    streams.pop(fd)
                    continue
                if streams[fd] == "stderr":
                    stderr.extend(chunk[: max(0, 4096 - len(stderr))])
                    if len(stderr) == 4096:
                        raise RuntimeError("SSH stderr reached its byte limit")
                    continue
                stdout.extend(chunk[: max(0, 65536 - len(stdout))])
                if len(stdout) == 65536:
                    raise RuntimeError("SSH stdout reached its byte limit")
                pending.extend(chunk)
                while b"\n" in pending:
                    line, _, rest = pending.partition(b"\n")
                    pending = bytearray(rest)
                    record = json.loads(line)
                    status = record.get("status")
                    if status == "traffic_started":
                        if (
                            ready is not None
                            or type(record.get("pid")) is not int
                            or record["pid"] <= 0
                        ):
                            raise RuntimeError("traffic readiness invalid or repeated")
                        datetime.fromisoformat(record["observed_at"])
                        ready = record
                        private_write(
                            output / "readiness.json",
                            (json.dumps(record) + "\n").encode(),
                        )
                        print(json.dumps(record), flush=True)
                    elif status in {
                        "traffic_complete",
                        "traffic_failed",
                        "traffic_rejected",
                    }:
                        if terminal is not None:
                            raise RuntimeError("traffic terminal record repeated")
                        terminal = record
                    else:
                        raise RuntimeError("unexpected guest traffic record")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeError("SSH runner deadline expired")
        process.wait(timeout=remaining)
    except Exception as error:
        failure = type(error).__name__
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=2)
        private_write(output / "stdout", bytes(stdout))
        private_write(output / "stderr", bytes(stderr))
        passed = (
            process.returncode == 0
            and ready is not None
            and terminal is not None
            and terminal.get("status") == "traffic_complete"
            and terminal.get("pid") == ready["pid"]
            and not pending
            and failure is None
        )
        result = {
            "status": "passed" if passed else "failed",
            "returncode": process.returncode,
            "failure_type": failure,
            "readiness": ready,
            "terminal": terminal,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "ssh_deadline_seconds": 130,
        }
        private_write(
            output / "result.json", (json.dumps(result, indent=2) + "\n").encode()
        )
    print(json.dumps(result), flush=True)
    return 0 if passed else 1


def probe():
    source = (ROOT / "guest.py").read_bytes()
    if (
        hashlib.sha256(source).hexdigest() != GUEST_SHA256
        or hashlib.sha256((ROOT / "required-host-known_hosts").read_bytes()).hexdigest()
        != KNOWN_HOSTS_SHA256
    ):
        raise RuntimeError("reviewed source or host key binding differs")
    process = subprocess.Popen(
        ssh_argv("probe"),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    stdout, stderr = bytearray(), bytearray()
    try:
        if process.stdin is None or process.stdout is None or process.stderr is None:
            raise RuntimeError("Fedora probe SSH pipes unavailable")
        process.stdin.write(source)
        process.stdin.close()
        streams = {process.stdout.fileno(): stdout, process.stderr.fileno(): stderr}
        deadline = time.monotonic() + 20
        while streams:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError("Fedora network probe deadline expired")
            readable, _, _ = select.select(list(streams), [], [], min(remaining, 0.2))
            for fd in readable:
                chunk = os.read(fd, 8192)
                if not chunk:
                    streams.pop(fd)
                    continue
                buffer = streams[fd]
                limit = 32768 if buffer is stdout else 4096
                if len(buffer) + len(chunk) > limit:
                    raise RuntimeError("Fedora network probe output exceeded its bound")
                buffer.extend(chunk)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeError("Fedora network probe deadline expired")
        process.wait(timeout=remaining)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=2)
    if process.returncode != 0 or stderr or len(stdout.splitlines()) != 1:
        raise RuntimeError("Fedora network probe failed its bounded SSH contract")
    record = json.loads(stdout)
    if type(record) is not dict or set(record) != {"fedora", "dns"}:
        raise RuntimeError("Fedora network probe evidence shape differs")
    print(json.dumps(record, separators=(",", ":")), flush=True)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--probe", action="store_true")
    args = parser.parse_args()
    if args.probe:
        if args.output is not None:
            parser.error("--probe does not accept --output")
        raise SystemExit(probe())
    if args.output is None:
        parser.error("--output is required for the traffic generator")
    raise SystemExit(launch(args.output))
