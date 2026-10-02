#!/usr/bin/env bash
set -euo pipefail

export DISPLAY=:0 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus
: "${PVE_CA_FILE:?set PVE_CA_FILE to the private Proxmox CA certificate file}"
export SSL_CERT_FILE=$PVE_CA_FILE
token_secret=$(secret-tool lookup homelab pve-tofu-api-token)
[[ -n $token_secret ]] || { echo 'missing PVE OpenTofu token in desktop keyring' >&2; exit 1; }
export PROXMOX_VE_API_TOKEN="tofu@pve!opentofu=$token_secret"
unset token_secret

python3 - <<'PY'
import json
import os
import ssl
import urllib.error
import urllib.parse
import urllib.request

base = "https://192.168.0.188:8006/api2/json"
context = ssl.create_default_context(cafile=os.environ["SSL_CERT_FILE"])
headers = {"Authorization": f"PVEAPIToken={os.environ['PROXMOX_VE_API_TOKEN']}"}


def request(method, path, params=None):
    query = urllib.parse.urlencode(params or {})
    url = f"{base}{path}" + (f"?{query}" if query else "")
    req = urllib.request.Request(url, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, context=context, timeout=15) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code


if request("GET", "/version") != 200:
    raise SystemExit("API token could not read PVE version")

probes = [
    ("POST", "/pools", {"poolid": "tofu-denied-probe-20261001"}),
    (
        "POST",
        "/storage",
        {
            "storage": "tofu-denied-probe",
            "type": "dir",
            "path": "/nonexistent/tofu-denied-probe",
            "content": "images",
        },
    ),
    ("PUT", "/nodes/pve/network", {"iface": "tofu-denied0"}),
]

for method, path, params in probes:
    status = request(method, path, params)
    if status != 403:
        raise SystemExit(f"expected {method} {path} to be denied with 403, received {status}")

print("PVE API allow/deny probes PASS")
PY

unset PROXMOX_VE_API_TOKEN
