#!/usr/bin/env bash
set -euo pipefail
umask 077

mode=${1:-}
[[ $mode == preview || $mode == check || $mode == apply || $mode == test || $mode == pause ]] || {
  echo 'usage: manage-notifications.sh preview|check|apply|test|pause' >&2
  exit 2
}

pve_host=192.168.0.188
endpoint=cloudflare-email
sender=pve-alerts@alerts.kcd.one
smtp_server=smtp.mx.cloudflare.net

export DISPLAY=:0 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus
export SSHPASS
SSHPASS=$(secret-tool lookup homelab-pve-host "$pve_host" account root)
[[ -n $SSHPASS ]] || { echo 'missing PVE credential in desktop keyring' >&2; exit 1; }

token=
if [[ $mode == apply || $mode == test ]]; then
  token=$(secret-tool lookup service cloudflare purpose email-sending account-id 99ce13dde942a39b43e550a7de3962ac)
  [[ -n $token ]] || { echo 'missing Cloudflare Email Sending token in desktop keyring' >&2; exit 1; }
fi

remote_python=$(cat <<'PYEOF'
import http.cookiejar
import json
import os
import socket
import ssl
import sys
import urllib.parse
import urllib.request

mode = sys.argv[1]
payload = json.load(sys.stdin)
host = socket.getfqdn()
base = f"https://{host}:8006/api2/json"
context = ssl.create_default_context(cafile="/etc/pve/pve-root-ca.pem")
cookie_jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(
    urllib.request.HTTPCookieProcessor(cookie_jar),
    urllib.request.HTTPSHandler(context=context),
)

def request(path, method="GET", fields=None, headers=None):
    body = None if fields is None else urllib.parse.urlencode(fields, doseq=True).encode()
    request = urllib.request.Request(
        base + path,
        data=body,
        method=method,
        headers={"Content-Type": "application/x-www-form-urlencoded", **(headers or {})},
    )
    with opener.open(request, timeout=15) as response:
        return json.load(response).get("data")

ticket = request(
    "/access/ticket",
    "POST",
    {"username": "root@pam", "password": payload["pve_password"]},
)
opener.addheaders = [("CSRFPreventionToken", ticket["CSRFPreventionToken"])]
cookie = http.cookiejar.Cookie(
    version=0, name="PVEAuthCookie", value=ticket["ticket"], port=None,
    port_specified=False, domain=host, domain_specified=False,
    domain_initial_dot=False, path="/", path_specified=True,
    secure=True, expires=None, discard=True, comment=None,
    comment_url=None, rest={}, rfc2109=False,
)
cookie_jar.set_cookie(cookie)

endpoint = payload["endpoint"]
current = request("/cluster/notifications/endpoints/smtp")
matcher = request("/cluster/notifications/matchers/default-matcher")
endpoint_current = next((item for item in current if item.get("name") == endpoint), None)
targets = matcher.get("target", [])
if isinstance(targets, str):
    targets = [targets]
desired_targets = list(dict.fromkeys([*targets, endpoint]))
desired = {
    "from-address": payload["sender"],
    "server": payload["server"],
    "port": 465,
    "mode": "tls",
    "username": "api_token",
    "mailto-user": ["root@pam"],
    "disable": 0,
}

if mode == "preview":
    print(json.dumps({
        "endpoint_exists": endpoint_current is not None,
        "endpoint": endpoint,
        "sender": payload["sender"],
        "server": payload["server"],
        "port": 465,
        "tls": True,
        "recipient_user": "root@pam",
        "matcher_targets_before": targets,
        "matcher_targets_after": desired_targets,
        "existing_root_route_preserved": "mail-to-root" in desired_targets,
    }, indent=2))
elif mode == "check":
    if not endpoint_current:
        raise SystemExit("SMTP endpoint is missing")
    actual = request(f"/cluster/notifications/endpoints/smtp/{endpoint}")
    for key, value in desired.items():
        if actual.get(key) != value:
            raise SystemExit(f"SMTP endpoint setting differs: {key}")
    if not all(target in targets for target in ["mail-to-root", endpoint]):
        raise SystemExit("default matcher does not preserve both mail targets")
    print("PVE notification configuration PASS")
elif mode == "apply":
    desired["name"] = endpoint
    desired["password"] = payload["smtp_token"]
    desired["comment"] = "Cloudflare Email Sending for PVE alerts"
    if endpoint_current:
        request(
            f"/cluster/notifications/endpoints/smtp/{endpoint}",
            "PUT",
            desired,
        )
    else:
        request("/cluster/notifications/endpoints/smtp", "POST", desired)
    request(
        "/cluster/notifications/matchers/default-matcher",
        "PUT",
        {"target": desired_targets},
    )
    print("PVE notification endpoint and matcher applied")
elif mode == "test":
    request(f"/cluster/notifications/targets/{endpoint}/test", "POST")
    print("PVE test notification submitted")
elif mode == "pause":
    if endpoint_current:
        request(
            f"/cluster/notifications/endpoints/smtp/{endpoint}",
            "PUT",
            {"disable": 1},
        )
    safe_targets = [target for target in targets if target != endpoint]
    if safe_targets != targets:
        request(
            "/cluster/notifications/matchers/default-matcher",
            "PUT",
            {"target": safe_targets},
        )
    print("PVE SMTP endpoint paused; existing mail-to-root route preserved")
PYEOF
)
remote_python_b64=$(printf '%s' "$remote_python" | base64 -w0)
pve_password=$(secret-tool lookup homelab-pve-host "$pve_host" account root)
[[ -n $pve_password ]] || { echo 'missing PVE credential in desktop keyring' >&2; exit 1; }

payload=$(printf '%s\0%s' "$pve_password" "$token" | python3 -c '
import json, sys
password, token = sys.stdin.buffer.read().split(b"\0", 1)
print(json.dumps({
    "pve_password": password.decode(),
    "smtp_token": token.decode(),
    "endpoint": sys.argv[1],
    "sender": sys.argv[2],
    "server": sys.argv[3],
}))
' "$endpoint" "$sender" "$smtp_server")
unset pve_password token

printf '%s' "$payload" |
  sshpass -e ssh -F /dev/null -o ConnectTimeout=10 -o StrictHostKeyChecking=yes \
    -o UserKnownHostsFile=/home/mpeter/.ssh/known_hosts "root@$pve_host" \
    "python3 -c \"\$(printf '%s' '$remote_python_b64' | base64 -d)\" '$mode'"
