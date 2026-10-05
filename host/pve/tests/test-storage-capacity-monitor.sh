#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
monitor="$repo_root/host/pve/storage-capacity-monitor.sh"
manager="$repo_root/host/pve/manage-storage-capacity-monitor.sh"
scratch_root=${XDG_CACHE_HOME:-$HOME/.cache}/agent-scratch
mkdir -p "$scratch_root"
test_dir=$(mktemp -d "$scratch_root/homelab-storage-capacity.XXXXXX")
trap '/bin/rm -rf -- "$test_dir"' EXIT

bin="$test_dir/bin"
mkdir -p "$bin"
cat > "$bin/zpool" <<'MOCK'
#!/usr/bin/env bash
set -euo pipefail
[[ $# == 6 && $1 == list && $2 == -H && $3 == -p && $4 == -o && $5 == name,capacity,health ]]
pool=${6}
awk -v pool="$pool" '$1 == pool { print; found = 1 } END { exit !found }' "$PVE_TEST_POOL_FILE" || exit $?
[[ ${PVE_TEST_ZPOOL_FAIL_AFTER_OUTPUT:-} != "$pool" ]] || exit 1
MOCK
cat > "$bin/logger" <<'MOCK'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >> "$PVE_TEST_LOGGER_OUTPUT"
MOCK
chmod 755 "$bin/zpool" "$bin/logger"

state_dir="$test_dir/state"
pool_file="$test_dir/pools.txt"
logger_output="$test_dir/logger.txt"
: > "$logger_output"

write_pools() {
  cat > "$pool_file"
}

run_monitor() {
  PVE_STORAGE_CAPACITY_TEST_MODE=1 \
    PVE_STORAGE_CAPACITY_STATE_DIR="$state_dir" \
    PVE_TEST_POOL_FILE="$pool_file" \
    PVE_TEST_LOGGER_OUTPUT="$logger_output" \
    PVE_TEST_ZPOOL_FAIL_AFTER_OUTPUT="${PVE_TEST_ZPOOL_FAIL_AFTER_OUTPUT:-}" \
    PATH="$bin:$PATH" \
    bash "$monitor"
}

write_pools <<'POOLS'
rpool 79 ONLINE
fast-vm 0 ONLINE
scratch 0 ONLINE
POOLS
run_monitor
[[ $(cat "$state_dir/rpool") == normal ]]
[[ $(cat "$state_dir/fast-vm") == normal ]]
[[ $(cat "$state_dir/scratch") == normal ]]
! rg -q 'pool=rpool.*level=warning' "$logger_output"

write_pools <<'POOLS'
rpool 80 ONLINE
fast-vm 0 ONLINE
scratch 0 ONLINE
POOLS
run_monitor
[[ $(rg -c 'daemon.warning.*pool=rpool.*capacity=80%.*level=warning' "$logger_output") == 1 ]]

run_monitor
[[ $(rg -c 'daemon.warning.*pool=rpool.*level=warning' "$logger_output") == 1 ]]

write_pools <<'POOLS'
rpool 90 ONLINE
fast-vm 0 ONLINE
scratch 0 ONLINE
POOLS
run_monitor
[[ $(cat "$state_dir/rpool") == critical ]]
[[ $(rg -c 'daemon.crit.*pool=rpool.*capacity=90%.*level=critical' "$logger_output") == 1 ]]

write_pools <<'POOLS'
rpool 89 ONLINE
fast-vm 0 ONLINE
scratch 0 ONLINE
POOLS
run_monitor
[[ $(cat "$state_dir/rpool") == warning ]]
[[ $(rg -c 'daemon.warning.*pool=rpool.*capacity=89%.*level=warning' "$logger_output") == 1 ]]

write_pools <<'POOLS'
rpool 79 ONLINE
fast-vm 0 ONLINE
scratch 0 ONLINE
POOLS
run_monitor
[[ $(cat "$state_dir/rpool") == normal ]]
[[ $(rg -c 'daemon.notice.*pool=rpool.*recovered' "$logger_output") == 1 ]]

write_pools <<'POOLS'
rpool malformed ONLINE
fast-vm 0 ONLINE
scratch 0 ONLINE
POOLS
if run_monitor >/dev/null 2>&1; then
  printf 'monitor accepted malformed capacity output\n' >&2
  exit 1
fi
[[ $(cat "$state_dir/rpool") == normal ]]

write_pools <<'POOLS'
rpool 1 ONLINE
fast-vm 0 ONLINE
scratch 90 ONLINE
POOLS
run_monitor
[[ $(cat "$state_dir/scratch") == critical ]]
[[ $(rg -c 'daemon.crit.*pool=scratch.*capacity=90%.*level=critical' "$logger_output") == 1 ]]

write_pools <<'POOLS'
rpool 1 ONLINE
fast-vm 0 ONLINE
POOLS
printf 'normal\n' > "$state_dir/scratch"
run_monitor
[[ $(cat "$state_dir/rpool") == normal ]]
[[ $(cat "$state_dir/fast-vm") == normal ]]
[[ $(cat "$state_dir/scratch") == critical:pool_unreadable ]]
[[ $(rg -c 'daemon.crit.*pool=scratch.*capacity=unknown.*reason=pool_unreadable' "$logger_output") == 1 ]]

write_pools <<'POOLS'
rpool 1 ONLINE
fast-vm 0 ONLINE
scratch 0 ONLINE
POOLS
run_monitor
[[ $(cat "$state_dir/scratch") == normal ]]
[[ $(rg -c 'pool=scratch.*level=normal recovered_from=critical' "$logger_output") == 1 ]]

write_pools <<'POOLS'
rpool 1 ONLINE
fast-vm 0 ONLINE
scratch 95 ONLINE
POOLS
run_monitor
[[ $(cat "$state_dir/scratch") == critical ]]

write_pools <<'POOLS'
rpool 1 ONLINE
fast-vm 0 ONLINE
scratch 0 ONLINE
POOLS
PVE_TEST_ZPOOL_FAIL_AFTER_OUTPUT=scratch run_monitor
unset PVE_TEST_ZPOOL_FAIL_AFTER_OUTPUT
[[ $(cat "$state_dir/rpool") == normal ]]
[[ $(cat "$state_dir/fast-vm") == normal ]]
[[ $(cat "$state_dir/scratch") == critical:pool_unreadable ]]
[[ $(rg -c 'daemon.crit.*pool=scratch.*capacity=unknown.*reason=pool_unreadable' "$logger_output") == 2 ]]

test_root="$test_dir/pve-root"
systemctl_state="$test_dir/systemctl-state"
mkdir -p "$test_dir/test-bin"
cat > "$test_dir/test-bin/systemctl" <<'MOCK'
#!/usr/bin/env bash
set -euo pipefail
state=${PVE_TEST_SYSTEMCTL_STATE:?}
mkdir -p "$state"
case "$*" in
  'daemon-reload') touch "$state/reloaded" ;;
  'enable --now pve-storage-capacity-monitor.timer') touch "$state/enabled" "$state/active" ;;
  'disable --now pve-storage-capacity-monitor.timer') /bin/rm -f "$state/enabled" "$state/active" ;;
  'stop pve-storage-capacity-monitor.service') /bin/rm -f "$state/service-active" ;;
  'is-enabled --quiet pve-storage-capacity-monitor.timer') [[ -e $state/enabled ]] ;;
  'is-active --quiet pve-storage-capacity-monitor.timer') [[ -e $state/active ]] ;;
  *) printf 'unexpected systemctl call: %s\n' "$*" >&2; exit 1 ;;
