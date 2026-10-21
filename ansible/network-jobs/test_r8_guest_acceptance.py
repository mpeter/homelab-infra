"""Offline R8 held-proof acceptance with independent semantic mutations."""

import base64
import copy
from datetime import datetime, timezone
import json
import struct

import pytest

import active40g_observation as host
import r8_guest_acceptance as validator


def stamp(seconds: float) -> str:
    return datetime.fromtimestamp(seconds, timezone.utc).isoformat()


def host_sample(seconds: float) -> dict:
    return {
        "source_sha256": host.SOURCE_SHA256,
        "hostname": "pve",
        "sampled_at": stamp(seconds),
        "interfaces_sha256": "a" * 64,
        "links": [
            {
                "ifname": dev,
                "mtu": 1500,
                "flags": ["UP"] if dev == "nic0" else ["UP", "LOWER_UP"],
                "operstate": "DOWN" if dev == "nic0" else "UP",
                "master": {"nic0": "bond0", "nic5": "bond0", "bond0": "vmbr0"}.get(dev),
            }
            for dev in host.DEVICES
        ],
        "addresses": [
            {
                "ifname": dev,
                "addr_info": [{"family": "inet", "local": "10.1.0.2", "prefixlen": 24}]
                if dev == "nic1"
                else [],
            }
            for dev in host.DEVICES
        ],
        "routes": [{"dst": "default", "gateway": "10.1.0.1", "dev": "nic1"}],
        "active": "nic5",
        "bond": "Bonding Mode: fault-tolerance (active-backup)\nPrimary Slave: nic0 (primary_reselect always)\nCurrently Active Slave: nic5\nMII Status: up\nMII Polling Interval (ms): 100\nSlave Interface: nic0\nMII Status: down\nLink Failure Count: 3\nSlave Interface: nic5\nMII Status: up\nLink Failure Count: 2\n",
        "members": {
            dev: {
                "carrier": "0" if dev == "nic0" else "1",
                "carrier_changes": "6",
                "carrier_up_count": "3",
                "carrier_down_count": "3",
                **({"speed": "40000"} if dev == "nic5" else {}),
            }
            for dev in ("nic0", "nic5")
        },
        "guests": {"100": "status: running", "200": "status: running"},
    }


def receipts(proof: dict) -> None:
    proof["receipts"] = {
        key: validator.digest(proof[key]) for key in validator.FACT_FIELDS
    }


