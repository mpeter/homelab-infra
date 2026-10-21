"""Recorded empty output and synthetic candidate tables confer no qualification."""

import hashlib

import pytest

import standby_native_membership as engine
from test_bond_vlan_membership import AFTER1, AFTER132

BASELINE = {1: AFTER1, 132: AFTER132}
SYNTHETIC10 = """Total PORT-VLAN entries: 3
Maximum PORT-VLAN entries: 64
Legend: [Stk=Stack-Id, S=Slot]
PORT-VLAN 10, Name LAB-MGMT, Priority level0, Spanning tree Off
Untagged Ports: None
Tagged Ports: None
Uplink Ports: None
DualMode Ports: None
Mac-Vlan Ports: None
Monitoring: Disabled
"""


def tables(phase: str, *, dual_only: bool = False) -> dict[int, str]:
    if phase == "baseline":
        return dict(BASELINE)
    if phase == "empty":
        return {**BASELINE, 10: "Port-vlan 10 does not have any members."}
    result = {
        vlan: text.replace("Total PORT-VLAN entries: 2", "Total PORT-VLAN entries: 3")
        for vlan, text in BASELINE.items()
    }
    result[10] = SYNTHETIC10
    if phase in ("tagged", "native"):
        result[10] = SYNTHETIC10.replace(
            "Tagged Ports: None", "Tagged Ports: (U1/M2) 6"
        )
    if phase == "tagged" or dual_only:
        result[1] = result[1].replace(
            "(U1/M2)   1   2   3   4   5   6   7", "(U1/M2)   1   2   3   4   5   7"
        )
    if phase == "native":
        result[1] = result[1].replace(
            "DualMode Ports: None", "DualMode Ports: (U1/M2) 6"
        )
    return result


def check(responses: dict[int, str], phase: str) -> dict[str, object]:
    return engine.check_membership(
        responses, baseline_vlan1=AFTER1, baseline_vlan132=AFTER132, phase=phase
    )


@pytest.mark.parametrize("phase", ["baseline", "empty", "tagged", "native"])
def test_complete_phase_tables_and_no_qualification(phase: str) -> None:
    result = check(tables(phase), phase)
    assert result["accepted"] is True
    assert result["installed_vlan_count"] == (3 if phase in ("tagged", "native") else 2)
    for flag in (
        "qualified",
        "live_admission",
        "actual_forward_observed",
        "pvid_verified",
    ):
        assert result[flag] is False


@pytest.mark.parametrize("dual_only", [False, True])
def test_explicit_native_representations(dual_only: bool) -> None:
    result = check(tables("native", dual_only=dual_only), "native")
    assert result["accepted"] is True
    assert result["native_representation"] == (
        "dual_mode_only" if dual_only else "untagged_and_dual_mode"
    )


@pytest.mark.parametrize(
    "old,new",
    [
        ("Total PORT-VLAN entries: 3", "Total PORT-VLAN entries: 2"),
        ("Maximum PORT-VLAN entries: 64", "Maximum PORT-VLAN entries: 128"),
        ("Legend: [Stk=Stack-Id, S=Slot]", "Legend: Other"),
        ("LAB-MGMT", "Other"),
        ("PORT-VLAN 10,", "PORT-VLAN 1,"),
        ("Priority level0", "Priority level1"),
        ("Spanning tree Off", "Spanning tree On"),
        ("Monitoring: Disabled", "Monitoring: Enabled"),
        ("Tagged Ports: None", "Tagged Ports: (U1/M2) 6 6"),
        ("Tagged Ports: None", "Tagged Ports: (U1/M2) 6\nTagged Ports: (U1/M2) 6"),
        ("Tagged Ports: None", "Tagged Ports: (U1/M2) 7 6"),
        ("Tagged Ports: None", "Tagged Ports: (U1/M2) 06"),
        ("Tagged Ports: None", "Tagged Ports: (U1/M2) 11"),
        ("Tagged Ports: None", "Tagged Ports: (U2/M2) 6"),
        ("Tagged Ports: None", "Tagged Ports: (U1/M4) 6"),
        (
            "Uplink Ports: None\nDualMode Ports: None",
            "DualMode Ports: None\nUplink Ports: None",
        ),
        ("Uplink Ports: None", "Uplink Ports: None\nUplink Ports: None"),
        ("Mac-Vlan Ports: None", "Mac-Vlan Ports: None\nUnknown: None"),
    ],
)
def test_malformed_or_mutated_complete_table_rejected(old: str, new: str) -> None:
    with pytest.raises(engine.Rejected):
        engine.parse_vlan(SYNTHETIC10.replace(old, new), 10, expected_total=3)


