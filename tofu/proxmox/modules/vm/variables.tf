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
  type = string
}

variable "ssh_public_key" {
  type = string
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

variable "disk_size_gib" {
  type = number
}

variable "on_boot" {
  type = bool
}

variable "protection" {
  type = bool
}

variable "wait_for_ip_disabled" {
  type = bool
}
