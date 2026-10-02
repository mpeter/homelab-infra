module "disposable" {
  count  = var.disposable_enabled ? 1 : 0
  source = "./modules/vm"

  name                 = "r720-disposable"
  vm_id                = 9900
  node_name            = var.node_name
  pool_id              = "tofu-vms"
  bridge               = "vmbr0"
  datastore_id         = "fast-vm"
  import_from          = "local:import/Fedora-Cloud-Base-Generic-44-1.7.x86_64.qcow2"
  ssh_public_key       = var.ssh_public_key
  description          = "Disposable OpenTofu lifecycle verification VM"
  cpu_cores            = 2
  memory_mib           = 4096
  disk_size_gib        = 12
  on_boot              = false
  protection           = false
  wait_for_ip_disabled = false
}

module "fedora" {
  count  = var.fedora_enabled ? 1 : 0
  source = "./modules/vm"

  name                 = "fedora-dev"
  vm_id                = 100
  node_name            = var.node_name
  pool_id              = "tofu-vms"
  bridge               = "vmbr0"
  datastore_id         = "fast-vm"
  import_from          = "local:import/Fedora-Cloud-Base-Generic-44-1.7.x86_64.qcow2"
  ssh_public_key       = var.ssh_public_key
  description          = "Reproducible Fedora development VM; unique data gated by group 5 recovery"
  cpu_cores            = 8
  memory_mib           = 32768
  disk_size_gib        = 300
  on_boot              = true
  protection           = true
  wait_for_ip_disabled = true
}

module "nas" {
  count  = var.nas_enabled ? 1 : 0
  source = "./modules/vm"

  name                 = "nas"
  vm_id                = 200
  node_name            = var.node_name
  pool_id              = "tofu-vms"
  bridge               = "vmbr0"
  datastore_id         = "fast-vm"
  import_from          = null
  ssh_public_key       = null
  description          = "TrueNAS NAS; HBA and pool remain gated"
  cpu_cores            = 4
  memory_mib           = 16384
  memory_floating_mib  = 0
  disk_size_gib        = 32
  on_boot              = false
  started              = false
  protection           = true
  wait_for_ip_disabled = true
  machine_type         = "q35"
  hostpci              = []
  cloud_init           = false
  agent_enabled        = false
  cdrom_file_id        = "local:iso/TrueNAS-SCALE-25.10.7.iso"
  boot_order           = ["ide2", "scsi0"]
}

variable "disposable_enabled" {
  type    = bool
  default = false
}

variable "fedora_enabled" {
  type    = bool
  default = true
}

variable "nas_enabled" {
  type    = bool
  default = false
}