def test_missing_every_required_line_and_extra_text_rejected() -> None:
    lines = SYNTHETIC10.splitlines()
    for index in range(len(lines)):
        with pytest.raises(engine.Rejected):
            engine.parse_vlan(
                "\n".join(lines[:index] + lines[index + 1 :]), 10, expected_total=3
            )
    for text in (
        SYNTHETIC10 + "unknown\n",
        "--More--\n" + SYNTHETIC10,
        SYNTHETIC10.replace("\n", "\r"),
    ):
        with pytest.raises(engine.Rejected):
            engine.parse_vlan(text, 10, expected_total=3)


@pytest.mark.parametrize("phase", ["baseline", "empty", "tagged", "native"])
def test_missing_extra_tables_and_wrong_count_rejected(phase: str) -> None:
    responses = tables(phase)
    del responses[132]
    with pytest.raises(engine.Rejected):
        check(responses, phase)
    responses = tables(phase)
    responses[999] = SYNTHETIC10
    with pytest.raises(engine.Rejected):
        check(responses, phase)
    responses = tables(phase)
    responses[1] = responses[1].replace(
        f"Total PORT-VLAN entries: {3 if phase in ('tagged', 'native') else 2}",
        f"Total PORT-VLAN entries: {2 if phase in ('tagged', 'native') else 3}",
    )
    with pytest.raises(engine.Rejected):
        check(responses, phase)


@pytest.mark.parametrize(
    "vlan,old,new",
    [
        (132, "Tagged Ports: (U1/M1)  48", "Tagged Ports: (U1/M1) 47"),
        (132, "Untagged Ports: None", "Untagged Ports: (U1/M2) 6"),
        (1, "1   2   3", "2   3"),
        (1, "Tagged Ports: None", "Tagged Ports: (U1/M1) 48"),
        (1, "Uplink Ports: None", "Uplink Ports: (U1/M1) 48"),
        (1, "Mac-Vlan Ports: None", "Mac-Vlan Ports: (U1/M1) 48"),
        (1, "DualMode Ports: (U1/M2) 6", "DualMode Ports: (U1/M2) 7"),
        (1, "DualMode Ports: (U1/M2) 6", "DualMode Ports: (U1/M2) 6 7"),
        (1, "DualMode Ports: (U1/M2) 6", "DualMode Ports: None"),
        (10, "Tagged Ports: (U1/M2) 6", "Tagged Ports: (U1/M2) 7"),
        (10, "Tagged Ports: (U1/M2) 6", "Tagged Ports: (U1/M2) 6 7"),
        (10, "Untagged Ports: None", "Untagged Ports: (U1/M2) 6"),
        (10, "DualMode Ports: None", "DualMode Ports: (U1/M2) 6"),
    ],
)
def test_legacy_drift_nonstandby_leaks_and_wrong_native_port_not_accepted(
    vlan: int, old: str, new: str
) -> None:
    responses = tables("native")
    responses[vlan] = responses[vlan].replace(old, new)
    assert check(responses, "native")["accepted"] is False


def test_tag_requires_standby_removed_and_native_requires_restored_union() -> None:
    with pytest.raises(engine.Rejected):
        check(tables("empty"), "tagged")
    assert check(tables("tagged"), "native")["accepted"] is False
    responses = tables("native", dual_only=True)
    responses[1] = responses[1].replace("3   4   5   7", "3   4   7")
    assert check(responses, "native")["accepted"] is False


def test_canonical_baseline_required_and_unknown_phase_rejected() -> None:
    with pytest.raises(engine.Rejected):
        engine.check_membership(
            BASELINE,
            baseline_vlan1=AFTER1.replace("1   2   3", "2   3"),
            baseline_vlan132=AFTER132,
            phase="baseline",
        )
    with pytest.raises(engine.Rejected):
        check(BASELINE, "unknown")
    with pytest.raises(engine.Rejected):
        engine.parse_vlan(SYNTHETIC10, 10, expected_total=2)


