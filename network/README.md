# Network infrastructure management

This directory defines how the Brocade switch and UniFi control plane enter the
same review, backup, and recovery system as Proxmox without combining their
failure domains.

- [`brocade/README.md`](brocade/README.md) defines the AAP workflow and legacy
  ICX compatibility boundary.
- [`unifi/README.md`](unifi/README.md) defines provider selection, import, and
  separate-state requirements.

Exact endpoints, device identifiers, and controller exports belong in the
ignored `inventory/local/` tree. Credentials belong in AAP credentials, an
encrypted secrets system, or the OpenTofu runner environment. Raw configuration
backups belong in encrypted off-host storage because they can contain password
hashes, keys, addressing, and other sensitive operational data.
