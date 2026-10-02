#!/usr/bin/env bash
set -euo pipefail

mode=${1:-}
[[ $mode == preview || $mode == check || $mode == apply || $mode == rollback ]] || {
  echo 'usage: manage-nas-pci-mapping.sh preview|check|apply|rollback' >&2
  exit 2
}

pve_host=192.168.0.188
node=pve
mapping_id=nas-hba
device_path=0000:02:00.0
device_id=1000:0087
subsystem_id=1028:1f38
iommu_group=32
description='LSI SAS2308 for TrueNAS VM 200'
repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)

export DISPLAY=:0 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus SSHPASS
SSHPASS=$(secret-tool lookup homelab-pve-host "$pve_host" account root)
[[ -n $SSHPASS ]] || { echo 'missing PVE credential in desktop keyring' >&2; exit 1; }
pve() { sshpass -e ssh -o ConnectTimeout=10 "root@$pve_host" "$*"; }
fail() { printf 'NAS PCI mapping %s: %s\n' "$mode" "$*" >&2; exit 1; }

if [[ $mode != rollback ]]; then
  inventory=$(pve "pvesh get /nodes/$node/hardware/pci --pci-class-blacklist '' --output-format json")
  jq -e --arg path "$device_path" --arg id "$device_id" --arg subsystem "$subsystem_id" --argjson group "$iommu_group" '
    [.[] | select(.iommugroup == $group)] as $group_devices |
    ($group_devices | length == 1) and $group_devices[0].id == $path and
    $group_devices[0].vendor == ("0x" + ($id | split(":")[0])) and
    $group_devices[0].device == ("0x" + ($id | split(":")[1])) and
    $group_devices[0].subsystem_vendor == ("0x" + ($subsystem | split(":")[0])) and
    $group_devices[0].subsystem_device == ("0x" + ($subsystem | split(":")[1]))
  ' <<< "$inventory" >/dev/null || fail 'live PCI identity or IOMMU group differs'
fi

mapping=$(pve 'pvesh get /cluster/mapping/pci --output-format json')
mapping_count=$(jq --arg id "$mapping_id" '[.[] | select(.id == $id)] | length' <<< "$mapping")
mapping_matches() {
  jq -e --arg id "$mapping_id" --arg node "$node" --arg path "$device_path" \
    --arg pci_id "$device_id" --arg subsystem "$subsystem_id" \
    --argjson group "$iommu_group" --arg description "$description" '
    def fields: split(",") | map(split("=")) | from_entries;
    [.[] | select(.id == $id)] as $matches |
    ($matches | length == 1) and
    ($matches[0].description == $description) and
    ($matches[0].map | length == 1) and
    (($matches[0].map[0] | fields) as $entry |
      $entry.node == $node and $entry.path == $path and $entry.id == $pci_id and
      $entry["subsystem-id"] == $subsystem and ($entry.iommugroup | tonumber) == $group
    )
  ' <<< "$mapping" >/dev/null
}

if [[ $mode == check ]]; then
  [[ $mapping_count == 1 ]] && mapping_matches || fail 'mapping does not match the pinned SAS2308 identity'
  checks=$(pve "pvesh get /cluster/mapping/pci --check-node $node --output-format json")
  jq -e --arg id "$mapping_id" 'any(.[]; .id == $id and ((.checks // []) | length == 0))' <<< "$checks" >/dev/null || fail 'PVE reports a PCI mapping error'
  printf 'NAS PCI mapping check PASS: %s -> %s (%s, IOMMU group %s)\n' "$mapping_id" "$device_path" "$device_id" "$iommu_group"
  exit 0
fi

if [[ $mode == preview ]]; then
  if [[ $mapping_count == 0 ]]; then
    printf 'NAS PCI mapping preview: create %s on %s for %s (%s, subsystem %s, IOMMU group %s); no host driver binding change\n' \
      "$mapping_id" "$node" "$device_path" "$device_id" "$subsystem_id" "$iommu_group"
  else
    mapping_matches || fail 'mapping ID already exists with different content'
    printf 'NAS PCI mapping preview: %s already matches the pinned SAS2308 identity; no change\n' "$mapping_id"
  fi
  exit 0
fi

vm_config=$(pve 'qm config 200')
vm_status=$(pve 'qm status 200')
if [[ $mode == apply ]]; then
  [[ $vm_status == *'status: stopped'* ]] || fail 'NAS VM must be stopped'
  [[ $vm_config != *hostpci* ]] || fail 'NAS VM already has a PCI device configured'
  if [[ $mapping_count == 0 ]]; then
    "$repo_root/host/pve/backup-host-config.sh"
    pve "pvesh create /cluster/mapping/pci --id $mapping_id --description '$description' --map 'node=$node,path=$device_path,id=$device_id,subsystem-id=$subsystem_id,iommugroup=$iommu_group,description=SAS2308'"
  else
    mapping_matches || fail 'mapping ID already exists with different content'
  fi
  bash "$repo_root/host/pve/manage-tofu-identity.sh" apply
  bash "$repo_root/host/pve/manage-nas-pci-mapping.sh" check
  exit 0
fi

[[ $mapping_count == 1 ]] && mapping_matches || fail 'refusing to remove a missing or changed mapping'
[[ $vm_status == *'status: stopped'* ]] || fail 'NAS VM must be stopped before mapping rollback'
[[ $vm_config != *hostpci* ]] || fail 'remove the NAS VM PCI assignment through its gated OpenTofu plan first'
"$repo_root/host/pve/backup-host-config.sh"
pve "pveum acl delete /mapping/pci/$mapping_id --roles OpenTofuMappingUse --users tofu@pve"
pve "pveum acl delete /mapping/pci/$mapping_id --roles OpenTofuMappingUse --tokens tofu@pve!opentofu"
pve "pvesh delete /cluster/mapping/pci/$mapping_id"
if pve "pvesh get /cluster/mapping/pci/$mapping_id" >/dev/null 2>&1; then
  fail 'mapping still exists after rollback'
fi
printf 'NAS PCI mapping rollback PASS: %s removed; HBA host driver binding was not changed\n' "$mapping_id"
