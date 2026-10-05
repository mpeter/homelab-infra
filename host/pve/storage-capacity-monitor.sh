#!/usr/bin/env bash
set -euo pipefail

fail() { printf 'PVE storage capacity monitor: %s\n' "$*" >&2; exit 1; }

if [[ ${PVE_STORAGE_CAPACITY_TEST_MODE:-0} != 1 ]]; then
  [[ $(id -u) == 0 ]] || fail 'must run as root'
fi

state_dir=${PVE_STORAGE_CAPACITY_STATE_DIR:-/var/lib/pve-storage-capacity-monitor}
[[ ! -L $state_dir ]] || fail "state directory is a symlink: $state_dir"
mkdir -p -- "$state_dir"

for command_name in logger zpool; do
  command -v "$command_name" >/dev/null || fail "missing required command: $command_name"
done

pools=(rpool fast-vm scratch)
capacities=()
health_states=()
levels=()
state_values=()
previous_states=()
state_existed=()

for pool in "${pools[@]}"; do
  readable=0
  if output=$(zpool list -H -p -o name,capacity,health "$pool" 2>/dev/null); then
    [[ -n $output && $output != *$'\n'* ]] || fail "unexpected zpool output for $pool"
    read -r output_pool capacity health extra <<< "$output"
    [[ $output_pool == "$pool" && -z ${extra:-} ]] || fail "unexpected zpool row for $pool"
    [[ $capacity =~ ^[0-9]{1,3}$ ]] && (( capacity <= 100 )) || fail "invalid capacity for $pool"
    [[ $health =~ ^[A-Z_]+$ ]] || fail "invalid health status for $pool"

    if [[ $health != ONLINE || $capacity -ge 90 ]]; then
      levels+=(critical)
      state_values+=(critical)
    elif (( capacity >= 80 )); then
      levels+=(warning)
      state_values+=(warning)
    else
      levels+=(normal)
      state_values+=(normal)
    fi
    readable=1
  fi
  if (( readable == 0 )); then
    capacities+=(unknown)
    health_states+=(UNKNOWN)
    levels+=(critical)
    state_values+=(critical:pool_unreadable)
  else
    capacities+=("$capacity")
    health_states+=("$health")
  fi

  state_file="$state_dir/$pool"
  if [[ -e $state_file ]]; then
    [[ -f $state_file && ! -L $state_file ]] || fail "invalid state file for $pool"
    previous=$(<"$state_file")
    [[ $previous == normal || $previous == warning || $previous == critical ||
      $previous == critical:pool_unreadable ]] || fail "invalid saved state for $pool"
    state_existed+=(1)
  else
    previous=normal
    state_existed+=(0)
  fi
  previous_states+=("$previous")
done

for index in "${!pools[@]}"; do
  pool=${pools[$index]}
  capacity=${capacities[$index]}
  health=${health_states[$index]}
  level=${levels[$index]}
  state_value=${state_values[$index]}
  previous=${previous_states[$index]}
  previous_level=${previous%%:*}

  if [[ $state_value != "$previous" || ${state_existed[$index]} == 0 ]]; then
    if [[ $level == "$previous_level" && $level == normal ]]; then
      temporary=$(mktemp "$state_dir/.$pool.XXXXXX")
      printf '%s\n' "$state_value" > "$temporary"
      chmod 0640 "$temporary"
      mv -f -- "$temporary" "$state_dir/$pool"
      continue
    fi

    if [[ $level == normal ]]; then
      logger --priority daemon.notice --tag pve-storage-capacity-monitor \
        "pool=$pool capacity=${capacity}% health=$health level=normal recovered_from=$previous_level"
    elif [[ $health == UNKNOWN ]]; then
      logger --priority daemon.crit --tag pve-storage-capacity-monitor \
        "pool=$pool capacity=unknown health=UNKNOWN level=critical reason=pool_unreadable"
    elif [[ $health != ONLINE ]]; then
      logger --priority daemon.crit --tag pve-storage-capacity-monitor \
        "pool=$pool capacity=${capacity}% health=$health level=critical reason=pool_health"
    elif [[ $level == critical ]]; then
      logger --priority daemon.crit --tag pve-storage-capacity-monitor \
        "pool=$pool capacity=${capacity}% health=$health level=critical threshold=90%"
    else
      logger --priority daemon.warning --tag pve-storage-capacity-monitor \
        "pool=$pool capacity=${capacity}% health=$health level=warning threshold=80%"
    fi

    temporary=$(mktemp "$state_dir/.$pool.XXXXXX")
    printf '%s\n' "$state_value" > "$temporary"
    chmod 0640 "$temporary"
    mv -f -- "$temporary" "$state_dir/$pool"
  fi
done
