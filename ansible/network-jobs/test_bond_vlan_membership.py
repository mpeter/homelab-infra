"""Actual read-only before output and synthetic after output stay distinct."""

import pytest

import bond_vlan_membership as engine

# Transcribed from the 2026-10-09 read-only membership capture.
BEFORE1 = """Total PORT-VLAN entries: 2
Maximum PORT-VLAN entries: 64

Legend: [Stk=Stack-Id, S=Slot]

PORT-VLAN 1, Name DEFAULT-VLAN, Priority level0, Spanning tree On
 Untagged Ports: (U1/M1)   1   2   3   4   5   6   7   8   9  10  11  12
 Untagged Ports: (U1/M1)  13  14  15  16  17  18  19  20  21  22  23  24
 Untagged Ports: (U1/M1)  25  26  27  28  29  30  31  32  33  34  35  36
 Untagged Ports: (U1/M1)  37  38  39  40  41  42  43  44  45  46  47
 Untagged Ports: (U1/M2)   1   2   3   4   5   7   8   9  10
 Untagged Ports: (U1/M3)   1   2   3   4   5   6   7   8
   Tagged Ports: None
   Uplink Ports: None
 DualMode Ports: None
 Mac-Vlan Ports: None
     Monitoring: Disabled
"""
BEFORE132 = """Total PORT-VLAN entries: 2
Maximum PORT-VLAN entries: 64

Legend: [Stk=Stack-Id, S=Slot]

PORT-VLAN 132, Name DEFAULT-DECKPIN, Priority level0, Spanning tree On
 Untagged Ports: (U1/M2)   6
   Tagged Ports: (U1/M1)  48
   Uplink Ports: None
 DualMode Ports: None
 Mac-Vlan Ports: None
     Monitoring: Disabled
"""
AFTER1 = BEFORE1.replace("3   4   5   7", "3   4   5   6   7")
AFTER132 = BEFORE132.replace("Untagged Ports: (U1/M2)   6", "Untagged Ports: None")


def test_actual_before_and_synthetic_after() -> None:
    for phase, vlan1, vlan132 in (
        ("before", BEFORE1, BEFORE132),
        ("after", AFTER1, AFTER132),
    ):
        result = engine.check_membership(vlan1, vlan132, phase=phase)
        assert result["accepted"] is True
        assert result["scope"] == "fixed_vlan_membership_only"
        for flag in (
            "live_admission",
            "apply_enabled",
            "task_complete",
            "actual_forward_observed",
        ):
            assert result[flag] is False
    assert (
        engine.check_membership(BEFORE1, BEFORE132, phase="after")["accepted"] is False
    )
    assert (
        engine.check_membership(AFTER1, AFTER132, phase="before")["accepted"] is False
    )
    facts = engine.parse_vlan(BEFORE132, 132)
    assert facts.untagged == ((1, 2, 6),)
    assert facts.tagged == ((1, 1, 48),)
    assert facts.spanning_tree == "On"
    assert facts.monitoring == "Disabled"


def test_numeric_row_wrapping_changes_are_allowed() -> None:
    wrapped = AFTER1.replace(
        "(U1/M2)   1   2   3   4   5   6   7",
        "(U1/M2)   1   2   3   4   5\n Untagged Ports: (U1/M2)   6   7",
    )
    assert engine.check_membership(wrapped, AFTER132, phase="after")["accepted"] is True
    assert engine.parse_vlan(BEFORE1.replace("\n", "\r\n"), 1) == engine.parse_vlan(
        BEFORE1, 1
    )


@pytest.mark.parametrize(
    "old,new",
    [
        ("Total PORT-VLAN entries: 2", "Total PORT-VLAN entries: 3"),
        ("Maximum PORT-VLAN entries: 64", "Maximum PORT-VLAN entries: 128"),
        ("Legend: [Stk=Stack-Id, S=Slot]", "Legend: Unknown"),
        ("DEFAULT-VLAN", "Other"),
        ("PORT-VLAN 1,", "PORT-VLAN 132,"),
        ("Priority level0", "Priority level1"),
        ("Spanning tree On", "Spanning tree Off"),
        ("Monitoring: Disabled", "Monitoring: Enabled"),
        ("Mac-Vlan Ports: None", "Mac-Vlan Ports: None\nUnknown: None"),
        ("Uplink Ports: None", "Uplink Ports: None\nUplink Ports: None"),
        ("Tagged Ports: None", "Tagged Ports: None\nTagged Ports: (U1/M1) 48"),
        ("Tagged Ports: None", "Tagged Ports: (U1/M1) 48\nTagged Ports: None"),
        ("(U1/M3)   1", "(U2/M3)   1"),
        ("(U1/M3)   1", "(U1/M4)   1"),
        ("(U1/M3)   1", "(U1/M3)   01"),
        ("(U1/M3)   1", "(U1/M3)   9"),
        ("1   2   3", "1   1   3"),
        ("1   2   3", "2   1   3"),
        ("(U1/M2)   1", "(U1/M1)   1"),
    ],
)
def test_headers_unknown_state_duplicates_and_order_rejected(
    old: str, new: str
) -> None:
    with pytest.raises(engine.Rejected):
        engine.parse_vlan(BEFORE1.replace(old, new), 1)


