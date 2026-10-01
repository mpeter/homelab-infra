#!/usr/bin/env bash
set -euo pipefail

# Run on PVE with: bash -s -- preview|check|apply < manage-repositories.sh
apt_dir=${PVE_APT_DIR:-/etc/apt/sources.list.d}
mode=${1:-}
[[ $mode == preview || $mode == check || $mode == apply ]] || {
  printf 'usage: %s preview|check|apply\n' "$0" >&2
  exit 2
}

original_pve() {
  cat <<'EOF'
Types: deb
URIs: https://enterprise.proxmox.com/debian/pve
Suites: trixie
Components: pve-enterprise
Signed-By: /usr/share/keyrings/proxmox-archive-keyring.gpg
EOF
}

original_ceph() {
  cat <<'EOF'
Types: deb
URIs: https://enterprise.proxmox.com/debian/ceph-squid
Suites: trixie
Components: enterprise
Signed-By: /usr/share/keyrings/proxmox-archive-keyring.gpg
EOF
}

desired_pve() { original_pve; printf 'Enabled: no\n'; }
desired_ceph() { original_ceph; printf 'Enabled: no\n'; }
desired_nosub() {
  cat <<'EOF'
Types: deb
URIs: http://download.proxmox.com/debian/pve
Suites: trixie
Components: pve-no-subscription
Signed-By: /usr/share/keyrings/proxmox-archive-keyring.gpg
EOF
}

check_known_input() {
  local name=$1 original=$2 desired=$3 path="$apt_dir/$1"
  if [[ -f $path ]] && cmp -s "$path" <("$desired"); then return; fi
  if [[ $original == absent && ! -e $path ]]; then return; fi
  if [[ $original != absent && -f $path ]] && cmp -s "$path" <("$original"); then return; fi
  printf 'refusing unknown source content: %s\n' "$path" >&2
  exit 1
}

show_diff() {
  local path="$apt_dir/$1" desired=$2
  if [[ -f $path ]]; then
    diff -u --label "current/$1" --label "desired/$1" "$path" <("$desired") || [[ $? == 1 ]]
  else
    diff -u --label /dev/null --label "desired/$1" /dev/null <("$desired") || [[ $? == 1 ]]
  fi
}

check_known_input pve-enterprise.sources original_pve desired_pve
check_known_input ceph.sources original_ceph desired_ceph
check_known_input proxmox.sources absent desired_nosub

if [[ $mode == check ]]; then
  cmp -s "$apt_dir/pve-enterprise.sources" <(desired_pve) &&
  cmp -s "$apt_dir/ceph.sources" <(desired_ceph) &&
  cmp -s "$apt_dir/proxmox.sources" <(desired_nosub) && {
    printf 'PVE repositories PASS\n'
    exit 0
  }
  printf 'PVE repositories differ from desired state\n' >&2
  exit 1
fi

show_diff pve-enterprise.sources desired_pve
show_diff ceph.sources desired_ceph
show_diff proxmox.sources desired_nosub
[[ $mode == preview ]] && exit 0

[[ $apt_dir == /etc/apt/sources.list.d ]] || {
  printf 'apply requires the live APT directory\n' >&2
  exit 1
}
[[ $(id -u) == 0 ]] || { printf 'apply requires root\n' >&2; exit 1; }

for entry in 'pve-enterprise.sources desired_pve' 'ceph.sources desired_ceph' 'proxmox.sources desired_nosub'; do
  read -r name render <<< "$entry"
  target="$apt_dir/$name"
  if [[ -f $target ]] && cmp -s "$target" <("$render"); then continue; fi
  temp=$(mktemp "$apt_dir/.${name}.XXXXXX")
  "$render" > "$temp"
  chmod 644 "$temp"
  mv -T "$temp" "$target"
done

cmp -s "$apt_dir/pve-enterprise.sources" <(desired_pve) &&
cmp -s "$apt_dir/ceph.sources" <(desired_ceph) &&
cmp -s "$apt_dir/proxmox.sources" <(desired_nosub) || {
  printf 'post-apply repository check failed\n' >&2
  exit 1
}
printf 'PVE repositories PASS\n'
