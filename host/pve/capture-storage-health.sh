#!/usr/bin/env bash
set -euo pipefail

if [[ $# != 0 ]]; then
  echo 'usage: capture-storage-health.sh' >&2
  exit 2
fi

fail() { printf 'storage evidence capture: %s\n' "$*" >&2; exit 1; }
for command_name in awk cat pvesm smartctl systemctl zfs zpool; do
  command -v "$command_name" >/dev/null || fail "missing required command: $command_name"
done

add_device() {
  local candidate=$1 existing
  for existing in "${devices[@]}"; do
    [[ $existing == "$candidate" ]] && return
  done
  devices+=("$candidate")
}

printf 'Read-only PVE storage evidence. smartctl bits 0x07 are acquisition errors and bits 0xf8 are SMART status/log findings. Exit 1 means acquisition error, 2 means status/log finding, and 3 means both; other command failures stop the capture. Pool health is reported separately. No capacity thresholds are evaluated and no failure procedure is exercised.\n'

devices=()
for pool in rpool fast-vm scratch; do
  printf '\n== %s capacity (bytes) ==\n' "$pool"
  zpool list -Hp -o name,size,alloc,free,capacity,health "$pool"

  printf '\n== %s topology, errors, and scrub state ==\n' "$pool"
  status=$(zpool status -P -v "$pool")
  printf '%s\n' "$status"
  members=$(awk '$1 ~ /^\/dev\/disk\/by-id\// { print $1 }' <<< "$status")
  [[ -n $members ]] || fail "no persistent device paths found for $pool"
  while IFS= read -r member; do
    add_device "${member%-part[0-9]*}"
  done <<< "$members"

  printf '\n== %s dataset usage and quotas ==\n' "$pool"
  zfs list -H -p -r -o name,used,avail,quota,refquota "$pool"
done

add_device /dev/disk/by-id/ata-KINGSTON_SUV400S37240G_50026B7767031A82

printf '\n== Proxmox storage usage ==\n'
pvesm status

printf '\n== Periodic scrub configuration ==\n'
cat /etc/cron.d/zfsutils-linux

printf '\n== SMART monitoring configuration ==\n'
if smartd_state=$(systemctl is-active smartd); then
  printf 'smartd service: %s\n' "$smartd_state"
else
  status=$?
  printf 'smartd service: %s (systemctl exit %s)\n' "$smartd_state" "$status"
fi
cat /etc/smartd.conf

smart_collection_failures=0
smart_status_findings=0
for device in "${devices[@]}"; do
  printf '\n== SMART details: %s ==\n' "$device"
  if smartctl -x "$device"; then
    smart_status=0
  else
    smart_status=$?
  fi
  printf 'smartctl exit status: %s\n' "$smart_status"
  collection_error_bits=$((smart_status & 7))
  status_finding_bits=$((smart_status & 248))
  printf 'SMART collection error bits: %s\n' "$collection_error_bits"
  printf 'SMART status/log finding bits: %s\n' "$status_finding_bits"
  smart_collection_failures=$((smart_collection_failures | collection_error_bits))
  smart_status_findings=$((smart_status_findings | status_finding_bits))
done

if (( smart_collection_failures != 0 && smart_status_findings != 0 )); then
  exit 3
elif (( smart_collection_failures != 0 )); then
  exit 1
elif (( smart_status_findings != 0 )); then
  exit 2
fi
