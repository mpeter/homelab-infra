"""Pure semantic acceptance of a source-bound R8 held guest evidence body.

``validate`` accepts the proof body (not the retained ledger envelope). ``binding``
contains operation_id, forward_count, boundary_observation_sha256 and
source_binding_sha256 from the current in-process boundary. The caller must pass
its current SOURCE_DIGEST; this module deliberately contains no historical pins.
``policy`` supplies the exact expected environment and collection closure plus
an epoch-second held_bounds pair. This module owns the fixed host validator,
DNS decoder, and Brocade table parser. Host baseline hashes cover the complete
normalized result of host validation, including counters. No helper collection
or live action is invoked. The policy binds Fedora VM 100,
while host samples independently require both configured guests (VMs 100 and 200)
to remain running. Production integration must pin policy in its current verified
source closure and construct binding from the ledger boundary. Neither value may
come from the proof or an untrusted caller; this pure function does not establish
authorization or production admission.
"""

import base64
import binascii
from datetime import datetime
import hashlib
from ipaddress import ip_address
import json
import math
import re
import struct
from typing import Any
from urllib.parse import urlsplit

import active40g_observation as host_observation
import native_trunk_plan as trunk_plan


class Rejected(ValueError):
    """Evidence does not establish the bound held interval."""


BINDING_FIELDS = {
    "operation_id",
    "forward_count",
    "boundary_observation_sha256",
    "source_binding_sha256",
}
FACT_FIELDS = {
    "host_before",
    "host_after",
    "vm_before",
    "vm_after",
    "management",
    "nas",
    "fedora",
    "dns",
    "switch",
    "generator",
    "activity",
    "window",
}
POLICY_FIELDS = {
    "sources",
    "host_helper_sha256",
    "host_baseline_sha256",
    "hostname",
    "active_member",
    "fedora_vm_config_sha256",
    "fedora_vm_bridge",
    "pve_name",
    "pve_leaf_sha256",
    "nas_name",
    "nas_leaf_sha256",
    "fedora_interface",
    "fedora_mac",
    "fedora_ipv4",
    "gateway_ipv4",
    "dns_ipv4",
    "dns_name",
    "wan_url",
    "switch_facts",
    "held_bounds",
    "max_window_seconds",
    "max_host_gap_seconds",
    "max_clock_uncertainty_seconds",
    "min_traffic_seconds",
}


def canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise Rejected(message)


def dns_answers(packet: bytes, transaction: int, expected_name: str) -> list[str]:
    """Read bounded A answers from a matching successful DNS response."""
    require(type(packet) is bytes and 12 <= len(packet) <= 4096, "DNS packet size")
    require(type(transaction) is int and 0 <= transaction <= 65535, "DNS transaction")
    ident, flags, questions, answers, authorities, additional = struct.unpack_from(
        "!6H", packet
    )
    require(
        ident == transaction
        and flags & 0x8000
        and flags & 0x7800 == 0
        and flags & 0x0200 == 0
        and flags & 0x000F == 0
        and questions == 1
        and answers <= 128
        and authorities <= 128
        and additional <= 128,
        "DNS response header",
    )

    def name(offset: int) -> tuple[str, int]:
        labels: list[str] = []
        cursor, end, visited = offset, None, set()
        while True:
            require(
                cursor < len(packet) and cursor not in visited, "DNS name bounds/loop"
            )
            visited.add(cursor)
            size = packet[cursor]
            if size & 0xC0 == 0xC0:
                require(cursor + 1 < len(packet), "DNS pointer bounds")
                pointer = ((size & 0x3F) << 8) | packet[cursor + 1]
                require(pointer < len(packet), "DNS pointer target")
                if end is None:
                    end = cursor + 2
                cursor = pointer
                continue
            require(size & 0xC0 == 0 and size <= 63, "DNS label encoding")
            cursor += 1
            if size == 0:
                return ".".join(labels), cursor if end is None else end
            require(cursor + size <= len(packet), "DNS label bounds")
            label = packet[cursor : cursor + size]
            require(all(32 <= byte <= 126 for byte in label), "DNS label encoding")
            labels.append(label.decode("ascii").lower())
            require(sum(map(len, labels)) + len(labels) - 1 <= 253, "DNS name length")
            cursor += size

    qname, cursor = name(12)
    require(cursor + 4 <= len(packet), "DNS question bounds")
    qtype, qclass = struct.unpack_from("!HH", packet, cursor)
    require(
        qtype == 1 and qclass == 1 and qname == expected_name.lower(),
        "DNS A/IN question identity required",
    )
    cursor += 4
    result: list[str] = []
    for index in range(answers + authorities + additional):
        owner, cursor = name(cursor)
        require(cursor + 10 <= len(packet), "DNS record bounds")
        rtype, rclass, _ttl, length = struct.unpack_from("!HHIH", packet, cursor)
        cursor += 10
        require(cursor + length <= len(packet), "DNS RDATA bounds")
        if index < answers and rtype == 1 and rclass == 1:
            require(length == 4 and owner == qname, "DNS A answer shape")
            result.append(".".join(str(byte) for byte in packet[cursor : cursor + 4]))
        cursor += length
    require(cursor == len(packet), "DNS trailing bytes")
    return result