def test_wrapped_numeric_rows_crlf_and_observed_facts() -> None:
    responses = tables("native", dual_only=True)
    responses[1] = (
        responses[1]
        .replace(
            "(U1/M2)   1   2   3   4   5   7",
            "(U1/M2) 1 2 3\nUntagged Ports: (U1/M2) 4 5 7",
        )
        .replace("\n", "\r\n")
    )
    assert check(responses, "native")["accepted"] is True
    facts = engine.parse_vlan(responses[10], 10, expected_total=3)
    assert facts.vlan == 10
    assert facts.name == "LAB-MGMT"
    assert facts.tagged == ((1, 2, 6),)


def test_recorded_empty_marker_does_not_invent_vlan10_facts() -> None:
    # 2026-10-10 stopped cycle, native-observe-jmc9dcdj/tables/vlan-tables.json.
    result = check(tables("empty"), "empty")
    assert result["accepted"] is True
    assert result["installed_vlan_count"] == 2
    assert result["vlan10_empty_marker"] == "Port-vlan 10 does not have any members."
    assert result["vlan10_present"] is None
    observed = result["observed"]
    assert isinstance(observed, dict)
    assert set(observed) == {1, 132}


@pytest.mark.parametrize(
    "marker",
    [
        "",
        "Port-vlan 10 does not have any members.\n",
        " Port-vlan 10 does not have any members.",
        "Port-vlan 10 does not have any members.\nUnknown: None",
        "Port-vlan 11 does not have any members.",
        "Port-vlan 10 does not have any members.\r",
        "Port-vlan 10 does not have any members.\x00",
        SYNTHETIC10,
    ],
)
def test_empty_marker_mutations_rejected(marker: str) -> None:
    responses = tables("empty")
    responses[10] = marker
    with pytest.raises(engine.Rejected):
        check(responses, "empty")


@pytest.mark.parametrize(
    "vlan,old,new",
    [
        (132, "Tagged Ports: (U1/M1)  48", "Tagged Ports: (U1/M1) 47"),
        (132, "Untagged Ports: None", "Untagged Ports: (U1/M2) 6"),
        (1, "1   2   3", "2   3"),
        (1, "DualMode Ports: None", "DualMode Ports: (U1/M2) 6"),
        (1, "Tagged Ports: None", "Tagged Ports: (U1/M1) 48"),
    ],
)
def test_empty_preserves_legacy_and_every_unrelated_membership(
    vlan: int, old: str, new: str
) -> None:
    responses = tables("empty")
    responses[vlan] = responses[vlan].replace(old, new)
    assert check(responses, "empty")["accepted"] is False


RECORDED_TAGGED10 = """Total PORT-VLAN entries: 3
Maximum PORT-VLAN entries: 64

Legend: [Stk=Stack-Id, S=Slot]

PORT-VLAN 10, Name LAB-MGMT, Priority level0, Spanning tree Off
 Untagged Ports: None
   Tagged Ports: (U1/M2)   6
   Uplink Ports: None
 DualMode Ports: None
 Mac-Vlan Ports: None
     Monitoring: Disabled
"""


def test_recorded_tagged_tables_sha_and_spanning_tree_facts() -> None:
    # 2026-10-10 native-observe-8rsfeb4z/tables/vlan-tables.json.
    responses = tables("tagged")
    responses[10] = RECORDED_TAGGED10
    hashes = {
        1: "d2d4457cebea1a86b88cf6466d24173558558fa4086954f51a522b9354bb1899",
        10: "f57279ae1a2f457fec225a2fd4cc8a6808b48570f46be6f5446176dec95fe9c6",
        132: "5542f68a48a00d588b807697b6896d55730e3f89b4878fbbedf0a0e14de2c633",
    }
    for vlan, raw in responses.items():
        assert hashlib.sha256(raw.encode()).hexdigest() == hashes[vlan]
    result = check(responses, "tagged")
    assert result["accepted"] is True
    assert result["qualified"] is False
    for vlan, raw in responses.items():
        facts = engine.parse_vlan(raw, vlan, expected_total=3)
        assert facts.spanning_tree == ("Off" if vlan == 10 else "On")


@pytest.mark.parametrize("vlan", [1, 10, 132])
def test_wrong_observed_spanning_tree_state_rejected(vlan: int) -> None:
    responses = tables("tagged")
    responses[10] = RECORDED_TAGGED10
    old, new = ("Off", "On") if vlan == 10 else ("On", "Off")
    responses[vlan] = responses[vlan].replace(
        "Spanning tree " + old, "Spanning tree " + new
    )
    with pytest.raises(engine.Rejected):
        check(responses, "tagged")