def test_every_port_is_checked_and_no_other_port_can_move() -> None:
    facts = engine.parse_vlan(AFTER1, 1)
    for unit, slot, port in facts.untagged:
        # Re-render with one independently selected missing port.
        lines = AFTER1.splitlines()
        for index, line in enumerate(lines):
            if f"(U{unit}/M{slot})" in line:
                prefix, _, numbers = line.partition(")")
                values = numbers.split()
                if str(port) in values:
                    values.remove(str(port))
                    lines[index] = prefix + ") " + " ".join(values)
                    break
        assert (
            engine.check_membership("\n".join(lines), AFTER132, phase="after")[
                "accepted"
            ]
            is False
        )


@pytest.mark.parametrize(
    "old,new",
    [
        ("Tagged Ports: None", "Tagged Ports: (U1/M1) 48"),
        ("Uplink Ports: None", "Uplink Ports: (U1/M1) 48"),
        ("DualMode Ports: None", "DualMode Ports: (U1/M1) 48"),
        ("Mac-Vlan Ports: None", "Mac-Vlan Ports: (U1/M1) 48"),
    ],
)
def test_nonempty_other_memberships_are_not_accepted(old: str, new: str) -> None:
    assert (
        engine.check_membership(AFTER1.replace(old, new), AFTER132, phase="after")[
            "accepted"
        ]
        is False
    )


def test_tagged_uplink_and_fixed_single_port_drift() -> None:
    for changed in (
        AFTER132.replace("Tagged Ports: (U1/M1)  48", "Tagged Ports: None"),
        AFTER132.replace("Tagged Ports: (U1/M1)  48", "Tagged Ports: (U1/M1) 47"),
        AFTER132.replace("Untagged Ports: None", "Untagged Ports: (U1/M2) 7"),
    ):
        assert (
            engine.check_membership(AFTER1, changed, phase="after")["accepted"] is False
        )
    with pytest.raises(engine.Rejected):
        engine.parse_vlan(BEFORE132.replace("DEFAULT-DECKPIN", "Other"), 132)


def test_every_required_line_partial_and_extra_text_rejected() -> None:
    for text, vlan in ((BEFORE1, 1), (BEFORE132, 132)):
        lines = text.splitlines()
        for index, line in enumerate(lines):
            if not line.strip() or line.strip().startswith("Untagged Ports:"):
                continue
            with pytest.raises(engine.Rejected):
                engine.parse_vlan("\n".join(lines[:index] + lines[index + 1 :]), vlan)
        for changed in (
            text + "unknown\n",
            "--More--\n" + text,
            text.replace("\n", "\r"),
        ):
            with pytest.raises(engine.Rejected):
                engine.parse_vlan(changed, vlan)
    with pytest.raises(engine.Rejected):
        engine.check_membership(BEFORE1, BEFORE132, phase="other")
    with pytest.raises(engine.Rejected):
        engine.parse_vlan(BEFORE1, 2)
    with pytest.raises(engine.Rejected):
        engine.parse_vlan(BEFORE1, True)


def test_membership_label_order_missing_group_and_duplicate_port_row() -> None:
    for changed in (
        BEFORE132.replace(
            "   Uplink Ports: None\n DualMode Ports: None",
            " DualMode Ports: None\n   Uplink Ports: None",
        ),
        BEFORE132.replace(" Untagged Ports: (U1/M2)   6\n", ""),
        BEFORE132.replace(
            " Untagged Ports: (U1/M2)   6",
            " Untagged Ports: (U1/M2)   6\n Untagged Ports: (U1/M2)   6",
        ),
    ):
        with pytest.raises(engine.Rejected):
            engine.parse_vlan(changed, 132)
