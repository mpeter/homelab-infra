#!/usr/bin/env python3
"""Store the three audit responses exclusively in the private runtime."""

import json
from importlib.util import module_from_spec, spec_from_file_location
import os
from pathlib import Path
import re
import stat
import sys

COMMANDS = ["show version", "show running-config", "show configuration"]
PAGER = "--More--, next page: Space, next line: Return key, quit: Control-c"
PAGER_LIMIT = 128


def consumed_pagers(raw: str) -> str:
    """Accept only the exact complete pager erasure observed on this release."""
    erased = PAGER + "\x08 \x08" * len(PAGER)
    if raw.count(erased) > PAGER_LIMIT:
        raise ValueError("pager limit exceeded")
    text = raw.replace(erased, "")
    if re.search(r"--\s*More\s*--", text, re.I) or "\x08" in text:
        raise ValueError("residual pager")
    return text


def validate(responses: list[str]) -> None:
    """Check pinned response boundaries without comparing running to startup."""
    spec = spec_from_file_location(
        "audit_identity", Path(__file__).with_name("bootstrap-identity.py")
    )
    if spec is None or spec.loader is None:
        raise ValueError("identity validation unavailable")
    identity = module_from_spec(spec)
    spec.loader.exec_module(identity)
    normalized = []
    for raw in responses:
        try:
            text = identity.cleaned(consumed_pagers(raw))
        except identity.Rejected as error:
            raise ValueError("invalid terminal response") from error
        if identity.ERROR.search(text) or identity.DENIED.search(text):
            raise ValueError("command error")
        normalized.append(text)
    version = normalized[0]
    releases = re.findall(r"\bSW:\s+Version\s+(\S+)", version)
    models = re.findall(
        r"^UNIT 1: SL 1: (ICX\d+-\S+) POE.*Management Module$", version, re.M
    )
    if releases != [identity.RELEASE] or models != ["ICX6610-48P"]:
        raise ValueError("release or model mismatch")
    if not re.fullmatch(
        r'The system\s*:\s*started=(?:cold start|warm start(?:[ \t]+reloaded=by "reload")?)',
        version.strip().splitlines()[-1].strip(),
    ):
        raise ValueError("incomplete version response")
    for text in normalized[1:]:
        try:
            identity.configuration(text)
        except identity.Rejected as error:
            raise ValueError("incomplete configuration response") from error


def store(payload: object, path: Path) -> None:
    if (
        not path.is_absolute()
        or ".." in path.parts
        or path.name != "audit-capture.json"
    ):
        raise ValueError("invalid capture path")
    if any(p.is_symlink() for p in [path, *path.parents]):
        raise ValueError("symlink capture path")
    parent = path.parent.stat()
    if (
        not stat.S_ISDIR(parent.st_mode)
        or parent.st_uid != os.getuid()
        or stat.S_IMODE(parent.st_mode) != 0o700
    ):
        raise ValueError("unsafe capture directory")
    if not isinstance(payload, list) or len(payload) != len(COMMANDS):
        raise ValueError("invalid response count")
    for command, result in zip(COMMANDS, payload, strict=True):
        if (
            not isinstance(result, dict)
            or result.get("item") != command
            or result.get("failed", False)
        ):
            raise ValueError("invalid command result")
        if not isinstance(result.get("stdout"), str) or not result["stdout"].strip():
            raise ValueError("missing command response")
    validate([result["stdout"] for result in payload])
    data = [
        {"command": command, "stdout": result["stdout"]}
        for command, result in zip(COMMANDS, payload, strict=True)
    ]
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as output:
        json.dump(data, output)
        output.write("\n")


def main() -> int:
    try:
        store(json.load(sys.stdin), Path(os.environ.get("BROCADE_AUDIT_OUTPUT", "")))
    except (OSError, ValueError, TypeError):
        print("Private capture rejected.", file=sys.stderr)
        return 2
    print("Private audit capture written; pinned response boundaries verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
