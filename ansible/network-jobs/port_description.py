#!/usr/bin/env python3
"""Credential-free, private draft previews and configuration-only verification."""

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import Any

HOST = "192.168.0.251"
MODEL = "ICX6610-48P"
RELEASE = "08.0.30uT7f3"
FINGERPRINT = "SHA256:UJulVmfAMmHcUctvJrlGzBZR7I7uN8/TWNeJIs25yks"
EE_DIGEST = "7eb690b9bbac7dd602ad4eac7b1a537a1f3d8e54d6178e764b0e4df96813c2e2"
CHECKOUT = Path(__file__).resolve().parents[2]
AUDIT = Path(__file__).resolve().parents[1] / "network-audit"
SOURCE_PATHS = {
    "collector": Path(__file__).with_name("collect-port-evidence.py"),
    "bootstrap": AUDIT / "bootstrap-identity.py",
    "capture": AUDIT / "capture.py",
    "launcher": AUDIT / "run-audit.py",
    "engine": Path(__file__).resolve(),
}
SOURCE_SHA256 = {
    name: hashlib.sha256(path.read_bytes()).hexdigest()
    for name, path in SOURCE_PATHS.items()
}
COMMANDS = (
    "show version",
    "show running-config",
    "show configuration",
    "show interfaces brief",
    "show mac-address",
)
ERROR = re.compile(
    r"(?:^|\n)\s*%|invalid (?:input|command)|unknown command|not authorized|"
    r"access denied|error:|permission denied|insufficient privilege|not allowed|"
    r"command authorization failed",
    re.I,
)
MAX_BYTES = 4 * 1024 * 1024
LIMITATIONS = (
    "firmware command syntax and configuration serialization are unverified",
    "observed absent-interface serialization evidence is required for admission",
    "unused port and reserved purpose require separate operational review",
    "dedicated writer, recovery, rescue, backup and approval gates are unverified",
    "configuration verification does not verify management, rescue or restore",
    "private input bindings are digests, not authenticated operational acceptance",
)


class Rejected(ValueError):
    """Invalid input; never echo private input in diagnostics."""


def unchanged_sources() -> None:
    if any(
        hashlib.sha256(p.read_bytes()).hexdigest() != SOURCE_SHA256[n]
        for n, p in SOURCE_PATHS.items()
    ):
        raise Rejected("source drift")


def port(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(
        r"1/1/(?:[1-9]|[1-3][0-9]|4[0-7])", value
    ):
        raise Rejected("invalid front-panel port")
    return value


def description(value: str) -> str:
    if (
        not isinstance(value, str)
        or not re.fullmatch(r"[A-Za-z0-9 _.\-]{1,48}", value)
        or value != value.strip()
        or ERROR.search(value)
    ):
        raise Rejected("invalid description")
    return value


def configuration(text: str) -> tuple[str, ...]:
    """Use the pinned collector's canonical boundaries, preserving ordered lines."""
    if (
        not isinstance(text, str)
        or not text.isascii()
        or re.search(r"[^\x20-\x7e\r\n]", text)
        or re.search(r"\r(?!\n)", text)
        or ERROR.search(text)
    ):
        raise Rejected("configuration characters or error")
    lines = tuple(line.rstrip() for line in text.splitlines() if line.strip())
    starts = [
        i
        for i, line in enumerate(lines)
        if re.fullmatch(r"(?:ver|version) " + re.escape(RELEASE), line)
    ]
    if len(starts) != 1 or not lines or lines[-1] != "end":
        raise Rejected("configuration boundary")
    for line in lines[: starts[0]]:
        if not re.fullmatch(
            r"(?:Current configuration:.*|Startup configuration:.*|"
            r"Startup-config data location is flash memory|!|\d+ bytes)",
            line,
        ):
            raise Rejected("configuration header")
    result = lines[starts[0] :]
    if "end" in result[:-1]:
        raise Rejected("early configuration end")
    stanzas(result)
    return result


def stanzas(lines: tuple[str, ...]) -> dict[str, tuple[int, int, int | None]]:
    """Require single physical interfaces and unambiguous one-space leaves."""
    result: dict[str, tuple[int, int, int | None]] = {}
    for start, line in enumerate(lines):
        if not line.lstrip().startswith("interface"):
            continue
        if not line.lstrip().startswith("interface ethernet"):
            if line.startswith(" "):
                raise Rejected("ambiguous interface indentation")
            continue
        match = re.fullmatch(
            r"interface ethernet ([1-9][0-9]*/[1-9][0-9]*/[1-9][0-9]*)", line
        )
        if match is None:
            raise Rejected("ambiguous interface stanza")
        name = match.group(1)
        if name in result:
            raise Rejected("duplicate interface stanza")
        end = start + 1
        leaf: int | None = None
        while end < len(lines) and lines[end].startswith(" "):
            child = lines[end]
            if child.startswith("  "):
                raise Rejected("ambiguous interface indentation")
            if child.lstrip().startswith("port-name"):
                value = child.removeprefix(" port-name ")
                if not child.startswith(" port-name ") or leaf is not None:
                    raise Rejected("duplicate or ambiguous port-name")
                description(value)
                leaf = end
            end += 1
        result[name] = (start, end, leaf)
    # A port-name outside a physical stanza cannot be safely interpreted.
    leaves = {leaf for _, _, leaf in result.values() if leaf is not None}
    if any(
        line.lstrip().startswith("port-name") and i not in leaves
        for i, line in enumerate(lines)
    ):
        raise Rejected("orphan port-name")
    return result


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("ascii")
    ).hexdigest()