def synthetic_evidence():
    epoch = 1_800_000_000
    binding = {
        "operation_id": "1" * 64,
        "forward_count": len(validator.trunk_plan.R8_FULL_FORWARD),
        "boundary_observation_sha256": "2" * 64,
        "source_binding_sha256": "3" * 64,
    }
    before = host_sample(epoch)
    mac = "02:00:00:00:00:02"
    policy = {
        "sources": {"host": host.SOURCE_SHA256, "collector": "b" * 64, "dns": "c" * 64},
        "host_helper_sha256": host.SOURCE_SHA256,
        "host_baseline_sha256": validator.digest(host.validate(before)),
        "hostname": "pve",
        "active_member": "nic5",
        "fedora_vm_config_sha256": "d" * 64,
        "fedora_vm_bridge": "vmbr0",
        "pve_name": "pve.lab.example",
        "pve_leaf_sha256": "e" * 64,
        "nas_name": "nas.lab.example",
        "nas_leaf_sha256": "f" * 64,
        "fedora_interface": "eth0",
        "fedora_mac": mac,
        "fedora_ipv4": "10.1.0.3",
        "gateway_ipv4": "10.1.0.1",
        "dns_ipv4": "10.1.0.1",
        "dns_name": "wan.example",
        "wan_url": "https://wan.example/",
        "switch_facts": {"mac": mac, "port": "1/2/8", "vlan": 1, "forwarding": True},
        "held_bounds": [epoch, epoch + 12],
        "max_window_seconds": 12,
        "max_host_gap_seconds": 2,
        "max_clock_uncertainty_seconds": 2,
        "min_traffic_seconds": 3,
    }
    vm = {
        "active": "nic5",
        "interfaces_sha256": "a" * 64,
        "vm100_sha256": "d" * 64,
        "vm100_status": "status: running",
        "vm100_bridge": "vmbr0",
        "vm100_mac": mac,
        "usb_up": True,
        "usb_default": True,
    }
    question = b"\x03wan\x07example\x00\x00\x01\x00\x01"
    response = (
        struct.pack("!6H", 42, 0x8180, 1, 1, 0, 0)
        + question
        + b"\xc0\x0c\x00\x01\x00\x01\x00\x00\x00\x3c\x00\x04\x08\x08\x08\x08"
    )
    dns = {
        "server": "10.1.0.1",
        "port": 53,
        "transport": "UDP",
        "query_name": "wan.example",
        "query_type": "A",
        "status": "NOERROR",
        "cache_disabled": True,
        "answers": ["8.8.8.8"],
        "query_hex": (struct.pack("!6H", 42, 0x100, 1, 0, 0, 0) + question).hex(),
        "response_hex": response.hex(),
    }

    def command(data):
        return {"exit": 0, "stderr": "", "stdout": json.dumps(data)}

    result = {
        "identity": command(
            [
                {
                    "ifname": "eth0",
                    "address": mac,
                    "addr_info": [{"family": "inet", "local": "10.1.0.3"}],
                }
            ]
        ),
        "gateway_route": command(
            [{"dst": "10.1.0.1", "dev": "eth0", "prefsrc": "10.1.0.3"}]
        ),
        "gateway_tcp_443": True,
        "https": {
            "url": "https://wan.example/",
            "status": 200,
            "tls_verified": True,
            "peer_ipv4": "8.8.8.8",
        },
        "dns": copy.deepcopy(dns),
        "https_observed_at": stamp(epoch + 4),
        "dns_observed_at": stamp(epoch + 3),
    }
    raw = "\n".join(
        f"[{epoch + seconds}.000] 64 bytes from 10.1.0.1: icmp_seq={seq} ttl=64 time=0.3 ms"
        for seq, seconds in enumerate((2, 5, 9), 1)
    ).encode()
    proof = {
        **binding,
        "kind": "read-only-active40g",
        "sources": copy.deepcopy(policy["sources"]),
        "selector_used": False,
        "status": "passed",
        "host_before": before,
        "host_after": host_sample(epoch + 12),
        "vm_before": vm,
        "vm_after": copy.deepcopy(vm),
        "management": {
            "name": "pve.lab.example",
            "normal_ca_hostname_verified": True,
            "der_sha256": "e" * 64,
            "observed_at": stamp(epoch + 4),
        },
        "nas": {
            "name": "nas.lab.example",
            "der_sha256": "f" * 64,
            "normal_trust_claimed": False,
            "observed_at": stamp(epoch + 5),
        },
        "fedora": {"result": result},
        "dns": {"result": dns},
        "switch": {
            "observed_at": stamp(epoch + 6),
            "responses": {
                "show mac-address": (
                    "MAC-Address Port Type Index VLAN\n"
                    f"{mac.replace(':', '')[:4]}.{mac.replace(':', '')[4:8]}.{mac.replace(':', '')[8:]} 1/2/8 Dynamic 1 1\n"
                    "Total active entries from all ports = 1"
                ),
                "show interfaces brief": (
                    "Port Link State Dupl Speed Trunk Tag Pvid Pri MAC Name\n"
                    f"1/2/8 Up Forward None 10G None No 1 0 "
                    f"{mac.replace(':', '')[:4]}.{mac.replace(':', '')[4:8]}.{mac.replace(':', '')[8:]} guest"
                ),
            },
        },
        "generator": {
            "status": "passed",
            "terminal": {
                "stdout_truncated": False,
                "stderr_truncated": False,
                "stdout_base64": base64.b64encode(raw).decode(),
            },
        },
        "window": {
            "inner_interval": [epoch + 1, epoch + 11],
            "clock_offset_bounds": [-0.1, 0.1],
        },
        "activity": {
            "successful_replies_in_window": 3,
            "window_seconds": 10,
            "nic5_inner_interval": [epoch + 1, epoch + 11],
            "guest_to_workstation_offset_bounds": [-0.1, 0.1],
            "exit_zero_required": False,
        },
    }
    receipts(proof)
    return proof, binding, policy


@pytest.fixture
def evidence():
    return synthetic_evidence()


