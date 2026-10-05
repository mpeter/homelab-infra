#!/usr/bin/env bash
set -euo pipefail
umask 077
: "${PVE_SCRATCH_EVIDENCE_DIR:=/home/mpeter/.cache/agent-scratch/homelab-infra-group6}"

host=pve
pve_host=192.168.0.188
serial_c=PHHH8505034Q512H
serial_d=BTHH8244042V512D
whole_c=/dev/disk/by-id/nvme-INTEL_SSDPEKKF512G8_PHHH8505034Q512H_1
whole_d=/dev/disk/by-id/nvme-INTEL_SSDPEKKF512G8_BTHH8244042V512D_1
part_c2=/dev/disk/by-id/nvme-INTEL_SSDPEKKF512G8_PHHH8505034Q512H_1-part2
part_c3=/dev/disk/by-id/nvme-INTEL_SSDPEKKF512G8_PHHH8505034Q512H_1-part3
expected_c=/dev/nvme4n1
expected_d=/dev/nvme5n1
expected_p3=/dev/nvme4n1p3
expected_confirmation=PHHH8505034Q512H,BTHH8244042V512D
marker_text=homelab-infra:scratch-pool:v1
capture_manifest_name=scratch-capture-manifest.txt
plan_lock_name=scratch-apply-plan.lock
transaction_predecessor=false
recovery_layout_c=''
recovery_layout_d=''
recovery_findings_sha256=''

fail() { printf 'scratch pool manager: %s\n' "$*" >&2; exit 1; }

script_dir=$(cd -- "$(dirname -- "$0")" && pwd)
project_root=$(cd -- "$script_dir/../.." && pwd)
plan_helper="$script_dir/check_scratch_apply_plan.py"
preflight_source="$script_dir/check_scratch_preflight.py"
monitor_manager="$script_dir/manage-storage-capacity-monitor.sh"
monitor_source="$script_dir/storage-capacity-monitor.sh"

source_list=$(cat <<'FILES'
host/pve/manage-scratch-pool.sh
host/pve/check_scratch_apply_plan.py
host/pve/check_scratch_preflight.py
host/pve/manage-storage-capacity-monitor.sh
host/pve/storage-capacity-monitor.sh
host/pve/capture-storage-health.sh
host/pve/systemd/pve-storage-capacity-monitor.service
host/pve/systemd/pve-storage-capacity-monitor.timer
tofu/proxmox/check-plan.sh
tofu/proxmox/tests/test-check-plan.sh
docs/storage-plan.md
docs/decisions/0003-use-tiered-storage-protection.md
FILES
)

check_tofu_boundary() {
  local matches result
  if matches=$(rg -n -i 'scratch' --glob '*.tf' "$project_root/tofu/proxmox"); then
    printf 'scratch pool is referenced by versioned OpenTofu source:\n%s\n' "$matches" >&2
    fail 'durable VM provisioning must not select scratch'
  else
    result=$?
    [[ $result == 1 ]] || fail 'could not scan versioned OpenTofu source'
  fi
}

make_bundle() {
  local bundle_dir=$1 source_file
  local evidence_dir=$PVE_SCRATCH_EVIDENCE_DIR
  python3 "$plan_helper" capture-manifest "$evidence_dir" > "$bundle_dir/$capture_manifest_name" ||
    fail 'off-target metadata captures failed mode, size, or hash verification'
  : > "$bundle_dir/plan.manifest"
  while IFS= read -r source_file; do
    (cd -- "$project_root" && sha256sum "$source_file") >> "$bundle_dir/plan.manifest"
  done <<< "$source_list"
  (cd -- "$bundle_dir" && sha256sum "$capture_manifest_name") >> "$bundle_dir/plan.manifest"
  sha256sum "$bundle_dir/plan.manifest" | awk '{print $1}'
}

run_remote() {
  local operation=$1 expected_boot=$2 expected_plan=$3 expected_findings=$4 confirmation=$5
  local bundle_dir plan_sha bootstrap encoded remote_command command_name
  for command_name in base64 secret-tool sshpass tar; do
    command -v "$command_name" >/dev/null || fail "missing required command: $command_name"
  done
  bundle_dir=$(mktemp -d "$PVE_SCRATCH_EVIDENCE_DIR/.scratch-plan.XXXXXX")
  plan_sha=$(make_bundle "$bundle_dir")
  [[ -z $expected_plan || $plan_sha == "$expected_plan" ]] ||
    fail 'versioned sources or off-target captures changed since preview'

  bootstrap=$(cat <<'REMOTE'
set -euo pipefail
operation=$1
expected_boot=$2
expected_plan=$3
expected_findings=$4
confirmation=$5
temporary=$(mktemp -d /run/pve-scratch-pool.XXXXXX)
trap 'rm -rf -- "$temporary"' EXIT
tar -xf - -C "$temporary"
cd "$temporary"
sha256sum -c plan.manifest
actual_plan=$(sha256sum plan.manifest | awk '{print $1}')
[[ $actual_plan == "$expected_plan" ]] || {
  echo 'refusing: source bundle hash differs from reviewed plan' >&2
  exit 1
}
bash host/pve/manage-scratch-pool.sh __host \
  "$operation" "$expected_boot" "$expected_plan" "$expected_findings" "$confirmation"
REMOTE
)
  encoded=$(printf '%s' "$bootstrap" | base64 -w0)
  remote_command="bash -c \"\$(printf '%s' '$encoded' | base64 -d)\" -- '$operation' '$expected_boot' '$plan_sha' '$expected_findings' '$confirmation'"

  export DISPLAY=:0 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus
  export SSHPASS
  SSHPASS=$(secret-tool lookup homelab-pve-host "$pve_host" account root)
  [[ -n $SSHPASS ]] || fail 'missing PVE credential in desktop keyring'
  if tar -C "$project_root" -cf - -T <(printf '%s\n' "$source_list") \
      -C "$bundle_dir" "$capture_manifest_name" plan.manifest |
      sshpass -e ssh -F /dev/null -o ConnectTimeout=10 -o StrictHostKeyChecking=yes \
        -o UserKnownHostsFile=/home/mpeter/.ssh/known_hosts -o ControlMaster=no \
        -o ControlPath=none -o PreferredAuthentications=password "root@$pve_host" \
        "$remote_command"; then
    /bin/rm -rf -- "$bundle_dir"
  else
    local result_code=$?
    /bin/rm -rf -- "$bundle_dir"
    return "$result_code"
  fi
}

