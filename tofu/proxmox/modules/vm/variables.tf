variable "name" {
  type = string
}

variable "vm_id" {
  type = number
}

variable "node_name" {
  type = string
}

variable "pool_id" {
  type = string
}

variable "bridge" {
  type = string
}

variable "datastore_id" {
  type = string
}

variable "import_from" {
  type     = string
  default  = null
  nullable = true
}

variable "ssh_public_key" {
  type     = string
  default  = null
  nullable = true
}

variable "description" {
  type = string
}

variable "cpu_cores" {
  type = number
}

variable "memory_mib" {
  type = number
}

variable "memory_floating_mib" {
  type     = number
  default  = null
  nullable = true
}

variable "disk_size_gib" {
  type = number
}

variable "on_boot" {
  type = bool
}

variable "started" {
  type    = bool
  default = true
}

variable "protection" {
  type = bool
}

variable "wait_for_ip_disabled" {
  type = bool
}

variable "machine_type" {
  type     = string
  default  = null
  nullable = true
}

variable "hostpci" {
  type = list(object({
    device  = string
    mapping = string
    pcie    = optional(bool)
  }))
  default = []
}

variable "cloud_init" {
  type    = bool
  default = true
}

variable "agent_enabled" {
  type    = bool
  default = true
}

variable "cdrom_file_id" {
  type     = string
  default  = null
  nullable = true
}

variable "boot_order" {
  type     = list(string)
  default  = null
  nullable = true
}
