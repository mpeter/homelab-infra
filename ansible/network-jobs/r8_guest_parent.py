"""Fixed current-source inputs for R8 held guest qualification."""

from __future__ import annotations

import base64
from collections.abc import Callable
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import time
from typing import Any

import active40g_observation as host
import r8_current_observation as switch_observation
import r8_guest_acceptance as acceptance
import r8_guest_producer as guest_producer
import r8_guest_generator

PVE_ADDRESS = "10.72.10.10"
PVE_HOST_KEY_ALIAS = "192.168.0.188"
PVE_NAME = "pve01.lab.kcd.one"
PVE_LEAF_SHA256 = "9c85c50036a70ab8250cefa2518f2f0175475be24793e3edad7b419aabfb9574"
NAS_ADDRESS = "192.168.0.186"
NAS_NAME = "nas01.lab.kcd.one"
NAS_LEAF_SHA256 = "450d80068423e23d45dcaab1d1c694d4fbbd32dfab7b73c83bc731c65155306b"
VM100_SHA256 = "c17a5ef1768cf7c4a9ae1f5fd2578d4a93013b4c1b9f4ea9dd0ee7aab029b41b"
FEDORA_MAC = "bc:24:11:f0:d6:4d"
FEDORA_IPV4 = "192.168.0.114"
GATEWAY_IPV4 = "192.168.0.1"
PVE_GATEWAY_IPV4 = "10.72.10.1"
WAN_URL = "https://example.com/"
SOURCE = Path(__file__).resolve()
SOURCE_SHA256 = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
HOST_SOURCE_SHA256 = host.SOURCE_SHA256
MAX_OUTPUT = 65536


class Rejected(RuntimeError):
    """A fixed R8 source or current environment input failed its contract."""


def _remaining(deadline: float) -> float:
    value = deadline - time.monotonic()
    if value <= 0:
        raise TimeoutError("R8 parent deadline expired")
    return value


def pve_credential() -> str:
    """Read the existing PVE root credential without placing it in arguments."""
    env = os.environ.copy()
    env.update(
        {
            "DISPLAY": ":0",
            "DBUS_SESSION_BUS_ADDRESS": "unix:path=/run/user/1000/bus",
        }
    )
    result = subprocess.run(
        [
            "secret-tool",
            "lookup",
            "homelab-pve-host",
            PVE_HOST_KEY_ALIAS,
            "account",
            "root",
        ],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        timeout=5,
        check=False,
        env=env,
    )
    if result.returncode != 0 or result.stderr:
        raise Rejected("PVE keyring credential unavailable")
    value = result.stdout.decode("utf-8").rstrip("\n")
    if not value:
        raise Rejected("PVE keyring credential unavailable")
    return value


def _pve_script(script: bytes, deadline: float, credential: str) -> bytes:
    remaining = _remaining(deadline)
    known_hosts = Path.home() / ".ssh/known_hosts"
    if (
        not known_hosts.is_file()
        or known_hosts.is_symlink()
        or known_hosts.resolve() != known_hosts
    ):
        raise Rejected("pinned PVE known-hosts file unavailable")
    env = os.environ.copy()
    env["SSHPASS"] = credential
    env.pop("DISPLAY", None)
    env.pop("DBUS_SESSION_BUS_ADDRESS", None)
    command = [
        "sshpass",
        "-e",
        "ssh",
        "-F",
        "/dev/null",
        "-T",
        "-o",
        "BatchMode=no",
        "-o",
        "PreferredAuthentications=password",
        "-o",
        "HostKeyAlias=" + PVE_HOST_KEY_ALIAS,
        "-o",
        "UserKnownHostsFile=" + str(known_hosts),
        "-o",
        "GlobalKnownHostsFile=/dev/null",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        "ConnectTimeout=8",
        "-o",
        "ConnectionAttempts=1",
        "-o",
        "ControlMaster=no",
        "-o",
        "ControlPath=none",
        "root@" + PVE_ADDRESS,
        "python3 -I -B -",
    ]
    result = subprocess.run(
        command,
        input=script,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=remaining,
        check=False,
        env=env,
    )
    if (
        result.returncode != 0
        or result.stderr
        or not result.stdout
        or len(result.stdout) > MAX_OUTPUT
        or time.monotonic() >= deadline
    ):
        raise Rejected("pinned PVE read failed its bounded contract")
    return result.stdout