check_device_identity() {
  local serial=$1 alias=$2 canonical=$3 size=$4 info type found_serial found_size extra=''
  [[ -b $alias ]] || fail "serial-bound device is not a block device: $alias"
  [[ $(readlink -f "$alias") == "$canonical" ]] || fail "by-id path no longer resolves to $canonical"
  info=$(lsblk -b -dnro TYPE,SERIAL,SIZE "$alias") || fail "cannot read lsblk identity for $serial"
  read -r type found_serial found_size extra <<< "$info"
  [[ $type == disk && $found_serial == "$serial" && $found_size == "$size" && -z $extra ]] ||
    fail "live disk identity or size changed for $serial"
  [[ $(blockdev --getsize64 "$alias") == "$size" ]] || fail "block-device size changed for $serial"
  [[ $(blockdev --getss "$alias") == 512 ]] || fail "logical sector size changed for $serial"
  [[ $(udevadm info --query=property --name="$alias" |
      awk -F= '$1 == "ID_SERIAL_SHORT" {print $2}') == "$serial" ]] ||
    fail "udev serial disagrees for $serial"
}

check_partition_identity() {
  local alias=$1 canonical=$2 partuuid=$3 fstype=$4 size=$5
  [[ -b $alias ]] || fail "expected partition is missing: $alias"
  [[ $(readlink -f "$alias") == "$canonical" ]] || fail "partition alias changed: $alias"
  [[ $(lsblk -dnro PARTUUID "$alias") == "$partuuid" ]] || fail "partition PARTUUID changed: $alias"
  [[ $(lsblk -dnro FSTYPE "$alias") == "$fstype" ]] || fail "partition signature changed: $alias"
  [[ $(blockdev --getsize64 "$alias") == "$size" ]] || fail "partition size changed: $alias"
}

verify_live_boundaries() {
  local manifest="$project_root/$capture_manifest_name"
  local serial target region expected alias size sectors skip actual
  python3 "$plan_helper" validate-capture-manifest "$manifest" >/dev/null ||
    fail 'capture manifest is invalid'
  while IFS=$'\t' read -r serial target region expected; do
    case "$serial:$target" in
      "$serial_c:whole") alias=$whole_c; size=512110190592 ;;
      "$serial_d:whole") alias=$whole_d; size=512110190592 ;;
      "$serial_c:p3") alias=$part_c3; size=510026318336 ;;
      *) fail "capture manifest named an unreviewed device: $serial $target" ;;
    esac
    [[ $(blockdev --getsize64 "$alias") == "$size" ]] ||
      fail "boundary target size changed for $serial $target"
    sectors=$((size / 512))
    if [[ $region == first ]]; then
      skip=0
    elif [[ $region == last ]]; then
      skip=$((sectors - 16384))
    else
      fail "unknown boundary region: $region"
    fi
    actual=$(dd if="$alias" bs=512 skip="$skip" count=16384 iflag=fullblock status=none |
      sha256sum | awk '{print $1}')
    [[ $actual == "$expected" ]] ||
      fail "saved boundary metadata no longer matches $serial $target $region"
  done < "$manifest"
}

verify_versioned_bundle() {
  local expected_plan=$1 actual_plan
  sha256sum -c "$project_root/plan.manifest"
  actual_plan=$(sha256sum "$project_root/plan.manifest" | awk '{print $1}')
  [[ $actual_plan == "$expected_plan" ]] || fail 'source bundle hash changed after transfer'
  python3 "$plan_helper" validate-capture-manifest "$project_root/$capture_manifest_name" >/dev/null ||
    fail 'transferred capture manifest did not validate'
}

prewrite_checks() {
  local expected_boot=$1 expected_plan=$2 expected_findings=$3
  local actual_boot actual_findings parsed report exit_code
  verify_versioned_bundle "$expected_plan"
  [[ $(hostname -s) == pve ]] || fail 'connected host is not the reviewed PVE node'
  if [[ -n $expected_boot ]]; then
    [[ $(< /proc/sys/kernel/random/boot_id) == "$expected_boot" ]] ||
      fail 'PVE boot ID changed since preview'
  fi
  [[ ! -e /var/lib/homelab-infra-scratch-pool && ! -L /var/lib/homelab-infra-scratch-pool ]] ||
    fail 'scratch ownership path already exists'
  check_monitor_upgrade_state
  local command_name
  for command_name in lsblk readlink blockdev udevadm dd sha256sum blkid smartctl zpool zfs zdb wipefs pvesm systemctl sync; do
    command -v "$command_name" >/dev/null || fail "required host command is missing: $command_name"
  done
  check_device_identity "$serial_c" "$whole_c" "$expected_c" 512110190592
  check_device_identity "$serial_d" "$whole_d" "$expected_d" 512110190592
  check_partition_identity "$part_c2" /dev/nvme4n1p2 \
    7d7d54b6-42a7-4dde-a045-c97aa2c911ee vfat 1073741824
  check_partition_identity "$part_c3" "$expected_p3" \
    01153cd9-d265-4292-a8f3-d66ace72ac89 zfs_member 510026318336
  verify_live_boundaries

  if report=$(python3 "$preflight_source"); then
    exit_code=0
  else
    exit_code=$?
  fi
  parsed=$(printf '%s\n' "$report" | python3 "$plan_helper" validate-preflight - "$exit_code") || {
    fail 'fresh preflight is not the exact reviewed BLOCK state'
  }
  actual_boot=$(awk -F= '$1 == "boot_id" {print $2}' <<< "$parsed")
  actual_findings=$(awk -F= '$1 == "findings_sha256" {print $2}' <<< "$parsed")
  if [[ -n $expected_boot && $actual_boot != "$expected_boot" ]]; then
    fail 'fresh preflight boot ID differs from preview'
  fi
  if [[ -n $expected_findings && $actual_findings != "$expected_findings" ]]; then
    fail 'serial-bound preflight findings differ from preview'
  fi
  printf 'PVE_SCRATCH_BOOT_ID=%s\n' "$actual_boot"
  printf 'PVE_SCRATCH_PLAN_SHA256=%s\n' "$expected_plan"
  printf 'PVE_SCRATCH_FINDINGS_SHA256=%s\n' "$actual_findings"
  printf '%s\n' "$report"
}

