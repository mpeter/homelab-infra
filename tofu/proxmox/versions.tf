terraform {
  required_version = "= 1.13.0"

  required_providers {
    proxmox = {
      source  = "bpg/proxmox"
      version = "= 0.112.0"
    }
  }

  backend "local" {
    path = "../../../homelab-private/tofu/proxmox/terraform.tfstate"
  }

  encryption {
    key_provider "pbkdf2" "state" {
      passphrase               = var.state_passphrase
      encrypted_metadata_alias = "r720-proxmox-state"
    }

    method "aes_gcm" "state" {
      keys = key_provider.pbkdf2.state
    }

    state {
      method   = method.aes_gcm.state
      enforced = true
    }

    plan {
      method   = method.aes_gcm.state
      enforced = true
    }
  }
}

variable "state_passphrase" {
  type      = string
  sensitive = true

  validation {
    condition     = length(var.state_passphrase) >= 32
    error_message = "The state passphrase must be at least 32 characters."
  }
}
