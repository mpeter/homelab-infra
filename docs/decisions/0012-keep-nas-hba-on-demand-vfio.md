# ADR 0012. Keep NAS HBA passthrough on demand

Date: 2026-10-02

## Status

Accepted

## Context

The SAS2308 HBA is isolated in IOMMU group 32 and mapped to NAS VM 200 through
Proxmox's PCI resource mapping. A gated OpenTofu start moved it from
`mpt3sas` to `vfio-pci`; QEMU reported the SAS controller on the guest PCI bus.
After a gated stop, Proxmox left it bound to `vfio-pci`. This keeps the eight
guest disks invisible to host block-device discovery. A host cold boot with the
NAS VM stopped may instead bind the controller to `mpt3sas`.

## Decision

Use Proxmox's on-demand resource mapping to transfer the HBA when NAS VM 200
starts. Do not install a post-stop rebind hook or persistent boot-time VFIO
binding. The versioned host check accepts `vfio-pci` or `mpt3sas` while the VM
is stopped, requires `vfio-pci` while it is running, rejects unexpected
drivers, and confirms the host has not imported pool `array`.

## Alternatives rejected

- Rebind to `mpt3sas` after every stop. This exposes all guest disks to host
  device discovery, adds a host-driver write after each stop, and has not been
  tested with this SAS2308 after guest use.
- Add a Proxmox post-stop hook. It introduces a second deployment path and a
  timing-sensitive host mutation after QEMU exits; the guarded manual check is
  easier to observe and recover.
- Bind VFIO persistently at boot. This expands the host boot change before
  cold-boot recovery and restart behavior have been proven.

## Consequences

- NAS starts dynamically claim the HBA; stopped guests do not require the host
  to reclaim it.
- When the VM is stopped after passthrough, host-side SMART and disk inventory
  are unavailable until a host reboot or an explicitly reviewed maintenance
  rebind. The guest remains the normal owner of disk health monitoring.
- After a host cold boot, `mpt3sas` may bind the HBA while the NAS VM remains
  stopped. The host check accepts that state only while the guest is stopped
  and pool `array` remains unimported.
- Keep `on_boot=false` until cold-boot behavior and guest recovery are tested.

## References

- [ADR 0010: Run the bulk NAS as a VM with HBA passthrough](0010-run-the-bulk-nas-as-a-vm-with-hba-passthrough.md)
- [Linux driver binding documentation](https://www.kernel.org/doc/html/latest/driver-api/driver-model/binding.html)
- [Proxmox PCI(e) passthrough guide](https://pve.proxmox.com/wiki/PCI(e)_Passthrough)
