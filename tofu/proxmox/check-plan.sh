#!/usr/bin/env bash
set -euo pipefail

# Pipe `tofu show -json saved.tfplan` here; never save the JSON containing secrets.
mode=${1:-}
[[ -z $mode || $mode == --disposable-create || $mode == --disposable-destroy || $mode == --fedora-create || $mode == --fedora-start ]] || {
  echo 'usage: check-plan.sh [--disposable-create|--disposable-destroy|--fedora-create|--fedora-start] < plan.json' >&2
  exit 2
}

if ! jq -e --arg mode "$mode" '
  type == "object" and
  (.format_version | type == "string") and
  ((.resource_changes == null) or (.resource_changes | type == "array")) and
  (
    (.resource_changes // []) as $changes |
    if $mode == "--disposable-destroy" then
      ($changes | length == 1) and
      ($changes[0].address == "module.disposable[0].proxmox_virtual_environment_vm.this") and
      ($changes[0].type == "proxmox_virtual_environment_vm") and
      ($changes[0].change.actions == ["delete"])
    elif $mode == "--disposable-create" then
      ($changes | length == 1) and
      ($changes[0].address == "module.disposable[0].proxmox_virtual_environment_vm.this") and
      ($changes[0].type == "proxmox_virtual_environment_vm") and
      ($changes[0].change.actions == ["create"]) and
      ($changes[0].change.after.vm_id == 9900) and
      ($changes[0].change.after.name == "r720-disposable") and
      ($changes[0].change.after.pool_id == "tofu-vms") and
      ($changes[0].change.after.cpu[0].cores == 2) and
      ($changes[0].change.after.memory[0].dedicated == 4096) and
      ($changes[0].change.after.network_device | length == 1) and
      ($changes[0].change.after.network_device[0].bridge == "vmbr0") and
      ($changes[0].change.after.disk | length == 1) and
      ($changes[0].change.after.disk[0].datastore_id == "fast-vm") and
      ($changes[0].change.after.disk[0].file_format == "raw") and
      ($changes[0].change.after.disk[0].import_from == "local:import/Fedora-Cloud-Base-Generic-44-1.7.x86_64.qcow2") and
      ($changes[0].change.after.agent[0].enabled == true) and
      ($changes[0].change.after.initialization[0].ip_config[0].ipv4[0].address == "dhcp")
    elif $mode == "--fedora-create" then
      ($changes | length == 1) and
      ($changes[0].address == "module.fedora[0].proxmox_virtual_environment_vm.this") and
      ($changes[0].type == "proxmox_virtual_environment_vm") and
      ($changes[0].change.actions == ["create"]) and
      ($changes[0].change.after.vm_id == 100) and
      ($changes[0].change.after.name == "fedora-dev") and
      ($changes[0].change.after.node_name == "pve") and
      ($changes[0].change.after.pool_id == "tofu-vms") and
      ($changes[0].change.after.cpu[0].cores == 8) and
      ($changes[0].change.after.cpu[0].type == "host") and
      ($changes[0].change.after.memory[0].dedicated == 32768) and
      ($changes[0].change.after.network_device | length == 1) and
      ($changes[0].change.after.network_device[0].bridge == "vmbr0") and
      ($changes[0].change.after.network_device[0].model == "virtio") and
      ($changes[0].change.after.disk | length == 1) and
      ($changes[0].change.after.disk[0].datastore_id == "fast-vm") and
      ($changes[0].change.after.disk[0].file_format == "raw") and
      ($changes[0].change.after.disk[0].import_from == "local:import/Fedora-Cloud-Base-Generic-44-1.7.x86_64.qcow2") and
      ($changes[0].change.after.disk[0].interface == "scsi0") and
      ($changes[0].change.after.disk[0].size == 300) and
      ($changes[0].change.after.agent[0].enabled == true) and
      ($changes[0].change.after.agent[0].wait_for_ip[0].disabled == true) and
      ($changes[0].change.after.operating_system[0].type == "l26") and
      ($changes[0].change.after.initialization[0].ip_config[0].ipv4[0].address == "dhcp") and
      ($changes[0].change.after.initialization[0].user_account[0].username == "mpeter") and
      ($changes[0].change.after.on_boot == true) and
      ($changes[0].change.after.protection == true) and
      ($changes[0].change.after.started == true) and
      ($changes[0].change.after.stop_on_destroy == true)
    elif $mode == "--fedora-start" then
      ($changes | length == 1) and
      ($changes[0].address == "module.fedora[0].proxmox_virtual_environment_vm.this") and
      ($changes[0].type == "proxmox_virtual_environment_vm") and
      ($changes[0].change.actions == ["update"]) and
      ($changes[0].change.before.vm_id == 100) and
      ($changes[0].change.before.name == "fedora-dev") and
      ($changes[0].change.before.started == false) and
      ($changes[0].change.after.vm_id == 100) and
      ($changes[0].change.after.name == "fedora-dev") and
      ($changes[0].change.after.node_name == "pve") and
      ($changes[0].change.after.pool_id == "tofu-vms") and
      ($changes[0].change.after.cpu[0].cores == 8) and
      ($changes[0].change.after.cpu[0].type == "host") and
      ($changes[0].change.after.memory[0].dedicated == 32768) and
      ($changes[0].change.after.network_device | length == 1) and
      ($changes[0].change.after.network_device[0].bridge == "vmbr0") and
      ($changes[0].change.after.disk | length == 1) and
      ($changes[0].change.after.disk[0].datastore_id == "fast-vm") and
      ($changes[0].change.after.disk[0].file_format == "raw") and
      ($changes[0].change.after.disk[0].size == 300) and
      ($changes[0].change.after.agent[0].enabled == true) and
      ($changes[0].change.after.agent[0].wait_for_ip[0].disabled == true) and
      ($changes[0].change.after.operating_system[0].type == "l26") and
      ($changes[0].change.after.on_boot == true) and
      ($changes[0].change.after.protection == true) and
      ($changes[0].change.after.started == true) and
      ($changes[0].change.after.stop_on_destroy == true)
    else
      all($changes[];
        (.address == "module.disposable[0].proxmox_virtual_environment_vm.this" or .address == "module.fedora[0].proxmox_virtual_environment_vm.this") and
        .type == "proxmox_virtual_environment_vm" and
        .change.actions == ["no-op"]
      )
    end
  )
' >/dev/null 2>&1; then
  echo 'plan gate rejected unexpected resource type or action' >&2
  exit 1
fi

echo 'plan gate PASS'
