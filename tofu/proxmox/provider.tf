provider "proxmox" {
  endpoint  = var.endpoint
  api_token = var.api_token
  insecure  = false
}

variable "endpoint" {
  type = string
}

variable "api_token" {
  type      = string
  sensitive = true
}

variable "node_name" {
  type = string
}

variable "ssh_public_key" {
  type = string
}
