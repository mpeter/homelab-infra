"""Exact command-prefix configuration diagnostics; no writer or admission."""

from typing import Any

import port_description as evidence
import trunk_observation
import trunk_plan


def _check_step(
    baseline: tuple[str, ...] | list[str],
    running: tuple[str, ...] | list[str],
    startup: tuple[str, ...] | list[str],
    completed_commands: int,
    *,
    baseline_sha256: str,
) -> dict[str, Any]:
    if (
        isinstance(completed_commands, bool)
        or not isinstance(completed_commands, int)
        or not 0 <= completed_commands <= len(trunk_plan.FORWARD_COMMANDS)
    ):
        raise evidence.Rejected("invalid completed command position")
    report = trunk_observation._classify_observation(
        baseline, running, startup, baseline_sha256=baseline_sha256
    )
    expected: dict[int, list[str]] = {}
    current_vlan: int | None = None
    for command in trunk_plan.FORWARD_COMMANDS[:completed_commands]:
        if command.startswith("vlan "):
            current_vlan = int(command.split(" ")[1])
            expected[current_vlan] = []
        elif command.startswith("tagged ethernet "):
            assert current_vlan is not None
            expected[current_vlan].append(command.removeprefix("tagged ethernet "))
        elif command == "exit":
            current_vlan = None
    for vlan_id, _ in trunk_plan.TARGET_VLANS:
        observed = report["vlans"][str(vlan_id)]
        if observed["present"] != (vlan_id in expected) or observed[
            "observed_members"
        ] != tuple(expected.get(vlan_id, ())):
            raise evidence.Rejected(
                "configuration does not match completed command prefix"
            )
    commands = trunk_plan.FORWARD_COMMANDS
    report["command_position"] = {
        "completed_commands": completed_commands,
        "total_commands": len(commands),
        "last_completed_command": commands[completed_commands - 1]
        if completed_commands
        else None,
        "next_command": commands[completed_commands]
        if completed_commands < len(commands)
        else None,
    }
    return report


def check_step(
    baseline: tuple[str, ...] | list[str],
    running: tuple[str, ...] | list[str],
    startup: tuple[str, ...] | list[str],
    completed_commands: int,
) -> dict[str, Any]:
    """Require the fixed baseline and exact target state after a command prefix."""
    return _check_step(
        baseline,
        running,
        startup,
        completed_commands,
        baseline_sha256=trunk_plan.BASELINE_SHA256,
    )
