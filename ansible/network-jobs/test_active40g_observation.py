"""Offline sampled host invariants and read-only collection regressions."""

import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess

import pytest

import active40g_observation as observer


def sample() -> dict:
    links = [
        {
            "ifname": device,
            "mtu": 1500,
            "flags": ["UP"] if device == "nic0" else ["UP", "LOWER_UP"],
            "operstate": "DOWN" if device == "nic0" else "UP",
            "master": {"nic0": "bond0", "nic5": "bond0", "bond0": "vmbr0"}.get(device),
        }
        for device in observer.DEVICES
    ]
    return {
        "hostname": "pve",
        "source_sha256": observer.SOURCE_SHA256,
        "sampled_at": datetime.now(timezone.utc).isoformat(),
        "interfaces_sha256": "a" * 64,
        "links": links,
        "addresses": [
            {
                "ifname": device,
                "addr_info": [
                    {"family": "inet", "local": "192.168.0.190", "prefixlen": 24}
                ]
                if device == "nic1"
                else [],
            }
            for device in observer.DEVICES
        ],
        "routes": [{"dst": "default", "gateway": "192.168.0.1", "dev": "nic1"}],
        "active": "nic5",
        "bond": "Bonding Mode: fault-tolerance (active-backup)\nPrimary Slave: nic0 (primary_reselect always)\nCurrently Active Slave: nic5\nMII Status: up\nMII Polling Interval (ms): 100\nSlave Interface: nic0\nMII Status: down\nLink Failure Count: 3\nSlave Interface: nic5\nMII Status: up\nLink Failure Count: 2\n",
        "members": {
            device: {
                "carrier": "0" if device == "nic0" else "1",
                "carrier_changes": "6",
                "carrier_up_count": "3",
                "carrier_down_count": "3",
                **({"speed": "40000"} if device == "nic5" else {}),
            }
            for device in ("nic0", "nic5")
        },
        "guests": {"100": "status: running", "200": "status: running"},
    }


def test_frozen_baseline_is_copied_and_management_is_observed_per_run() -> None:
    before = sample()
    before["addresses"][1]["addr_info"][0]["local"] = "192.168.0.191"
    frozen = observer.validate(before)
    observer.validate(copy.deepcopy(before), frozen)
    before["members"]["nic0"]["carrier_changes"] = "7"
    before["members"]["nic0"]["carrier_down_count"] = "4"
    assert frozen["primary_counters"]["carrier_changes"] == "6"
    with pytest.raises(observer.Rejected, match="baseline drift"):
        observer.validate(before, frozen)


@pytest.mark.parametrize(
    "mutation",
    [
        "primary",
        "active",
        "speed",
        "counter",
        "failure",
        "address",
        "route",
        "config",
        "policy",
        "missing",
        "source",
        "admin",
        "guest",
    ],
)
def test_primary_down_sample_rejects_drift(mutation: str) -> None:
    original = sample()
    baseline = observer.validate(original)
    changed = copy.deepcopy(original)
    if mutation == "primary":
        changed["members"]["nic0"]["carrier"] = "1"
    elif mutation == "active":
        changed["active"] = "nic0"
    elif mutation == "speed":
        changed["members"]["nic5"]["speed"] = "10000"
    elif mutation == "counter":
        changed["members"]["nic0"]["carrier_up_count"] = "4"
    elif mutation == "failure":
        changed["bond"] = changed["bond"].replace(
            "Failure Count: 3", "Failure Count: 4"
        )
    elif mutation == "address":
        changed["addresses"][1]["addr_info"][0]["local"] = "192.168.0.191"
    elif mutation == "route":
        changed["routes"][0]["dev"] = "vmbr0"
    elif mutation == "config":
        changed["interfaces_sha256"] = "b" * 64
    elif mutation == "policy":
        changed["bond"] = changed["bond"].replace("always", "failure")
    elif mutation == "missing":
        changed["links"].pop()
    elif mutation == "source":
        changed["source_sha256"] = "b" * 64
    elif mutation == "admin":
        changed["links"][0]["flags"] = []
    else:
        changed["guests"]["100"] = "status: stopped"
    with pytest.raises(observer.Rejected):
        observer.validate(changed, baseline)


