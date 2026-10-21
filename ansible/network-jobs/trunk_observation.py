"""Pure whole-configuration trunk diagnostics; never qualify execution or admission."""

import re
from typing import Any

import port_description as evidence
import trunk_plan


def _target_stanzas(
    running: tuple[str, ...],
) -> dict[int, tuple[int, tuple[str, ...], tuple[str, ...]]]:
    targets = dict(trunk_plan.TARGET_VLANS)
    result: dict[int, tuple[int, tuple[str, ...], tuple[str, ...]]] = {}
    seen: set[int] = set()
    for start, line in enumerate(running):
        match = re.match(r"\s*vlan ([0-9]+)\b", line)
        if match is None or int(match.group(1)) not in targets:
            continue
        vlan_id = int(match.group(1))
        if line != f"vlan {vlan_id} name {targets[vlan_id]} by port":
            raise evidence.Rejected("unrecognized target VLAN header")
        if vlan_id in seen:
            raise evidence.Rejected("duplicate target VLAN stanza")
        seen.add(vlan_id)
        end = start + 1
        members: set[str] = set()
        while end < len(running) and running[end].startswith(" "):
            leaf = re.fullmatch(
                r" tagged (?:ethernet|ethe) ([1-9][0-9]*/[1-9][0-9]*/[1-9][0-9]*"
                r"(?: [1-9][0-9]*/[1-9][0-9]*/[1-9][0-9]*)*)",
                running[end],
            )
            if leaf is not None:
                ports = leaf.group(1).split(" ")
            else:
                repeated = re.fullmatch(
                    r" tagged ethe ([1-9][0-9]*/[1-9][0-9]*/[1-9][0-9]*"
                    r"(?: ethe [1-9][0-9]*/[1-9][0-9]*/[1-9][0-9]*)+)",
                    running[end],
                )
                if repeated is None:
                    raise evidence.Rejected("unrecognized target VLAN leaf")
                ports = repeated.group(1).split(" ethe ")
            for port in ports:
                if port not in trunk_plan.PORTS or port in members:
                    raise evidence.Rejected("duplicate or out-of-scope tagged port")
                members.add(port)
            end += 1
        result[start] = (
            end,
            running[start:end],
            tuple(port for port in trunk_plan.PORTS if port in members),
        )
    return result


def _require_exact_remainder(
    baseline: tuple[str, ...],
    running: tuple[str, ...],
    stanzas: dict[int, tuple[int, tuple[str, ...], tuple[str, ...]]],
) -> None:
    # Track distinct separator removal paths, capped at two: ambiguity rejects.
    paths: dict[int, dict[int, int]] = {0: {0: 1}}
    for index in range(len(running)):
        states = paths.pop(index, {})
        for baseline_index, count in states.items():
            destinations: list[tuple[int, int]] = []
            if index in stanzas:
                if 0 < baseline_index < len(baseline) and not baseline[
                    baseline_index
                ].startswith(" "):
                    end = stanzas[index][0]
                    destinations.append((end, baseline_index))
                    if end < len(running) and running[end] == "!":
                        destinations.append((end + 1, baseline_index))
            elif (
                baseline_index < len(baseline)
                and running[index] == baseline[baseline_index]
            ):
                destinations.append((index + 1, baseline_index + 1))
            for next_index, next_baseline in destinations:
                next_states = paths.setdefault(next_index, {})
                next_states[next_baseline] = min(
                    2, next_states.get(next_baseline, 0) + count
                )
    count = paths.get(len(running), {}).get(len(baseline), 0)
    if count != 1:
        raise evidence.Rejected("unrelated configuration drift or ambiguous insertion")


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
    stanzas = _target_stanzas(running)
    _require_exact_remainder(before, running, stanzas)
    observed = {
        int(block[0].split(" ")[1]): (block, members)
        for _, block, members in stanzas.values()
    }
    complete = len(observed) == len(trunk_plan.TARGET_VLANS) and all(
        members == trunk_plan.PORTS for _, members in observed.values()
    )
    return {
        "schema": 1,
        "scope": "configuration_only",
        "classification": "complete_candidate"
        if complete
        else "partial_candidate"
        if observed
        else "unchanged",
        "baseline_sha256": evidence.configuration_hash(before),
        "running_sha256": evidence.configuration_hash(running),
        "startup_sha256": evidence.configuration_hash(startup),
        "target_configuration_sha256": evidence.configuration_hash(
            tuple(line for _, block, _ in stanzas.values() for line in block)
        ),
        "vlans": {
            str(vlan_id): {
                "name": name,
                "present": vlan_id in observed,
                "observed_members": observed[vlan_id][1] if vlan_id in observed else (),
                "configuration_sha256": evidence.configuration_hash(
                    observed[vlan_id][0]
                )
                if vlan_id in observed
                else None,
            }
            for vlan_id, name in trunk_plan.TARGET_VLANS
        },
        "execution_qualified": False,
        "live_admission": False,
        "limitations": (
            "candidate labels describe diagnostic configuration observations only",
            "firmware grouping and ordering acceptance remain unqualified",
            "no command acknowledgement, forwarding, inverse or writer is qualified",
        ),
    }


def classify_observation(
    baseline: tuple[str, ...] | list[str],
    current_running: tuple[str, ...] | list[str],
    current_startup: tuple[str, ...] | list[str],
) -> dict[str, Any]:
    """Require the fixed complete saved baseline and classify unsaved additions."""
    return _classify_observation(
        baseline,
        current_running,
        current_startup,
        baseline_sha256=trunk_plan.BASELINE_SHA256,
    )
