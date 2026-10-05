#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
capture="$repo_root/host/pve/capture-storage-health.sh"
scratch_root=${XDG_CACHE_HOME:-$HOME/.cache}/agent-scratch
mkdir -p "$scratch_root"
test_dir=$(mktemp -d "$scratch_root/homelab-storage-health.XXXXXX")
trap '/bin/rm -rf -- "$test_dir"' EXIT
bin="$test_dir/bin"
mkdir -p "$bin"

cat > "$bin/zpool" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
case "$*" in
  'list -Hp -o name,size,alloc,free,capacity,health rpool')
    printf 'rpool\t506806140928\t6827597824\t499978543104\t1\tDEGRADED\n' ;;
  'list -Hp -o name,size,alloc,free,capacity,health fast-vm')
    printf 'fast-vm\t1022202216448\t5947244544\t1016254971904\t0\tONLINE\n' ;;
  'list -Hp -o name,size,alloc,free,capacity,health scratch')
    printf 'scratch\t1024220381184\t0\t1024220381184\t0\tONLINE\n' ;;
  'status -P -v rpool')
    printf '  pool: rpool\n state: DEGRADED\n  /dev/disk/by-id/nvme-eui.rpool-a-part3 ONLINE 2 1 4\n  /dev/disk/by-id/nvme-eui.rpool-b-part3 UNAVAIL 0 0 0\nerrors: Permanent errors have been detected in the following files:\n        /rpool/diagnostics/payload.bin\n' ;;
  'status -P -v fast-vm')
    printf '  pool: fast-vm\n state: ONLINE\n  /dev/disk/by-id/nvme-INTEL_fast-a-part1 ONLINE\n  /dev/disk/by-id/nvme-INTEL_fast-b-part1 ONLINE\nerrors: No known data errors\n' ;;
  'status -P -v scratch')
    printf '  pool: scratch\n state: ONLINE\n  /dev/disk/by-id/nvme-INTEL_scratch-c-part1 ONLINE\n  /dev/disk/by-id/nvme-INTEL_scratch-d-part1 ONLINE\nerrors: No known data errors\n' ;;
  *) exit 2 ;;
esac
SH

cat > "$bin/zfs" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
case "${@: -1}" in
  rpool) printf 'rpool\t1024\t499978000000\tnone\tnone\n' ;;
  fast-vm) printf 'fast-vm/data\t1024\t1016250000000\tnone\tnone\n' ;;
  scratch) printf 'scratch/vm\t1024\t1024220000000\tnone\tnone\n' ;;
  *) exit 2 ;;
esac
SH

cat > "$bin/pvesm" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
[[ ${PVESM_STATUS:-0} == 0 ]] || exit "$PVESM_STATUS"
printf 'Name Type Status Total Used Available %%\nfast-vm zfspool active 100 1 99 1%%\nscratch zfspool active 100 1 99 1%%\n'
SH

cat > "$bin/systemctl" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
[[ "$*" == 'is-active smartd' ]] || exit 2
printf '%s\n' "${SMARTD_STATE:-active}"
[[ ${SMARTD_STATE:-active} == active ]]
SH

cat > "$bin/cat" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
case "$1" in
  /etc/cron.d/zfsutils-linux) printf '# scrub schedule\n24 0 8-14 * * root /usr/lib/zfs-linux/scrub\n' ;;
  /etc/smartd.conf) printf 'DEVICESCAN -d removable -n standby -m root\n' ;;
  *) exec /usr/bin/cat "$@" ;;
esac
SH

cat > "$bin/smartctl" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
[[ ${1:-} == -x && $# == 2 ]] || exit 2
printf '%s\n' "$2" >> "$TEST_CALL_LOG"
printf 'SMART fixture for %s\n' "$2"
exit "${SMARTCTL_STATUS:-0}"
SH

chmod +x "$bin"/*
output="$test_dir/output"
calls="$test_dir/smartctl-calls"
PATH="$bin:$PATH" TEST_CALL_LOG="$calls" bash "$capture" > "$output"

for expected in \
  'rpool' \
  'DEGRADED' \
  'ONLINE 2 1 4' \
  'UNAVAIL 0 0 0' \
  'Permanent errors have been detected in the following files:' \
  '/rpool/diagnostics/payload.bin' \
  'fast-vm' \
  'scratch' \
  'nvme-INTEL_scratch-c' \
  'nvme-INTEL_scratch-d' \
  'Proxmox storage usage' \
  'Periodic scrub configuration' \
  'SMART monitoring configuration' \
  'smartd service: active' \
  'ata-KINGSTON_SUV400S37240G_50026B7767031A82'; do
  grep -Fq "$expected" "$output" || {
    printf 'missing expected evidence: %s\n' "$expected" >&2
    exit 1
  }
done

cat > "$test_dir/expected-smartctl-calls" <<'EOF'
/dev/disk/by-id/nvme-eui.rpool-a
/dev/disk/by-id/nvme-eui.rpool-b
/dev/disk/by-id/nvme-INTEL_fast-a
/dev/disk/by-id/nvme-INTEL_fast-b
/dev/disk/by-id/nvme-INTEL_scratch-c
/dev/disk/by-id/nvme-INTEL_scratch-d
/dev/disk/by-id/ata-KINGSTON_SUV400S37240G_50026B7767031A82
EOF
diff -u "$test_dir/expected-smartctl-calls" "$calls"

if PATH="$bin:$PATH" TEST_CALL_LOG="$calls" PVESM_STATUS=1 bash "$capture" > /dev/null 2>&1; then
  echo 'storage command failure was reported as successful evidence capture' >&2
  exit 1
fi

run_with_smart_status() {
  local expected_status=$1 smart_status=$2 actual_status=0
  if PATH="$bin:$PATH" TEST_CALL_LOG="$calls" SMARTCTL_STATUS="$smart_status" bash "$capture" > "$output" 2>&1; then
    actual_status=0
  else
    actual_status=$?
  fi
  [[ $actual_status == "$expected_status" ]] || {
    printf 'expected collector exit %s for SMART status %s, got %s\n' "$expected_status" "$smart_status" "$actual_status" >&2
    cat "$output" >&2
    exit 1
  }
}

run_with_smart_status 1 2
grep -Fq 'SMART collection error bits: 2' "$output"
run_with_smart_status 2 8
grep -Fq 'SMART status/log finding bits: 8' "$output"
run_with_smart_status 3 10
grep -Fq 'SMART collection error bits: 2' "$output"
grep -Fq 'SMART status/log finding bits: 8' "$output"

printf 'PVE storage evidence capture tests PASS\n'