def test_collector_executes_only_fixed_reads(tmp_path: Path, monkeypatch) -> None:
    example = sample()
    files = {
        "etc/network/interfaces": "observed interfaces\n",
        "proc/net/bonding/bond0": example["bond"],
        "sys/class/net/bond0/bonding/active_slave": "nic5\n",
        **{
            f"sys/class/net/{device}/{key}": value
            for device, fields in example["members"].items()
            for key, value in fields.items()
        },
    }
    for relative, value in files.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value)
    before = {relative: (tmp_path / relative).read_bytes() for relative in files}
    calls = []

    def command(argv, **kwargs):
        calls.append(argv)
        assert kwargs["shell"] is False and kwargs["timeout"] <= 5
        result = (
            "status: running"
            if argv[0] == "qm"
            else json.dumps(
                example[
                    {"link": "links", "address": "addresses", "route": "routes"}[
                        argv[2] if argv[2] != "-4" else argv[3]
                    ]
                ]
            )
        )
        return subprocess.CompletedProcess(argv, 0, result.encode(), b"")

    monkeypatch.setattr(observer.subprocess, "run", command)
    monkeypatch.setattr(observer.socket, "gethostname", lambda: "pve")
    collected = observer.collect(tmp_path)
    observer.validate(collected)
    assert calls == [
        ["ip", "-j", "link", "show"],
        ["ip", "-j", "address", "show"],
        ["ip", "-j", "-4", "route", "show", "default"],
        ["qm", "status", "100"],
        ["qm", "status", "200"],
    ]
    assert before == {
        relative: (tmp_path / relative).read_bytes() for relative in files
    }


def bridge_address() -> dict[str, object]:
    return {
        "family": "inet6",
        "local": "fe80::20a:f7ff:fe14:8c90",
        "preferred_life_time": 4294967295,
        "prefixlen": 64,
        "protocol": "kernel_ll",
        "scope": "link",
        "valid_life_time": 4294967295,
    }


def test_kernel_bridge_link_local_is_accepted_and_fully_frozen() -> None:
    original = sample()
    original["addresses"][4]["addr_info"] = [bridge_address()]
    baseline = observer.validate(original)
    observer.validate(copy.deepcopy(original), baseline)
    assert baseline["addresses"][4]["addr_info"] == [bridge_address()]
    for key, value in (
        ("local", "fe80::1"),
        ("valid_life_time", 4294967294),
        ("preferred_life_time", 4294967294),
    ):
        changed = copy.deepcopy(original)
        changed["addresses"][4]["addr_info"][0][key] = value
        with pytest.raises(observer.Rejected, match="baseline drift"):
            observer.validate(changed, baseline)
    changed = copy.deepcopy(original)
    changed["addresses"][4]["addr_info"] = []
    with pytest.raises(observer.Rejected, match="baseline drift"):
        observer.validate(changed, baseline)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("local", "2001:db8::1"),
        ("local", "fd00::1"),
        ("local", "192.168.0.190"),
        ("local", "::ffff:169.254.1.1"),
        ("local", "invalid"),
        ("local", "fe80::1%vmbr0"),
        ("local", None),
        ("family", "inet"),
        ("scope", "global"),
        ("protocol", "static"),
        ("prefixlen", 128),
        ("prefixlen", "64"),
        ("valid_life_time", -1),
        ("preferred_life_time", True),
        ("unknown", "value"),
    ],
)
def test_bridge_rejects_other_address_shapes(key: str, value: object) -> None:
    observed = sample()
    address = bridge_address()
    address[key] = value
    observed["addresses"][4]["addr_info"] = [address]
    with pytest.raises(observer.Rejected, match="management ownership drift"):
        observer.validate(observed)


@pytest.mark.parametrize("value", [None, {}, [None], [bridge_address()] * 2])
def test_bridge_rejects_invalid_address_list(value: object) -> None:
    observed = sample()
    observed["addresses"][4]["addr_info"] = value
    with pytest.raises(observer.Rejected, match="management ownership drift"):
        observer.validate(observed)