esac
MOCK
chmod 755 "$test_dir/test-bin/systemctl"

run_manager_at() {
  local root=$1 operation=$2 recovery=${3:-0}
  PVE_STORAGE_CAPACITY_TEST_ROOT="$root" \
    PVE_STORAGE_CAPACITY_RECOVERY="$recovery" \
    PVE_TEST_SYSTEMCTL_STATE="$systemctl_state" \
    PATH="$test_dir/test-bin:$PATH" \
    bash "$manager" "$operation"
}

run_manager() {
  run_manager_at "$test_root" "$1"
}

run_managed_monitor() {
  PVE_STORAGE_CAPACITY_TEST_MODE=1 \
    PVE_STORAGE_CAPACITY_STATE_DIR="$test_root/var/lib/pve-storage-capacity-monitor" \
    PVE_TEST_POOL_FILE="$pool_file" \
    PVE_TEST_LOGGER_OUTPUT="$logger_output" \
    PVE_TEST_ZPOOL_FAIL_AFTER_OUTPUT="${PVE_TEST_ZPOOL_FAIL_AFTER_OUTPUT:-}" \
    PATH="$bin:$PATH" \
    bash "$test_root/usr/local/sbin/pve-storage-capacity-monitor"
}

run_manager preview >/dev/null
[[ ! -e $test_root ]]
run_manager apply >/dev/null
run_manager apply >/dev/null
[[ -x $test_root/usr/local/sbin/pve-storage-capacity-monitor ]]
[[ -f $test_root/etc/systemd/system/pve-storage-capacity-monitor.service ]]
[[ -f $test_root/etc/systemd/system/pve-storage-capacity-monitor.timer ]]
[[ -f $test_root/var/lib/pve-storage-capacity-monitor/managed-by-code ]]
mkdir -p "$test_root/etc/systemd/system"
for target in sysinit timers zfs; do
  cat > "$test_root/etc/systemd/system/$target.target" <<EOF