def _remote_parent_script() -> bytes:
    raw = Path(host.__file__).read_bytes()
    if hashlib.sha256(raw).hexdigest() != HOST_SOURCE_SHA256:
        raise Rejected("active40G helper source drift")
    source = raw.decode("utf-8")
    needle = "SOURCE_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()"
    if source.count(needle) != 1:
        raise Rejected("active40G helper source shape differs")
    source = source.replace(needle, "SOURCE_SHA256 = " + repr(HOST_SOURCE_SHA256))
    raw = source.encode()
    encoded = base64.b64encode(raw).decode("ascii")
    remote_sha256 = hashlib.sha256(raw).hexdigest()
    return (
        "import base64,hashlib,json,pathlib,types\n"
        f"raw=base64.b64decode({encoded!r},validate=True)\n"
        f"expected={remote_sha256!r}\n"
        "if hashlib.sha256(raw).hexdigest()!=expected:raise SystemExit(2)\n"
        "module=types.ModuleType('active40g_observation')\n"
        "module.__file__='/tmp/active40g_observation.py'\n"
        "exec(compile(raw,module.__file__,'exec'),module.__dict__)\n"
        "sample=module.collect()\n"
        "config=pathlib.Path('/etc/pve/qemu-server/100.conf').read_bytes()\n"
        "net=next(line.split(':',1)[1].strip() for line in config.decode().splitlines() if line.startswith('net0:'))\n"
        "vm={'vm100_sha256':hashlib.sha256(config).hexdigest(),'vm100_status':sample['guests']['100'],'net0':net}\n"
        "print(json.dumps({'host':sample,'vm':vm},separators=(',',':')))\n"
    ).encode()


def _vm_facts(host_sample: dict[str, Any], vm: dict[str, Any]) -> dict[str, Any]:
    if vm["vm100_sha256"] != VM100_SHA256 or vm["vm100_status"] != "status: running":
        raise Rejected("Fedora VM 100 differs from the current accepted source")
    network = dict(part.split("=", 1) for part in vm["net0"].split(","))
    links = {item["ifname"]: item for item in host_sample["links"]}
    addresses = {item["ifname"]: item for item in host_sample["addresses"]}
    routes = host_sample["routes"]
    nic1_ipv4 = {
        item["local"]
        for item in addresses["nic1"].get("addr_info", [])
        if item.get("family") == "inet"
    }
    return {
        "active": host_sample["active"],
        "interfaces_sha256": host_sample["interfaces_sha256"],
        "vm100_sha256": vm["vm100_sha256"],
        "vm100_status": vm["vm100_status"],
        "vm100_bridge": network["bridge"],
        "vm100_mac": network["virtio"].lower(),
        "usb_up": "UP" in links["nic1"]["flags"] and PVE_ADDRESS in nic1_ipv4,
        "usb_default": bool(routes)
        and routes[0].get("dev") == "nic1"
        and routes[0].get("gateway") == PVE_GATEWAY_IPV4,
    }


def _remote_vm_script() -> bytes:
    return b"""import hashlib,json,pathlib,subprocess
config=pathlib.Path("/etc/pve/qemu-server/100.conf").read_bytes()
status=subprocess.run(["qm","status","100"],capture_output=True,text=True,timeout=5,check=True).stdout.strip()
net=next(line.split(":",1)[1].strip() for line in config.decode().splitlines() if line.startswith("net0:"))
print(json.dumps({"vm100_sha256":hashlib.sha256(config).hexdigest(),"vm100_status":status,"net0":net},separators=(",",":")))
"""


def _json_object(raw: bytes | dict[str, Any], name: str) -> dict[str, Any]:
    if type(raw) is dict:
        return raw
    if type(raw) is not bytes:
        raise Rejected(name + " JSON bytes or object required")
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise Rejected(name + " JSON response malformed") from error
    if type(value) is not dict:
        raise Rejected(name + " JSON object required")
    return value


def _tls_leaf(
    address: str, name: str, port: int, *, verify: bool, deadline: float
) -> dict[str, Any]:
    remaining = min(8.0, _remaining(deadline))
    context = (
        ssl.create_default_context() if verify else ssl._create_unverified_context()
    )
    try:
        with socket.create_connection((address, port), timeout=remaining) as raw:
            raw.settimeout(remaining)
            with context.wrap_socket(raw, server_hostname=name) as connection:
                certificate = connection.getpeercert(binary_form=True)
                if not certificate:
                    raise Rejected("management TLS leaf missing")
    except (OSError, ssl.SSLError) as error:
        raise Rejected("management TLS endpoint unavailable or invalid") from error
    if time.monotonic() >= deadline:
        raise TimeoutError("management TLS collector exceeded deadline")
    result: dict[str, Any] = {
        "name": name,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "der_sha256": hashlib.sha256(certificate).hexdigest(),
    }
    if verify:
        result["normal_ca_hostname_verified"] = True
    else:
        result["normal_trust_claimed"] = False
    return result