def parse_switch(responses: dict[str, str], mac: str) -> dict[str, Any]:
    """Derive one dynamic FDB identity and forwarding state from strict CLI tables."""
    require(
        type(responses) is dict
        and set(responses) >= {"show mac-address", "show interfaces brief"},
        "switch responses",
    )
    wanted = _normalize_mac(mac)
    fdb_rows: list[list[str]] = []
    fdb_header = 0
    totals: list[int] = []
    for line in responses["show mac-address"].splitlines():
        words = line.split()
        if words == ["MAC-Address", "Port", "Type", "Index", "VLAN"]:
            fdb_header += 1
        elif len(words) == 5:
            mac_match = _normalize_mac_or_none(words[0])
            port_match = re.fullmatch(r"[1-9][0-9]*/[1-9][0-9]*/[1-9][0-9]*", words[1])
            require(
                mac_match is not None
                and port_match is not None
                and words[2] in {"Dynamic", "Static"}
                and words[3].isdigit()
                and words[4].isdigit()
                and 1 <= int(words[4]) <= 4094,
                "FDB row shape",
            )
            fdb_rows.append(words)
        elif line.startswith("Total active entries from all ports = "):
            match = re.fullmatch(
                r"Total active entries from all ports = ([0-9]+)", line.strip()
            )
            if match is None:
                raise Rejected("FDB total shape")
            totals.append(int(match.group(1)))
        elif words:
            raise Rejected("FDB table shape")
    require(
        fdb_header >= 1 and len(totals) == 1 and totals[0] == len(fdb_rows),
        "complete FDB table required",
    )
    matches = [row for row in fdb_rows if _normalize_mac(row[0]) == wanted]
    require(
        len(matches) == 1 and matches[0][2] == "Dynamic",
        "unique dynamic guest FDB entry required",
    )
    row = matches[0]
    header = "Port Link State Dupl Speed Trunk Tag Pvid Pri MAC Name"
    rows: dict[str, list[str]] = {}
    seen_header = 0
    for line in responses["show interfaces brief"].splitlines():
        words = line.split()
        if not words:
            continue
        if " ".join(words) == header:
            seen_header += 1
            continue
        if words[0] == "Port":
            raise Rejected("interface brief header shape")
        if seen_header:
            require(
                len(words) >= 10
                and re.fullmatch(
                    r"(?:[1-9][0-9]*/[1-9][0-9]*/[1-9][0-9]*|mgmt[1-9][0-9]*|ve[1-9][0-9]*)",
                    words[0],
                )
                is not None
                and _normalize_mac_or_none(words[9]) is not None
                and words[0] not in rows,
                "interface brief row shape",
            )
            rows[words[0]] = words
    port = row[1]
    interface = rows.get(port)
    if interface is None or seen_header < 1 or len(interface) < 10:
        raise Rejected("guest interface forwarding state required")
    interface_mac = _normalize_mac_or_none(interface[9])
    if interface_mac is None or interface[1:3] != ["Up", "Forward"]:
        raise Rejected("guest interface forwarding state required")
    return {"mac": wanted, "port": port, "vlan": int(row[4]), "forwarding": True}


