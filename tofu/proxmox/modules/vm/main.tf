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
  started         = var.started
  stop_on_destroy = true
  protection      = var.protection
  machine         = var.machine_type
  boot_order      = var.boot_order

  cpu {
    cores = var.cpu_cores
    type  = "host"
  }

  memory {
    dedicated = var.memory_mib
    floating  = var.memory_floating_mib
  }

  dynamic "hostpci" {
    for_each = var.hostpci

    content {
      device  = hostpci.value.device
      mapping = hostpci.value.mapping
      pcie    = hostpci.value.pcie
    }
  }

  dynamic "cdrom" {
    for_each = var.cdrom_file_id == null ? [] : [var.cdrom_file_id]

    content {
      file_id   = cdrom.value
      interface = "ide2"
    }
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

  dynamic "initialization" {
    for_each = var.cloud_init ? [true] : []

    content {
      datastore_id = var.datastore_id

      ip_config {
        ipv4 {
          address = "dhcp"
        }
      }

      user_account {
        username = "mpeter"
        keys     = var.ssh_public_key == null ? [] : [var.ssh_public_key]
      }
    }
  }

  dynamic "agent" {
    for_each = var.agent_enabled ? [true] : []

    content {
      enabled = true

      wait_for_ip {
        disabled = var.wait_for_ip_disabled
      }
    }
  }

  operating_system {
    type = "l26"
  }
}
