"""Local durable coordination for the adopted Brocade persistence root.

The caller selects the canonical private parent. Alternate roots and other hosts
are not coordinated by this filesystem lock. Phase records describe evidence;
the orchestrator remains responsible for switch mutation and admission gates.
"""

from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Iterator

# Full R8 intent records can embed an independently collected guest proof.
# Keep the reader bounded while allowing those canonical records to be read
# back during restoration and custody reconciliation.
LIMIT = 1024 * 1024
PHASES = (
    "bootstrap_intent",
    "bootstrap_observed",
    "description_intent",
    "description_observed",
    "inverse_intent",
    "inverse_observed",
    "removal_intent",
    "final_observed",
)
BINDING_KEYS = frozenset(
    (
        "baseline_running_sha256",
        "baseline_startup_sha256",
        "preview_sha256",
        "execution_environment_sha256",
        "engine_sha256",
        "writer_sha256",
        "bootstrap_sha256",
    )
)
FIXED = {
    "schema": 2,
    "operation": "port_description_serialization_exercise",
    "host": "192.168.0.251",
    "fingerprint": "SHA256:UJulVmfAMmHcUctvJrlGzBZR7I7uN8/TWNeJIs25yks",
    "writer": "homelab_writer",
    "port": "1/1/47",
    "desired": "homelab-description-exercise",
}


class Rejected(Exception):
    """An input or coordination invariant failed; payloads are never reported."""


class Uncertain(Rejected):
    """Durability or an interrupted operation requires recovery inspection."""


def canonical(data: object) -> bytes:
    return (json.dumps(data, sort_keys=True, separators=(",", ":")) + "\n").encode()


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def identity(info: os.stat_result) -> tuple[int, int]:
    return info.st_dev, info.st_ino


def private_directory(path: Path) -> tuple[int, int]:
    if not path.is_absolute() or ".." in path.parts:
        raise Rejected("private directory path")
    for component in (path, *path.parents):
        if component.is_symlink():
            raise Rejected("private directory symlink")
    info = path.lstat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.getuid()
        or stat.S_IMODE(info.st_mode) != 0o700
    ):
        raise Rejected("private directory ownership or mode")
    return identity(info)


def private_file(info: os.stat_result) -> None:
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.getuid()
        or stat.S_IMODE(info.st_mode) != 0o600
        or info.st_nlink != 1
    ):
        raise Rejected("private file ownership, mode or links")


def sync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def exclusive_write(path: Path, raw: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        private_file(os.fstat(fd))
        if os.write(fd, raw) != len(raw):
            raise Uncertain("short journal write")
        os.fsync(fd)
    finally:
        os.close(fd)
    sync_directory(path.parent)


def read_file(path: Path) -> tuple[bytes, tuple[int, int]]:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        private_file(info)
        if not 0 < info.st_size <= LIMIT:
            raise Rejected("journal size")
        raw = os.read(fd, LIMIT + 1)
        if len(raw) != info.st_size or len(raw) > LIMIT:
            raise Rejected("journal size changed")
        if identity(path.lstat()) != identity(info):
            raise Rejected("journal path changed")
        return raw, identity(info)
    finally:
        os.close(fd)


def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise Rejected("duplicate journal key")
        result[key] = value
    return result


def decode(raw: bytes) -> dict[str, object]:
    try:
        value = json.loads(raw, object_pairs_hook=unique_object)
        if not isinstance(value, dict) or canonical(value) != raw:
            raise Rejected("noncanonical journal")
        return value
    except (ValueError, UnicodeError, RecursionError) as error:
        raise Rejected("invalid journal JSON") from error


def hashes(data: object, keys: frozenset[str]) -> dict[str, str]:
    if (
        not isinstance(data, dict)
        or set(data) != keys
        or not all(
            type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value)
            for value in data.values()
        )
    ):
        raise Rejected("digest binding shape")
    return data


