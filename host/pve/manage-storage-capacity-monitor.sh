#!/usr/bin/env bash
set -euo pipefail
umask 077

host_only=0
if [[ ${1:-} == --host ]]; then
  host_only=1
  mode=${2:-}
else
  mode=${1:-}
fi
[[ $mode == preview || $mode == check || $mode == apply || $mode == rollback ]] || {
  printf 'usage: %s preview|check|apply|rollback\n' "$0" >&2
  exit 2
}

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
monitor_source="$script_dir/storage-capacity-monitor.sh"
service_source="$script_dir/systemd/pve-storage-capacity-monitor.service"
timer_source="$script_dir/systemd/pve-storage-capacity-monitor.timer"
marker_text='homelab-infra:pve-storage-capacity-monitor:v2'
previous_marker_text='homelab-infra:pve-storage-capacity-monitor:v1'
recovery_mode=${PVE_STORAGE_CAPACITY_RECOVERY:-0}
previous_monitor_sha256='c0e1c3c3b15df1544fc31b6ff3ece0d4cf4d4b7140431051db817e7fae9db60f'
if [[ -n ${PVE_STORAGE_CAPACITY_TEST_ROOT:-} ]]; then
  previous_monitor_sha256=${PVE_STORAGE_CAPACITY_TEST_LEGACY_MONITOR_SHA256:-$previous_monitor_sha256}
fi
host=pve
pve_host=192.168.0.188