@pytest.mark.parametrize("key", list(bridge_address()))
def test_bridge_rejects_missing_address_fields(key: str) -> None:
    observed = sample()
    address = bridge_address()
    del address[key]
    observed["addresses"][4]["addr_info"] = [address]
    with pytest.raises(observer.Rejected, match="management ownership drift"):
        observer.validate(observed)


@pytest.mark.parametrize("device", ["nic0", "nic5", "bond0"])
def test_physical_members_and_bond_reject_link_local(device: str) -> None:
    observed = sample()
    for row in observed["addresses"]:
        if row["ifname"] == device:
            row["addr_info"] = [bridge_address()]
    with pytest.raises(observer.Rejected, match="management ownership drift"):
        observer.validate(observed)


def transition_sample(failures: int, down: int, up: int) -> dict:
    observed = sample()
    observed["bond"] = observed["bond"].replace(
        "Failure Count: 2", f"Failure Count: {failures}"
    )
    observed["members"]["nic5"].update(
        carrier_changes=str(down + up),
        carrier_down_count=str(down),
        carrier_up_count=str(up),
    )
    return observed


def test_reviewed_native_change_and_inverse_counter_cycles() -> None:
    # Reviewed completed7: 35/81/40/41 -> 36/83/41/42; inverse: 37/85/42/43.
    before = observer.validate(transition_sample(35, 40, 41))
    after = observer.validate(
        transition_sample(36, 41, 42), before, acknowledged_active_changes=2
    )
    assert after["active_counters"]["link_failure_count"] == "36"
    observer.validate(transition_sample(36, 41, 42), after)
    restored = observer.validate(
        transition_sample(37, 42, 43), after, acknowledged_active_changes=2
    )
    observer.validate(transition_sample(37, 42, 43), restored)


@pytest.mark.parametrize("acknowledged", [0, 1])
def test_unexpected_or_over_budget_active_cycles_reject(acknowledged: int) -> None:
    before = observer.validate(transition_sample(35, 40, 41))
    with pytest.raises(observer.Rejected, match="transition counters drift"):
        observer.validate(
            transition_sample(37, 42, 43),
            before,
            acknowledged_active_changes=acknowledged,
        )


@pytest.mark.parametrize(
    ("failures", "down", "up"),
    [(34, 39, 40), (36, 40, 42), (35, 41, 42), (37, 41, 42)],
)
def test_acknowledged_changes_reject_nonmonotonic_or_incoherent_counters(
    failures: int, down: int, up: int
) -> None:
    before = observer.validate(transition_sample(35, 40, 41))
    with pytest.raises(observer.Rejected, match="transition counters drift"):
        observer.validate(
            transition_sample(failures, down, up),
            before,
            acknowledged_active_changes=2,
        )


@pytest.mark.parametrize("key", [*observer.COUNTERS, "link_failure_count"])
@pytest.mark.parametrize("value", ["-1", "1.0", "１２", None, True])
def test_active_counter_invalid_shapes_reject(key: str, value: object) -> None:
    observed = transition_sample(35, 40, 41)
    if key == "link_failure_count":
        observed["bond"] = observed["bond"].replace("Failure Count: 35", f"Failure Count: {value}")
    else:
        observed["members"]["nic5"][key] = value
    with pytest.raises(observer.Rejected, match="counter shape"):
        observer.validate(observed)


def test_active_change_budget_does_not_permit_primary_or_configuration_drift() -> None:
    before = observer.validate(transition_sample(35, 40, 41))
    for field in ("primary", "config"):
        observed = transition_sample(36, 41, 42)
        if field == "primary":
            observed["bond"] = observed["bond"].replace("Failure Count: 3", "Failure Count: 4")
        else:
            observed["interfaces_sha256"] = "b" * 64
        with pytest.raises(observer.Rejected, match="baseline drift"):
            observer.validate(observed, before, acknowledged_active_changes=2)


def test_active_absolute_carrier_counters_must_sum() -> None:
    observed = transition_sample(35, 40, 41)
    observed["members"]["nic5"]["carrier_changes"] = "82"
    with pytest.raises(observer.Rejected, match="counter inconsistency"):
        observer.validate(observed)