check_monitor_upgrade_state() {
  local marker=/var/lib/pve-storage-capacity-monitor/managed-by-code
  [[ -f /usr/local/sbin/pve-storage-capacity-monitor && ! -L /usr/local/sbin/pve-storage-capacity-monitor ]] ||
    fail 'installed capacity monitor is not a regular managed file'
  [[ -f /etc/systemd/system/pve-storage-capacity-monitor.service &&
      ! -L /etc/systemd/system/pve-storage-capacity-monitor.service &&
      -f /etc/systemd/system/pve-storage-capacity-monitor.timer &&
      ! -L /etc/systemd/system/pve-storage-capacity-monitor.timer ]] ||
    fail 'installed capacity monitor units are not regular managed files'
  [[ -f $marker && ! -L $marker && $(< "$marker") == homelab-infra:pve-storage-capacity-monitor:v1 ]] ||
    fail 'capacity monitor is not the reviewed managed v1 installation'
  [[ $(sha256sum /usr/local/sbin/pve-storage-capacity-monitor | awk '{print $1}') == \
      c0e1c3c3b15df1544fc31b6ff3ece0d4cf4d4b7140431051db817e7fae9db60f ]] ||
    fail 'installed capacity monitor v1 source differs from the reviewed version'
  cmp -s /etc/systemd/system/pve-storage-capacity-monitor.service \
      "$script_dir/systemd/pve-storage-capacity-monitor.service" ||
    fail 'installed capacity monitor service differs from the versioned source'
  cmp -s /etc/systemd/system/pve-storage-capacity-monitor.timer \
      "$script_dir/systemd/pve-storage-capacity-monitor.timer" ||
    fail 'installed capacity monitor timer differs from the versioned source'
  [[ $(systemctl is-enabled pve-storage-capacity-monitor.timer) == enabled ]] ||
    fail 'capacity monitor timer is not enabled before the scratch upgrade'
  [[ $(systemctl is-active pve-storage-capacity-monitor.timer) == active ]] ||
    fail 'capacity monitor timer is not active before the scratch upgrade'
}

pool_exists() {
  local pools
  pools=$(zpool list -H -o name) || fail 'cannot query imported ZFS pools'
  grep -Fxq scratch <<< "$pools"
}

write_transaction_state() {
  local phase=$1 temporary
  temporary=$(mktemp "$state_dir/.apply-plan.XXXXXX") || return 1
  if ! printf '%s\n' \
    'format=scratch-apply-plan-v1' \
    "plan_sha256=$expected_plan" \
    "boot_id=$expected_boot" \
    "serial_c=$serial_c" \
    "serial_d=$serial_d" \
    "findings_sha256=$expected_findings" \
    "phase=$phase" > "$temporary"; then
    /bin/rm -f -- "$temporary"
    return 1
  fi
  if ! chmod 0640 "$temporary" || ! sync "$temporary"; then
    /bin/rm -f -- "$temporary"
    return 1
  fi
  if ! mv -fT -- "$temporary" "$state_dir/apply-plan"; then
    /bin/rm -f -- "$temporary"
    return 1
  fi
  sync "$state_dir" || return 1
  transaction_phase=$phase
  transaction_predecessor=false
}

validate_transaction() {
  local expected_plan=$1 expected_boot_arg=$2 expected_findings_arg=$3 operation=$4
  local parsed
  [[ -d $state_dir && ! -L $state_dir && $(stat -c %a "$state_dir") == 750 &&
      $(stat -c %u "$state_dir") == 0 && -f $state_dir/apply-plan &&
      ! -L $state_dir/apply-plan && $(stat -c %a "$state_dir/apply-plan") == 640 &&
      $(stat -c %u "$state_dir/apply-plan") == 0 ]] ||
    fail 'scratch transaction journal is missing or unsafe'
  parsed=$(python3 "$plan_helper" validate-transaction-journal \
    "$expected_plan" "$expected_boot_arg" "$expected_findings_arg" \
    "$operation" "$state_dir/apply-plan") ||
    fail 'scratch transaction journal does not match the reviewed plan or exact predecessor'
  transaction_boot=$(awk -F= '$1 == "boot_id" {print $2}' <<< "$parsed")
  transaction_findings=$(awk -F= '$1 == "findings_sha256" {print $2}' <<< "$parsed")
  transaction_phase=$(awk -F= '$1 == "phase" {print $2}' <<< "$parsed")
  transaction_predecessor=$(awk -F= '$1 == "predecessor" {print $2}' <<< "$parsed")
  [[ $transaction_predecessor == true || $transaction_predecessor == false ]] ||
    fail 'scratch transaction validator returned an invalid predecessor state'
}

