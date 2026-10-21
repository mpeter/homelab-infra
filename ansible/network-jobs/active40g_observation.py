"""Read-only sampled active40G host evidence; no member selection or live admission."""

from collections.abc import Callable
from datetime import datetime, timezone
import hashlib
from ipaddress import IPv6Address
import json
from pathlib import Path
import subprocess
import socket
import time
from typing import Any

SOURCE_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
DEVICES = ("nic0", "nic1", "nic5", "bond0", "vmbr0")
COUNTERS = ("carrier_changes", "carrier_up_count", "carrier_down_count")


class Rejected(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise Rejected(message)


def collect(root: Path = Path("/"), seconds: float = 5) -> dict[str, Any]:
    """Fixed local PVE reads bounded by one deadline; management is not migrated."""
    deadline = time.monotonic() + seconds

    def read(relative: str) -> str:
        require(time.monotonic() < deadline, "host sample deadline expired")
        return (root / relative).read_text(encoding="ascii").strip()

    def command(argv: list[str]) -> str:
        remaining = deadline - time.monotonic()
        require(remaining > 0, "host sample deadline expired")
        result = subprocess.run(
            argv,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=remaining,
            check=False,
            shell=False,
        )
        require(
            result.returncode == 0 and not result.stderr, "host sample command failed"
        )
        return result.stdout.decode("ascii")

    interfaces = (root / "etc/network/interfaces").read_bytes()
    links = json.loads(command(["ip", "-j", "link", "show"]))
    addresses = json.loads(command(["ip", "-j", "address", "show"]))
    routes = json.loads(command(["ip", "-j", "-4", "route", "show", "default"]))
    members = {
        device: {
            key: read(f"sys/class/net/{device}/{key}") for key in ("carrier", *COUNTERS)
        }
        for device in ("nic0", "nic5")
    }
    members["nic5"]["speed"] = read("sys/class/net/nic5/speed")
    active = read("sys/class/net/bond0/bonding/active_slave")
    bond = read("proc/net/bonding/bond0")
    guests = {vm: command(["qm", "status", vm]).strip() for vm in ("100", "200")}
    require(
        (root / "etc/network/interfaces").read_bytes() == interfaces,
        "interfaces changed during sample",
    )
    require(time.monotonic() < deadline, "host sample deadline expired")
    return {
        "source_sha256": SOURCE_SHA256,
        "sampled_at": datetime.now(timezone.utc).isoformat(),
        "interfaces_sha256": hashlib.sha256(interfaces).hexdigest(),
        "hostname": socket.gethostname(),
        "links": links,
        "addresses": addresses,
        "routes": routes,
        "members": members,
        "active": active,
        "bond": bond,
        "guests": guests,
    }


def indexed(value: Any) -> dict[str, Any]:
    require(type(value) is list, "complete host interface list required")
    result: dict[str, Any] = {}
    for item in value:
        require(
            type(item) is dict and type(item.get("ifname")) is str,
            "host interface shape",
        )
        require(item["ifname"] not in result, "duplicate host interface")
        result[item["ifname"]] = item
    require(set(DEVICES) <= result.keys(), "host interface missing")
    return {device: result[device] for device in DEVICES}


def fields(section: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in section.splitlines():
        if ": " in line:
            key, value = line.split(": ", 1)
            require(key not in result, "duplicate host bond field")
            result[key] = value
    return result


def bridge_link_local(value: Any) -> bool:
    if type(value) is not list:
        return False
    if not value:
        return True
    if len(value) != 1 or type(value[0]) is not dict:
        return False
    address = value[0]
    if set(address) != {
        "family",
        "local",
        "prefixlen",
        "scope",
        "protocol",
        "valid_life_time",
        "preferred_life_time",
    }:
        return False
    if (
        address["family"] != "inet6"
        or address["scope"] != "link"
        or address["protocol"] != "kernel_ll"
        or type(address["prefixlen"]) is not int
        or address["prefixlen"] != 64
        or type(address["local"]) is not str
        or "%" in address["local"]
        or any(
            type(address[key]) is not int or address[key] < 0
            for key in ("valid_life_time", "preferred_life_time")
        )
    ):
        return False
    try:
        parsed = IPv6Address(address["local"])
        return parsed.ipv4_mapped is None and parsed.is_link_local
    except ValueError:
        return False


def validate(
    sample: dict[str, Any],
    baseline: dict[str, Any] | None = None,
    *,
    acknowledged_active_changes: int = 0,
) -> dict[str, Any]:
    """Freeze observed configuration and primary counters; sampling is not continuous."""
    require(
        type(acknowledged_active_changes) is int and acknowledged_active_changes >= 0,
        "acknowledged active change count required",
    )
    require(sample["hostname"] == "pve", "host identity drift")
    require(sample["source_sha256"] == SOURCE_SHA256, "active40G helper source drift")
    stamp = datetime.fromisoformat(sample["sampled_at"])
    require(stamp.tzinfo is not None, "host sample timezone required")
    require(
        type(sample["interfaces_sha256"]) is str
        and len(sample["interfaces_sha256"]) == 64,
        "host interfaces digest required",
    )
    links, addresses = indexed(sample["links"]), indexed(sample["addresses"])
    for device in DEVICES:
        row = links[device]
        require(
            row["mtu"] == 1500 and "UP" in row["flags"], "host admin state or MTU drift"
        )
        require(
            row.get("master")
            == {"nic0": "bond0", "nic5": "bond0", "bond0": "vmbr0"}.get(device),
            "host bridge membership drift",
        )
        require(
            row["operstate"] == ("DOWN" if device == "nic0" else "UP"),
            "host carrier state drift",
        )
        require(
            ("LOWER_UP" in row["flags"]) == (device != "nic0"),
            "host lower carrier drift",
        )
    require(sample["active"] == "nic5", "active40G member drift")
    parts = sample["bond"].split("Slave Interface: ")
    require(len(parts) == 3, "host bond member count drift")
    header = fields(parts[0])
    require(
        header.get("Bonding Mode") == "fault-tolerance (active-backup)"
        and header.get("Primary Slave") == "nic0 (primary_reselect always)"
        and header.get("Currently Active Slave") == "nic5"
        and header.get("MII Status") == "up"
        and header.get("MII Polling Interval (ms)") == "100",
        "host bond policy drift",
    )
    slaves = {part.splitlines()[0]: fields(part) for part in parts[1:]}
    require(set(slaves) == {"nic0", "nic5"}, "host bond membership drift")
    require(
        slaves["nic0"].get("MII Status") == "down"
        and slaves["nic5"].get("MII Status") == "up",
        "host bond carrier drift",
    )
    require(set(sample["members"]) == {"nic0", "nic5"}, "host member evidence missing")
    for device, carrier in (("nic0", "0"), ("nic5", "1")):
        member = sample["members"][device]
        require(member["carrier"] == carrier, "host sysfs carrier drift")
        for key in COUNTERS:
            require(
                type(member[key]) is str
                and member[key].isascii()
                and member[key].isdecimal(),
                "host carrier counter shape",
            )
        failure = slaves[device].get("Link Failure Count")
        require(
            type(failure) is str and failure.isascii() and failure.isdecimal(),
            "host bond failure counter shape",
        )
        require(
            int(member["carrier_changes"])
            == int(member["carrier_up_count"]) + int(member["carrier_down_count"]),
            "host carrier counter inconsistency",
        )
    require(sample["members"]["nic5"]["speed"] == "40000", "active40G speed drift")
    require(
        all(not addresses[device]["addr_info"] for device in ("nic0", "nic5", "bond0"))
        and bridge_link_local(addresses["vmbr0"].get("addr_info")),
        "host management ownership drift",
    )
    ipv4 = [item for item in addresses["nic1"]["addr_info"] if item["family"] == "inet"]
    require(
        len(ipv4) == 1 and ipv4[0]["prefixlen"] == 24, "USB management address shape"
    )
    routes = sample["routes"]
    require(
        type(routes) is list
        and len(routes) == 1
        and routes[0].get("dst") == "default"
        and routes[0].get("dev") == "nic1",
        "USB management route ownership drift",
    )
    require(
        sample["guests"] == {"100": "status: running", "200": "status: running"},
        "guest status drift",
    )
    frozen = {
        key: sample[key]
        for key in ("interfaces_sha256", "addresses", "routes", "guests", "active")
    }
    active_counters = {key: sample["members"]["nic5"][key] for key in COUNTERS}
    active_counters["link_failure_count"] = slaves["nic5"].pop("Link Failure Count")
    frozen.update(
        {
            "links": links,
            "bond_header": header,
            "bond_slaves": slaves,
            "primary_counters": sample["members"]["nic0"],
            "active_counters": active_counters,
        }
    )
    # Deep copy prevents caller mutation from changing the retained baseline.
    copied = json.loads(json.dumps(frozen, sort_keys=True))
    assert isinstance(copied, dict)
    frozen = copied
    if baseline is not None:
        require(
            {key: value for key, value in frozen.items() if key != "active_counters"}
            == {key: value for key, value in baseline.items() if key != "active_counters"},
            "sampled active40G baseline drift",
        )
        delta = {
            key: int(value) - int(baseline["active_counters"][key])
            for key, value in active_counters.items()
        }
        cycles = delta["carrier_down_count"]
        require(
            0 <= cycles <= acknowledged_active_changes
            and delta["carrier_up_count"] == cycles
            and delta["carrier_changes"] == 2 * cycles
            and delta["link_failure_count"] == cycles,
            "active40G transition counters drift outside acknowledged changes",
        )
    return frozen


Observer = Callable[[], dict[str, Any]]
