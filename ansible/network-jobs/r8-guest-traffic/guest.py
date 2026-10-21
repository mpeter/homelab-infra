"""Finite guest traffic after accepted identity and route checks."""

import base64
from datetime import datetime, timezone
import http.client
import json
import secrets
import socket
import ssl
import struct
import subprocess
import sys
import time
from urllib.parse import urlsplit

SOURCE = "192.168.0.114"
MAC = "bc:24:11:f0:d6:4d"
GATEWAY = "192.168.0.1"
DNS_NAME = "example.com"
WAN_URL = "https://example.com/"


def stamp():
    return datetime.now(timezone.utc).isoformat()


def remaining(deadline):
    value = deadline - time.monotonic()
    if value <= 0:
        raise RuntimeError("guest traffic deadline expired")
    return value


def command_record(argv, deadline):
    result = subprocess.run(
        argv, capture_output=True, timeout=min(5, remaining(deadline)), check=False
    )
    if len(result.stdout) > 32768 or len(result.stderr) > 4096:
        raise RuntimeError("guest probe command exceeded its output bound")
    return {
        "exit": result.returncode,
        "stdout": result.stdout.decode("utf-8", errors="strict"),
        "stderr": result.stderr.decode("utf-8", errors="strict"),
    }


def identity(deadline):
    identity_result = command_record(
        ["ip", "-j", "address", "show", "dev", "eth0"], deadline
    )
    if identity_result["exit"] or identity_result["stderr"]:
        raise RuntimeError("Fedora identity command failed")
    records = json.loads(identity_result["stdout"])
    if not (
        isinstance(records, list)
        and len(records) == 1
        and records[0].get("ifname") == "eth0"
        and records[0].get("address", "").lower() == MAC
        and SOURCE
        in [
            a.get("local")
            for a in records[0].get("addr_info", [])
            if a.get("family") == "inet"
        ]
    ):
        raise RuntimeError("accepted Fedora identity absent")
    route_get_result = command_record(
        ["ip", "-j", "-4", "route", "get", GATEWAY, "from", SOURCE], deadline
    )
    if route_get_result["exit"] or route_get_result["stderr"]:
        raise RuntimeError("Fedora gateway route lookup failed")
    route_get = json.loads(route_get_result["stdout"])
    if not (
        isinstance(route_get, list)
        and len(route_get) == 1
        and route_get[0].get("dst") == GATEWAY
        and route_get[0].get("from") == SOURCE
        and route_get[0].get("dev") == "eth0"
    ):
        raise RuntimeError("Fedora gateway route lookup differs")
    default_result = command_record(
        ["ip", "-j", "-4", "route", "show", "default"], deadline
    )
    if default_result["exit"] or default_result["stderr"]:
        raise RuntimeError("Fedora default route command failed")
    defaults = json.loads(default_result["stdout"])
    if not (
        isinstance(defaults, list)
        and len(defaults) == 1
        and defaults[0].get("dst") == "default"
        and defaults[0].get("gateway") == GATEWAY
        and defaults[0].get("dev") == "eth0"
        and defaults[0].get("prefsrc") == SOURCE
    ):
        raise RuntimeError("Fedora default route identity differs")
    route_result = {
        "exit": 0,
        "stdout": json.dumps(
            [
                {
                    "dst": route_get[0]["dst"],
                    "dev": defaults[0]["dev"],
                    "gateway": defaults[0]["gateway"],
                    "prefsrc": defaults[0]["prefsrc"],
                }
            ],
            separators=(",", ":"),
        ),
        "stderr": "",
    }
    return identity_result, route_result


def _dns_question(name, transaction):
    labels = name.encode("ascii").split(b".")
    question = b"".join(bytes((len(label),)) + label for label in labels)
    question += b"\0\0\1\0\1"
    return struct.pack("!HHHHHH", transaction, 0x0100, 1, 0, 0, 0) + question


def _dns_answers(packet, transaction, name):
    if not 12 <= len(packet) <= 4096:
        raise RuntimeError("DNS response size differs")
    ident, flags, questions, answers, authorities, additional = struct.unpack_from(
        "!6H", packet
    )
    if (
        ident != transaction
        or flags & 0x8000 == 0
        or flags & 0x7800
        or flags & 0x0200
        or flags & 0x000F
        or questions != 1
        or answers > 128
        or authorities > 128
        or additional > 128
    ):
        raise RuntimeError("DNS response header differs")

    def read_name(offset):
        labels, cursor, end, visited = [], offset, None, set()
        while True:
            if cursor >= len(packet) or cursor in visited:
                raise RuntimeError("DNS name bounds or pointer loop")
            visited.add(cursor)
            size = packet[cursor]
            if size & 0xC0 == 0xC0:
                if cursor + 1 >= len(packet):
                    raise RuntimeError("DNS pointer bounds")
                pointer = ((size & 0x3F) << 8) | packet[cursor + 1]
                if pointer >= len(packet):
                    raise RuntimeError("DNS pointer target")
                if end is None:
                    end = cursor + 2
                cursor = pointer
                continue
            if size & 0xC0 or size > 63:
                raise RuntimeError("DNS label encoding")
            cursor += 1
            if size == 0:
                return b".".join(labels).decode("ascii").lower(), (
                    cursor if end is None else end
                )
            if cursor + size > len(packet):
                raise RuntimeError("DNS label bounds")
            labels.append(packet[cursor : cursor + size])
            cursor += size

    question_name, cursor = read_name(12)
    if cursor + 4 > len(packet):
        raise RuntimeError("DNS question bounds")
    qtype, qclass = struct.unpack_from("!HH", packet, cursor)
    if (question_name, qtype, qclass) != (name, 1, 1):
        raise RuntimeError("DNS question identity differs")
    cursor += 4
    addresses = []
    for index in range(answers + authorities + additional):
        owner, cursor = read_name(cursor)
        if cursor + 10 > len(packet):
            raise RuntimeError("DNS record bounds")
        rtype, rclass, _ttl, size = struct.unpack_from("!HHIH", packet, cursor)
        cursor += 10
        if cursor + size > len(packet):
            raise RuntimeError("DNS record data bounds")
        if index < answers and rtype == 1 and rclass == 1:
            if owner != name or size != 4:
                raise RuntimeError("DNS A answer shape differs")
            addresses.append(
                socket.inet_ntop(socket.AF_INET, packet[cursor : cursor + 4])
            )
        cursor += size
    if cursor != len(packet) or not addresses:
        raise RuntimeError("DNS response has no complete A answer")
    return addresses