def _normalize_mac_or_none(value: str) -> str | None:
    if re.fullmatch(r"[0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){5}", value):
        compact = value.replace(":", "").lower()
    elif re.fullmatch(r"[0-9a-fA-F]{4}(?:\.[0-9a-fA-F]{4}){2}", value):
        compact = value.replace(".", "").lower()
    else:
        return None
    return ":".join(compact[index : index + 2] for index in range(0, 12, 2))


def _normalize_mac(value: str) -> str:
    normalized = _normalize_mac_or_none(value)
    if normalized is None:
        raise Rejected("switch MAC")
    return normalized


def _hash(value: Any) -> bool:
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _number(value: Any) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def _stamp(value: Any) -> float:
    require(type(value) is str, "evidence timestamp required")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(parsed.tzinfo is not None, "evidence timestamp timezone required")
    return parsed.timestamp()


def _pair(value: Any) -> tuple[float, float]:
    require(
        type(value) is list and len(value) == 2 and all(_number(v) for v in value),
        "finite interval pair required",
    )
    return value[0], value[1]


def _name(value: Any) -> bool:
    return (
        type(value) is str
        and len(value) <= 253
        and "." in value
        and all(
            re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", part) is not None
            for part in value.split(".")
        )
    )


def _policy(policy: dict[str, Any]) -> None:
    require(
        type(policy) is dict and set(policy) == POLICY_FIELDS,
        "explicit policy fields required",
    )
    for key in (
        "host_helper_sha256",
        "host_baseline_sha256",
        "fedora_vm_config_sha256",
        "pve_leaf_sha256",
        "nas_leaf_sha256",
    ):
        require(_hash(policy[key]), f"policy {key} digest required")
    require(
        type(policy["sources"]) is dict
        and bool(policy["sources"])
        and all(
            type(k) is str and k and _hash(v) for k, v in policy["sources"].items()
        ),
        "policy source closure required",
    )
    for key in ("hostname", "active_member", "fedora_vm_bridge", "fedora_interface"):
        require(
            type(policy[key]) is str
            and bool(policy[key])
            and re.fullmatch(r"[a-zA-Z0-9_.-]+", policy[key]) is not None,
            f"policy {key} identity required",
        )
    require(
        type(policy["fedora_mac"]) is str
        and re.fullmatch(r"[0-9a-f]{2}(?::[0-9a-f]{2}){5}", policy["fedora_mac"])
        is not None,
        "policy Fedora MAC required",
    )
    for key in ("pve_name", "nas_name", "dns_name"):
        require(_name(policy[key]), f"policy {key} name required")
    for key in ("fedora_ipv4", "gateway_ipv4", "dns_ipv4"):
        require(
            type(policy[key]) is str and ip_address(policy[key]).version == 4,
            f"policy {key} IPv4 required",
        )
    url = urlsplit(policy["wan_url"])
    require(
        url.scheme == "https"
        and _name(url.hostname)
        and not url.username
        and not url.password
        and not url.fragment
        and url.hostname == policy["dns_name"],
        "policy named WAN HTTPS required",
    )
    switch = policy["switch_facts"]
    require(
        type(switch) is dict
        and set(switch) == {"mac", "port", "vlan", "forwarding"}
        and switch["mac"] == policy["fedora_mac"]
        and switch["forwarding"] is True
        and type(switch["vlan"]) is int
        and 1 <= switch["vlan"] <= 4094
        and type(switch["port"]) is str
        and re.fullmatch(r"[1-9][0-9]*/[1-9][0-9]*/[1-9][0-9]*", switch["port"])
        is not None,
        "policy switch forwarding identity required",
    )
    low, high = _pair(policy["held_bounds"])
    require(low < high, "policy held bounds order")
    for key in (
        "max_window_seconds",
        "max_host_gap_seconds",
        "max_clock_uncertainty_seconds",
        "min_traffic_seconds",
    ):
        require(
            _number(policy[key]) and policy[key] > 0,
            f"policy {key} positive bound required",
        )
    require(
        policy["min_traffic_seconds"] >= 3
        and policy["min_traffic_seconds"] <= policy["max_window_seconds"],
        "policy sustained traffic bounds",
    )