class ExerciseLedger:
    def __init__(self, parent: Path, runtime: Path, path: Path, lock_fd: int):
        self.parent = parent
        self.runtime = runtime
        self.path = path
        self.pending = path / "pending.json"
        self.lock_fd = lock_fd
        self.lock_identity = identity(os.fstat(lock_fd))
        self.directories = {p: private_directory(p) for p in (parent, runtime, path)}
        self.data: dict[str, object] | None = None
        self.phases: list[dict[str, object]] = []
        self.files: dict[Path, tuple[bytes, tuple[int, int]]] = {}
        self.failed = False
        self.closed = False

    def guard(self) -> None:
        if self.closed:
            raise Rejected("exercise coordination context is closed")
        if self.failed:
            raise Uncertain("journal requires recovery after failed write")
        for path, expected in self.directories.items():
            if private_directory(path) != expected:
                raise Uncertain("private directory replaced")
        info = (self.path / "lock").lstat()
        private_file(info)
        held = os.fstat(self.lock_fd)
        private_file(held)
        if identity(info) != self.lock_identity or identity(held) != self.lock_identity:
            raise Uncertain("coordination lock replaced")
        for path, expected_file in self.files.items():
            if read_file(path) != expected_file:
                raise Uncertain("journal file changed")

    @property
    def origin(self) -> Path:
        if self.data is None:
            raise Rejected("no loaded exercise")
        return Path(str(self.data["runtime"]))

    def remember(self, path: Path) -> dict[str, object]:
        self.files[path] = read_file(path)
        return decode(self.files[path][0])

    def begin(self, binding: dict[str, str]) -> None:
        self.guard()
        checked = hashes(binding, BINDING_KEYS)
        if checked["baseline_running_sha256"] != checked["baseline_startup_sha256"]:
            raise Rejected("baseline is not stable")
        if os.path.lexists(self.pending) or self.data is not None:
            raise Uncertain("pending operation blocks new exercise")
        if any(
            entry.name.startswith("exercise-phase-")
            or entry.name == "exercise-complete.json"
            for entry in self.runtime.iterdir()
        ):
            raise Rejected("exercise runtime already contains journal records")
        data: dict[str, object] = {
            **FIXED,
            "binding": dict(checked),
            "runtime": str(self.runtime),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        data["operation_id"] = digest(canonical(data))
        try:
            exclusive_write(self.pending, canonical(data))
            self.data = self.remember(self.pending)
        except (OSError, Rejected, KeyboardInterrupt) as error:
            self.failed = True
            raise Uncertain("exercise begin durability uncertain") from error

    def load(self, binding: dict[str, str]) -> None:
        self.guard()
        checked = hashes(binding, BINDING_KEYS)
        try:
            data = self.remember(self.pending)
            required = set(FIXED) | {"binding", "runtime", "created_at", "operation_id"}
            if set(data) != required or type(data["schema"]) is not int:
                raise Rejected("pending exercise schema")
            if any(data[key] != value for key, value in FIXED.items()):
                raise Rejected("pending operation identity")
            if hashes(data["binding"], BINDING_KEYS) != checked:
                raise Rejected("pending digest binding")
            if checked["baseline_running_sha256"] != checked["baseline_startup_sha256"]:
                raise Rejected("pending baseline is not stable")
            initial = {
                key: value for key, value in data.items() if key != "operation_id"
            }
            if data["operation_id"] != digest(canonical(initial)):
                raise Rejected("pending operation digest")
            stamp = data["created_at"]
            if type(stamp) is not str:
                raise Rejected("pending timestamp")
            parsed = datetime.fromisoformat(stamp)
            if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(
                parsed
            ):
                raise Rejected("pending UTC timestamp")
            runtime = data["runtime"]
            if (
                type(runtime) is not str
                or any(ord(c) < 32 or ord(c) == 127 for c in runtime)
                or Path(runtime).parent != self.parent
            ):
                raise Rejected("pending origin runtime")
            origin = Path(runtime)
            self.directories[origin] = private_directory(origin)
            self.data = data
            self.read_chain()
            self.sync_recovered_records()
        except (OSError, ValueError, Rejected, KeyboardInterrupt) as error:
            self.failed = True
            raise Uncertain("pending exercise requires recovery") from error

    def sync_recovered_records(self) -> None:
        """Establish durability of full records left by interrupted writes."""
        self.guard()
        for path, (_, expected_identity) in self.files.items():
            self.guard()
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            try:
                info = os.fstat(fd)
                private_file(info)
                if identity(info) != expected_identity:
                    raise Uncertain("recovered journal inode changed")
                os.fsync(fd)
            finally:
                os.close(fd)
            self.guard()
        for directory in (self.origin, self.path, self.parent):
            self.guard()
            sync_directory(directory)
            self.guard()

    def phase_path(self, index: int, phase: str) -> Path:
        return self.origin / f"exercise-phase-{index:02d}-{phase}.json"

    def read_chain(self) -> None:
        self.guard()
        if self.data is None:
            raise Rejected("no loaded exercise")
        names = {
            p.name
            for p in self.origin.iterdir()
            if p.name.startswith("exercise-phase-")
        }
        if len(names) > len(PHASES):
            raise Rejected("phase chain count")
        records: list[dict[str, object]] = []
        previous = digest(self.files[self.pending][0])
        for index, phase in enumerate(PHASES, 1):
            path = self.phase_path(index, phase)
            if path.name not in names:
                break
            record = self.remember(path)
            if (
                set(record)
                != {"operation_id", "phase", "index", "prev_digest", "metadata"}
                or type(record["index"]) is not int
                or record["index"] != index
                or record["phase"] != phase
                or self.data is None
                or record["operation_id"] != self.data["operation_id"]
                or record["prev_digest"] != previous
            ):
                raise Rejected("phase chain binding")
            self.metadata(phase, record["metadata"])
            records.append(record)
            previous = digest(self.files[path][0])
        if names != {
            self.phase_path(i, str(r["phase"])).name for i, r in enumerate(records, 1)
        }:
            raise Rejected("phase chain order or unexpected record")
        self.phases = records

    @staticmethod
    def metadata(phase: str, metadata: object) -> None:
        if phase.endswith("_intent"):
            if type(metadata) is not dict or metadata:
                raise Rejected("intent metadata")
        else:
            hashes(
                metadata,
                frozenset(("running_sha256", "startup_sha256", "evidence_sha256")),
            )

    def append_phase(self, phase: str, observedmetadata: dict[str, str]) -> None:
        self.guard()
        self.read_chain()
        if len(self.phases) == len(PHASES) or phase != PHASES[len(self.phases)]:
            raise Rejected("phase out of order")
        self.metadata(phase, observedmetadata)
        index = len(self.phases) + 1
        previous_path = (
            self.pending
            if index == 1
            else self.phase_path(index - 1, PHASES[index - 2])
        )
        if self.data is None:
            raise Rejected("no loaded exercise")
        record = {
            "operation_id": self.data["operation_id"],
            "phase": phase,
            "index": index,
            "prev_digest": digest(self.files[previous_path][0]),
            "metadata": dict(observedmetadata),
        }
        path = self.phase_path(index, phase)
        try:
            exclusive_write(path, canonical(record))
            self.remember(path)
            self.phases.append(record)
        except (OSError, Rejected, KeyboardInterrupt) as error:
            self.failed = True
            raise Uncertain("phase append durability uncertain") from error

    def finish(self) -> None:
        self.guard()
        self.read_chain()
        if len(self.phases) != len(PHASES) or self.data is None:
            raise Rejected("exercise is incomplete")
        final = hashes(
            self.phases[-1]["metadata"],
            frozenset(("running_sha256", "startup_sha256", "evidence_sha256")),
        )
        binding = hashes(self.data["binding"], BINDING_KEYS)
        if (
            final["running_sha256"] != binding["baseline_running_sha256"]
            or final["startup_sha256"] != binding["baseline_startup_sha256"]
        ):
            raise Rejected("final baseline differs")
        raw = self.files[self.pending][0]
        receipt = self.origin / "exercise-complete.json"
        payload = {
            "operation_id": self.data["operation_id"],
            "status": "complete",
            "final_digest": digest(self.files[self.phase_path(8, PHASES[-1])][0]),
        }
        try:
            if os.path.lexists(receipt):
                if self.remember(receipt) != payload:
                    raise Rejected("completion receipt differs")
                fd = os.open(receipt, os.O_RDONLY | os.O_NOFOLLOW)
                try:
                    private_file(os.fstat(fd))
                    os.fsync(fd)
                finally:
                    os.close(fd)
                sync_directory(self.origin)
            else:
                exclusive_write(receipt, canonical(payload))
                self.remember(receipt)
            self.guard()
            self.pending.unlink()
            try:
                sync_directory(self.path)
            except (OSError, KeyboardInterrupt):
                # One restoration attempt retains the exact blocking payload.
                if not os.path.lexists(self.pending):
                    exclusive_write(self.pending, raw)
                raise
        except (OSError, Rejected, KeyboardInterrupt) as error:
            self.failed = True
            raise Uncertain("completion durability uncertain") from error
        self.files.pop(self.pending)
        self.data = None


@contextmanager
def locked_exercise(parent: Path, runtime: Path) -> Iterator[ExerciseLedger]:
    """Lock the caller's adopted root, interoperating with account persistence."""
    private_directory(parent)
    private_directory(runtime)
    checkout = Path(__file__).resolve().parents[2]
    if parent.is_relative_to(checkout) or runtime.parent != parent:
        raise Rejected("private runtime location")
    path = parent / "brocade-persistence-ledger"
    if not os.path.lexists(path):
        path.mkdir(mode=0o700)
        sync_directory(parent)
    private_directory(path)
    lock = path / "lock"
    fd = os.open(lock, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    ledger: ExerciseLedger | None = None
    try:
        private_file(os.fstat(fd))
        if identity(lock.lstat()) != identity(os.fstat(fd)):
            raise Rejected("coordination lock replaced")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise Rejected("another persistence workflow holds the lock") from error
        os.fsync(fd)
        sync_directory(path)
        ledger = ExerciseLedger(parent, runtime, path, fd)
        ledger.guard()
        yield ledger
    finally:
        if ledger is not None:
            ledger.closed = True
        os.close(fd)
