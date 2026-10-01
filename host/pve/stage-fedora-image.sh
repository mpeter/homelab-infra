#!/usr/bin/env bash
set -euo pipefail

# Stage the verified cloud image in local:import; VM disks belong on fast-vm.
mode=${1:-}
[[ $mode == preview || $mode == check || $mode == apply ]] || {
  printf 'usage: %s preview|check|apply\n' "$0" >&2
  exit 2
}

pve_host=192.168.0.188
image_name=Fedora-Cloud-Base-Generic-44-1.7.x86_64.qcow2
expected_sha=28680fe5b371a5a82ebf43a31926e086a168e59949d03969c5093e7071f90b7f
source_image=/home/mpeter/work/homelab-private/fedora-44-cloud/$image_name
target=/var/lib/vz/import/$image_name
export DISPLAY=:0 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus
export SSHPASS
SSHPASS=$(secret-tool lookup homelab-pve-host "$pve_host" account root)
[[ -n $SSHPASS ]] || { echo 'missing PVE credential in desktop keyring' >&2; exit 1; }

pve() { sshpass -e ssh -o ConnectTimeout=10 "root@$pve_host" "$@"; }
fail() { printf 'Fedora image staging blocked: %s\n' "$*" >&2; exit 1; }

[[ -f $source_image ]] || fail 'verified source image is missing'
[[ $(sha256sum "$source_image" | cut -d ' ' -f 1) == "$expected_sha" ]] || fail 'source SHA-256 differs'
storage=$(pve 'sed -n "/^dir: local$/,/^[[:space:]]*$/p" /etc/pve/storage.cfg')
[[ $storage == *'content '*import* ]] || fail 'local storage does not allow import content'
[[ $(pve 'zpool list -H -o health rpool fast-vm') == $'ONLINE\nONLINE' ]] || fail 'pool is not healthy'

remote_sha=$(pve "if test -e '$target'; then sha256sum '$target' | cut -d ' ' -f 1; fi")
if [[ -n $remote_sha ]]; then
  [[ $remote_sha == "$expected_sha" ]] || fail 'target exists with a different SHA-256'
  printf 'Fedora image staging PASS: local:import/%s\n' "$image_name"
  exit 0
fi

[[ $mode != check ]] || fail 'image is not staged'
available_kib=$(pve "df -Pk /var/lib/vz/import | awk 'NR==2 {print \$4}'")
needed_kib=$(( ($(stat -c %s "$source_image") + 1023) / 1024 * 2 ))
[[ $available_kib =~ ^[0-9]+$ && $available_kib -gt $needed_kib ]] || fail 'insufficient space on local storage'
printf 'stage %s to local:import/%s; SHA-256 %s; free %s KiB\n' \
  "$source_image" "$image_name" "$expected_sha" "$available_kib"
[[ $mode == preview ]] && exit 0

temp=$(pve 'mktemp /var/lib/vz/import/.fedora-44.XXXXXX')
trap 'pve "rm -f -- '\''$temp'\''"' EXIT
sshpass -e scp -q "$source_image" "root@$pve_host:$temp"
[[ $(pve "sha256sum '$temp' | cut -d ' ' -f 1") == "$expected_sha" ]] || fail 'remote temporary file hash differs'
pve "test ! -e '$target' && chmod 644 '$temp' && mv -T '$temp' '$target'"
trap - EXIT
[[ $(pve "sha256sum '$target' | cut -d ' ' -f 1") == "$expected_sha" ]] || fail 'final remote file hash differs'
printf 'Fedora image staging PASS: local:import/%s\n' "$image_name"