verify_pool_core() {
  local status pool_row values zdb_config
  pool_row=$(zpool list -H -o name,health scratch) || fail 'scratch pool is not imported'
  [[ $pool_row == $'scratch\tONLINE' ]] || fail "scratch pool is not ONLINE: $pool_row"
  status=$(zpool status -P -v scratch) || fail 'cannot read scratch pool topology'
  grep -Fq 'state: ONLINE' <<< "$status" || fail 'scratch pool status is not ONLINE'
  grep -Fq 'errors: No known data errors' <<< "$status" ||
    fail 'scratch pool reports known data errors'
  printf '%s\n' "$status" |
    python3 "$plan_helper" validate-zpool-status - "$whole_c" "$whole_d" >/dev/null ||
    fail 'scratch topology does not match the two reviewed partition paths'
  values=$(zpool get -H -o property,value comment,failmode,autoexpand,autoreplace,autotrim scratch)
  grep -Fq $'comment\tDISPOSABLE: no unique data' <<< "$values" ||
    fail 'scratch pool comment does not mark the disposable stripe'
  grep -Fq $'failmode\tcontinue' <<< "$values" || fail 'scratch failmode differs from plan'
  grep -Fq $'autoexpand\toff' <<< "$values" || fail 'scratch autoexpand differs from plan'
  grep -Fq $'autoreplace\toff' <<< "$values" || fail 'scratch autoreplace differs from plan'
  grep -Fq $'autotrim\toff' <<< "$values" || fail 'scratch autotrim differs from plan'
  zdb_config=$(zdb -C scratch) || fail 'cannot read scratch pool configuration'
  printf '%s\n' "$zdb_config" |
    python3 "$plan_helper" validate-zdb-config - "$whole_c" "$whole_d" >/dev/null ||
    fail 'scratch member paths and ashift do not match the reviewed stripe'
  [[ $(zfs get -H -o value mountpoint scratch) == none ]] || fail 'scratch root mountpoint differs from plan'
  [[ $(zfs get -H -o value compression scratch) == lz4 ]] || fail 'scratch root compression differs from plan'
  [[ $(zfs get -H -o value atime scratch) == off ]] || fail 'scratch root atime differs from plan'
}

verify_scratch_dataset() {
  [[ $(zfs get -H -o value mountpoint scratch/vm) == /scratch/vm ]] ||
    fail 'scratch/vm mountpoint differs from plan'
  [[ $(zfs get -H -o value compression scratch/vm) == lz4 ]] ||
    fail 'scratch/vm compression differs from plan'
  [[ $(zfs get -H -o value atime scratch/vm) == off ]] ||
    fail 'scratch/vm atime differs from plan'
}

verify_installed_pool() {
  local config
  [[ -f $state_dir/managed-by-code && ! -L $state_dir/managed-by-code &&
      $(< "$state_dir/managed-by-code") == "$marker_text" ]] ||
    fail 'scratch ownership marker is missing or unexpected'
  verify_pool_core
  verify_scratch_dataset
  config=$(< /etc/pve/storage.cfg)
  verify_storage_block "$config"
  pvesm status | awk '$1 == "scratch" && $2 == "zfspool" && $3 == "active" {found=1} END {exit !found}' ||
    fail 'PVE scratch storage is not active'
  [[ $(systemctl is-enabled pve-storage-capacity-monitor.timer) == enabled ]] ||
    fail 'capacity monitor timer is not enabled'
  [[ $(systemctl is-active pve-storage-capacity-monitor.timer) == active ]] ||
    fail 'capacity monitor timer is not active'
  cmp -s /usr/local/sbin/pve-storage-capacity-monitor "$monitor_source" ||
    fail 'installed capacity monitor differs from versioned source'
  [[ $(< /var/lib/pve-storage-capacity-monitor/managed-by-code) == homelab-infra:pve-storage-capacity-monitor:v2 ]] ||
    fail 'capacity monitor ownership marker is unexpected'
}

verify_postapply() {
  local result
  verify_installed_pool
  PVE_STORAGE_CAPACITY_RECOVERY=1 bash "$monitor_manager" --host apply
  systemctl start pve-storage-capacity-monitor.service
  result=$(systemctl show pve-storage-capacity-monitor.service -p Result --value)
  [[ $result == success ]] || fail "capacity monitor service result is $result"
  verify_installed_pool
  case $(< /var/lib/pve-storage-capacity-monitor/scratch) in
    normal|warning|critical) ;;
    *) fail 'capacity monitor did not record the scratch pool' ;;
  esac
  printf 'scratch pool, PVE storage, and three-pool capacity monitor read-back PASS\n'
}