def validate(evidence):
    proof, binding, policy = evidence
    return validator.validate(
        proof,
        binding=binding,
        policy=policy,
    )


def test_passing_fixture(evidence):
    assert validate(evidence) == validator.digest(evidence[0])


def test_switch_port_hardware_mac_is_distinct_from_guest_fdb_mac(evidence):
    proof = evidence[0]
    section = proof["switch"]["responses"]
    header, row = section["show interfaces brief"].splitlines()
    fields = row.split()
    fields[9] = "aabb.ccdd.eeff"
    section["show interfaces brief"] = header + "\n" + " ".join(fields)
    receipts(proof)

    assert validate(evidence) == validator.digest(proof)


def test_switch_parser_accepts_repeated_paged_fdb_headers(evidence):
    proof, _, _ = evidence
    table = proof["switch"]["responses"]["show mac-address"]
    header, row, total = table.splitlines()
    proof["switch"]["responses"]["show mac-address"] = "\n".join(
        (header, row, header, header, total)
    )
    brief = proof["switch"]["responses"]["show interfaces brief"]
    brief_header, brief_row = brief.splitlines()
    proof["switch"]["responses"]["show interfaces brief"] = "\n".join(
        (brief_header, brief_row, brief_header, brief_row.replace("1/2/8", "1/2/9"))
    )
    receipts(proof)

    assert validate(evidence) == validator.digest(proof)


def test_switch_parser_rejects_malformed_repeated_interface_header(evidence):
    proof = evidence[0]
    header, row = proof["switch"]["responses"]["show interfaces brief"].splitlines()
    proof["switch"]["responses"]["show interfaces brief"] = "\n".join(
        (header, row, header.replace("Speed", "Bogus"), row)
    )
    receipts(proof)

    with pytest.raises(validator.Rejected, match="interface brief header shape"):
        validate(evidence)


def test_dns_response_must_echo_policy_name(evidence):
    proof, _, policy = evidence
    dns = proof["dns"]["result"]
    with pytest.raises(validator.Rejected, match="question identity"):
        validator.dns_answers(
            bytes.fromhex(dns["response_hex"]),
            int.from_bytes(bytes.fromhex(dns["query_hex"])[:2], "big"),
            policy["dns_name"] + ".invalid",
        )


def test_truncated_dns_response_is_not_accepted(evidence):
    proof, _, policy = evidence
    dns = proof["dns"]["result"]
    response = bytearray.fromhex(dns["response_hex"])
    flags = struct.unpack_from("!H", response, 2)[0]
    struct.pack_into("!H", response, 2, flags | 0x0200)
    with pytest.raises(validator.Rejected, match="response header"):
        validator.dns_answers(
            bytes(response),
            int.from_bytes(bytes.fromhex(dns["query_hex"])[:2], "big"),
            policy["dns_name"],
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("operation_id", "9" * 64),
        ("forward_count", 35),
        ("boundary_observation_sha256", "9" * 64),
        ("source_binding_sha256", "9" * 64),
        ("forward_count", True),
    ],
)
def test_proof_body_binding_mismatch(evidence, field, value):
    evidence[0][field] = value
    with pytest.raises(validator.Rejected, match="binding"):
        validate(evidence)


@pytest.mark.parametrize("section", sorted(validator.FACT_FIELDS))
def test_missing_evidence(evidence, section):
    del evidence[0][section]
    with pytest.raises(validator.Rejected):
        validate(evidence)


@pytest.mark.parametrize("section", sorted(validator.FACT_FIELDS))
def test_receipt_corruption(evidence, section):
    evidence[0]["receipts"][section] = "0" * 64
    with pytest.raises(validator.Rejected, match="receipt"):
        validate(evidence)


