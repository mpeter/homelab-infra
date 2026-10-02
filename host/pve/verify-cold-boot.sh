#!/usr/bin/env bash
set -euo pipefail

# Run from the break-glass workstation in an isolated tmux session.
mode=${1:-run}
[[ $mode == run || $mode == preflight ]] || { echo 'usage: verify-cold-boot.sh [preflight|run]' >&2; exit 2; }
pve_host=192.168.0.188
idrac_url=https://192.168.0.80
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
export DISPLAY=:0 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus
export SSHPASS
SSHPASS=$(secret-tool lookup homelab-pve-host "$pve_host" account root)
idrac_password=$(secret-tool lookup homelab-idrac-host 192.168.0.80 account root)
[[ -n $SSHPASS && -n $idrac_password ]] || { echo 'missing keyring credential' >&2; exit 1; }

pve() { sshpass -e ssh -o ConnectTimeout=10 "root@$pve_host" "$@"; }
idrac() {
  printf 'user = "root:%s"\n' "$idrac_password" |
    curl -skS --max-time 15 -K - "$@"
}
power_state() {
  idrac "$idrac_url/redfish/v1/Systems/System.Embedded.1" | jq -r .PowerState
}
fail() { printf 'cold-boot verification failed: %s\n' "$*" >&2; exit 1; }
vm_state() {
  pve 'qm list' | awk 'NR > 1 && $1 ~ /^[0-9]+$/ {print $1, $2, $3}' | sort
}
require_vm_state() {
  local expected=$1
  [[ $(vm_state) == "$expected" ]] || fail "VM roster differs; expected: ${expected//$'\n'/, }"
  [[ -z $(pve 'pct list' | awk 'NR > 1 && NF {print $1}') ]] || fail 'a container is present'
}

[[ $(power_state) == On ]] || fail 'iDRAC does not report power on before test'
before=$(pve 'cat /proc/sys/kernel/random/boot_id')
require_vm_state $'100 fedora-dev running\n200 nas stopped'
[[ $(pve 'qm config 100') == *$'onboot: 1'* ]] || fail 'Fedora VM is not configured to restart after boot'
[[ $(pve 'qm config 200') == *$'onboot: 0'* ]] || fail 'NAS VM must remain stopped during host recovery test'
[[ $(pve 'zpool list -H -o health rpool fast-vm') == $'ONLINE\nONLINE' ]] || fail 'pool not healthy'
pve 'bash -s' < "$script_dir/check-fast-vm.sh"
bash "$script_dir/check-nas-passthrough.sh"
printf 'preflight boot ID: %s\n' "$before"
[[ $mode == preflight ]] && exit 0

timeout 20s sshpass -e ssh -o ConnectTimeout=10 "root@$pve_host" 'systemctl poweroff' || true
for attempt in {1..90}; do
  [[ $(power_state) == Off ]] && break
  sleep 5
done
[[ $(power_state) == Off ]] || fail 'iDRAC did not confirm power off; no power-on action sent'
echo 'iDRAC confirmed power off'

code=$(idrac -o /dev/null -w '%{http_code}' -X POST -H 'Content-Type: application/json' \
  -d '{"ResetType":"On"}' \
  "$idrac_url/redfish/v1/Systems/System.Embedded.1/Actions/ComputerSystem.Reset")
[[ $code == 204 ]] || fail "iDRAC power-on returned HTTP $code"

after=
for attempt in {1..120}; do
  after=$(pve 'cat /proc/sys/kernel/random/boot_id' 2>/dev/null || true)
  [[ -n $after && $after != "$before" ]] && break
  sleep 5
done
[[ -n $after && $after != "$before" ]] || fail 'no new PVE boot ID observed'
[[ $(power_state) == On ]] || fail 'iDRAC does not report power on after boot'
[[ $(pve 'zpool list -H -o health rpool fast-vm') == $'ONLINE\nONLINE' ]] || fail 'pool not healthy after boot'
pve 'bash -s' < "$script_dir/check-fast-vm.sh"
require_vm_state $'100 fedora-dev running\n200 nas stopped'
bash "$script_dir/check-nas-passthrough.sh"
pve 'pvesm status; systemctl --failed --no-legend; proxmox-boot-tool status'
printf 'cold boot PASS: %s -> %s\n' "$before" "$after"