assert_no_signatures() {
  local device=$1 signatures
  signatures=$(wipefs --no-act --noheadings --output TYPE "$device") ||
    fail "cannot verify signature state on $device"
  [[ -z ${signatures//[[:space:]]/} ]] ||
    fail "recognized signature remains on $device: $signatures"
}

classify_recovery_disk() {
  local serial=$1 alias=$2 canonical=$3 layout_json layout nodes expected_nodes node kind signatures state
  check_device_identity "$serial" "$alias" "$canonical" 512110190592
  layout_json=$(lsblk --json --bytes --paths \
    --output NAME,TYPE,SERIAL,SIZE,START,PARTTYPE,PARTLABEL,PARTUUID,FSTYPE "$alias") ||
    fail "cannot read recovery layout for $serial"
  layout=$(python3 "$plan_helper" validate-recovery-layout "$serial" "$canonical" - <<< "$layout_json") ||
    fail "recovery partition layout is not exact for $serial"
  state=${layout#layout=}
  nodes=$(lsblk -nrpo NAME "$alias") || fail "cannot enumerate recovery nodes for $serial"
  if [[ $state == generated ]]; then
    expected_nodes="$canonical"$'\n'"${canonical}p1"$'\n'"${canonical}p9"
  else
    expected_nodes=$canonical
  fi
  [[ $nodes == "$expected_nodes" ]] || fail "recovery node list changed for $serial"
  while IFS= read -r node; do
    if [[ $node == "$canonical" ]]; then
      if [[ $state == generated ]]; then
        kind=generated-disk
      else
        kind=clean-disk
      fi
    else
      [[ $state == generated ]] || fail "unexpected recovery child node for $serial: $node"
      kind=partition
    fi
    signatures=$(wipefs --no-act --json --output DEVICE,TYPE,OFFSET,USAGE,UUID "$node") ||
      fail "cannot read recovery signatures for $serial at $node"
    python3 "$plan_helper" validate-recovery-signatures "$node" "$kind" - <<< "$signatures" >/dev/null ||
      fail "recovery signatures are not exact for $serial at $node"
  done <<< "$nodes"
  printf '%s\n' "$state"
}

validate_recovery_preflight() {
  local expected_findings=$1 report exit_code parsed observed_boot observed_findings
  if report=$(python3 "$preflight_source"); then
    exit_code=0
  else
    exit_code=$?
  fi
  parsed=$(printf '%s\n' "$report" | python3 "$plan_helper" \
    validate-recovery-preflight - "$exit_code" "$recovery_layout_c" "$recovery_layout_d") ||
    fail 'interrupted scratch transaction no longer matches the exact reviewed layout and reference state'
  observed_boot=$(awk -F= '$1 == "boot_id" {print $2}' <<< "$parsed")
  [[ $observed_boot == "$expected_boot" ]] ||
    fail 'recovery preflight boot ID differs from the transaction plan'
  observed_findings=$(awk -F= '$1 == "findings_sha256" {print $2}' <<< "$parsed")
  [[ $observed_findings =~ ^[0-9a-f]{64}$ ]] ||
    fail 'recovery preflight findings hash is malformed'
  [[ -z $expected_findings || $observed_findings == "$expected_findings" ]] ||
    fail 'recovery preflight findings differ from the saved reviewed plan'
  recovery_findings_sha256=$observed_findings
}

recovery_checks() {
  verify_versioned_bundle "$expected_plan"
  [[ $(< /proc/sys/kernel/random/boot_id) == "$expected_boot" ]] ||
    fail 'PVE rebooted during the interrupted scratch transaction; a new recovery review is required'
  check_device_identity "$serial_c" "$whole_c" "$expected_c" 512110190592
  check_device_identity "$serial_d" "$whole_d" "$expected_d" 512110190592
  if pool_exists; then
    verify_pool_core
    printf 'recovery state: exact scratch pool already exists and passes topology/property read-back\n'
    return
  fi
  [[ $transaction_phase == labels-cleared ]] ||
    fail "scratch recovery phase $transaction_phase requires a new reviewed recovery plan"
  recovery_layout_c=$(classify_recovery_disk "$serial_c" "$whole_c" "$expected_c")
  recovery_layout_d=$(classify_recovery_disk "$serial_d" "$whole_d" "$expected_d")
  validate_recovery_preflight "$expected_findings"
  printf 'recovery state: exact serial-bound layouts pass (%s=%s, %s=%s); reference checks pass\n' \
    "$serial_c" "$recovery_layout_c" "$serial_d" "$recovery_layout_d"
}

clear_recovery_gpt() {
  local serial=$1 alias=$2 canonical=$3 expected_state=$4 current_state
  current_state=$(classify_recovery_disk "$serial" "$alias" "$canonical")
  [[ $current_state == "$expected_state" ]] ||
    fail "recovery layout changed for $serial after check: $current_state"
  if [[ $current_state == generated ]]; then
    wipefs --all "$alias"
    udevadm settle
  fi
}

verify_clean_recovery_layouts() {
  recovery_layout_c=$(classify_recovery_disk "$serial_c" "$whole_c" "$expected_c")
  recovery_layout_d=$(classify_recovery_disk "$serial_d" "$whole_d" "$expected_d")
  [[ $recovery_layout_c == clean && $recovery_layout_d == clean ]] ||
    fail 'serial-bound scratch candidates are not both free of partition tables'
  validate_recovery_preflight ''
}

clear_candidate_metadata() {
  local alias=$1 canonical=$2 partuuid=$3 size=$4 expected_type=$5
  local type
  if [[ -e $alias || -L $alias ]]; then
    [[ -b $alias ]] || fail "expected candidate partition alias is unsafe: $alias"
    [[ $(readlink -f "$alias") == "$canonical" ]] || fail "candidate partition alias changed: $alias"
    [[ $(lsblk -dnro PARTUUID "$alias") == "$partuuid" ]] || fail "candidate partition PARTUUID changed: $alias"
    [[ $(blockdev --getsize64 "$alias") == "$size" ]] || fail "candidate partition size changed: $alias"
    type=$(lsblk -dnro FSTYPE "$alias") || fail "cannot read candidate partition signature: $alias"
    case "$expected_type:$type" in
      zfs_member:zfs_member) zpool labelclear -f "$alias" ;;
      zfs_member:'') ;;
      vfat:vfat) wipefs --all "$alias" ;;
      vfat:'') ;;
      *) fail "candidate partition signature changed on $alias: ${type:-none}" ;;
    esac
  fi
}

