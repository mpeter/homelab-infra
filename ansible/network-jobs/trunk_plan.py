"""Offline fixed trunk command planning; no execution or serializer qualification."""

from dataclasses import dataclass
import re

import port_description as evidence

MODEL = "ICX6610-48P"
RELEASE = "08.0.30uT7f3"
BASELINE_SHA256 = "8ba673bd4d2c842085b4fba39ff278192352c69926ab0c1c6b1c362edcfac2cd"
TARGET_VLANS = (
    (10, "LAB-MGMT"),
    (20, "LAB-DEV"),
    (30, "LAB-LAB"),
    (40, "LAB-SERVICES"),
)
PORTS = ("1/2/2", "1/2/6", "1/3/1")
FORWARD_COMMANDS = (
    "configure terminal",
    *(
        command
        for vlan_id, name in TARGET_VLANS
        for command in (
            f"vlan {vlan_id} name {name} by port",
            *(f"tagged ethernet {port}" for port in PORTS),
            "exit",
        )
    ),
    "exit",
)


@dataclass(frozen=True)
class Plan:
    baseline_sha256: str
    model: str = MODEL
    release: str = RELEASE
    forward_commands: tuple[str, ...] = FORWARD_COMMANDS
    status: str = "diagnostic_unverified"
    live_admission: bool = False
    execution_qualified: bool = False
    limitations: tuple[str, ...] = (
        "new VLAN command acknowledgements and serialization are unverified",
        "no expected configuration or inverse is qualified by this plan",
        "baseline match does not establish recovery custody or live admission",
    )


def _configuration(value: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    if not isinstance(value, (tuple, list)) or any(
        not isinstance(line, str) for line in value
    ):
        raise evidence.Rejected("canonical ordered configuration lines required")
    lines = tuple(value)
    canonical = evidence.configuration("\n".join(lines) + "\n")
    if lines != canonical:
        raise evidence.Rejected("canonical ordered configuration lines required")
    return canonical


def _build_plan(
    before_running: tuple[str, ...] | list[str],
    before_startup: tuple[str, ...] | list[str],
    *,
    baseline_sha256: str,
    model: str,
    release: str,
) -> Plan:
    if model != MODEL or release != RELEASE:
        raise evidence.Rejected("unsupported fixed target")
    running = _configuration(before_running)
    startup = _configuration(before_startup)
    if running != startup:
        raise evidence.Rejected("running and startup differ")
    vlan_ids: set[int] = set()
    for line in running:
        if not re.match(r"vlan\b", line.lstrip()):
            continue
        match = re.fullmatch(
            r"vlan ([1-9][0-9]*)(?: name [A-Za-z0-9_-]+)? by port", line
        )
        if match is None:
            raise evidence.Rejected("ambiguous VLAN stanza")
        vlan_id = int(match.group(1))
        if vlan_id in vlan_ids:
            raise evidence.Rejected("duplicate VLAN stanza")
        vlan_ids.add(vlan_id)
    if vlan_ids.intersection(vlan_id for vlan_id, _ in TARGET_VLANS):
        raise evidence.Rejected("target VLAN already exists")
    if not {1, 132}.issubset(vlan_ids):
        raise evidence.Rejected("required VLAN 1 or 132 absent")
    actual_sha256 = evidence.configuration_hash(running)
    if actual_sha256 != baseline_sha256:
        raise evidence.Rejected("fixed baseline drift")
    return Plan(actual_sha256)


def build_plan(
    before_running: tuple[str, ...] | list[str],
    before_startup: tuple[str, ...] | list[str],
    *,
    model: str = MODEL,
    release: str = RELEASE,
) -> Plan:
    """Require the saved baseline and return the reviewed 22-command diagnostic."""
    return _build_plan(
        before_running,
        before_startup,
        baseline_sha256=BASELINE_SHA256,
        model=model,
        release=release,
    )