@pytest.mark.parametrize(
    "gate",
    [
        "host_before",
        "host_after",
        "active_counter",
        "baseline",
        "vm",
        "usb",
        "pve_trust",
        "pve_name",
        "nas_peer",
        "guest_identity",
        "gateway",
        "wan_tls",
        "wan_peer",
        "dns_packet",
        "dns_claim",
        "fdb",
        "traffic",
        "traffic_cluster",
        "malformed_rtt",
        "selector",
        "source",
        "failure",
    ],
)
def test_independent_semantic_failure_with_fresh_receipts(evidence, gate):
    proof, _, policy = evidence
    if gate in {"host_before", "host_after"}:
        proof[gate]["active"] = "nic0"
    elif gate == "active_counter":
        proof["host_after"]["members"]["nic5"]["carrier_up_count"] = "4"
    elif gate == "baseline":
        policy["host_baseline_sha256"] = "0" * 64
    elif gate == "vm":
        proof["vm_after"]["vm100_sha256"] = "0" * 64
    elif gate == "usb":
        proof["vm_before"]["usb_default"] = proof["vm_after"]["usb_default"] = False
    elif gate == "pve_trust":
        proof["management"]["normal_ca_hostname_verified"] = False
    elif gate == "pve_name":
        proof["management"]["name"] = "wrong.lab.example"
    elif gate == "nas_peer":
        proof["nas"]["der_sha256"] = "0" * 64
    elif gate == "guest_identity":
        proof["fedora"]["result"]["identity"]["exit"] = 1
    elif gate == "gateway":
        proof["fedora"]["result"]["gateway_tcp_443"] = False
    elif gate == "wan_tls":
        proof["fedora"]["result"]["https"]["tls_verified"] = False
    elif gate == "wan_peer":
        proof["fedora"]["result"]["https"]["peer_ipv4"] = "1.1.1.1"
    elif gate in {"dns_packet", "dns_claim"}:
        dns = proof["dns"]["result"]
        dns["response_hex" if gate == "dns_packet" else "server"] = (
            "00" if gate == "dns_packet" else "10.1.0.99"
        )
        proof["fedora"]["result"]["dns"] = copy.deepcopy(dns)
    elif gate == "fdb":
        proof["switch"]["responses"]["show mac-address"] = json.dumps(
            {"mac": policy["fedora_mac"], "type": "Static", "vlan": 1}
        )
    elif gate == "traffic":
        proof["activity"]["successful_replies_in_window"] = 0
    elif gate == "traffic_cluster":
        raw = base64.b64decode(proof["generator"]["terminal"]["stdout_base64"])
        raw = raw.replace(b"1800000005.000", b"1800000002.100").replace(
            b"1800000009.000", b"1800000002.200"
        )
        proof["generator"]["terminal"]["stdout_base64"] = base64.b64encode(raw).decode()
    elif gate == "malformed_rtt":
        raw = base64.b64decode(proof["generator"]["terminal"]["stdout_base64"])
        raw = raw.replace(b"time=0.3 ms", b"time=.. ms")
        proof["generator"]["terminal"]["stdout_base64"] = base64.b64encode(raw).decode()
    elif gate == "selector":
        proof["selector_used"] = True
    elif gate == "source":
        proof["sources"]["collector"] = "0" * 64
    else:
        proof["status"] = "rejected"
    receipts(proof)
    with pytest.raises(validator.Rejected):
        validate(evidence)


@pytest.mark.parametrize(
    "gate",
    [
        "naive",
        "old_guest",
        "late_guest",
        "before_unbracketed",
        "after_unbracketed",
        "outside_held",
        "nan",
        "offset",
        "short",
    ],
)
def test_timestamp_and_window_constraints(evidence, gate):
    proof, _, _ = evidence
    if gate == "naive":
        proof["management"]["observed_at"] = "2027-01-01T00:00:00"
    elif gate in {"old_guest", "late_guest"}:
        proof["management"]["observed_at"] = stamp(
            1_800_000_000 if gate == "old_guest" else 1_800_000_012
        )
    elif gate == "before_unbracketed":
        proof["host_before"]["sampled_at"] = stamp(1_800_000_002)
    elif gate == "after_unbracketed":
        proof["host_after"]["sampled_at"] = stamp(1_800_000_010)
    elif gate == "outside_held":
        proof["window"]["inner_interval"] = [1_799_999_000, 1_800_000_011]
    elif gate == "nan":
        proof["window"]["inner_interval"][0] = float("nan")
    elif gate == "offset":
        proof["window"]["clock_offset_bounds"] = [-1.05, 1.05]
    else:
        proof["window"]["inner_interval"] = [1_800_000_004, 1_800_000_006]
    if gate != "nan":
        receipts(proof)
    with pytest.raises(validator.Rejected):
        validate(evidence)