def network_probe(deadline):
    identity_result, route_result = identity(deadline)
    now = stamp()
    with socket.create_connection((GATEWAY, 443), timeout=min(5, remaining(deadline))):
        gateway_tcp_443 = True

    transaction = secrets.randbelow(65536)
    query = _dns_question(DNS_NAME, transaction)
    request = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    request.settimeout(min(5, remaining(deadline)))
    try:
        request.sendto(query, (GATEWAY, 53))
        response, peer = request.recvfrom(4097)
    finally:
        request.close()
    if peer != (GATEWAY, 53):
        raise RuntimeError("DNS responder differs")
    answers = _dns_answers(response, transaction, DNS_NAME)
    dns_observed_at = stamp()

    url = urlsplit(WAN_URL)
    connection = http.client.HTTPSConnection(
        url.hostname,
        url.port or 443,
        timeout=min(8, remaining(deadline)),
        context=ssl.create_default_context(),
    )
    try:
        connection.request("GET", url.path or "/")
        response_http = connection.getresponse()
        status = response_http.status
        peer_ip = connection.sock.getpeername()[0]
        response_http.read(1)
    finally:
        connection.close()
    https_observed_at = stamp()
    return {
        "fedora": {
            "observed_at": now,
            "result": {
                "identity": identity_result,
                "gateway_route": route_result,
                "gateway_tcp_443": gateway_tcp_443,
                "https": {
                    "url": WAN_URL,
                    "status": status,
                    "tls_verified": True,
                    "peer_ipv4": peer_ip,
                },
                "https_observed_at": https_observed_at,
                "dns": {
                    "server": GATEWAY,
                    "port": 53,
                    "transport": "UDP",
                    "query_name": DNS_NAME,
                    "query_type": "A",
                    "status": "NOERROR",
                    "cache_disabled": True,
                    "query_hex": query.hex(),
                    "response_hex": response.hex(),
                    "answers": answers,
                },
                "dns_observed_at": dns_observed_at,
            },
        },
        "dns": {
            "observed_at": dns_observed_at,
            "result": {
                "server": GATEWAY,
                "port": 53,
                "transport": "UDP",
                "query_name": DNS_NAME,
                "query_type": "A",
                "status": "NOERROR",
                "cache_disabled": True,
                "query_hex": query.hex(),
                "response_hex": response.hex(),
                "answers": answers,
            },
        },
    }


def traffic(deadline, emit):
    identity(deadline)
    remaining(deadline)
    process = subprocess.Popen(
        [
            "ping",
            "-D",
            "-n",
            "-I",
            SOURCE,
            "-i",
            "1",
            "-c",
            "120",
            "-w",
            "120",
            "-W",
            "1",
            GATEWAY,
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    timed_out = False
    started = process.poll() is None
    try:
        try:
            remaining(deadline)
            if started:
                emit(
                    {
                        "status": "traffic_started",
                        "pid": process.pid,
                        "observed_at": stamp(),
                    }
                )
            stdout, stderr = process.communicate(timeout=remaining(deadline))
        except (subprocess.TimeoutExpired, RuntimeError):
            timed_out = True
            process.kill()
            stdout, stderr = process.communicate(timeout=2)
        record = {
            "status": "traffic_complete"
            if started and process.returncode == 0 and not timed_out
            else "traffic_failed",
            "pid": process.pid,
            "observed_at": stamp(),
            "returncode": process.returncode,
            "timed_out": timed_out,
            "stdout_bytes": len(stdout),
            "stderr_bytes": len(stderr),
            "stdout_truncated": len(stdout) > 32768,
            "stderr_truncated": len(stderr) > 4096,
            "stdout_base64": base64.b64encode(stdout[:32768]).decode(),
            "stderr_base64": base64.b64encode(stderr[:4096]).decode(),
        }
        emit(record)
        return (
            0
            if record["status"] == "traffic_complete"
            and not record["stdout_truncated"]
            and not record["stderr_truncated"]
            else 1
        )
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate(timeout=2)


if __name__ == "__main__":

    def emit(record):
        print(json.dumps(record, separators=(",", ":")), flush=True)

    try:
        if sys.argv[1:] == ["probe"]:
            emit(network_probe(time.monotonic() + 20))
            raise SystemExit(0)
        if sys.argv[1:]:
            raise RuntimeError("unsupported guest operation")
        raise SystemExit(traffic(time.monotonic() + 125, emit))
    except Exception as error:
        emit(
            {
                "status": "traffic_rejected",
                "observed_at": stamp(),
                "reason": str(error)[:1024],
            }
        )
        raise SystemExit(1)
