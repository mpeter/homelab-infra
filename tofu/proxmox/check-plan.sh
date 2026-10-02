#!/usr/bin/env bash
set -euo pipefail

# Pipe `tofu show -json saved.tfplan` here; never save the JSON containing secrets.
mode=${1:-}
[[ -z $mode || $mode == --disposable-create || $mode == --disposable-destroy || $mode == --fedora-create || $mode == --fedora-start || $mode == --nas-create || $mode == --nas-attach || $mode == --nas-install-complete || $mode == --nas-start || $mode == --nas-stop ]] || {
  echo 'usage: check-plan.sh [--disposable-create|--disposable-destroy|--fedora-create|--fedora-start|--nas-create|--nas-attach|--nas-install-complete|--nas-start|--nas-stop] < plan.json' >&2
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
    elif $mode == "--nas-attach" then
      ($changes | map(select(.change.actions != ["no-op"]))) as $mutations |
      all($changes[];
        (.address == "module.fedora[0].proxmox_virtual_environment_vm.this" or .address == "module.nas[0].proxmox_virtual_environment_vm.this") and
        .type == "proxmox_virtual_environment_vm" and
        (.change.actions == ["no-op"] or (.address == "module.nas[0].proxmox_virtual_environment_vm.this" and .change.actions == ["update"]))
      ) and
      ($mutations | length == 1) and
      ($mutations[0].address == "module.nas[0].proxmox_virtual_environment_vm.this") and
      ($mutations[0].change.before.vm_id == 200) and
      ($mutations[0].change.before.started == false) and
      (($mutations[0].change.before.hostpci // []) | length == 0) and
      ($mutations[0].change.actions == ["update"]) and
      (($mutations[0].change.before | del(.hostpci)) == ($mutations[0].change.after | del(.hostpci))) and
      ($mutations[0].change.after.vm_id == 200) and
      ($mutations[0].change.after.name == "nas") and
      ($mutations[0].change.after.node_name == "pve") and
      ($mutations[0].change.after.pool_id == "tofu-vms") and
      ($mutations[0].change.after.machine == "q35") and
      ($mutations[0].change.after.cpu[0].cores == 4) and
      ($mutations[0].change.after.memory[0].dedicated == 16384) and
      ($mutations[0].change.after.network_device | length == 1) and
      ($mutations[0].change.after.disk | length == 1) and
      ($mutations[0].change.after.disk[0].datastore_id == "fast-vm") and
      ($mutations[0].change.after.cdrom[0].file_id == "local:iso/TrueNAS-SCALE-25.10.7.iso") and
      ($mutations[0].change.after.boot_order == ["ide2", "scsi0"]) and
      ($mutations[0].change.after.hostpci | map(with_entries(select(.value != null and .value != "" and .value != false)))) == [{"device":"hostpci0","mapping":"nas-hba","pcie":true}] and
      ($mutations[0].change.after.on_boot == false) and
      ($mutations[0].change.after.protection == true) and
      ($mutations[0].change.after.started == false)
    elif $mode == "--nas-install-complete" then
      ($changes | map(select(.change.actions != ["no-op"]))) as $mutations |
      all($changes[];
        (.address == "module.fedora[0].proxmox_virtual_environment_vm.this" or .address == "module.nas[0].proxmox_virtual_environment_vm.this") and
        .type == "proxmox_virtual_environment_vm" and
        (.change.actions == ["no-op"] or (.address == "module.nas[0].proxmox_virtual_environment_vm.this" and .change.actions == ["update"]))
      ) and
      ($mutations | length == 1) and
      ($mutations[0].address == "module.nas[0].proxmox_virtual_environment_vm.this") and
      ($mutations[0].change.actions == ["update"]) and
      ($mutations[0].change.before.vm_id == 200) and
      ($mutations[0].change.before.started == true) and
      (
        ($mutations[0].change.before.cdrom // []) as $before_cdrom |
        ($before_cdrom | length == 0) or
        ($before_cdrom | length == 1 and
          .[0].file_id == "local:iso/TrueNAS-SCALE-25.10.7.iso" and .[0].interface == "ide2")
      ) and
      (
        $mutations[0].change.before.boot_order == ["ide2", "scsi0"] or
        $mutations[0].change.before.boot_order == ["scsi0"]
      ) and
      ($mutations[0].change.after.vm_id == 200) and
      ($mutations[0].change.after.started == false) and
      (($mutations[0].change.after.cdrom // []) | length == 1) and
      ($mutations[0].change.after.cdrom[0].file_id == "none") and
      ($mutations[0].change.after.cdrom[0].interface == "ide2") and
      ($mutations[0].change.after.boot_order == ["scsi0"]) and
      (($mutations[0].change.before | del(.started, .cdrom, .boot_order, .ipv4_addresses, .ipv6_addresses, .network_interface_names)) ==
        ($mutations[0].change.after | del(.started, .cdrom, .boot_order, .ipv4_addresses, .ipv6_addresses, .network_interface_names))) and
      (($mutations[0].change.after_unknown | with_entries(select(.value == true))) ==
        {ipv4_addresses:true,ipv6_addresses:true,network_interface_names:true})
    elif $mode == "--nas-start" or $mode == "--nas-stop" then
      ($changes | map(select(.change.actions != ["no-op"]))) as $mutations |
      all($changes[];
        (.address == "module.fedora[0].proxmox_virtual_environment_vm.this" or .address == "module.nas[0].proxmox_virtual_environment_vm.this") and
        .type == "proxmox_virtual_environment_vm" and
        (.change.actions == ["no-op"] or (.address == "module.nas[0].proxmox_virtual_environment_vm.this" and .change.actions == ["update"]))
      ) and
      ($mutations | length == 1) and
      ($mutations[0].address == "module.nas[0].proxmox_virtual_environment_vm.this") and
      ($mutations[0].change.before.vm_id == 200) and
      ($mutations[0].change.before.started == ($mode == "--nas-stop")) and
      ($mutations[0].change.actions == ["update"]) and
      (($mutations[0].change.before | del(.started, .ipv4_addresses, .ipv6_addresses, .network_interface_names)) ==
        ($mutations[0].change.after | del(.started, .ipv4_addresses, .ipv6_addresses, .network_interface_names))) and
      (($mutations[0].change.after_unknown | with_entries(select(.value == true))) ==
        {ipv4_addresses:true,ipv6_addresses:true,network_interface_names:true}) and
      ($mutations[0].change.after.vm_id == 200) and
      ($mutations[0].change.after.name == "nas") and
      ($mutations[0].change.after.node_name == "pve") and
      ($mutations[0].change.after.pool_id == "tofu-vms") and
      ($mutations[0].change.after.machine == "q35") and
      ($mutations[0].change.after.cpu[0].cores == 4) and
      ($mutations[0].change.after.memory[0].dedicated == 16384) and
      ($mutations[0].change.after.network_device | length == 1) and
      ($mutations[0].change.after.disk | length == 1) and
      ($mutations[0].change.after.disk[0].datastore_id == "fast-vm") and
      (($mutations[0].change.after.cdrom // []) | length == 1) and
      ($mutations[0].change.after.cdrom[0].file_id == "none") and
      ($mutations[0].change.after.cdrom[0].interface == "ide2") and
      ($mutations[0].change.after.boot_order == ["scsi0"]) and
      ($mutations[0].change.after.hostpci | map(with_entries(select(.value != null and .value != "" and .value != false)))) == [{"device":"hostpci0","mapping":"nas-hba","pcie":true}] and
      ($mutations[0].change.after.on_boot == false) and
      ($mutations[0].change.after.protection == true) and
      ($mutations[0].change.after.started == ($mode == "--nas-start"))
    elif $mode == "--nas-create" then
      ($changes | map(select(.change.actions != ["no-op"]))) as $mutations |
      all($changes[];
        (.address == "module.fedora[0].proxmox_virtual_environment_vm.this" or .address == "module.nas[0].proxmox_virtual_environment_vm.this") and
        .type == "proxmox_virtual_environment_vm" and
        (.change.actions == ["no-op"] or (.address == "module.nas[0].proxmox_virtual_environment_vm.this" and .change.actions == ["create"]))
      ) and
      ($mutations | length == 1) and
      ($mutations[0].address == "module.nas[0].proxmox_virtual_environment_vm.this") and
      ($mutations[0].type == "proxmox_virtual_environment_vm") and
      ($mutations[0].change.actions == ["create"]) and
      ($mutations[0].change.after.vm_id == 200) and
      ($mutations[0].change.after.name == "nas") and
      ($mutations[0].change.after.node_name == "pve") and
      ($mutations[0].change.after.pool_id == "tofu-vms") and
      ($mutations[0].change.after.machine == "q35") and
      ($mutations[0].change.after.description == "TrueNAS NAS; HBA and pool remain gated") and
      ($mutations[0].change.after.cpu[0].cores == 4) and
      ($mutations[0].change.after.cpu[0].type == "host") and
      ($mutations[0].change.after.memory[0].dedicated == 16384) and
      ($mutations[0].change.after.memory[0].floating == 0) and
      ($mutations[0].change.after.network_device | length == 1) and
      ($mutations[0].change.after.network_device[0].bridge == "vmbr0") and
      ($mutations[0].change.after.network_device[0].model == "virtio") and
      ($mutations[0].change.after.disk | length == 1) and
      ($mutations[0].change.after.disk[0].datastore_id == "fast-vm") and
      ($mutations[0].change.after.disk[0].file_format == "raw") and
      ($mutations[0].change.after.disk[0].interface == "scsi0") and
      ($mutations[0].change.after.disk[0].size == 32) and
      ($mutations[0].change.after.cdrom | length == 1) and
      ($mutations[0].change.after.cdrom[0].file_id == "local:iso/TrueNAS-SCALE-25.10.7.iso") and
      ($mutations[0].change.after.cdrom[0].interface == "ide2") and
      ($mutations[0].change.after.boot_order == ["ide2", "scsi0"]) and
      ($mutations[0].change.after.hostpci | length == 0) and
      ($mutations[0].change.after.initialization | length == 0) and
      ($mutations[0].change.after.agent | length == 0) and
      ($mutations[0].change.after.on_boot == false) and
      ($mutations[0].change.after.protection == true) and
      ($mutations[0].change.after.started == false) and
      ($mutations[0].change.after.stop_on_destroy == true)
    else
      all($changes[];
        (.address == "module.disposable[0].proxmox_virtual_environment_vm.this" or .address == "module.fedora[0].proxmox_virtual_environment_vm.this" or .address == "module.nas[0].proxmox_virtual_environment_vm.this") and
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
