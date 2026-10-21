"""Current-source R8 observations through the pinned read-only audit identity."""

from collections.abc import Callable
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import tempfile
from typing import Any

import exercise_observation as base
import native_trunk_observation as trunk

_BASE = Path(__file__).resolve().parent
SOURCE_PATHS = {
    "self": Path(__file__).resolve(),
    "base": _BASE / "exercise_observation.py",
    "collector": _BASE / "collect-port-evidence.py",
    "bootstrap": _BASE.parent / "network-audit/bootstrap-identity.py",
    "capture": _BASE.parent / "network-audit/capture.py",
    "launcher": _BASE.parent / "network-audit/run-audit.py",
    "engine": _BASE / "port_description.py",
    "trunk_observation": _BASE / "native_trunk_observation.py",
}
SOURCE_SHA256 = {
    name: hashlib.sha256(path.read_bytes()).hexdigest()
    for name, path in SOURCE_PATHS.items()
}
COMMANDS = trunk.R8_VLAN_COMMANDS


class Rejected(ValueError):
    """A current-source audit observation failed its fixed contract."""


def unchanged_sources() -> None:
    base.unchanged_sources()
    for name, path in SOURCE_PATHS.items():
        if hashlib.sha256(path.read_bytes()).hexdigest() != SOURCE_SHA256[name]:
            raise Rejected("R8 observation source drift")


def observe(
    pin: Path,
    runtime: Path,
    expected_startup: tuple[str, ...],
    credential_provider: Callable[[], str],
    deadline: float | None = None,
) -> dict[str, Any]:
    """Read startup anchor, current running state, interface and VLAN tables."""
    unchanged_sources()
    base._private_path(pin, directory=False)
    base._private_path(runtime, directory=True)
    if not callable(credential_provider) or not isinstance(expected_startup, tuple):
        raise Rejected("canonical startup anchor and audit credential required")
    if base.engine.configuration("\n".join(expected_startup)) != expected_startup:
        raise Rejected("canonical startup anchor required")
    audit_runtime = Path(tempfile.mkdtemp(prefix="r8-audit-", dir=runtime))
    os.chmod(audit_runtime, 0o700)
    session_bootstrap = base._load(
        "r8_current_observation_session", SOURCE_PATHS["bootstrap"]
    )
    consoles: list[Any] = []

    class Console(base._Console):
        def __init__(self, channel: Any, password: str, capture_runtime: Path):
            super().__init__(channel, password, capture_runtime)
            consoles.append(self)

    session_bootstrap.Console = Console
    started = datetime.now(timezone.utc).isoformat()
    try:
        session_args = {
            "user": "homelab_audit",
            "payload": base._AuditInput(credential_provider),
        }
        if deadline is not None:
            session_args["deadline"] = deadline
        with session_bootstrap.session(
            pin, audit_runtime, **session_args
        ) as (console, _):
            responses: dict[str, str] = {}
            for command in base.COMMANDS:
                unchanged_sources()
                responses[command] = base.collector.read_command(
                    console, command, base.PORT, deadline=deadline
                )
            version, running_text, startup_text = (
                responses[command] for command in base.COMMANDS[:3]
            )
            base.collector.capture.validate([version, running_text, startup_text])
            running = base.engine.configuration(running_text)
            startup = base.engine.configuration(startup_text)
            base._audit(running)
            base._audit(startup)
            if startup != expected_startup:
                raise Rejected("startup differs from the accepted R8 anchor")

            tables: dict[str, str] = {}
            captures: dict[str, str] = {}
            for vlan, command in zip(trunk.R8_VLAN_IDS, COMMANDS, strict=True):
                unchanged_sources()
                tables[str(vlan)] = base.collector.read_command(
                    console, command, base.PORT, deadline=deadline
                )
                capture_path = console.runtime / f"capture-{console.sequence:02}.txt"
                captures[command] = hashlib.sha256(
                    capture_path.read_bytes()
                ).hexdigest()

            evidence = {
                "schema": 1,
                "observed_at": started,
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "host": base.bootstrap.HOST,
                "model": "ICX6610-48P",
                "release": base.bootstrap.RELEASE,
                "identity": "homelab_audit",
                "accepted_host_key_fingerprint": base.bootstrap.FINGERPRINT,
                "selected_port": base.PORT,
                "commands": list(base.COMMANDS),
                "expected_execution_environment_sha256": base.collector.EE_DIGEST,
                "source_sha256": dict(base.collector.SOURCE_SHA256),
                "observation_source_sha256": dict(SOURCE_SHA256),
                "captures_directory": str(console.runtime),
                "raw_capture_sha256": {
                    f"capture-{index:02}.txt": hashlib.sha256(
                        (console.runtime / f"capture-{index:02}.txt").read_bytes()
                    ).hexdigest()
                    for index in range(1, len(base.COMMANDS) + 1)
                },
                "responses": responses,
                "terminal_boundaries_complete": True,
                "operational_parsing_complete": False,
                "r8_vlan_commands": list(COMMANDS),
                "r8_vlan_tables": tables,
                "r8_vlan_capture_sha256": captures,
                "r8_vlan_raw_capture_sha256": {
                    f"capture-{index:02}.txt": hashlib.sha256(
                        (console.runtime / f"capture-{index:02}.txt").read_bytes()
                    ).hexdigest()
                    for index in range(
                        len(base.COMMANDS) + 1, len(base.COMMANDS) + len(COMMANDS) + 1
                    )
                },
            }
            base.engine.evidence_config(evidence, base.PORT)
            trunk.require_r8_vlan_capture(evidence)
            unchanged_sources()
            return evidence
    finally:
        for console in consoles:
            console.wire.close_capture()
