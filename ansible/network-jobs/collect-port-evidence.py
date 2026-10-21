#!/usr/bin/env python3
"""Collect private read-only evidence for a bounded front-panel port review."""

import argparse
from datetime import datetime, timezone
import hashlib
from importlib.util import module_from_spec, spec_from_file_location
import json
import os
from pathlib import Path
import re
import sys
import tempfile

BOOTSTRAP_PATH = (
    Path(__file__).resolve().parents[1] / "network-audit/bootstrap-identity.py"
)
SOURCE_PATHS = {
    "collector": Path(__file__).resolve(),
    "bootstrap": BOOTSTRAP_PATH,
    "capture": BOOTSTRAP_PATH.with_name("capture.py"),
    "launcher": BOOTSTRAP_PATH.with_name("run-audit.py"),
}
SOURCE_SHA256 = {
    name: hashlib.sha256(path.read_bytes()).hexdigest()
    for name, path in SOURCE_PATHS.items()
}
SPEC = spec_from_file_location("port_evidence_bootstrap", BOOTSTRAP_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("pinned bootstrap unavailable")
bootstrap = module_from_spec(SPEC)
SPEC.loader.exec_module(bootstrap)
Rejected = bootstrap.Rejected
CAPTURE_SPEC = spec_from_file_location(
    "port_evidence_capture", BOOTSTRAP_PATH.with_name("capture.py")
)
if CAPTURE_SPEC is None or CAPTURE_SPEC.loader is None:
    raise RuntimeError("capture validation unavailable")
capture = module_from_spec(CAPTURE_SPEC)
CAPTURE_SPEC.loader.exec_module(capture)
EE_DIGEST = "7eb690b9bbac7dd602ad4eac7b1a537a1f3d8e54d6178e764b0e4df96813c2e2"
COMMANDS = (*bootstrap.COMMANDS, "show interfaces brief", "show mac-address")
R8_VLAN_IDS = (1, 10, 20, 30, 40, 132)
R8_VLAN_COMMANDS = tuple(f"show vlan {vlan}" for vlan in R8_VLAN_IDS)


def unchanged_sources():
    if any(
        hashlib.sha256(path.read_bytes()).hexdigest() != SOURCE_SHA256[name]
        for name, path in SOURCE_PATHS.items()
    ):
        raise Rejected("collector source drift")


unchanged_sources()


def port(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(
        r"1/1/(?:[1-9]|[1-3][0-9]|4[0-7])", value
    ):
        raise Rejected("port must be front-panel 1/1/1 through 1/1/47")
    return value


def credentials() -> dict[str, str]:
    try:
        raw = sys.stdin.read(8193)
        if len(raw) > 8192:
            raise Rejected("audit credential size")
        payload = json.loads(raw, object_pairs_hook=bootstrap.credential_object)
    except (ValueError, UnicodeError) as error:
        raise Rejected("audit credential shape") from error
    if (
        not isinstance(payload, dict)
        or set(payload) != {"audit_password"}
        or not isinstance(payload["audit_password"], str)
        or not re.fullmatch(r"[A-Za-z0-9]{32,48}", payload["audit_password"])
    ):
        raise Rejected("audit credential shape")
    return payload


class AuditInput:
    """Defer stdin until the shared transport verifies the accepted host key."""

    def __init__(self):
        self.payload = None

    def __getitem__(self, key):
        if key != "audit_password":
            raise Rejected("root credential prohibited")
        if self.payload is None:
            self.payload = credentials()
        return self.payload[key]


def paths(env):
    if env.get("BROCADE_AUDIT_USER", bootstrap.USER) != bootstrap.USER:
        raise Rejected("dedicated audit identity required")
    unchanged_sources()
    spec = spec_from_file_location(
        "port_evidence_launcher", BOOTSTRAP_PATH.with_name("run-audit.py")
    )
    if spec is None or spec.loader is None:
        raise Rejected("launcher unavailable")
    launcher = module_from_spec(spec)
    spec.loader.exec_module(launcher)
    unchanged_sources()
    pin = Path(env.get("BROCADE_KNOWN_HOSTS", ""))
    parent = Path(env.get("BROCADE_RUNTIME_PRIVATE", ""))
    launcher.private_path(pin)
    launcher.private_path(parent, directory=True)
    if parent.is_relative_to(Path(__file__).resolve().parents[2]):
        raise Rejected("runtime inside checkout")
    return pin, Path(tempfile.mkdtemp(prefix="brocade-port-evidence-", dir=parent))


def read_command(console, command, selected, *, deadline=None):
    selected = port(selected)
    if command not in (
        *COMMANDS,
        f"show interfaces ethernet {selected}",
        *R8_VLAN_COMMANDS,
    ):
        raise Rejected("command outside port evidence")
    console.channel.sendall(command + "\r")
    if deadline is None:
        console.read(bootstrap.PROMPT)
    else:
        console.read(bootstrap.PROMPT, deadline=deadline)
    raw = (
        (console.runtime / f"capture-{console.sequence:02}.txt")
        .read_bytes()
        .decode("ascii")
    )
    if bootstrap.DENIED.search(raw) or bootstrap.ERROR.search(raw):
        raise Rejected("raw command error")
    try:
        consumed = capture.consumed_pagers(raw)
        if re.search(r"\r(?!\n)|[\x08\x7f]", consumed):
            raise Rejected("terminal overwrite or control")
        response = bootstrap.cleaned(consumed)
    except ValueError as error:
        raise Rejected("pager boundary") from error
    lines = response.strip().splitlines()
    prompt = bootstrap.PROMPT.fullmatch(lines[-1]) if lines else None
    if (
        len(lines) < 3
        or lines[0] != command
        or prompt is None
        or prompt.group(1) != "#"
        or any(bootstrap.ANY_PROMPT.search(line) for line in lines[1:-1])
        or bootstrap.DENIED.search(response)
        or bootstrap.ERROR.search(response)
    ):
        raise Rejected("port evidence command boundary")
    body = "\n".join(lines[1:-1])
    if not body.strip():
        raise Rejected("empty evidence")
    return body


def baseline(version, running, startup):
    unchanged_sources()
    capture.validate([version, running, startup])
    unchanged_sources()
    current = bootstrap.configuration(running)
    if current != bootstrap.configuration(startup):
        raise Rejected("unsaved differences")
    audit_accounts = [
        line for line in current if re.match(r"username homelab_audit\b", line.lstrip())
    ]
    if len(audit_accounts) != 1 or not re.fullmatch(
        r"username homelab_audit privilege 5 password \S[^\r\n]*", audit_accounts[0]
    ):
        raise Rejected("persisted privilege-5 audit account required")
    return current


def collect(pin, runtime, selected, *, include_r8_vlan_tables=False):
    selected = port(selected)
    commands = (*COMMANDS, f"show interfaces ethernet {selected}")
    started = datetime.now(timezone.utc).isoformat()
    unchanged_sources()
    with bootstrap.session(pin, runtime, user=bootstrap.USER, payload=AuditInput()) as (
        console,
        _,
    ):
        responses = []
        for command in commands:
            responses.append(read_command(console, command, selected))
            if len(responses) == 3:
                baseline(*responses)
        r8_vlan_tables = None
        r8_vlan_capture_sha256 = None
        if include_r8_vlan_tables:
            r8_vlan_tables = {}
            r8_vlan_capture_sha256 = {}
            for vlan, command in zip(R8_VLAN_IDS, R8_VLAN_COMMANDS, strict=True):
                r8_vlan_tables[str(vlan)] = read_command(console, command, selected)
                capture_path = console.runtime / f"capture-{console.sequence:02}.txt"
                r8_vlan_capture_sha256[command] = hashlib.sha256(
                    capture_path.read_bytes()
                ).hexdigest()
        unchanged_sources()
        evidence = {
            "schema": 1,
            "observed_at": started,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "host": bootstrap.HOST,
            "model": "ICX6610-48P",
            "release": bootstrap.RELEASE,
            "identity": bootstrap.USER,
            "accepted_host_key_fingerprint": bootstrap.FINGERPRINT,
            "selected_port": selected,
            "commands": list(commands),
            "expected_execution_environment_sha256": EE_DIGEST,
            "source_sha256": dict(SOURCE_SHA256),
            "captures_directory": str(console.runtime),
            "raw_capture_sha256": {
                f"capture-{index:02}.txt": hashlib.sha256(
                    (console.runtime / f"capture-{index:02}.txt").read_bytes()
                ).hexdigest()
                for index in range(1, len(commands) + 1)
            },
            "responses": dict(zip(commands, responses)),
            "terminal_boundaries_complete": True,
            "operational_parsing_complete": False,
            "reserved_use_reviewed": False,
            "unused_port_verified": False,
            "task_7_4_complete": False,
        }
        if include_r8_vlan_tables:
            evidence["r8_vlan_commands"] = list(R8_VLAN_COMMANDS)
            evidence["r8_vlan_tables"] = r8_vlan_tables
            evidence["r8_vlan_capture_sha256"] = r8_vlan_capture_sha256
        unchanged_sources()
        bootstrap.private_json(runtime / "evidence.json", evidence)
    return {
        "schema": 1,
        "observed_at": started,
        "host": bootstrap.HOST,
        "model": "ICX6610-48P",
        "release": bootstrap.RELEASE,
        "selected_port": selected,
        "capture_complete": True,
        "operational_parsing_complete": False,
        "reserved_use_reviewed": False,
        "unused_port_verified": False,
        "task_7_4_complete": False,
        "private_runtime": str(runtime),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--r8-vlan-tables", action="store_true")
    args = parser.parse_args()
    os.umask(0o077)
    runtime = None
    try:
        selected = port(args.port)
        pin, runtime = paths(os.environ)
        summary = collect(
            pin, runtime, selected, include_r8_vlan_tables=args.r8_vlan_tables
        )
    except Exception as error:
        if runtime is not None:
            try:
                bootstrap.private_json(
                    runtime / "failure.json", {"exception_type": type(error).__name__}
                )
            except OSError:
                pass
        print(f"Port evidence rejected; private runtime: {runtime}.", file=sys.stderr)
        return 2
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
