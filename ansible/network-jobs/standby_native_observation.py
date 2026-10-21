"""Pure standby VLAN/native diagnostics; no writer or live admission."""

from typing import Any

import port_description as evidence
import trunk_link_admission
import trunk_observation
import trunk_plan

STANDBY_PORT = "1/2/6"
INTERFACE = f"interface ethernet {STANDBY_PORT}"
NATIVE_LEAF = " dual-mode"


def _interface_blocks(lines: tuple[str, ...]) -> list[tuple[int, int]]:
    blocks = []
    for start, line in enumerate(lines):
        if line != INTERFACE:
            continue
        end = start + 1
        while end < len(lines) and lines[end].startswith(" "):
            end += 1
        blocks.append((start, end))
    if len(blocks) > 1:
        raise evidence.Rejected("duplicate standby interface stanza")
    return blocks


def _classify_observation(
    baseline: tuple[str, ...] | list[str],
    current_running: tuple[str, ...] | list[str],
    current_startup: tuple[str, ...] | list[str],
    *,
    baseline_sha256: str,
) -> dict[str, Any]:
    trunk_plan._build_plan(
        baseline,
        baseline,
        baseline_sha256=baseline_sha256,
        model=trunk_plan.MODEL,
        release=trunk_plan.RELEASE,
    )
    before = trunk_plan._configuration(baseline)
    running = trunk_plan._configuration(current_running)
    startup = trunk_plan._configuration(current_startup)
    if startup != before:
        raise evidence.Rejected("startup must remain exact baseline")
    baseline_interfaces = _interface_blocks(before)
    if baseline_interfaces:
        start, end = baseline_interfaces[0]
        if any(line.lstrip().startswith("dual-mode") for line in before[start:end]):
            raise evidence.Rejected("baseline standby native mode already configured")
    interfaces = _interface_blocks(running)
    native_mode = False
    remainder = running
    inserted_interface: tuple[int, int] | None = None
    if interfaces:
        start, end = interfaces[0]
        leaves = running[start + 1 : end]
        native_mode = NATIVE_LEAF in leaves
        if leaves.count(NATIVE_LEAF) > 1:
            raise evidence.Rejected("duplicate standby native leaf")
        if baseline_interfaces:
            if native_mode:
                remainder = (
                    *running[: start + 1],
                    *(line for line in leaves if line != NATIVE_LEAF),
                    *running[end:],
                )
        else:
            if leaves != (NATIVE_LEAF,):
                raise evidence.Rejected(
                    "inserted standby interface requires only implicit dual-mode"
                )
            inserted_interface = (start, end)
    stanzas = trunk_observation._target_stanzas(remainder)
    tagged_standby = False
    vlan_present = False
    for _, block, members in stanzas.values():
        if block[0] != "vlan 10 name LAB-MGMT by port" or members not in (
            (),
            (STANDBY_PORT,),
        ):
            raise evidence.Rejected(
                "only VLAN 10 and standby tagged membership allowed"
            )
        vlan_present = True
        tagged_standby = members == (STANDBY_PORT,)
    if inserted_interface is not None:
        start, end = inserted_interface
        stanzas[start] = (end, running[start:end], ())
    trunk_observation._require_exact_remainder(before, remainder, stanzas)
    return {
        "schema": 1,
        "scope": "standby_configuration_only",
        "classification": "native_candidate"
        if native_mode
        else "tagged_candidate"
        if tagged_standby
        else "partial_candidate"
        if vlan_present
        else "unchanged",
        "baseline_sha256": evidence.configuration_hash(before),
        "running_sha256": evidence.configuration_hash(running),
        "startup_sha256": evidence.configuration_hash(startup),
        "vlan_present": vlan_present,
        "tagged_standby": tagged_standby,
        "native_mode": native_mode,
        "execution_qualified": False,
        "live_admission": False,
        "limitations": (
            "configuration observations do not prove native membership or PVID",
            "serialization, inverse and execution remain unqualified",
            "inactive standby membership does not prove traffic traverses standby",
        ),
    }


def classify_observation(
    baseline: tuple[str, ...] | list[str],
    current_running: tuple[str, ...] | list[str],
    current_startup: tuple[str, ...] | list[str],
) -> dict[str, Any]:
    """Require the fixed saved baseline and permit only standby VLAN/native delta."""
    return _classify_observation(
        baseline,
        current_running,
        current_startup,
        baseline_sha256=trunk_plan.BASELINE_SHA256,
    )


def require_operational_state(brief: str, *, phase: str) -> None:
    """Check complete carrier/PVID evidence, without asserting traffic traversal."""
    if phase not in ("baseline", "standby", "native"):
        raise evidence.Rejected("unknown standby observation phase")
    trunk_link_admission.require_links(brief)
    rows = {
        words[0]: words
        for line in brief.splitlines()
        if (words := line.split()) and words[0] in trunk_link_admission.EXPECTED_SPEEDS
    }
    for port in ("1/2/2", "1/3/1"):
        row = rows[port]
        if row[1:3] != ["Up", "Forward"] or row[6:8] != ["No", "1"]:
            raise evidence.Rejected(
                "primary and gateway must remain native VLAN 1 forwarding"
            )
    standby = rows[STANDBY_PORT]
    allowed = (
        (("Yes", "N/A"), ("Yes", "1"))
        if phase == "standby"
        else (("Yes", "1"),)
        if phase == "native"
        else (("No", "1"),)
    )
    if standby[1:3] != ["Up", "Forward"] or tuple(standby[6:8]) not in allowed:
        raise evidence.Rejected("standby phase requires exact tag and PVID state")
