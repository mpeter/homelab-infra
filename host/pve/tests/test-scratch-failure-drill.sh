#!/usr/bin/env bash
set -euo pipefail

script_dir=$(cd -- "$(dirname -- "$0")" && pwd)
plan_helper="$script_dir/../check_scratch_apply_plan.py"
whole_c=/dev/disk/by-id/nvme-INTEL_SSDPEKKF512G8_PHHH8505034Q512H_1
whole_d=/dev/disk/by-id/nvme-INTEL_SSDPEKKF512G8_BTHH8244042V512D_1

if output=$(python3 "$plan_helper" validate-zpool-status - "$whole_c" "$whole_d" 2>&1 <<'STATUS'
  pool: scratch
 state: UNAVAIL
status: One or more devices could not be opened. Sufficient replicas are not available.
 action: Attach the missing device and online it using 'zpool online'.
config:
	NAME STATE READ WRITE CKSUM
	scratch UNAVAIL 0 0 0
	  /dev/disk/by-id/nvme-INTEL_SSDPEKKF512G8_PHHH8505034Q512H_1-part1 ONLINE 0 0 0
	  /dev/disk/by-id/nvme-INTEL_SSDPEKKF512G8_BTHH8244042V512D_1-part1 UNAVAIL 0 0 0
errors: No known data errors
STATUS
); then
  printf 'FAIL: unavailable scratch stripe passed the topology validator\n' >&2
  exit 1
else
  result=$?
fi

[[ $result == 1 ]] || {
  printf 'FAIL: validator exited %s instead of 1\n%s\n' "$result" "$output" >&2
  exit 1
}
grep -Fq 'scratch stripe members are not direct ONLINE children' <<< "$output" || {
  printf 'FAIL: unexpected refusal reason\n%s\n' "$output" >&2
  exit 1
}

printf 'PASS: synthetic scratch member loss is refused by the read-only topology validator\n'
