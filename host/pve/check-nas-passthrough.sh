#!/usr/bin/env bash
set -euo pipefail

pve_host=192.168.0.188
device_path=0000:02:00.0
repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)

fail() { printf 'NAS passthrough check: %s\n' "$*" >&2; exit 1; }

check_state() {
  local vm_status=$1 driver=$2 pools=$3

  case $vm_status in
    running)
      [[ $driver == vfio-pci ]] || fail 'running NAS VM does not own the HBA through vfio-pci'
      ;;
    stopped)
      [[ $driver == vfio-pci || $driver == mpt3sas ]] || fail "unexpected stopped-state HBA driver: $driver"
      ;;
    *) fail "unexpected NAS VM state: $vm_status" ;;
  esac

  for pool in tank array; do
    if grep -Fxq "$pool" <<< "$pools"; then
      fail "guest pool $pool is imported by the Proxmox host"
    fi
  done
}

if [[ ${1:-} == validate ]]; then
  [[ $# == 4 ]] || fail 'usage: check-nas-passthrough.sh validate <running|stopped> <driver> <pool-list>'
  check_state "$2" "$3" "$4"
  printf 'NAS passthrough state PASS\n'
  exit 0
fi

[[ $# == 0 ]] || fail 'usage: check-nas-passthrough.sh [validate <running|stopped> <driver> <pool-list>]'
export DISPLAY=:0 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus SSHPASS
SSHPASS=$(secret-tool lookup homelab-pve-host "$pve_host" account root)
[[ -n $SSHPASS ]] || fail 'missing PVE credential in desktop keyring'
pve() { sshpass -e ssh -o ConnectTimeout=10 "root@$pve_host" "$@"; }

bash "$repo_root/host/pve/manage-nas-pci-mapping.sh" check
vm_status=$(pve 'qm status 200' | awk '$1 == "status:" {print $2}')
driver=$(pve "basename \$(readlink -f /sys/bus/pci/devices/$device_path/driver)")
pools=$(pve 'zpool list -H -o name')
check_state "$vm_status" "$driver" "$pools"

printf 'NAS passthrough check PASS: VM 200 %s, HBA driver %s, PVE excludes current and legacy NAS pool names\n' "$vm_status" "$driver"