verify_storage_block() {
  local config=$1 block expected
  block=$(awk '
    /^zfspool: scratch$/ {inside=1; count++; print; next}
    inside && (/^$/ || /^[^[:space:]]+:/) {inside=0}
    inside {print}
    END {if (count != 1) exit 1}
  ' <<< "$config") || fail 'PVE storage.cfg must contain exactly one scratch entry'
  for expected in 'pool scratch/vm' 'mountpoint /scratch/vm' 'nodes pve' 'sparse 1'; do
    grep -Eq "^[[:space:]]+$expected$" <<< "$block" ||
      fail "PVE scratch storage setting is missing: $expected"
  done
  python3 "$plan_helper" validate-scratch-storage-content - <<< "$block" >/dev/null ||
    fail 'PVE scratch storage content must be exactly one images,rootdir directive'
}

ensure_scratch_dataset() {
  local datasets
  datasets=$(zfs list -H -o name) || fail 'cannot query ZFS datasets'
  if grep -Fxq scratch/vm <<< "$datasets"; then
    verify_scratch_dataset
  else
    zfs create -o mountpoint=/scratch/vm -o compression=lz4 -o atime=off scratch/vm
    verify_scratch_dataset
  fi
  write_transaction_state dataset-created
}

ensure_scratch_registration() {
  local config entry_count status
  config=$(cat /etc/pve/storage.cfg) || fail 'cannot read PVE storage configuration'
  entry_count=$(awk '$0 == "zfspool: scratch" {count++} END {print count+0}' <<< "$config")
  case "$entry_count" in
    0)
      pvesm add zfspool scratch --pool scratch/vm --content images,rootdir \
        --nodes pve --sparse 1 --mountpoint /scratch/vm
      config=$(cat /etc/pve/storage.cfg) || fail 'cannot read PVE storage configuration after registration'
      ;;
    1) ;;
    *) fail 'PVE storage.cfg contains multiple scratch entries' ;;
  esac
  verify_storage_block "$config"
  status=$(pvesm status) || fail 'cannot read PVE storage status'
  awk '$1 == "scratch" && $2 == "zfspool" && $3 == "active" {found=1} END {exit !found}' <<< "$status" ||
    fail 'PVE scratch storage is not active'
  write_transaction_state storage-registered
}

continue_apply() {
  local candidate_nodes temporary
  check_device_identity "$serial_c" "$whole_c" "$expected_c" 512110190592
  check_device_identity "$serial_d" "$whole_d" "$expected_d" 512110190592
  if pool_exists; then
    verify_pool_core
  else
    if [[ $transaction_phase == labels-cleared ]]; then
      write_transaction_state labels-cleared ||
        fail 'could not durably adopt the reviewed recovery plan before cleanup'
      clear_recovery_gpt "$serial_c" "$whole_c" "$expected_c" "$recovery_layout_c"
      clear_recovery_gpt "$serial_d" "$whole_d" "$expected_d" "$recovery_layout_d"
      verify_clean_recovery_layouts
      expected_findings=$recovery_findings_sha256
      write_transaction_state labels-cleared ||
        fail 'could not durably record the clean serial-bound recovery state'
    else
      clear_candidate_metadata "$part_c3" /dev/nvme4n1p3 \
        01153cd9-d265-4292-a8f3-d66ace72ac89 510026318336 zfs_member
      clear_candidate_metadata "$part_c2" /dev/nvme4n1p2 \
        7d7d54b6-42a7-4dde-a045-c97aa2c911ee 1073741824 vfat
      wipefs --all "$whole_c"
      udevadm settle
      assert_no_signatures "$whole_c"
      assert_no_signatures "$whole_d"
      candidate_nodes=$(lsblk -nrpo NAME "$whole_c") || fail 'cannot verify C partition table removal'
      [[ $candidate_nodes == "$expected_c" ]] || fail "C still has child partitions: $candidate_nodes"
      candidate_nodes=$(lsblk -nrpo NAME "$whole_d") || fail 'cannot verify D partition table removal'
      [[ $candidate_nodes == "$expected_d" ]] || fail "D still has child partitions: $candidate_nodes"
      write_transaction_state labels-cleared
    fi
    write_transaction_state zpool-create-started ||
      fail 'could not durably record the ZFS create boundary before pool creation'
    zpool create \
      -o ashift=12 \
      -o failmode=continue \
      -o autoexpand=off \
      -o autoreplace=off \
      -o autotrim=off \
      -o 'comment=DISPOSABLE: no unique data' \
      -O mountpoint=none \
      -O compression=lz4 \
      -O atime=off \
      scratch "$whole_c" "$whole_d"
    verify_pool_core
  fi
  write_transaction_state pool-created
  ensure_scratch_dataset
  PVE_STORAGE_CAPACITY_RECOVERY=1 bash "$monitor_manager" --host apply
  write_transaction_state monitor-installed
  ensure_scratch_registration
  if [[ -e $state_dir/managed-by-code || -L $state_dir/managed-by-code ]]; then
    [[ -f $state_dir/managed-by-code && ! -L $state_dir/managed-by-code &&
        $(< "$state_dir/managed-by-code") == "$marker_text" ]] ||
      fail 'scratch ownership marker exists with unexpected contents'
  else
    temporary=$(mktemp "$state_dir/.managed-by-code.XXXXXX")
    printf '%s\n' "$marker_text" > "$temporary"
    chmod 0640 "$temporary"
    mv -fT -- "$temporary" "$state_dir/managed-by-code"
  fi
  verify_postapply
  verify_installed_pool
  write_transaction_state complete
}

