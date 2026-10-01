#!/usr/bin/env bash
set -euo pipefail
umask 077

# Run from the break-glass workstation. The keyring holds the symmetric key.
pve_host=192.168.0.188
private_dir=/home/mpeter/work/homelab-private
bundle="$private_dir/pve-host-config-$(date -u +%Y%m%dT%H%M%SZ).tar.gz.gpg"
export DISPLAY=:0 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus
export SSHPASS
SSHPASS=$(secret-tool lookup homelab-pve-host "$pve_host" account root)
[[ -n $SSHPASS ]] || { echo 'missing PVE credential in desktop keyring' >&2; exit 1; }

key=$(secret-tool lookup homelab-bundle-kind pve-host-config account root || true)
if [[ -z $key ]]; then
  key=$(openssl rand -base64 48)
  printf '%s' "$key" | secret-tool store --label='R720 host configuration bundle' \
    homelab-bundle-kind pve-host-config account root
  [[ $(secret-tool lookup homelab-bundle-kind pve-host-config account root) == "$key" ]] || {
    echo 'bundle key was not stored successfully' >&2
    exit 1
  }
fi

[[ -d $private_dir && ! -e $bundle ]] || { echo 'private directory missing or bundle already exists' >&2; exit 1; }
temp=$(mktemp "$private_dir/.pve-host-config.XXXXXX")
trap 'rm -f -- "$temp"' EXIT
exec 3<<< "$key"
sshpass -e ssh -o ConnectTimeout=10 "root@$pve_host" \
  'tar -C / -czf - etc/pve etc/hostid etc/network etc/apt/sources.list.d etc/zfs/zpool.cache etc/default/grub etc/kernel/proxmox-boot-uuids' |
  gpg --batch --yes --no-tty --pinentry-mode loopback --passphrase-fd 3 \
    --symmetric --cipher-algo AES256 --output "$temp"
exec 3<&-

exec 3<<< "$key"
gpg --batch --no-tty --pinentry-mode loopback --passphrase-fd 3 --decrypt "$temp" |
  tar -tzf - |
  awk '
    $0 == "etc/pve/storage.cfg" { storage=1 }
    $0 == "etc/pve/priv/authkey.key" { auth=1 }
    $0 == "etc/hostid" { hostid=1 }
    $0 == "etc/network/interfaces" { network=1 }
    $0 == "etc/zfs/zpool.cache" { zpool=1 }
    $0 == "etc/apt/sources.list.d/proxmox.sources" { repo=1 }
    END { if (!(storage && auth && hostid && network && zpool && repo)) exit 1 }
  '
exec 3<&-

mv -T -- "$temp" "$bundle"
trap - EXIT
sha256sum "$bundle"
stat -c '%a %U:%G %s %n' "$bundle"
printf 'host configuration bundle PASS\n'
