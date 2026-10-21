"""Complete installed VLAN facts for the unsaved standby native candidate."""

from collections.abc import Mapping
from dataclasses import replace

import bond_vlan_membership as fixed

NAMES = {1: "DEFAULT-VLAN", 10: "LAB-MGMT", 132: "DEFAULT-DECKPIN"}
STANDBY: fixed.Port = (1, 2, 6)
EMPTY_VLAN10 = "Port-vlan 10 does not have any members."


class Rejected(ValueError):
    """Reject incomplete or unsupported tables without echoing their contents."""


def parse_vlan(text: str, vlan: int, *, expected_total: int) -> fixed.VlanMembership:
    """Validate identity/count, then reuse the exact observed firmware grammar."""
    if (
        type(vlan) is not int
        or vlan not in NAMES
        or type(expected_total) is not int
        or expected_total not in (2, 3)
        or (vlan == 10 and expected_total != 3)
        or not isinstance(text, str)
    ):
        raise Rejected("invalid installed VLAN read-back")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    spanning_tree = "Off" if vlan == 10 else "On"
    header = (
        f"PORT-VLAN {vlan}, Name {NAMES[vlan]}, Priority level0, "
        f"Spanning tree {spanning_tree}"
    )
    if (
        len(lines) < 4
        or lines[0] != f"Total PORT-VLAN entries: {expected_total}"
        or lines[3] != header
    ):
        raise Rejected("installed VLAN identity or count")
    # Substitute only validated fields unsupported by the two-VLAN parser.
    canonical = text.replace(
        f"Total PORT-VLAN entries: {expected_total}", "Total PORT-VLAN entries: 2", 1
    ).replace(
        header, "PORT-VLAN 1, Name DEFAULT-VLAN, Priority level0, Spanning tree On", 1
    )
    try:
        facts = fixed.parse_vlan(canonical, 1)
    except fixed.Rejected as error:
        raise Rejected(str(error)) from error
    return replace(facts, vlan=vlan, name=NAMES[vlan], spanning_tree=spanning_tree)


def check_membership(
    responses: Mapping[int, str],
    *,
    baseline_vlan1: str,
    baseline_vlan132: str,
    phase: str,
) -> dict[str, object]:
    """Compare complete candidate tables; table matches confer no qualification.

    An absent VLAN 10 has no invented CLI body: baseline requires only VLANs 1
    and 132. Empty uses the recorded no-members marker, which establishes no
    VLAN name or configuration existence. Native accepts the two explicit candidate dual-mode representations;
    actual numeric PVID and live representation qualification belong to the caller.
    """
    if phase not in ("baseline", "empty", "tagged", "native"):
        raise Rejected("fixed standby membership phase required")
    baseline1 = parse_vlan(baseline_vlan1, 1, expected_total=2)
    baseline132 = parse_vlan(baseline_vlan132, 132, expected_total=2)
    default_ports = (
        *((1, 1, port) for port in range(1, 48)),
        *((1, 2, port) for port in range(1, 11)),
        *((1, 3, port) for port in range(1, 9)),
    )
    canonical1 = fixed.VlanMembership(1, NAMES[1], default_ports, (), (), (), ())
    canonical132 = fixed.VlanMembership(132, NAMES[132], (), ((1, 1, 48),), (), (), ())
    if baseline1 != canonical1 or baseline132 != canonical132:
        raise Rejected("baseline is not the canonical restored membership")
    present = phase != "baseline"
    expected_ids = {1, 10, 132} if present else {1, 132}
    if (
        any(type(vlan) is not int for vlan in responses)
        or set(responses) != expected_ids
    ):
        raise Rejected("missing or unexpected installed VLAN table")
    populated = phase in ("tagged", "native")
    total = 3 if populated else 2
    empty_marker = None
    if phase == "empty":
        if responses[10] != EMPTY_VLAN10:
            raise Rejected("unexpected empty VLAN 10 marker")
        empty_marker = responses[10]
    table_ids = expected_ids if populated else {1, 132}
    observed = {
        vlan: parse_vlan(responses[vlan], vlan, expected_total=total)
        for vlan in sorted(table_ids)
    }
    expected1 = baseline1
    representation = "no_dual_mode"
    if phase == "tagged":
        expected1 = replace(
            baseline1, untagged=tuple(port for port in default_ports if port != STANDBY)
        )
    elif phase == "native":
        expected1 = replace(baseline1, dual_mode=(STANDBY,))
        if STANDBY not in observed[1].untagged:
            expected1 = replace(
                expected1,
                untagged=tuple(port for port in default_ports if port != STANDBY),
            )
            representation = "dual_mode_only"
        else:
            representation = "untagged_and_dual_mode"
    accepted = observed[1] == expected1 and observed[132] == baseline132
    if populated:
        expected10 = fixed.VlanMembership(
            10,
            NAMES[10],
            (),
            (STANDBY,) if phase in ("tagged", "native") else (),
            (),
            (),
            (),
            spanning_tree="Off",
        )
        accepted = accepted and observed[10] == expected10
    return {
        "scope": "standby_native_vlan_tables_only",
        "phase": phase,
        "accepted": accepted,
        "installed_vlan_count": total,
        "vlan10_present": None if phase == "empty" else present,
        "vlan10_empty_marker": empty_marker,
        "observed": observed,
        "native_representation": representation,
        "qualified": False,
        "live_admission": False,
        "actual_forward_observed": False,
        "pvid_verified": False,
    }