host_main() {
  [[ $# == 5 ]] || fail 'host operation requires exactly five arguments'
  local operation=$1 expected_boot=$2 expected_plan=$3 expected_findings=$4 confirmation=$5
  local state_dir=/var/lib/homelab-infra-scratch-pool
  local marker="$state_dir/managed-by-code"
  local transaction_phase='' transaction_boot='' transaction_findings='' reference_output reference_status
  local config entry_count volumes
  [[ $(id -u) == 0 ]] || fail 'host operation requires root'
  [[ $(hostname -s) == pve ]] || fail 'connected host is not the reviewed PVE node'
  [[ $operation == preview || $operation == check || $operation == apply || $operation == rollback ]] ||
    fail "unsupported host operation: $operation"
  [[ $expected_plan =~ ^[0-9a-f]{64}$ ]] ||
    fail 'host operation plan hash must be a lowercase SHA-256 value'
  if [[ $operation == preview ]]; then
    [[ -z $expected_boot && -z $expected_findings && -z $confirmation ]] ||
      fail 'preview arguments are malformed'
  elif [[ $operation == apply ]]; then
    [[ $expected_findings =~ ^[0-9a-f]{64}$ ]] ||
      fail 'host operation findings hash must be a lowercase SHA-256 value'
    [[ $expected_boot =~ ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ ]] ||
      fail 'host operation boot ID is malformed'
    [[ $confirmation == "$expected_confirmation" ]] ||
      fail "apply requires exact discard confirmation for $expected_confirmation"
  elif [[ $operation == check ]]; then
    if [[ -n $expected_boot || -n $expected_findings ]]; then
      [[ $expected_findings =~ ^[0-9a-f]{64}$ ]] || fail 'check findings hash is malformed'
      [[ $expected_boot =~ ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ ]] ||
        fail 'check boot ID is malformed'
    fi
    [[ -z $confirmation ]] || fail 'check must not include discard confirmation'
  else
    [[ -z $expected_boot && -z $expected_findings && -z $confirmation ]] ||
      fail 'rollback does not accept preview or confirmation values'
  fi
  if [[ $operation != apply ]]; then
    [[ -z $confirmation ]] || fail 'unexpected confirmation argument'
  fi
  verify_versioned_bundle "$expected_plan"

  if [[ -e $state_dir || -L $state_dir ]]; then
    validate_transaction "$expected_plan" "$expected_boot" "$expected_findings" "$operation"
    expected_boot=$transaction_boot
    if [[ $transaction_predecessor == false &&
        ( $transaction_phase != labels-cleared || $operation == rollback ) ]]; then
      expected_findings=$transaction_findings
    fi
  elif pool_exists; then
    fail 'scratch pool exists without a transaction journal; refusing to adopt it'
  fi

  if [[ $operation == rollback ]]; then
    [[ -d $state_dir ]] || fail 'scratch transaction journal is absent; refusing rollback'
    if [[ -e $marker || -L $marker ]]; then
      [[ -f $marker && ! -L $marker && $(< "$marker") == "$marker_text" ]] ||
        fail 'scratch ownership marker exists with unexpected contents'
    fi
    [[ -d /etc/pve && -r /etc/pve && -x /etc/pve ]] && mountpoint -q /etc/pve ||
      fail 'PVE configuration filesystem is unavailable'
    if reference_output=$(grep -R -n -E 'scratch:|(^|[[:space:]])(storage|storage_id)[[:space:]]*[:=][[:space:]]*scratch([[:space:],]|$)' \
        /etc/pve --include='*.conf' --include='*.cfg' --exclude='storage.cfg'); then
      fail "PVE configuration references scratch: $reference_output"
    else
      reference_status=$?
      [[ $reference_status == 1 ]] || fail 'PVE configuration reference scan failed'
    fi
    [[ -f /etc/pve/storage.cfg && -r /etc/pve/storage.cfg ]] ||
      fail 'PVE storage configuration is unavailable'
    config=$(cat /etc/pve/storage.cfg) || fail 'cannot read PVE storage configuration'
    entry_count=$(awk '$0 == "zfspool: scratch" {count++} END {print count+0}' <<< "$config")
    if [[ $entry_count == 1 ]]; then
      volumes=$(pvesm list scratch) || fail 'cannot inspect scratch volume list'
      printf '%s\n' "$volumes" |
        python3 "$plan_helper" validate-empty-pvesm-list - >/dev/null ||
        fail 'scratch storage volume listing is malformed or non-empty; refusing config rollback'
      pvesm remove scratch
      config=$(cat /etc/pve/storage.cfg) || fail 'cannot read PVE storage configuration after rollback'
    elif [[ $entry_count != 0 ]]; then
      fail 'PVE storage.cfg contains multiple scratch entries'
    fi
    if awk '$0 == "zfspool: scratch" {found=1} END {exit !found}' <<< "$config"; then
      fail 'PVE scratch registration remains after rollback'
    fi
    write_transaction_state rolled-back
    printf 'PVE scratch registration is absent; rollback did not modify ZFS labels, pools, or datasets\n'
    return
  fi

  if [[ -d $state_dir ]]; then
    if [[ $transaction_phase == complete ]]; then
      [[ -f $marker && ! -L $marker && $(< "$marker") == "$marker_text" ]] ||
        fail 'completed scratch transaction ownership marker is missing or unexpected'
      verify_installed_pool
      printf 'PVE_SCRATCH_BOOT_ID=%s\n' "$transaction_boot"
      printf 'PVE_SCRATCH_PLAN_SHA256=%s\n' "$expected_plan"
      printf 'PVE_SCRATCH_FINDINGS_SHA256=%s\n' "$transaction_findings"
      printf 'PVE scratch storage check PASS\n'
      return
    fi
    recovery_checks
    case "$operation" in
      preview)
        printf 'PVE_SCRATCH_BOOT_ID=%s\n' "$transaction_boot"
        printf 'PVE_SCRATCH_PLAN_SHA256=%s\n' "$expected_plan"
        if [[ $recovery_findings_sha256 =~ ^[0-9a-f]{64}$ ]]; then
          printf 'PVE_SCRATCH_FINDINGS_SHA256=%s\n' "$recovery_findings_sha256"
        else
          printf 'PVE_SCRATCH_FINDINGS_SHA256=%s\n' "$transaction_findings"
        fi
        printf 'interrupted scratch transaction phase: %s\n' "$transaction_phase"
        printf 'same-plan resume remains bounded to the two serials; no existing pool or dataset will be destroyed\n'
        return
        ;;
      check)
        printf 'interrupted scratch transaction phase: %s; serial-bound recovery is ready\n' "$transaction_phase"
        return
        ;;
      apply)
        [[ $confirmation == "$expected_confirmation" ]] ||
          fail "apply requires exact discard confirmation for $expected_confirmation"
        continue_apply
        printf 'scratch transaction resumed and verified\n'
        return
        ;;
    esac
  fi

  [[ $operation != rollback ]] || fail 'scratch transaction journal is absent; refusing rollback'
  prewrite_checks "$expected_boot" "$expected_plan" "$expected_findings"

  if [[ $operation == preview ]]; then
    printf 'reviewed targets: %s (%s), %s (%s)\n' "$whole_c" "$serial_c" "$whole_d" "$serial_d"
    printf 'scope: clear old ZFS labels only from C p3; clear FAT signature from C p2; clear GPT/PMBR from C; create scratch without -f as a two-device stripe; create scratch/vm; register PVE images,rootdir only.\n'
    printf 'rollback: unregister PVE storage only when unreferenced and empty; never destroy or export the ZFS pool.\n'
    return
  fi
  if [[ $operation == check ]]; then
    printf 'fresh serial, boot, capture, source, and preflight checks PASS; apply plan is current\n'
    return
  fi
  [[ $operation == apply ]] || fail "unsupported host operation: $operation"
  [[ $confirmation == "$expected_confirmation" ]] ||
    fail "apply requires exact discard confirmation for $expected_confirmation"
  [[ $(< /proc/sys/kernel/random/boot_id) == "$expected_boot" ]] ||
    fail 'PVE rebooted between final preflight and apply'

  mkdir -m 0750 -- "$state_dir"
  if ! sync /var/lib; then
    /bin/rm -rf -- "$state_dir" || fail 'could not clean scratch transaction directory after parent sync failure'
    fail 'could not persist the scratch transaction directory before disk writes'
  fi
  if ! write_transaction_state prepared; then
    /bin/rm -rf -- "$state_dir" || fail 'could not clean incomplete initial scratch transaction directory'
    fail 'could not write the initial scratch transaction journal'
  fi
  printf 'Applying the authorized plan on %s, boot %s\n' "$host" "$expected_boot"
  printf 'wipe scope: %s, %s, and %s\n' "$part_c3" "$part_c2" "$whole_c"
  continue_apply
}