host_main() {
  local operation=$1 test_root=${PVE_STORAGE_CAPACITY_TEST_ROOT:-}
  local monitor_target=/usr/local/sbin/pve-storage-capacity-monitor
  local service_target=/etc/systemd/system/pve-storage-capacity-monitor.service
  local timer_target=/etc/systemd/system/pve-storage-capacity-monitor.timer
  local state_target=/var/lib/pve-storage-capacity-monitor

  if [[ -n $test_root ]]; then
    monitor_target="$test_root$monitor_target"
    service_target="$test_root$service_target"
    timer_target="$test_root$timer_target"
    state_target="$test_root$state_target"
  else
    [[ $(id -u) == 0 ]] || { echo 'host operation requires root' >&2; return 1; }
  fi

  local marker="$state_target/managed-by-code"
  local path
  managed_files_match() {
    cmp -s "$monitor_target" "$monitor_source" &&
      cmp -s "$service_target" "$service_source" &&
      cmp -s "$timer_target" "$timer_source" &&
      [[ -f $marker && ! -L $marker ]] &&
      [[ $(<"$marker") == "$marker_text" ]]
  }

  previous_managed_files_match() {
    [[ -f $marker && ! -L $marker ]] &&
      [[ $(<"$marker") == "$previous_marker_text" ]] &&
      [[ $(sha256sum "$monitor_target" | awk '{print $1}') == "$previous_monitor_sha256" ]] &&
      cmp -s "$service_target" "$service_source" &&
      cmp -s "$timer_target" "$timer_source"
  }

  managed_files_owned() {
    managed_files_match || previous_managed_files_match
  }

  rollback_state_known() {
    local path name saved
    [[ -d $state_target && ! -L $state_target ]] || return 1
    while IFS= read -r -d '' path; do
      [[ -f $path && ! -L $path ]] || return 1
      name=${path##*/}
      case "$name" in
        managed-by-code) [[ $path == "$marker" ]] || return 1 ;;
        rpool|fast-vm|scratch)
          saved=$(<"$path")
          [[ $saved == normal || $saved == warning || $saved == critical ||
            $saved == critical:pool_unreadable ]] || return 1
          ;;
        *)
          [[ $name =~ ^\.(rpool|fast-vm|scratch)\.[[:alnum:]]{6}$ ||
            $name =~ ^\.managed-by-code\.[[:alnum:]]{6}$ ]] || return 1
          ;;
      esac
    done < <(find "$state_target" -mindepth 1 -maxdepth 1 -print0)
  }

  recovery_files_known() {
    local installed_marker
    if [[ -e $marker || -L $marker ]]; then
      [[ -f $marker && ! -L $marker ]] || return 1
      installed_marker=$(<"$marker")
      [[ $installed_marker == "$marker_text" || $installed_marker == "$previous_marker_text" ]] ||
        return 1
    fi
    for path in "$monitor_target" "$service_target" "$timer_target"; do
      [[ ! -e $path && ! -L $path ]] && continue
      [[ -f $path && ! -L $path ]] || return 1
      case "$path" in
        "$monitor_target")
          cmp -s "$path" "$monitor_source" ||
            [[ $(sha256sum "$path" | awk '{print $1}') == "$previous_monitor_sha256" ]] || return 1
          ;;
        "$service_target") cmp -s "$path" "$service_source" || return 1 ;;
        "$timer_target") cmp -s "$path" "$timer_source" || return 1 ;;
      esac
    done
    if [[ -e $state_target || -L $state_target ]]; then
      [[ -d $state_target && ! -L $state_target ]] || return 1
    fi
  }

  check_pool_preflight() {
    local pool row observed_pool capacity health extra
    for pool in rpool fast-vm scratch; do
      row=$(zpool list -H -p -o name,capacity,health "$pool") || {
        printf 'cannot read current pool state: %s\n' "$pool" >&2
        return 1
      }
      [[ -n $row && $row != *$'\n'* ]] || {
        printf 'unexpected pool result for %s\n' "$pool" >&2
        return 1
      }
      read -r observed_pool capacity health extra <<< "$row"
      [[ $observed_pool == "$pool" && $capacity =~ ^[0-9]{1,3}$ && $health == ONLINE && -z ${extra:-} ]] || {
        printf 'pool preflight did not pass for %s\n' "$pool" >&2
        return 1
      }
      printf 'live pool: %s capacity=%s%% health=%s\n' "$pool" "$capacity" "$health"
    done
  }

  if [[ $operation == rollback ]]; then
    managed_files_match || { echo 'refusing rollback: installed files are missing or differ' >&2; return 1; }
    rollback_state_known || {
      echo 'refusing rollback: monitor state directory contains unknown or invalid data' >&2
      return 1
    }
    systemctl disable --now pve-storage-capacity-monitor.timer
    systemctl stop pve-storage-capacity-monitor.service
    local -a state_entries=()
    while IFS= read -r -d '' path; do
      [[ $path == "$marker" ]] || state_entries+=("$path")
    done < <(find "$state_target" -mindepth 1 -maxdepth 1 -print0)
    if ((${#state_entries[@]})); then
      rm -- "${state_entries[@]}"
    fi
    rm -- "$monitor_target" "$service_target" "$timer_target"
    rm -- "$marker"
    rmdir -- "$state_target"
    systemctl daemon-reload
    echo 'PVE storage capacity monitor rollback PASS'
    return
  fi

  if [[ $recovery_mode == 1 ]]; then
    recovery_files_known || {
      echo 'refusing recovery: monitor files are not a known old/new installation state' >&2
      return 1
    }
  elif [[ -e $marker || -L $marker ]]; then
    [[ -f $marker && ! -L $marker && $(<"$marker") == "$marker_text" ]] || {
      if ! previous_managed_files_match; then
        echo 'refusing to overwrite an unknown ownership marker or modified managed file' >&2
        return 1
      fi
    }
    managed_files_owned || { echo 'refusing to replace managed files that differ from known versions' >&2; return 1; }
  else
    for path in "$monitor_target" "$service_target" "$timer_target" "$state_target"; do
      [[ ! -e $path && ! -L $path ]] || {
        printf 'refusing to overwrite an existing unowned path: %s\n' "$path" >&2
        return 1
      }
    done
  fi

  if [[ $operation == check ]]; then
    managed_files_match || { echo 'PVE storage capacity monitor files differ' >&2; return 1; }
    systemctl is-enabled --quiet pve-storage-capacity-monitor.timer || {
      echo 'PVE storage capacity timer is not enabled' >&2
      return 1
    }
    systemctl is-active --quiet pve-storage-capacity-monitor.timer || {
      echo 'PVE storage capacity timer is not active' >&2
      return 1
    }
    echo 'PVE storage capacity monitor check PASS'
    return
  fi

  if [[ $operation == preview ]]; then
    if [[ -z $test_root ]]; then check_pool_preflight; fi
    for path in "$monitor_target" "$service_target" "$timer_target"; do
      if [[ -e $path ]]; then
        printf 'managed target already present: %s\n' "$path"
      else
        printf 'target absent; would create: %s\n' "$path"
      fi
    done
    printf 'policy: warning >=80%%, critical >=90%%, evaluated every five minutes; journal only\n'
    return
  fi

  if [[ -z $test_root ]]; then check_pool_preflight; fi

  mkdir -p -- "$(dirname -- "$monitor_target")" "$(dirname -- "$service_target")" \
    "$(dirname -- "$timer_target")" "$state_target"
  chmod 0750 "$state_target"
  install_managed_file() {
    local source=$1 target=$2 permissions=$3 temporary
    temporary=$(mktemp "$(dirname -- "$target")/.$(basename -- "$target").XXXXXX")
    if [[ -n $test_root ]]; then
      install -m "$permissions" "$source" "$temporary"
    else
      install -o root -g root -m "$permissions" "$source" "$temporary"
    fi
    mv -fT -- "$temporary" "$target"
  }
  install_managed_file "$monitor_source" "$monitor_target" 0755
  install_managed_file "$service_source" "$service_target" 0644
  install_managed_file "$timer_source" "$timer_target" 0644
  temporary_marker=$(mktemp "$state_target/.managed-by-code.XXXXXX")
  printf '%s\n' "$marker_text" > "$temporary_marker"
  chmod 0644 "$temporary_marker"
  mv -fT -- "$temporary_marker" "$marker"
  systemctl daemon-reload
  systemctl enable --now pve-storage-capacity-monitor.timer
  host_main check
}

if [[ -n ${PVE_STORAGE_CAPACITY_TEST_ROOT:-} || $host_only == 1 ]]; then
  host_main "$mode"
  exit
fi

for command_name in base64 secret-tool sshpass tar; do
  command -v "$command_name" >/dev/null || {
    printf 'missing required command: %s\n' "$command_name" >&2
    exit 1
  }
done

export DISPLAY=:0 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus SSHPASS
SSHPASS=$(secret-tool lookup homelab-pve-host "$pve_host" account root)
[[ -n $SSHPASS ]] || { echo 'missing PVE credential in desktop keyring' >&2; exit 1; }

remote_bootstrap=$(cat <<'REMOTE'
set -euo pipefail
temporary=$(mktemp -d /run/pve-storage-capacity-monitor.XXXXXX)
trap 'rm -rf -- "$temporary"' EXIT
tar -xf - -C "$temporary"
bash "$temporary/manage-storage-capacity-monitor.sh" --host "$1"
REMOTE
)
bootstrap_b64=$(printf '%s' "$remote_bootstrap" | base64 -w0)
remote_command="bash -c \"\$(printf '%s' '$bootstrap_b64' | base64 -d)\" -- '$mode'"

tar -C "$script_dir" -cf - \
  manage-storage-capacity-monitor.sh \
  storage-capacity-monitor.sh \
  systemd/pve-storage-capacity-monitor.service \
  systemd/pve-storage-capacity-monitor.timer |
  sshpass -e ssh -F /dev/null -o ConnectTimeout=10 -o StrictHostKeyChecking=yes \
    -o UserKnownHostsFile=/home/mpeter/.ssh/known_hosts -o ControlMaster=no \
    -o ControlPath=none -o PreferredAuthentications=password "root@$pve_host" \
    "$remote_command"
