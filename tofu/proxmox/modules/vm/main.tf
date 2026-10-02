terraform {
  required_providers {
    proxmox = {
      source = "bpg/proxmox"
    }
  }
}

resource "proxmox_virtual_environment_vm" "this" {
  name            = var.name
  vm_id           = var.vm_id
  node_name       = var.node_name
  pool_id         = var.pool_id
  description     = var.description
  on_boot         = var.on_boot
  started         = true
  stop_on_destroy = true
  protection      = var.protection

  cpu {
    cores = var.cpu_cores
    type  = "host"
  }

  memory {
    dedicated = var.memory_mib
  }

  disk {
    datastore_id = var.datastore_id
    file_format  = "raw"
    import_from  = var.import_from
    interface    = "scsi0"
    size         = var.disk_size_gib
  }

  network_device {
    bridge = var.bridge
    model  = "virtio"
  }

  initialization {
    datastore_id = var.datastore_id

    ip_config {
      ipv4 {
        address = "dhcp"
      }
    }

    user_account {
      username = "mpeter"
      keys     = [var.ssh_public_key]
    }
  }

  agent {
    enabled = true

    wait_for_ip {
      disabled = var.wait_for_ip_disabled
    }
  }

  operating_system {
    type = "l26"
  }
}
