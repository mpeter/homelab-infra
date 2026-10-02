#!/usr/bin/env bash
set -euo pipefail

mode=${1:-}
[[ $mode == preview || $mode == check || $mode == apply ]] || {
  printf 'usage: %s preview|check|apply\n' "$0" >&2
  exit 2
}

pve_host=192.168.0.188
image_name=TrueNAS-SCALE-25.10.7.iso
expected_sha256=54ce9441ce66966a392e28f63604ca3c2c083d0bec4db7bb5af2f74f7a007c8e
source_image=/home/mpeter/work/homelab-private/truenas/$image_name
target=/var/lib/vz/template/iso/$image_name
export DISPLAY=:0 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus
export SSHPASS
SSHPASS=$(secret-tool lookup homelab-pve-host "$pve_host" account root)
[[ -n $SSHPASS ]] || { echo 'missing PVE credential in desktop keyring' >&2; exit 1; }

pve() { sshpass -e ssh -o ConnectTimeout=10 "root@$pve_host" "$@"; }
fail() { printf 'TrueNAS ISO staging blocked: %s\n' "$*" >&2; exit 1; }

[[ -f $source_image ]] || fail 'verified source ISO is missing'
[[ $(sha256sum "$source_image" | cut -d ' ' -f 1) == "$expected_sha256" ]] || fail 'source SHA-256 differs'
storage=$(pve 'sed -n "/^dir: local$/,/^[[:space:]]*$/p" /etc/pve/storage.cfg')
[[ $storage == *'content '*iso* ]] || fail 'local storage does not allow ISO content'
[[ $(pve 'zpool list -H -o health rpool fast-vm') == $'ONLINE\nONLINE' ]] || fail 'pool is not healthy'

remote_sha256=$(pve "if test -e '$target'; then sha256sum '$target' | cut -d ' ' -f 1; fi")
if [[ -n $remote_sha256 ]]; then
  [[ $remote_sha256 == "$expected_sha256" ]] || fail 'target exists with a different SHA-256'
  printf 'TrueNAS ISO staging PASS: local:iso/%s\n' "$image_name"
  exit 0
fi

[[ $mode != check ]] || fail 'ISO is not staged'
available_kib=$(pve "df -Pk /var/lib/vz/template/iso | awk 'NR==2 {print \$4}'")
needed_kib=$(( ($(stat -c %s "$source_image") + 1023) / 1024 * 2 ))
[[ $available_kib =~ ^[0-9]+$ && $available_kib -gt $needed_kib ]] || fail 'insufficient space on local storage'
printf 'stage %s to local:iso/%s; SHA-256 %s; free %s KiB\n' \
  "$source_image" "$image_name" "$expected_sha256" "$available_kib"
[[ $mode == preview ]] && exit 0

temp=$(pve 'mktemp /var/lib/vz/template/iso/.truenas-25.10.7.XXXXXX')
trap 'pve "rm -f -- '\''$temp'\''"' EXIT
sshpass -e scp -q "$source_image" "root@$pve_host:$temp"
[[ $(pve "sha256sum '$temp' | cut -d ' ' -f 1") == "$expected_sha256" ]] || fail 'remote temporary file SHA-256 differs'
pve "test ! -e '$target' && chmod 644 '$temp' && mv -T '$temp' '$target'"
trap - EXIT
[[ $(pve "sha256sum '$target' | cut -d ' ' -f 1") == "$expected_sha256" ]] || fail 'final remote file SHA-256 differs'
printf 'TrueNAS ISO staging PASS: local:iso/%s\n' "$image_name"
