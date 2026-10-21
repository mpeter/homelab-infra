#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
scratch_root=${XDG_CACHE_HOME:-$HOME/.cache}/agent-scratch
mkdir -p "$scratch_root"
test_dir=$(mktemp -d "$scratch_root/homelab-smart-cron.XXXXXX")
trap '/bin/rm -rf -- "$test_dir"' EXIT

devices="$test_dir/devices"
mkdir -p "$devices"
for i in {1..8}; do
  touch "$devices/ata-CT1000MX500SSD1_disk$i" "$devices/ata-CT1000MX500SSD1_disk$i-part1"
done

cat > "$test_dir/smartctl" <<'FAKE'
#!/usr/bin/env bash
set -euo pipefail
[[ $# == 3 && $1 == -t && ( $2 == short || $2 == long ) ]]
name=${3##*/}
printf '%s\t%s\n' "$2" "$name" >> "$SMART_TEST_CALLS"
case ",$SMART_TEST_FAILURES," in
  *",$name,"*) exit 7;;
esac
FAKE
chmod 755 "$test_dir/smartctl"

mapfile -t commands < <(awk '
  /^### TrueNAS SMART Cron Job target pattern/ { section = 1 }
  section && /^```sh$/ { code = 1; next }
  code && /^```$/ { exit }
  code { print }
' "$repo_root/docs/storage-plan.md")
[[ ${#commands[@]} == 2 ]]

for index in 0 1; do
  test_type=short
  [[ $index == 0 ]] || test_type=long
  cron_command=${commands[$index]//\/usr\/sbin\/smartctl/$test_dir\/smartctl}
  cron_command=${cron_command//\/dev\/disk\/by-id/$devices}
  for failures in disk1 disk8 disk1,disk3 none; do
    failure_names=${failures//disk/ata-CT1000MX500SSD1_disk}
    : > "$test_dir/calls"
    status=0
    SMART_TEST_CALLS="$test_dir/calls" SMART_TEST_FAILURES="$failure_names" \
      sh -c "$cron_command" > "$test_dir/output" 2>&1 || status=$?
    if [[ $failures == none ]]; then
      [[ $status == 0 ]] || { cat "$test_dir/output"; exit 1; }
    elif [[ $status == 0 ]]; then
      printf 'FAIL: %s test masks failure(s) on %s\n' "$test_type" "$failures" >&2
      exit 1
    fi
    [[ $(wc -l < "$test_dir/calls") == 8 ]]
    for i in {1..8}; do
      name="ata-CT1000MX500SSD1_disk$i"
      grep -Fxq "$test_type"$'\t'"$name" "$test_dir/calls"
      result=0
      case ",$failure_names," in *",$name,"*) result=7;; esac
      grep -Fxq "$devices/$name: exit=$result" "$test_dir/output"
    done
  done
done

printf 'PASS: short/long SMART commands report all eight whole-disk results and preserve failures\n'