def configuration_hash(lines: tuple[str, ...]) -> str:
    """Match the collector/recovery canonical configuration byte definition."""
    return hashlib.sha256(("\n".join(lines) + "\n").encode("ascii")).hexdigest()


def valid_digest(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def evidence_config(
    payload: Any, selected: str
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    unchanged_sources()
    commands = (*COMMANDS, f"show interfaces ethernet {port(selected)}")
    if (
        not isinstance(payload, dict)
        or type(payload.get("schema")) is not int
        or payload["schema"] != 1
    ):
        raise Rejected("evidence schema")
    expected = {
        "host": HOST,
        "model": MODEL,
        "release": RELEASE,
        "identity": "homelab_audit",
        "accepted_host_key_fingerprint": FINGERPRINT,
        "selected_port": selected,
        "commands": list(commands),
        "expected_execution_environment_sha256": EE_DIGEST,
        "terminal_boundaries_complete": True,
    }
    if any(
        type(payload.get(k)) is not type(v) or payload.get(k) != v
        for k, v in expected.items()
    ):
        raise Rejected("evidence target or boundary")
    if payload.get("source_sha256") != {
        k: v for k, v in SOURCE_SHA256.items() if k != "engine"
    }:
        raise Rejected("evidence source drift")
    raw = payload.get("raw_capture_sha256")
    if (
        not isinstance(raw, dict)
        or len(raw) not in (6, 10)
        or set(raw) != {f"capture-{i:02}.txt" for i in range(1, len(raw) + 1)}
        or any(
            not re.fullmatch(r"capture-(?:0[1-9]|10)\.txt", k) or not valid_digest(v)
            for k, v in raw.items()
        )
    ):
        raise Rejected("raw capture bindings")
    responses = payload.get("responses")
    if (
        not isinstance(responses, dict)
        or set(responses) != set(commands)
        or any(not isinstance(v, str) or not v.strip() for v in responses.values())
    ):
        raise Rejected("evidence responses")
    version = responses[COMMANDS[0]]
    if (
        ERROR.search(version)
        or re.findall(r"\bSW:\s+Version\s+(\S+)", version) != [RELEASE]
        or re.findall(
            r"^UNIT 1: SL 1: (ICX\d+-\S+) POE.*Management Module$", version, re.M
        )
        != [MODEL]
        or not re.fullmatch(
            r'The system\s*:\s*started=(?:cold start|warm start(?:[ \t]+reloaded=by "reload")?)',
            version.strip().splitlines()[-1].strip(),
        )
    ):
        raise Rejected("version boundary")
    return configuration(responses[COMMANDS[1]]), configuration(responses[COMMANDS[2]])


@dataclass(frozen=True)
class Preview:
    schema: int
    status: str
    selected_port: str
    desired_description: str
    original_description: str | None
    before_running: tuple[str, ...]
    before_startup: tuple[str, ...]
    expected_running: tuple[str, ...]
    original_running_sha256: str
    original_startup_sha256: str
    expected_running_sha256: str
    input_binding_sha256: str
    source_sha256: tuple[tuple[str, str], ...]
    response_sha256: tuple[tuple[str, str], ...]
    raw_capture_sha256: tuple[tuple[str, str], ...]
    forward_commands: tuple[str, ...]
    inverse_commands: tuple[str, ...]
    host: str = HOST
    model: str = MODEL
    release: str = RELEASE
    accepted_host_key_fingerprint: str = FINGERPRINT
    expected_execution_environment_sha256: str = EE_DIGEST
    admitted: bool = False
    apply_enabled: bool = False
    exact_firmware_syntax_verified: bool = False
    observed_serialization_verified: bool = False
    limitations: tuple[str, ...] = LIMITATIONS

    @property
    def preview_sha256(self) -> str:
        return digest(asdict(self))


def build_preview(payload: Any, selected: str, desired: str) -> Preview:
    selected, desired = port(selected), description(desired)
    before, startup = evidence_config(payload, selected)
    if before != startup:
        raise Rejected("unsaved baseline")
    accounts = [
        line for line in before if re.match(r"username homelab_audit\b", line.lstrip())
    ]
    if len(accounts) != 1 or not re.fullmatch(
        r"username homelab_audit privilege 5 password \S[^\r\n]*", accounts[0]
    ):
        raise Rejected("persisted audit account required")
    interfaces = stanzas(before)
    original = None
    expected = list(before)
    if selected in interfaces:
        start, end, leaf = interfaces[selected]
        if leaf is not None:
            original = description(before[leaf].removeprefix(" port-name "))
            expected[leaf] = f" port-name {desired}"
        else:
            expected.insert(start + 1, f" port-name {desired}")
    else:
        # Diagnostic candidate only: absent-stanza placement has no firmware receipt.
        ordered = sorted(interfaces, key=lambda name: tuple(map(int, name.split("/"))))
        later = [
            name
            for name in ordered
            if tuple(map(int, name.split("/"))) > tuple(map(int, selected.split("/")))
        ]
        index = interfaces[later[0]][0] if later else len(before) - 1
        expected[index:index] = [
            f"interface ethernet {selected}",
            f" port-name {desired}",
        ]
    prefix = ("configure terminal", f"interface ethernet {selected}")
    suffix = ("exit", "exit")
    return Preview(
        schema=1,
        status="draft_unverified",
        selected_port=selected,
        desired_description=desired,
        original_description=original,
        before_running=before,
        before_startup=startup,
        expected_running=tuple(expected),
        original_running_sha256=configuration_hash(before),
        original_startup_sha256=configuration_hash(startup),
        expected_running_sha256=configuration_hash(tuple(expected)),
        input_binding_sha256=digest(payload),
        source_sha256=tuple(sorted(SOURCE_SHA256.items())),
        response_sha256=tuple(
            (command, digest(payload["responses"][command]))
            for command in (*COMMANDS, f"show interfaces ethernet {selected}")
        ),
        raw_capture_sha256=tuple(sorted(payload["raw_capture_sha256"].items())),
        forward_commands=(*prefix, f"port-name {desired}", *suffix),
        inverse_commands=(
            *prefix,
            "no port-name" if original is None else f"port-name {original}",
            *suffix,
        ),
    )


def verify_configuration(preview: Preview, payload: Any) -> dict[str, Any]:
    """Classify configuration observations only; never authorize a writer."""
    running, startup = evidence_config(payload, preview.selected_port)
    original = running == preview.before_running and startup == preview.before_startup
    applied = running == preview.expected_running and startup == preview.before_startup
    return {
        "schema": 1,
        "scope": "configuration_only",
        "preview_sha256": preview.preview_sha256,
        "classification": "unchanged"
        if original
        else "applied"
        if applied
        else "uncertain",
        "expected_running_and_original_startup": applied,
        "rollback_exact_original_running_and_startup": original,
        "running_sha256": configuration_hash(running),
        "startup_sha256": configuration_hash(startup),
        "input_binding_sha256": digest(payload),
        "apply_enabled": False,
        "limitations": LIMITATIONS,
    }


def classify_observed_serialization(
    before_running: tuple[str, ...],
    before_startup: tuple[str, ...],
    after_running: tuple[str, ...],
    after_startup: tuple[str, ...],
    selected: str,
    desired: str,
) -> dict[str, Any]:
    """Recognize an exact insertion; do not establish baseline authorization."""
    selected, desired = port(selected), description(desired)
    for lines in (before_running, before_startup, after_running, after_startup):
        if configuration("\n".join(lines)) != lines:
            raise Rejected("canonical configuration tuple required")
    before, baseline_startup = before_running, before_startup
    after, startup = after_running, after_startup
    if selected in stanzas(before):
        raise Rejected("observed serialization requires absent baseline stanza")
    unchanged = after == before and startup == baseline_startup
    inserted: tuple[str, ...] | None = None
    insertion_index: int | None = None
    target = stanzas(after).get(selected)
    if startup == baseline_startup and target is not None:
        start, end, leaf = target
        block = (f"interface ethernet {selected}", f" port-name {desired}")
        if end == start + 2 and leaf == start + 1 and after[start:end] == block:
            # Remove only this contiguous block, optionally its following separator.
            for size in (2, 3):
                candidate = after[start : start + size]
                if size == 3 and candidate != (*block, "!"):
                    continue
                if after[:start] + after[start + size :] != before:
                    continue
                # Version and end bound the body; indented leaves are not boundaries.
                if not 0 < start < len(before) or before[start].startswith(" "):
                    continue
                inserted, insertion_index = candidate, start
                break
    observed = inserted is not None
    return {
        "schema": 1,
        "scope": "configuration_only",
        "classifier": "first_exercise_observed_serialization",
        "classification": "unchanged"
        if unchanged
        else "observed"
        if observed
        else "uncertain",
        "observed_insertion_configuration_only": observed,
        "actual_insertion_index": insertion_index,
        "actual_inserted_block_sha256": configuration_hash(inserted)
        if inserted is not None
        else None,
        "actual_separator_inserted": inserted is not None and len(inserted) == 3,
        "original_running_sha256": configuration_hash(before),
        "original_startup_sha256": configuration_hash(baseline_startup),
        "after_running_sha256": configuration_hash(after),
        "after_startup_sha256": configuration_hash(startup),
        "live_admission": False,
        "apply_enabled": False,
        "task_complete": False,
        "observed_serialization_verified": False,
        "limitations": (
            *LIMITATIONS,
            "capture bindings do not authenticate live identity, operator or transport",
            "offline fixtures never establish live serializer verification",
            "pure classification does not establish baseline authorization",
        ),
    }


def verify_observed_serialization(
    preview: Preview, after_payload: Any, restored_payload: Any
) -> dict[str, Any]:
    """Bind first-exercise captures and require an exact saved-baseline restore."""
    if preview.before_running != preview.before_startup:
        raise Rejected("exact saved preview baseline required")
    after, startup = evidence_config(after_payload, preview.selected_port)
    restored, restored_startup = evidence_config(
        restored_payload, preview.selected_port
    )
    result = classify_observed_serialization(
        preview.before_running,
        preview.before_startup,
        after,
        startup,
        preview.selected_port,
        preview.desired_description,
    )
    rollback_exact = (
        restored == preview.before_running
        and restored_startup == preview.before_startup
    )
    if not rollback_exact:
        result["classification"] = "uncertain"
        result["observed_insertion_configuration_only"] = False
    result.update(
        predicted_match=after == preview.expected_running,
        rollback_exact_original_running_and_startup=rollback_exact,
        preview_sha256=preview.preview_sha256,
        baseline_input_binding_sha256=preview.input_binding_sha256,
        baseline_raw_capture_sha256=dict(preview.raw_capture_sha256),
        after_input_binding_sha256=digest(after_payload),
        restored_input_binding_sha256=digest(restored_payload),
        after_raw_capture_sha256=dict(after_payload["raw_capture_sha256"]),
        restored_raw_capture_sha256=dict(restored_payload["raw_capture_sha256"]),
        restored_running_sha256=configuration_hash(restored),
        restored_startup_sha256=configuration_hash(restored_startup),
    )
    return result


def private_path(path: Path, *, output: bool = False) -> None:
    if not path.is_absolute() or ".." in path.parts or path.is_relative_to(CHECKOUT):
        raise Rejected("private path required outside checkout")
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise Rejected("symlink private path")
    parent = path.parent.stat()
    if (
        parent.st_uid != os.getuid()
        or stat.S_IMODE(parent.st_mode) != 0o700
        or not stat.S_ISDIR(parent.st_mode)
    ):
        raise Rejected("private parent required")
    if output:
        if path.exists():
            raise Rejected("exclusive output required")
    else:
        info = path.stat()
        if (
            info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o600
            or not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or info.st_size > MAX_BYTES
        ):
            raise Rejected("private bounded regular file required")


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise Rejected("duplicate JSON key")
        result[key] = value
    return result


def read_private(path: Path) -> Any:
    private_path(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as source:
        info = os.fstat(source.fileno())
        if (
            info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o600
            or not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
        ):
            raise Rejected("private file changed")
        raw = source.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise Rejected("private size limit")
    return json.loads(raw, object_pairs_hook=unique_object)


def write_private(path: Path, value: Any) -> None:
    private_path(path, output=True)
    data = json.dumps(value, sort_keys=True, indent=2).encode("ascii") + b"\n"
    if len(data) > MAX_BYTES:
        raise Rejected("private output size limit")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as output:
        output.write(data)
        output.flush()
        os.fsync(output.fileno())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--draft-preview", required=True, type=Path)
    parser.add_argument("--port", required=True)
    parser.add_argument("--description", required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-capture", type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    try:
        preview = build_preview(
            read_private(args.draft_preview), args.port, args.description
        )
        result: dict[str, Any] = {
            "preview": asdict(preview),
            "preview_sha256": preview.preview_sha256,
        }
        if args.verify_capture is not None:
            result["verification"] = verify_configuration(
                preview, read_private(args.verify_capture)
            )
        if args.output is not None:
            write_private(args.output, result)
        unchanged_sources()
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        print("Private draft preview rejected.", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "status": "draft_unverified",
                "admitted": False,
                "apply_enabled": False,
                "private_output_written": args.output is not None,
                "configuration_only_verification": args.verify_capture is not None,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