def test_clock_uncertainty_within_live_observed_range_is_accepted():
    proof, binding, policy = synthetic_evidence()
    proof["window"]["clock_offset_bounds"] = [-0.61, 0.61]
    proof["activity"]["guest_to_workstation_offset_bounds"] = [-0.61, 0.61]
    receipts(proof)

    assert validator.validate(
        proof, binding=binding, policy=policy
    ) == validator.digest(proof)


@pytest.mark.parametrize(
    "field,value",
    [
        ("fedora_vm_config_sha256", "bad"),
        ("held_bounds", [1, 1]),
        ("max_window_seconds", True),
        ("min_traffic_seconds", 0),
        ("pve_name", "localhost"),
        ("fedora_mac", "bad"),
        ("dns_ipv4", "::1"),
        ("sources", {}),
        ("wan_url", "http://wan.example/"),
    ],
)
def test_invalid_policy(evidence, field, value):
    evidence[2][field] = value
    with pytest.raises(validator.Rejected):
        validate(evidence)


def test_full_receipt_facts_not_just_selected_fields(evidence):
    evidence[0]["nas"]["extra_raw_fact"] = "tampered"
    with pytest.raises(validator.Rejected, match="receipt"):
        validate(evidence)


def test_finite_generator_can_finish_failed_with_useful_held_traffic(evidence):
    evidence[0]["generator"]["status"] = "failed"
    receipts(evidence[0])
    assert validate(evidence) == validator.digest(evidence[0])


@pytest.mark.parametrize(
    "section,key,value",
    [
        ("management", "der_sha256", "0" * 64),
        ("nas", "name", "wrong.lab.example"),
        ("nas", "normal_trust_claimed", True),
        ("generator", "status", "running"),
        ("activity", "successful_replies_in_window", True),
    ],
)
def test_additional_identity_and_terminal_gates(evidence, section, key, value):
    evidence[0][section][key] = value
    receipts(evidence[0])
    with pytest.raises(validator.Rejected):
        validate(evidence)


@pytest.mark.parametrize(
    "field,value",
    [
        ("vm100_status", "status: stopped"),
        ("vm100_mac", "02:00:00:00:00:99"),
        ("vm100_bridge", "other"),
        ("usb_up", False),
        ("interfaces_sha256", "0" * 64),
    ],
)
def test_vm_continuity_rejects_even_matching_before_after(evidence, field, value):
    for name in ("vm_before", "vm_after"):
        evidence[0][name][field] = value
    receipts(evidence[0])
    with pytest.raises(validator.Rejected):
        validate(evidence)


@pytest.mark.parametrize(
    "row_key,value", [("port", "1/2/9"), ("link", "Down"), ("state", "Blocked")]
)
def test_switch_semantics(evidence, row_key, value):
    section = evidence[0]["switch"]["responses"]
    header, row = section["show interfaces brief"].splitlines()
    fields = row.split()
    fields[{"port": 0, "link": 1, "state": 2}[row_key]] = value
    section["show interfaces brief"] = header + "\n" + " ".join(fields)
    receipts(evidence[0])
    with pytest.raises(validator.Rejected):
        validate(evidence)


@pytest.mark.parametrize(
    "key,value",
    [
        ("stdout_truncated", True),
        ("stderr_truncated", True),
        ("stdout_base64", "%%%"),
        ("stdout_base64", "A" * 43696),
    ],
)
def test_terminal_corruption(evidence, key, value):
    evidence[0]["generator"]["terminal"][key] = value
    receipts(evidence[0])
    with pytest.raises(validator.Rejected):
        validate(evidence)


def test_unknown_policy_field_rejected(evidence):
    evidence[2]["historical_pin"] = "0" * 64
    with pytest.raises(validator.Rejected, match="policy"):
        validate(evidence)


def test_binding_itself_must_be_current_r8_count(evidence):
    evidence[0]["forward_count"] = evidence[1]["forward_count"] = 35
    with pytest.raises(validator.Rejected, match="count"):
        validate(evidence)


def test_active_speed_failure(evidence):
    evidence[0]["host_after"]["members"]["nic5"]["speed"] = "10000"
    receipts(evidence[0])
    with pytest.raises(validator.Rejected):
        validate(evidence)
