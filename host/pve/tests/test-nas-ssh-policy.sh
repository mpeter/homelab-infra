#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
stage=$(mktemp -d)
trap 'rm -rf -- "$stage"' EXIT
mkdir "$stage/bin"

cat >"$stage/bin/secret-tool" <<'SH'
#!/usr/bin/env bash
printf 'test-only\n'
SH
cat >"$stage/bin/sshpass" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
[[ $1 == -e && $2 == ssh ]]
shift 2
config=$(ssh -G -F /dev/null "$@" 2>/dev/null)
grep -Fxq 'stricthostkeychecking true' <<< "$config" || {
  echo 'NAS SSH must require an already trusted host key' >&2
  exit 99
}
case ${!#} in
  *'hardware/pci'*)
    echo '[{"id":"0000:02:00.0","vendor":"0x1000","device":"0x0087","subsystem_vendor":"0x1028","subsystem_device":"0x1f38","iommugroup":32}]' ;;
  *'--check-node'*) echo '[{"id":"nas-hba","checks":[]}]' ;;
  *'/cluster/mapping/pci'*)
    echo '[{"id":"nas-hba","description":"LSI SAS2308 for TrueNAS VM 200","map":["node=pve,path=0000:02:00.0,id=1000:0087,subsystem-id=1028:1f38,iommugroup=32"]}]' ;;
  'qm status 200') echo 'status: running' ;;
  *'/driver)'*) echo 'vfio-pci' ;;
  'zpool list -H -o name') printf 'rpool\nfast-vm\n' ;;
  *) printf 'unexpected remote command: %s\n' "${!#}" >&2; exit 98 ;;
esac
SH
chmod +x "$stage/bin/secret-tool" "$stage/bin/sshpass"
export PATH="$stage/bin:$PATH"

bash "$repo_root/host/pve/manage-nas-pci-mapping.sh" check
bash "$repo_root/host/pve/check-nas-passthrough.sh"
printf 'NAS SSH policy tests PASS (no remote connections)\n'