def _command(value: dict[str, Any]) -> Any:
    require(
        type(value["exit"]) is int and value["exit"] == 0 and value["stderr"] == "",
        "guest command failed",
    )
    return json.loads(value["stdout"])


def _validate(
    proof: dict[str, Any],
    binding: dict[str, Any],
    policy: dict[str, Any],
) -> str:
    _policy(policy)
    require(
        type(binding) is dict and set(binding) == BINDING_FIELDS,
        "current R8 boundary binding required",
    )
    require(
        type(binding["forward_count"]) is int
        and binding["forward_count"] == len(trunk_plan.R8_FULL_FORWARD)
        and all(_hash(binding[k]) for k in BINDING_FIELDS - {"forward_count"}),
        "current R8 boundary identity/count required",
    )
    require(
        type(proof) is dict
        and set(proof)
        == BINDING_FIELDS
        | FACT_FIELDS
        | {"kind", "sources", "selector_used", "status", "receipts"},
        "complete guest proof fields required",
    )
    require(
        all(
            proof[k] == binding[k] and type(proof[k]) is type(binding[k])
            for k in BINDING_FIELDS
        ),
        "guest proof boundary binding differs",
    )
    require(
        proof["kind"] == "read-only-active40g"
        and proof["status"] == "passed"
        and proof["selector_used"] is False
        and proof["sources"] == policy["sources"],
        "source-bound read-only passing proof required",
    )
    require(
        host_observation.SOURCE_SHA256 == policy["host_helper_sha256"],
        "active40G helper source differs",
    )
    for key in ("host_before", "host_after"):
        require(
            proof[key]["hostname"] == policy["hostname"]
            and proof[key]["active"] == policy["active_member"],
            "host identity differs",
        )
    before = host_observation.validate(
        proof["host_before"], acknowledged_active_changes=0
    )
    after = host_observation.validate(
        proof["host_after"], before, acknowledged_active_changes=0
    )
    counters = {
        "carrier_changes",
        "carrier_down_count",
        "carrier_up_count",
        "link_failure_count",
    }
    require(
        set(before["active_counters"]) == counters
        and set(after["active_counters"]) == counters
        and before["active_counters"] == after["active_counters"],
        "held active40G counter continuity differs",
    )
    require(
        digest(before) == digest(after) == policy["host_baseline_sha256"],
        "held frozen host baseline differs",
    )
    vm = proof["vm_before"]
    require(
        vm == proof["vm_after"]
        and vm["active"] == policy["active_member"]
        and vm["interfaces_sha256"]
        == before["interfaces_sha256"]
        == after["interfaces_sha256"]
        and vm["vm100_sha256"] == policy["fedora_vm_config_sha256"]
        and vm["vm100_status"] == "status: running"
        and vm["vm100_bridge"] == policy["fedora_vm_bridge"]
        and vm["vm100_mac"] == policy["fedora_mac"]
        and vm["usb_up"] is True
        and vm["usb_default"] is True,
        "Fedora VM/USB continuity differs",
    )
    management, nas = proof["management"], proof["nas"]
    require(
        management["name"] == policy["pve_name"]
        and management["normal_ca_hostname_verified"] is True
        and management["der_sha256"] == policy["pve_leaf_sha256"],
        "normal named PVE TLS differs",
    )
    require(
        nas["name"] == policy["nas_name"]
        and nas["der_sha256"] == policy["nas_leaf_sha256"]
        and nas["normal_trust_claimed"] is False,
        "selected NAS peer identity differs",
    )
    fedora = proof["fedora"]["result"]
    rows = _command(fedora["identity"])
    require(
        type(rows) is list
        and len(rows) == 1
        and rows[0]["ifname"] == policy["fedora_interface"]
        and rows[0]["address"].lower() == policy["fedora_mac"]
        and policy["fedora_ipv4"]
        in [a.get("local") for a in rows[0]["addr_info"] if a.get("family") == "inet"],
        "Fedora identity differs",
    )
    route = _command(fedora["gateway_route"])
    require(
        type(route) is list
        and len(route) == 1
        and route[0].get("dst") == policy["gateway_ipv4"]
        and route[0].get("dev") == policy["fedora_interface"]
        and route[0].get("prefsrc") == policy["fedora_ipv4"]
        and route[0].get("gateway", policy["gateway_ipv4"]) == policy["gateway_ipv4"]
        and fedora["gateway_tcp_443"] is True,
        "Fedora gateway continuity differs",
    )
    https = fedora["https"]
    require(
        https["url"] == policy["wan_url"]
        and type(https["status"]) is int
        and https["status"] == 200
        and https["tls_verified"] is True
        and ip_address(https["peer_ipv4"]).version == 4
        and ip_address(https["peer_ipv4"]).is_global,
        "verified WAN HTTPS differs",
    )
    dns = proof["dns"]["result"]
    require(
        dns == fedora["dns"]
        and dns["server"] == policy["dns_ipv4"]
        and type(dns["port"]) is int
        and dns["port"] == 53
        and dns["transport"] == "UDP"
        and dns["query_name"] == policy["dns_name"]
        and dns["query_type"] == "A"
        and dns["status"] == "NOERROR"
        and dns["cache_disabled"] is True,
        "direct Fedora DNS differs",
    )
    query, response = (
        bytes.fromhex(dns["query_hex"]),
        bytes.fromhex(dns["response_hex"]),
    )
    require(len(response) <= 4096, "DNS response exceeds collection bound")
    question = b"".join(
        bytes([len(p)]) + p.encode("ascii") for p in policy["dns_name"].split(".")
    )
    question += b"\x00\x00\x01\x00\x01"
    require(
        len(query) == 12 + len(question)
        and query[2:12] == b"\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00"
        and query[12:] == question
        and dns_answers(response, int.from_bytes(query[:2], "big"), policy["dns_name"])
        == dns["answers"]
        and type(dns["answers"]) is list
        and bool(dns["answers"])
        and all(
            ip_address(a).version == 4 and ip_address(a).is_global
            for a in dns["answers"]
        ),
        "DNS packet evidence differs",
    )
    require(
        https["peer_ipv4"] in dns["answers"], "WAN peer not in observed DNS answers"
    )
    switch = parse_switch(proof["switch"]["responses"], policy["fedora_mac"])
    require(
        switch == policy["switch_facts"]
        and type(switch["vlan"]) is int
        and switch["forwarding"] is True,
        "Brocade FDB/forwarding differs",
    )
    _window(proof, policy)
    require(
        proof["receipts"] == {key: digest(proof[key]) for key in FACT_FIELDS},
        "guest receipt digests differ",
    )
    return digest(proof)