[Unit]
Description=Test $target target
EOF
done
systemd-analyze verify --root="$test_root" \
  pve-storage-capacity-monitor.service pve-storage-capacity-monitor.timer
run_manager check >/dev/null
write_pools <<'POOLS'
rpool 1 ONLINE
fast-vm 0 ONLINE
scratch 0 ONLINE
POOLS
run_managed_monitor
[[ $(cat "$test_root/var/lib/pve-storage-capacity-monitor/rpool") == normal ]]
[[ $(cat "$test_root/var/lib/pve-storage-capacity-monitor/fast-vm") == normal ]]
PVE_TEST_ZPOOL_FAIL_AFTER_OUTPUT=scratch run_managed_monitor
unset PVE_TEST_ZPOOL_FAIL_AFTER_OUTPUT
[[ $(cat "$test_root/var/lib/pve-storage-capacity-monitor/scratch") == critical:pool_unreadable ]]
printf 'normal\n' > "$test_root/var/lib/pve-storage-capacity-monitor/.rpool.Abc123"
printf 'interrupted\n' > "$test_root/var/lib/pve-storage-capacity-monitor/.managed-by-code.ZyX987"
run_manager rollback >/dev/null
[[ ! -e $test_root/usr/local/sbin/pve-storage-capacity-monitor ]]
[[ ! -e $test_root/etc/systemd/system/pve-storage-capacity-monitor.service ]]
[[ ! -e $test_root/etc/systemd/system/pve-storage-capacity-monitor.timer ]]
[[ ! -e $test_root/var/lib/pve-storage-capacity-monitor ]]
[[ ! -e $systemctl_state/enabled && ! -e $systemctl_state/active ]]
run_manager preview >/dev/null
run_manager apply >/dev/null

assert_rollback_refuses_state() {
  local name=$1 bad_state=$2 root="$test_dir/rollback-$1"
  local state_dir="$root/var/lib/pve-storage-capacity-monitor"
  run_manager_at "$root" apply >/dev/null
  case "$bad_state" in
    unknown)
      printf 'preserve\n' > "$state_dir/operator-data"
      ;;
    symlink)
      printf 'outside\n' > "$test_dir/outside-state"
      ln -s "$test_dir/outside-state" "$state_dir/rpool"
      ;;
    directory)
      mkdir "$state_dir/operator-data"
      ;;
    invalid)
      printf 'unexpected\n' > "$state_dir/fast-vm"
      ;;
  esac
  if run_manager_at "$root" rollback >/dev/null 2>&1; then
    printf 'rollback accepted %s state\n' "$name" >&2
    exit 1
  fi
  [[ -f $root/usr/local/sbin/pve-storage-capacity-monitor ]]
  [[ -f $root/etc/systemd/system/pve-storage-capacity-monitor.service ]]
  [[ -f $root/etc/systemd/system/pve-storage-capacity-monitor.timer ]]
  [[ -f $state_dir/managed-by-code ]]
  [[ -e $systemctl_state/enabled && -e $systemctl_state/active ]]
}

