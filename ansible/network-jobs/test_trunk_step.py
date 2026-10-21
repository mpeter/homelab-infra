"""Synthetic command-prefix checks never qualify switch execution."""

from typing import Any

import pytest

import port_description as evidence
import trunk_plan
import trunk_step as engine

BASELINE = (
    f"ver {trunk_plan.RELEASE}",
    "!",
    "vlan 1 name DEFAULT-VLAN by port",
    " untagged ethe 1/2/2 1/2/6 1/3/1",
    "!",
    "vlan 132 name DEFAULT-DECKPIN by port",
    " tagged ethe 1/1/48",
    " spanning-tree",
    "!",
    "interface ethernet 1/2/6",
    " port-name standby",
    "!",
    "end",
)


def state(position: int, *, grouped: bool = False) -> tuple[str, ...]:
    additions: list[str] = []
    for index, (vlan_id, name) in enumerate(trunk_plan.TARGET_VLANS):
        creation_position = 2 + index * 5
        if position < creation_position:
            continue
        additions.append(f"vlan {vlan_id} name {name} by port")
        members = trunk_plan.PORTS[: max(0, min(position - creation_position, 3))]
        if grouped and members:
            additions.append(" tagged ethernet " + " ".join(reversed(members)))
        else:
            additions.extend(f" tagged ethernet {port}" for port in members)
        additions.append("!")
    return (*BASELINE[:9], *additions, *BASELINE[9:])


def check(
    position: Any,
    running: Any = BASELINE,
    startup: Any = BASELINE,
    baseline: Any = BASELINE,
) -> dict[str, Any]:
    return engine._check_step(
        baseline,
        running,
        startup,
        position,
        baseline_sha256=evidence.configuration_hash(BASELINE),
    )


@pytest.mark.parametrize("position", range(23))
@pytest.mark.parametrize("grouped", [False, True])
def test_every_exact_prefix(position: int, grouped: bool) -> None:
    running = state(position, grouped=grouped)
    report = check(position, running)
    assert report["command_position"] == {
        "completed_commands": position,
        "total_commands": 22,
        "last_completed_command": trunk_plan.FORWARD_COMMANDS[position - 1]
        if position
        else None,
        "next_command": trunk_plan.FORWARD_COMMANDS[position]
        if position < 22
        else None,
    }
    assert report["running_sha256"] == evidence.configuration_hash(running)
    assert report["baseline_sha256"] == evidence.configuration_hash(BASELINE)
    assert report["startup_sha256"] == evidence.configuration_hash(BASELINE)
    assert report["execution_qualified"] is False
    assert report["live_admission"] is False
    assert "inverse_commands" not in report
    for index, (vlan_id, name) in enumerate(trunk_plan.TARGET_VLANS):
        target = report["vlans"][str(vlan_id)]
        assert target["name"] == name
        assert target["present"] == (position >= 2 + index * 5)
        assert (
            target["observed_members"]
            == trunk_plan.PORTS[: max(0, min(position - 2 - index * 5, 3))]
        )


@pytest.mark.parametrize("position", range(23))
def test_every_other_distinct_prefix_rejects(position: int) -> None:
    for other in range(23):
        if state(other) == state(position):
            continue
        with pytest.raises(evidence.Rejected, match="completed command prefix"):
            check(position, state(other))


@pytest.mark.parametrize("position", [True, False, -1, 23, 1.0, "2", None])
def test_invalid_command_positions_reject(position: Any) -> None:
    with pytest.raises(evidence.Rejected, match="command position"):
        check(position)


def test_public_baseline_is_fixed() -> None:
    with pytest.raises(evidence.Rejected, match="fixed baseline drift"):
        engine.check_step(BASELINE, BASELINE, BASELINE, 0)


@pytest.mark.parametrize(
    "old,new",
    [
        (" tagged ethernet 1/2/2", " tagged ethernet 1/2/6"),
        (" tagged ethernet 1/2/2", " tagged ethernet 1/2/2 1/2/6"),
        (" tagged ethernet 1/2/2", " tagged ethernet 1/1/48"),
        (" tagged ethernet 1/2/2", " tagged ethernet 1/2/2 1/2/2"),
        ("vlan 10 name LAB-MGMT by port", "vlan 10 name WRONG by port"),
        ("vlan 10 name LAB-MGMT by port", "vlan 50 name EXTRA by port"),
        (" port-name standby", " port-name changed"),
        (" spanning-tree", " spanning-tree 802-1w"),
        (" tagged ethe 1/1/48", " tagged ethe 1/1/47"),
        (" untagged ethe 1/2/2 1/2/6 1/3/1", " untagged ethe 1/2/2"),
    ],
)
def test_wrong_member_extra_or_unrelated_drift_rejects(old: str, new: str) -> None:
    running = tuple(new if line == old else line for line in state(3))
    with pytest.raises(evidence.Rejected):
        check(3, running)


def test_startup_change_rejects() -> None:
    with pytest.raises(evidence.Rejected, match="startup must remain exact baseline"):
        check(3, state(3), state(3))


@pytest.mark.parametrize(
    "value",
    [
        "invalid",
        ("end",),
        BASELINE[:-1],
        (*BASELINE, "end"),
        (*BASELINE[:-1], "", "end"),
        (*BASELINE[:-1], "end "),
        (*BASELINE[:-1], 1),
    ],
)
@pytest.mark.parametrize("input_position", range(3))
def test_noncanonical_or_incomplete_configurations_reject(
    value: Any, input_position: int
) -> None:
    inputs: list[Any] = [BASELINE, BASELINE, BASELINE]
    inputs[input_position] = value
    with pytest.raises(evidence.Rejected):
        engine._check_step(
            inputs[0],
            inputs[1],
            inputs[2],
            0,
            baseline_sha256=evidence.configuration_hash(BASELINE),
        )


def test_list_inputs_are_accepted_if_canonical() -> None:
    assert (
        check(3, list(state(3)), list(BASELINE), list(BASELINE))["classification"]
        == "partial_candidate"
    )