def _window(proof: dict[str, Any], policy: dict[str, Any]) -> None:
    start, end = _pair(proof["window"]["inner_interval"])
    lower, upper = _pair(proof["window"]["clock_offset_bounds"])
    held_start, held_end = _pair(policy["held_bounds"])
    require(
        held_start <= start < end <= held_end
        and end - start <= policy["max_window_seconds"]
        and lower <= upper
        and upper - lower <= policy["max_clock_uncertainty_seconds"]
        and end - start >= policy["min_traffic_seconds"] + upper - lower,
        "bounded sustained held interval differs",
    )
    before, after = (
        _stamp(proof[k]["sampled_at"]) for k in ("host_before", "host_after")
    )
    require(
        held_start <= before <= start
        and end <= after <= held_end
        and start - before <= policy["max_host_gap_seconds"]
        and after - end <= policy["max_host_gap_seconds"],
        "host reads must bracket held window",
    )
    for stamp in (
        proof["management"]["observed_at"],
        proof["nas"]["observed_at"],
        proof["fedora"]["result"]["https_observed_at"],
        proof["fedora"]["result"]["dns_observed_at"],
        proof["switch"]["observed_at"],
    ):
        require(start <= _stamp(stamp) <= end, "guest evidence escaped held window")
    terminal = proof["generator"]["terminal"]
    require(
        proof["generator"]["status"] in {"passed", "failed"}
        and terminal["stdout_truncated"] is False
        and terminal["stderr_truncated"] is False,
        "finite generator terminal evidence required",
    )
    require(
        type(terminal["stdout_base64"]) is str
        and len(terminal["stdout_base64"]) <= 43692,
        "encoded generator output exceeds bound",
    )
    raw = base64.b64decode(terminal["stdout_base64"], validate=True)
    require(len(raw) <= 32768, "generator output exceeds bound")
    pattern = (
        rb"(?m)^\[([0-9]+\.[0-9]+)\] 64 bytes from "
        + re.escape(policy["gateway_ipv4"].encode("ascii"))
        + rb": icmp_seq=([0-9]+) ttl=[0-9]+ time=((?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+)) ms$"
    )
    replies = [
        (float(m[1]), int(m[2]), float(m[3]))
        for m in re.finditer(pattern, raw)
        if start <= float(m[1]) + lower and float(m[1]) + upper <= end
    ]
    require(
        len(replies) >= 2
        and len({seq for _, seq, _ in replies}) == len(replies)
        and all(a[0] < b[0] and a[1] < b[1] for a, b in zip(replies, replies[1:]))
        and all(math.isfinite(rtt) and rtt >= 0 for _, _, rtt in replies)
        and replies[-1][0] - replies[0][0] >= policy["min_traffic_seconds"],
        "actual sustained useful guest traffic absent",
    )
    activity = proof["activity"]
    require(
        type(activity["successful_replies_in_window"]) is int
        and activity["successful_replies_in_window"] == len(replies)
        and _number(activity["window_seconds"])
        and activity["window_seconds"] == end - start
        and activity["nic5_inner_interval"] == [start, end]
        and activity["guest_to_workstation_offset_bounds"] == [lower, upper]
        and activity["exit_zero_required"] is False,
        "held traffic summary differs",
    )


def validate(
    proof: dict[str, Any],
    *,
    binding: dict[str, Any],
    policy: dict[str, Any],
) -> str:
    """Return the full proof SHA-256 or raise Rejected for malformed/failing facts.

    Receipt digests cover every fact section, including window and activity.
    Policy keys are enumerated in POLICY_FIELDS; no environment defaults apply.
    The production parent must pass its source-pinned policy and trusted boundary
    binding, never a caller-selected policy or proof-derived expected values.
    Malformed JSON, packet data, timestamps and parser rejection fail closed.
    """
    try:
        return _validate(proof, binding, policy)
    except Rejected:
        raise
    except (
        ValueError,
        TypeError,
        KeyError,
        IndexError,
        AttributeError,
        OverflowError,
        binascii.Error,
    ) as error:
        raise Rejected("malformed or rejected guest evidence") from error
