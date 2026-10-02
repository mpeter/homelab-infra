#!/usr/bin/env bash
set -euo pipefail

checker=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)/check-plan.sh

expect_status() {
  local expected=$1 input=$2
  shift 2
  local actual=0
  bash "$checker" "$@" <<< "$input" >/dev/null 2>&1 || actual=$?
  [[ $actual == "$expected" ]] || {
    printf 'expected exit %s, got %s for %s\n' "$expected" "$actual" "$input" >&2
    exit 1
  }
}

expect_status 0 '{"format_version":"1.2","resource_changes":[]}'
expect_status 0 '{"format_version":"1.2","resource_changes":[{"address":"module.disposable[0].proxmox_virtual_environment_vm.this","type":"proxmox_virtual_environment_vm","change":{"actions":["no-op"]}}]}'
expect_status 0 '{"format_version":"1.2","resource_changes":[{"address":"module.disposable[0].proxmox_virtual_environment_vm.this","type":"proxmox_virtual_environment_vm","change":{"actions":["create"],"after":{"vm_id":9900,"name":"r720-disposable","pool_id":"tofu-vms","cpu":[{"cores":2}],"memory":[{"dedicated":4096}],"network_device":[{"bridge":"vmbr0"}],"disk":[{"datastore_id":"fast-vm","file_format":"raw","import_from":"local:import/Fedora-Cloud-Base-Generic-44-1.7.x86_64.qcow2"}],"agent":[{"enabled":true}],"initialization":[{"ip_config":[{"ipv4":[{"address":"dhcp"}]}]}]}}}]}' --disposable-create
expect_status 1 '{"format_version":"1.2","resource_changes":[{"address":"module.other.proxmox_virtual_environment_vm.this","type":"proxmox_virtual_environment_vm","change":{"actions":["create"],"after":{"vm_id":9900,"pool_id":"tofu-vms","network_device":[{"bridge":"vmbr0"}],"disk":[{"datastore_id":"fast-vm","import_from":"local:import/Fedora-Cloud-Base-Generic-44-1.7.x86_64.qcow2"}]}}}]}' --disposable-create
expect_status 1 '{"format_version":"1.2","resource_changes":[{"address":"module.disposable[0].proxmox_virtual_environment_vm.this","type":"proxmox_virtual_environment_vm","change":{"actions":["create"],"after":{"vm_id":9900,"pool_id":"other","network_device":[{"bridge":"vmbr0"}],"disk":[{"datastore_id":"fast-vm","import_from":"local:import/Fedora-Cloud-Base-Generic-44-1.7.x86_64.qcow2"}]}}}]}' --disposable-create
expect_status 1 '{"format_version":"1.2","resource_changes":[{"address":"module.disposable[0].proxmox_virtual_environment_vm.this","type":"proxmox_virtual_environment_vm","change":{"actions":["create"],"after":{"vm_id":9900,"pool_id":"tofu-vms","network_device":[{"bridge":"vmbr0"}],"disk":[{"datastore_id":"other","import_from":"local:import/Fedora-Cloud-Base-Generic-44-1.7.x86_64.qcow2"}]}}}]}' --disposable-create
expect_status 1 '{"format_version":"1.2","resource_changes":[{"address":"module.disposable[0].proxmox_virtual_environment_vm.this","type":"proxmox_virtual_environment_vm","change":{"actions":["create"],"after":{"vm_id":9900,"pool_id":"tofu-vms","network_device":[{"bridge":"other"}],"disk":[{"datastore_id":"fast-vm","import_from":"local:import/Fedora-Cloud-Base-Generic-44-1.7.x86_64.qcow2"}]}}}]}' --disposable-create
expect_status 1 '{"format_version":"1.2","resource_changes":[{"address":"module.disposable[0].proxmox_virtual_environment_vm.this","type":"proxmox_virtual_environment_vm","change":{"actions":["create"],"after":{"vm_id":9900,"name":"other","pool_id":"tofu-vms","cpu":[{"cores":2}],"memory":[{"dedicated":4096}],"network_device":[{"bridge":"vmbr0"}],"disk":[{"datastore_id":"fast-vm","file_format":"raw","import_from":"local:import/Fedora-Cloud-Base-Generic-44-1.7.x86_64.qcow2"}],"initialization":[{"ip_config":[{"ipv4":[{"address":"dhcp"}]}]}]}}}]}' --disposable-create
expect_status 1 '{"format_version":"1.2","resource_changes":[{"address":"proxmox_storage_zfspool.bad","type":"proxmox_storage_zfspool","change":{"actions":["create"]}}]}'
expect_status 1 '{"format_version":"1.2","resource_changes":[{"address":"module.disposable[0].proxmox_virtual_environment_vm.this","type":"proxmox_virtual_environment_vm","change":{"actions":["delete","create"]}}]}'
expect_status 1 '{"format_version":"1.2","resource_changes":[{"address":"module.disposable[0].proxmox_virtual_environment_vm.this","type":"proxmox_virtual_environment_vm","change":{"actions":["delete"]}}]}'
expect_status 0 '{"format_version":"1.2","resource_changes":[{"address":"module.disposable[0].proxmox_virtual_environment_vm.this","type":"proxmox_virtual_environment_vm","change":{"actions":["delete"]}}]}' --disposable-destroy
expect_status 1 '{"format_version":"1.2","resource_changes":[{"address":"module.fedora.proxmox_virtual_environment_vm.this","type":"proxmox_virtual_environment_vm","change":{"actions":["delete"]}}]}' --disposable-destroy
expect_status 1 '{"format_version":"1.2","resource_changes":[{"address":"module.disposable[0].proxmox_virtual_environment_vm.this","type":"proxmox_virtual_environment_vm","change":{"actions":["delete"]}},{"address":"module.other.proxmox_virtual_environment_vm.this","type":"proxmox_virtual_environment_vm","change":{"actions":["create"]}}]}' --disposable-destroy
expect_status 1 '{not json}'
expect_status 0 '{"format_version":"1.2"}'
expect_status 1 '{"not_format_version":"1.2"}'
expect_status 1 '{"format_version":1.2,"resource_changes":[]}'
expect_status 0 '{"format_version":"1.2","resource_changes":[{"address":"module.fedora[0].proxmox_virtual_environment_vm.this","type":"proxmox_virtual_environment_vm","change":{"actions":["create"],"after":{"vm_id":100,"name":"fedora-dev","node_name":"pve","pool_id":"tofu-vms","cpu":[{"cores":8,"type":"host"}],"memory":[{"dedicated":32768}],"network_device":[{"bridge":"vmbr0","model":"virtio"}],"disk":[{"datastore_id":"fast-vm","file_format":"raw","import_from":"local:import/Fedora-Cloud-Base-Generic-44-1.7.x86_64.qcow2","interface":"scsi0","size":300}],"agent":[{"enabled":true,"wait_for_ip":[{"disabled":true}]}],"operating_system":[{"type":"l26"}],"initialization":[{"ip_config":[{"ipv4":[{"address":"dhcp"}]}],"user_account":[{"username":"mpeter"}]}],"on_boot":true,"protection":true,"started":true,"stop_on_destroy":true}}}]}' --fedora-create
expect_status 1 '{"format_version":"1.2","resource_changes":[{"address":"module.fedora[0].proxmox_virtual_environment_vm.this","type":"proxmox_virtual_environment_vm","change":{"actions":["create"],"after":{"vm_id":100,"name":"fedora-dev","node_name":"pve","pool_id":"tofu-vms","cpu":[{"cores":8,"type":"host"}],"memory":[{"dedicated":32768}],"network_device":[{"bridge":"vmbr0","model":"virtio"}],"disk":[{"datastore_id":"fast-vm","file_format":"raw","import_from":"local:import/Fedora-Cloud-Base-Generic-44-1.7.x86_64.qcow2","interface":"scsi0","size":300}],"agent":[{"enabled":true,"wait_for_ip":[{"disabled":true}]}],"operating_system":[{"type":"l26"}],"initialization":[{"ip_config":[{"ipv4":[{"address":"dhcp"}]}],"user_account":[{"username":"mpeter"}]}],"on_boot":true,"protection":false,"started":true,"stop_on_destroy":true}}}]}' --fedora-create
expect_status 1 '{"format_version":"1.2","resource_changes":[{"address":"module.fedora[0].proxmox_virtual_environment_vm.this","type":"proxmox_virtual_environment_vm","change":{"actions":["delete"]}}]}' --fedora-create
expect_status 0 '{"format_version":"1.2","resource_changes":[{"address":"module.fedora[0].proxmox_virtual_environment_vm.this","type":"proxmox_virtual_environment_vm","change":{"actions":["update"],"before":{"vm_id":100,"name":"fedora-dev","started":false},"after":{"vm_id":100,"name":"fedora-dev","node_name":"pve","pool_id":"tofu-vms","cpu":[{"cores":8,"type":"host"}],"memory":[{"dedicated":32768}],"network_device":[{"bridge":"vmbr0"}],"disk":[{"datastore_id":"fast-vm","file_format":"raw","size":300}],"agent":[{"enabled":true,"wait_for_ip":[{"disabled":true}]}],"operating_system":[{"type":"l26"}],"on_boot":true,"protection":true,"started":true,"stop_on_destroy":true}}}]}' --fedora-start
expect_status 1 '{"format_version":"1.2","resource_changes":[{"address":"module.fedora[0].proxmox_virtual_environment_vm.this","type":"proxmox_virtual_environment_vm","change":{"actions":["update"],"before":{"vm_id":100,"name":"fedora-dev","started":false},"after":{"vm_id":100,"name":"fedora-dev","node_name":"pve","pool_id":"tofu-vms","cpu":[{"cores":8,"type":"host"}],"memory":[{"dedicated":32768}],"network_device":[{"bridge":"vmbr0"}],"disk":[{"datastore_id":"fast-vm","file_format":"raw","size":300}],"agent":[{"enabled":true,"wait_for_ip":[{"disabled":true}]}],"operating_system":[{"type":"l26"}],"on_boot":true,"protection":false,"started":true,"stop_on_destroy":true}}}]}' --fedora-start
nas_create='{"format_version":"1.2","resource_changes":[{"address":"module.nas[0].proxmox_virtual_environment_vm.this","type":"proxmox_virtual_environment_vm","change":{"actions":["create"],"after":{"vm_id":200,"name":"nas","node_name":"pve","pool_id":"tofu-vms","machine":"q35","description":"TrueNAS NAS; HBA and pool remain gated","cpu":[{"cores":4,"type":"host"}],"memory":[{"dedicated":16384,"floating":0}],"network_device":[{"bridge":"vmbr0","model":"virtio"}],"disk":[{"datastore_id":"fast-vm","file_format":"raw","interface":"scsi0","size":32}],"cdrom":[{"file_id":"local:iso/TrueNAS-SCALE-25.10.7.iso","interface":"ide2"}],"boot_order":["ide2","scsi0"],"hostpci":[],"initialization":[],"agent":[],"on_boot":false,"protection":true,"started":false,"stop_on_destroy":true}}}]}'
expect_status 0 "$nas_create" --nas-create
expect_status 1 "${nas_create/\"hostpci\":\[\]/\"hostpci\":[{\"device\":\"hostpci0\",\"mapping\":\"nas-hba\"}]}" --nas-create
nas_attach=$(jq -nc --argjson plan "$nas_create" '
  ($plan.resource_changes[0]
    | .change.after.hostpci = [{device:"hostpci0",mapping:"nas-hba",pcie:true,id:"",mdev:"",rom_file:"",rombar:false,xvga:false}]
    | .change.before = (.change.after | .started = false | .hostpci = [])
    | .change.actions = ["update"]
  ) as $resource |
  {format_version:"1.2",resource_changes:[$resource]}
')
expect_status 0 "$nas_attach" --nas-attach
expect_status 1 "${nas_attach/\"mapping\":\"nas-hba\"/\"mapping\":\"other-hba\"}" --nas-attach
expect_status 1 "${nas_attach/\"started\":false/\"started\":true}" --nas-attach
expect_status 1 "${nas_attach/\"id\":\"\"/\"id\":\"0000:03:00.0\"}" --nas-attach
expect_status 1 "$nas_attach" --nas-reattach
nas_install_complete=$(jq -nc --argjson plan "$nas_create" '
  ($plan.resource_changes[0]
    | .change.after.hostpci = [{device:"hostpci0",mapping:"nas-hba",pcie:true,id:"",mdev:"",rom_file:"",rombar:false,xvga:false}]
    | .change.before = (.change.after | .started = true | .hostpci = [{device:"hostpci0",mapping:"nas-hba",pcie:true,id:"",mdev:"",rom_file:"",rombar:false,xvga:false}])
    | .change.after.cdrom = [{file_id:"none",interface:"ide2"}]
    | .change.after.boot_order = ["scsi0"]
    | .change.after.started = false
    | .change.before.cdrom = [{file_id:"local:iso/TrueNAS-SCALE-25.10.7.iso",interface:"ide2"}]
    | .change.before.boot_order = ["ide2","scsi0"]
    | .change.before.ipv4_addresses = []
    | .change.before.ipv6_addresses = []
    | .change.before.network_interface_names = []
    | del(.change.after.ipv4_addresses, .change.after.ipv6_addresses, .change.after.network_interface_names)
    | .change.after_unknown = {ipv4_addresses:true,ipv6_addresses:true,network_interface_names:true}
    | .change.actions = ["update"]
  ) as $resource |
  {format_version:"1.2",resource_changes:[$resource]}
')
expect_status 0 "$nas_install_complete" --nas-install-complete
expect_status 0 "$(jq -c '.resource_changes[0].change.before.cdrom = []' <<< "$nas_install_complete")" --nas-install-complete
expect_status 0 "$(jq -c '.resource_changes[0].change.before.boot_order = ["scsi0"]' <<< "$nas_install_complete")" --nas-install-complete
expect_status 1 "$(jq -c '.resource_changes[0].change.before.boot_order = ["ide2"]' <<< "$nas_install_complete")" --nas-install-complete
expect_status 1 "$(jq -c '.resource_changes[0].change.after.boot_order = ["ide2","scsi0"]' <<< "$nas_install_complete")" --nas-install-complete
expect_status 1 "$(jq -c '.resource_changes[0].change.after.cdrom[0].file_id = "cdrom"' <<< "$nas_install_complete")" --nas-install-complete
expect_status 1 "$(jq -c '.resource_changes[0].change.before.cdrom = [{file_id:"other.iso",interface:"ide2"}]' <<< "$nas_install_complete")" --nas-install-complete
expect_status 1 "$(jq -c '.resource_changes[0].change.after.hostpci[0].mapping = "other-hba"' <<< "$nas_install_complete")" --nas-install-complete
nas_start=$(jq -nc --argjson plan "$nas_create" '
  ($plan.resource_changes[0]
    | .change.after.hostpci = [{device:"hostpci0",mapping:"nas-hba",pcie:true,id:"",mdev:"",rom_file:"",rombar:false,xvga:false}]
    | .change.after.cdrom = [{file_id:"none",interface:"ide2"}]
    | .change.after.boot_order = ["scsi0"]
    | .change.before = (.change.after | .started = false | .hostpci = [{device:"hostpci0",mapping:"nas-hba",pcie:true,id:"",mdev:"",rom_file:"",rombar:false,xvga:false}])
    | .change.after.started = true
    | .change.before.ipv4_addresses = []
    | .change.before.ipv6_addresses = []
    | .change.before.network_interface_names = []
    | del(.change.after.ipv4_addresses, .change.after.ipv6_addresses, .change.after.network_interface_names)
    | .change.after_unknown = {ipv4_addresses:true,ipv6_addresses:true,network_interface_names:true}
    | .change.actions = ["update"]
  ) as $resource |
  {format_version:"1.2",resource_changes:[$resource]}
')
expect_status 0 "$nas_start" --nas-start
expect_status 1 "${nas_start/\"on_boot\":false/\"on_boot\":true}" --nas-start
expect_status 1 "${nas_start/\"mapping\":\"nas-hba\"/\"mapping\":\"other-hba\"}" --nas-start
expect_status 1 "${nas_start/\"rom_file\":\"\"/\"rom_file\":\"file.rom\"}" --nas-start
expect_status 1 "${nas_start/\"network_interface_names\":true/\"network_interface_names\":true,\"vm_id\":true}" --nas-start
expect_status 1 "${nas_start/\"cores\":4/\"cores\":8}" --nas-start
nas_detach=$(jq -nc --argjson plan "$nas_start" '
  ($plan.resource_changes[0]
    | .change.after = .change.before
    | .change.after.hostpci = []
    | .change.actions = ["update"]
  ) as $resource |
  {format_version:"1.2",resource_changes:[$resource]}
')
expect_status 0 "$nas_detach" --nas-detach
expect_status 1 "$nas_detach"
expect_status 1 "$(jq -c '.resource_changes[0].change.before.hostpci[0].mapping = "other-hba"' <<< "$nas_detach")" --nas-detach
expect_status 1 "$(jq -c '.resource_changes[0].change.after.hostpci = [{device:"hostpci0",mapping:"nas-hba",pcie:true}]' <<< "$nas_detach")" --nas-detach
expect_status 1 "$(jq -c '.resource_changes[0].change.after.cpu[0].cores = 8' <<< "$nas_detach")" --nas-detach
expect_status 1 "$(jq -c '.resource_changes[0].change.before.started = true' <<< "$nas_detach")" --nas-detach
expect_status 1 "$(jq -c '.resource_changes += [{address:"other",type:"proxmox_virtual_environment_vm",change:{actions:["delete"]}}]' <<< "$nas_detach")" --nas-detach
nas_reattach=$(jq -nc --argjson plan "$nas_detach" '
  ($plan.resource_changes[0]
    | .change.before.hostpci = []
    | .change.after = .change.before
    | .change.after.network_device[0].mac_address = "BC:24:11:87:F2:2B"
    | .change.before.network_device[0].mac_address = "BC:24:11:87:F2:2B"
    | .change.after.hostpci = [{device:"hostpci0",mapping:"nas-hba",pcie:true,id:"",mdev:"",rom_file:"",rombar:false,xvga:false}]
    | .change.actions = ["update"]
  ) as $resource |
  {format_version:"1.2",resource_changes:[$resource]}
')
expect_status 0 "$nas_reattach" --nas-reattach
expect_status 1 "$nas_reattach" --nas-attach
expect_status 1 "$nas_reattach" --nas-detach
expect_status 1 "$nas_reattach"
expect_status 1 "$(jq -c '.resource_changes[0].change.after.cdrom[0].file_id = "local:iso/TrueNAS-SCALE-25.10.7.iso"' <<< "$nas_reattach")" --nas-reattach
expect_status 1 "$(jq -c '.resource_changes[0].change.after.boot_order = ["ide2","scsi0"]' <<< "$nas_reattach")" --nas-reattach
expect_status 1 "$(jq -c '.resource_changes[0].change.before.cdrom[0].file_id = "other"' <<< "$nas_reattach")" --nas-reattach
expect_status 1 "$(jq -c '.resource_changes[0].change.before.boot_order = ["ide2","scsi0"]' <<< "$nas_reattach")" --nas-reattach
expect_status 1 "$(jq -c '.resource_changes[0].change.before.started = true' <<< "$nas_reattach")" --nas-reattach
expect_status 1 "$(jq -c '.resource_changes[0].change.after.started = true' <<< "$nas_reattach")" --nas-reattach
expect_status 1 "$(jq -c '.resource_changes[0].change.before.hostpci = [{device:"hostpci0",mapping:"nas-hba",pcie:true}]' <<< "$nas_reattach")" --nas-reattach
expect_status 1 "$(jq -c '.resource_changes[0].change.after.hostpci[0].mapping = "other-hba"' <<< "$nas_reattach")" --nas-reattach
expect_status 1 "$(jq -c '.resource_changes[0].change.after.hostpci[0].id = "0000:03:00.0"' <<< "$nas_reattach")" --nas-reattach
expect_status 1 "$(jq -c '.resource_changes[0].change.after.hostpci += [{device:"hostpci1",mapping:"nas-hba",pcie:true}]' <<< "$nas_reattach")" --nas-reattach
expect_status 1 "$(jq -c '.resource_changes[0].change.after.cpu[0].cores = 8' <<< "$nas_reattach")" --nas-reattach
expect_status 1 "$(jq -c '.resource_changes[0].change.after.memory[0].floating = 512' <<< "$nas_reattach")" --nas-reattach
expect_status 1 "$(jq -c '.resource_changes[0].change.after.network_device[0].bridge = "other"' <<< "$nas_reattach")" --nas-reattach
expect_status 1 "$(jq -c '.resource_changes[0].change.after.disk[0].size = 64' <<< "$nas_reattach")" --nas-reattach
expect_status 1 "$(jq -c '.resource_changes[0].change.after.agent = [{enabled:true}]' <<< "$nas_reattach")" --nas-reattach
expect_status 1 "$(jq -c '.resource_changes[0].change.after.on_boot = true' <<< "$nas_reattach")" --nas-reattach
expect_status 1 "$(jq -c '.resource_changes[0].change.actions = ["delete","create"]' <<< "$nas_reattach")" --nas-reattach
expect_status 0 "$(jq -c '.resource_changes += [{address:"module.fedora[0].proxmox_virtual_environment_vm.this",type:"proxmox_virtual_environment_vm",change:{actions:["no-op"]}}]' <<< "$nas_reattach")" --nas-reattach
nas_stop=$(jq -nc --argjson plan "$nas_start" '
  ($plan.resource_changes[0]
    | .change.before.started = true
    | .change.after.started = false
    | .change.actions = ["update"]
  ) as $resource |
  {format_version:"1.2",resource_changes:[$resource]}
')
expect_status 0 "$nas_stop" --nas-stop
expect_status 1 "${nas_stop/\"started\":false/\"started\":true}" --nas-stop
fedora_noop='{"address":"module.fedora[0].proxmox_virtual_environment_vm.this","type":"proxmox_virtual_environment_vm","change":{"actions":["no-op"]}}'
nas_with_fedora_noop=$(jq -nc --argjson plan "$nas_create" --argjson noop "$fedora_noop" '($plan | .resource_changes += [$noop])')
expect_status 0 "$nas_with_fedora_noop" --nas-create
nas_detach_with_fedora_noop=$(jq -nc --argjson plan "$nas_detach" --argjson noop "$fedora_noop" '($plan | .resource_changes += [$noop])')
expect_status 0 "$nas_detach_with_fedora_noop" --nas-detach
expect_status 0 '{"format_version":"1.2","resource_changes":[{"address":"module.nas[0].proxmox_virtual_environment_vm.this","type":"proxmox_virtual_environment_vm","change":{"actions":["no-op"]}}]}'
printf 'plan gate tests PASS\n'