class R8GuestParent:
    """Bind fixed, current collectors and acceptance policy to one R8 run."""

    def __init__(
        self,
        pin: Path,
        runtime: Path,
        expected_startup: tuple[str, ...],
        audit_credential_provider: Callable[[], str],
        pve_credential_provider: Callable[[], str] = pve_credential,
    ) -> None:
        self.pin = pin
        self.runtime = runtime
        self.expected_startup = expected_startup
        self.audit_credential_provider = audit_credential_provider
        self.pve_credential_provider = pve_credential_provider
        self._pve_credential: str | None = None
        self._pending_vm: tuple[float, dict[str, Any]] | None = None

    def _credential(self) -> str:
        if self._pve_credential is None:
            self._pve_credential = self.pve_credential_provider()
        return self._pve_credential

    def _host(self, deadline: float) -> dict[str, Any]:
        self._pending_vm = None
        sample = _json_object(
            _pve_script(_remote_parent_script(), deadline, self._credential()),
            "PVE parent",
        )
        if set(sample) != {"host", "vm"}:
            raise Rejected("paired PVE host and VM sample required")
        host_sample = _json_object(sample["host"], "PVE host")
        vm_sample = _json_object(sample["vm"], "PVE VM")
        self._pending_vm = (time.monotonic(), _vm_facts(host_sample, vm_sample))
        return host_sample

    def _vm(self, deadline: float) -> dict[str, Any]:
        pending, self._pending_vm = self._pending_vm, None
        if pending is None or time.monotonic() - pending[0] > 2:
            raise Rejected("paired PVE host sample required")
        if time.monotonic() >= deadline:
            raise TimeoutError("paired PVE host sample exceeded deadline")
        return pending[1]

    def _switch(self, deadline: float) -> dict[str, Any]:
        _remaining(deadline)
        evidence = switch_observation.observe(
            self.pin,
            self.runtime,
            self.expected_startup,
            self.audit_credential_provider,
            deadline=deadline,
        )
        if time.monotonic() >= deadline:
            raise TimeoutError("Brocade guest observation exceeded deadline")
        return {
            "observed_at": evidence["observed_at"],
            "responses": evidence["responses"],
        }

    def _sources(self, deadline: float) -> dict[str, str]:
        _remaining(deadline)
        paths = {
            "parent": SOURCE,
            "host": Path(host.__file__),
            "switch": Path(switch_observation.__file__),
            "acceptance": Path(acceptance.__file__),
            "producer": Path(guest_producer.__file__),
            "generator": Path(r8_guest_generator.__file__),
        }
        result = {
            key: hashlib.sha256(path.read_bytes()).hexdigest()
            for key, path in paths.items()
        }
        for name, path in switch_observation.SOURCE_PATHS.items():
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual != switch_observation.SOURCE_SHA256[name]:
                raise Rejected("R8 switch observer source drift")
            result["switch_" + name] = actual
        for name, expected in r8_guest_generator.SOURCE_PINS.items():
            path = r8_guest_generator.ROOT / name
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual != expected:
                raise Rejected("R8 guest generator source drift")
            result["guest_" + name.replace("-", "_")] = actual
        if result["host"] != HOST_SOURCE_SHA256:
            raise Rejected("active40G helper source drift")
        return result

    def prepare(
        self, deadline: float | None = None
    ) -> tuple[guest_producer.Producer, dict[str, Any]]:
        """Collect the fixed preflight baseline and return the only R8 proof pair."""
        deadline = min(deadline or float("inf"), time.monotonic() + 45)
        sources = self._sources(deadline)
        host_sample = self._host(deadline)
        baseline = host.validate(host_sample, acknowledged_active_changes=0)
        vm = self._vm(deadline)
        if (
            host_sample["hostname"] != "pve"
            or host_sample["active"] != "nic5"
            or vm["active"] != "nic5"
            or vm["interfaces_sha256"] != baseline["interfaces_sha256"]
            or vm["vm100_bridge"] != "vmbr0"
            or vm["vm100_mac"] != FEDORA_MAC
            or not vm["usb_up"]
            or not vm["usb_default"]
        ):
            raise Rejected("R8 host, guest or USB management preflight differs")
        now = time.time()
        policy = {
            "sources": sources,
            "host_helper_sha256": HOST_SOURCE_SHA256,
            "host_baseline_sha256": acceptance.digest(baseline),
            "hostname": "pve",
            "active_member": "nic5",
            "fedora_vm_config_sha256": VM100_SHA256,
            "fedora_vm_bridge": "vmbr0",
            "pve_name": PVE_NAME,
            "pve_leaf_sha256": PVE_LEAF_SHA256,
            "nas_name": NAS_NAME,
            "nas_leaf_sha256": NAS_LEAF_SHA256,
            "fedora_interface": "eth0",
            "fedora_mac": FEDORA_MAC,
            "fedora_ipv4": FEDORA_IPV4,
            "gateway_ipv4": GATEWAY_IPV4,
            "dns_ipv4": GATEWAY_IPV4,
            "dns_name": "example.com",
            "wan_url": WAN_URL,
            "switch_facts": {
                "mac": FEDORA_MAC,
                "port": "1/2/6",
                "vlan": 1,
                "forwarding": True,
            },
            "held_bounds": [now - 5, now + 1800],
            "max_window_seconds": 10,
            "max_host_gap_seconds": 15,
            "max_clock_uncertainty_seconds": 2,
            "min_traffic_seconds": 3,
        }
        acceptance._policy(policy)
        collectors = guest_producer.Collectors(
            sources=self._sources,
            host=self._host,
            vm=self._vm,
            management=lambda deadline: _tls_leaf(
                PVE_ADDRESS, PVE_NAME, 8006, verify=True, deadline=deadline
            ),
            nas=lambda deadline: _tls_leaf(
                NAS_ADDRESS, NAS_NAME, 443, verify=False, deadline=deadline
            ),
            fedora=r8_guest_generator.collect_network,
            switch=self._switch,
        )
        producer = guest_producer.Producer.with_fixed_generator(collectors)
        return producer, policy