if [[ ${1:-} == __host ]]; then
  shift
  host_main "$@"
  exit
fi

mode=''
if [[ $# -gt 0 ]]; then
  mode=$1
fi
confirmation=''
if [[ $mode == apply ]]; then
  [[ $# == 2 && $2 == --confirm-discard=* ]] || {
    printf 'usage: %s preview|check|rollback or apply --confirm-discard=%s\n' \
      "$0" "$expected_confirmation" >&2
    exit 2
  }
  confirmation=$(cut -d= -f2- <<< "$2")
fi
[[ $mode == preview || $mode == check || $mode == apply || $mode == rollback ]] || {
  printf 'usage: %s preview|check|apply --confirm-discard=%s|rollback\n' \
    "$0" "$expected_confirmation" >&2
  exit 2
}

check_tofu_boundary
evidence_dir=$PVE_SCRATCH_EVIDENCE_DIR
[[ -d $evidence_dir && ! -L $evidence_dir && $(stat -c %a "$evidence_dir") == 700 ]] ||
  fail 'evidence directory must exist as a non-symlink mode 0700 directory'

load_plan_lock() {
  local lock_file="$evidence_dir/$plan_lock_name"
  local -a fields
  [[ -f $lock_file && ! -L $lock_file && $(stat -c %a "$lock_file") == 600 ]] ||
    fail 'run preview and preserve its mode 0600 plan lock before check, apply, or rollback'
  mapfile -t fields < "$lock_file"
  [[ ${#fields[@]} == 4 && ${fields[0]} == format=scratch-apply-plan-v1 ]] ||
    fail 'plan lock has an unsupported format or unexpected fields'
  [[ ${fields[1]} =~ ^PVE_SCRATCH_BOOT_ID=([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$ ]] ||
    fail 'plan lock boot ID is malformed'
  expected_boot=${BASH_REMATCH[1]}
  [[ ${fields[2]} =~ ^PVE_SCRATCH_PLAN_SHA256=([0-9a-f]{64})$ ]] ||
    fail 'plan lock source hash is malformed'
  expected_plan=${BASH_REMATCH[1]}
  [[ ${fields[3]} =~ ^PVE_SCRATCH_FINDINGS_SHA256=([0-9a-f]{64})$ ]] ||
    fail 'plan lock findings hash is malformed'
  expected_findings=${BASH_REMATCH[1]}
}

bundle_dir=$(mktemp -d "$evidence_dir/.scratch-plan.XXXXXX")
plan_sha=$(make_bundle "$bundle_dir")
/bin/rm -rf -- "$bundle_dir"

if [[ $mode == preview ]]; then
  output=$(run_remote preview '' "$plan_sha" '' '')
  printf '%s\n' "$output"
  lock_file="$evidence_dir/$plan_lock_name"
  temporary=$(mktemp "$evidence_dir/.scratch-apply-plan.XXXXXX")
  {
    printf 'format=scratch-apply-plan-v1\n'
    printf '%s\n' "$output" |
      awk -F= '/^PVE_SCRATCH_BOOT_ID=|^PVE_SCRATCH_PLAN_SHA256=|^PVE_SCRATCH_FINDINGS_SHA256=/ {print}'
  } > "$temporary"
  chmod 0600 "$temporary"
  [[ $(wc -l < "$temporary") == 4 ]] || fail 'host preview did not return a complete plan lock'
  mv -fT -- "$temporary" "$lock_file"
  load_plan_lock
  [[ $expected_plan == "$plan_sha" ]] || fail 'host preview recorded a different source plan'
  printf 'saved_plan_lock=%s\n' "$lock_file"
elif [[ $mode == check ]]; then
  run_remote check '' "$plan_sha" '' ''
elif [[ $mode == apply ]]; then
  load_plan_lock
  [[ $plan_sha == "$expected_plan" ]] || fail 'sources or captures changed since preview'
  [[ $confirmation == "$expected_confirmation" ]] ||
    fail "apply requires --confirm-discard=$expected_confirmation"
  run_remote check "$expected_boot" "$expected_plan" "$expected_findings" ''
  run_remote apply "$expected_boot" "$expected_plan" "$expected_findings" "$confirmation"
else
  run_remote rollback '' "$plan_sha" '' ''
fi
