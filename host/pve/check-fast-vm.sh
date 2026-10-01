#!/usr/bin/env bash
set -euo pipefail

# Run on the Proxmox host. This check is read-only and never imports a pool.
fail() { printf 'fast-vm drift: %s\n' "$*" >&2; exit 1; }

[[ $(zpool list -H -o health fast-vm) == ONLINE ]] || fail 'pool is not ONLINE'
[[ $(zpool get -H -o value ashift fast-vm) == 12 ]] || fail 'ashift is not 12'
[[ $(zfs get -H -o value compression fast-vm/data) == lz4 ]] || fail 'compression is not lz4'
[[ $(zfs get -H -o value atime fast-vm/data) == off ]] || fail 'atime is not off'

status=$(zpool status -P fast-vm)
[[ $status == *'errors: No known data errors'* ]] || fail 'pool reports data errors'
actual=$(awk '$1 ~ /^(mirror|raidz|draid|spare|log|cache)-[0-9]+$/ || $1 ~ /^\/dev\/disk\/by-id\// { print $1 }' <<< "$status")
expected=$(printf '%s\n' \
  mirror-0 \
  /dev/disk/by-id/nvme-INTEL_SSDPEKKW010T8_PHHH829001A91P0E-part1 \
  /dev/disk/by-id/nvme-INTEL_SSDPEKKW010T8_PHHH828600761P0E-part1)
[[ $actual == "$expected" ]] || fail "mirror topology differs from the serial-specific baseline"

storage=$(awk '/^zfspool: fast-vm$/ { found=1; next } found && /^[^[:space:]]/ { exit } found { print }' /etc/pve/storage.cfg)
[[ $storage == *$'\tpool fast-vm/data'* ]] || fail 'PVE storage points at a different dataset'
[[ $storage == *$'\tcontent rootdir,images'* || $storage == *$'\tcontent images,rootdir'* ]] || fail 'PVE storage content differs'
[[ $storage == *$'\tsparse 1'* ]] || fail 'PVE storage is not sparse'

printf 'fast-vm baseline PASS\n'