assert_rollback_refuses_state unknown unknown
assert_rollback_refuses_state symlink symlink
assert_rollback_refuses_state directory directory
assert_rollback_refuses_state invalid invalid

legacy_root="$test_dir/legacy-root"
mkdir -p "$legacy_root/usr/local/sbin" "$legacy_root/etc/systemd/system" "$legacy_root/var/lib/pve-storage-capacity-monitor"
printf 'previous monitor source\n' > "$legacy_root/usr/local/sbin/pve-storage-capacity-monitor"
cp "$repo_root/host/pve/systemd/pve-storage-capacity-monitor.service" \
  "$legacy_root/etc/systemd/system/pve-storage-capacity-monitor.service"
cp "$repo_root/host/pve/systemd/pve-storage-capacity-monitor.timer" \
  "$legacy_root/etc/systemd/system/pve-storage-capacity-monitor.timer"
printf 'homelab-infra:pve-storage-capacity-monitor:v1\n' \
  > "$legacy_root/var/lib/pve-storage-capacity-monitor/managed-by-code"
legacy_hash=$(sha256sum "$legacy_root/usr/local/sbin/pve-storage-capacity-monitor" | awk '{print $1}')
PVE_STORAGE_CAPACITY_TEST_LEGACY_MONITOR_SHA256="$legacy_hash" \
  run_manager_at "$legacy_root" preview >/dev/null
[[ $(cat "$legacy_root/var/lib/pve-storage-capacity-monitor/managed-by-code") == 'homelab-infra:pve-storage-capacity-monitor:v1' ]]
PVE_STORAGE_CAPACITY_TEST_LEGACY_MONITOR_SHA256="$legacy_hash" \
  run_manager_at "$legacy_root" apply >/dev/null
[[ $(cat "$legacy_root/var/lib/pve-storage-capacity-monitor/managed-by-code") == 'homelab-infra:pve-storage-capacity-monitor:v2' ]]
run_manager_at "$legacy_root" check >/dev/null
run_manager_at "$legacy_root" rollback >/dev/null

interrupted_root="$test_dir/interrupted-root"
mkdir -p "$interrupted_root/usr/local/sbin" "$interrupted_root/etc/systemd/system" \
  "$interrupted_root/var/lib/pve-storage-capacity-monitor"
cp "$monitor" "$interrupted_root/usr/local/sbin/pve-storage-capacity-monitor"
cp "$repo_root/host/pve/systemd/pve-storage-capacity-monitor.service" \
  "$interrupted_root/etc/systemd/system/pve-storage-capacity-monitor.service"
cp "$repo_root/host/pve/systemd/pve-storage-capacity-monitor.timer" \
  "$interrupted_root/etc/systemd/system/pve-storage-capacity-monitor.timer"
printf 'homelab-infra:pve-storage-capacity-monitor:v1\n' \
  > "$interrupted_root/var/lib/pve-storage-capacity-monitor/managed-by-code"
PVE_STORAGE_CAPACITY_TEST_LEGACY_MONITOR_SHA256="$legacy_hash" \
  run_manager_at "$interrupted_root" apply 1 >/dev/null
[[ $(cat "$interrupted_root/var/lib/pve-storage-capacity-monitor/managed-by-code") == \
  'homelab-infra:pve-storage-capacity-monitor:v2' ]]
cmp -s "$monitor" "$interrupted_root/usr/local/sbin/pve-storage-capacity-monitor"

unknown_root="$test_dir/unknown-root"
mkdir -p "$unknown_root/usr/local/sbin"
printf 'preserve this\n' > "$unknown_root/usr/local/sbin/pve-storage-capacity-monitor"
if run_manager_at "$unknown_root" preview >/dev/null 2>&1; then
  printf 'manager accepted an unowned target path\n' >&2
  exit 1
fi
[[ $(cat "$unknown_root/usr/local/sbin/pve-storage-capacity-monitor") == 'preserve this' ]]

printf 'PVE storage capacity monitor tests PASS\n'
