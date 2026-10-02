# 0010. Run the bulk NAS as a VM with HBA passthrough

Date: 2026-10-01

## Status

Accepted

## Context

The R720 has eight unallocated 1 TB SATA SSDs behind an LSI SAS2308 HBA. The
operator wants a NAS appliance, not merely a Proxmox datastore with a file
sharing front end. Read-only checks found that the HBA is alone in its IOMMU
group and that the firmware-visible Proxmox boot SSD is on a separate SATA
controller. These checks establish a plausible passthrough boundary, not a
working NAS or a completed disk-safety preflight.

[ADR 0003](0003-use-tiered-storage-protection.md) chose RAIDZ2 for bulk
capacity. That protection choice remains; this decision changes who owns the
SATA disks and the bulk pool.

## Decision

Create a NAS VM on Proxmox with its boot disk on `fast-vm`. Pass the complete
SAS2308 PCI device to the VM. The NAS guest owns the eight SATA SSDs, its ZFS
pool, datasets, snapshots, health checks, and SMB/NFS shares. Proxmox must not
import or manage that pool. Use eight disks in a RAIDZ2 vdev as the initial
capacity-oriented layout, subject to fresh serial, SMART, and topology checks
before pool creation. Do not place Proxmox VM boot disks or the NAS VM's own
boot disk on storage exported by this guest.

Versioned host maintenance code owns the HBA binding and passthrough preflight;
OpenTofu owns the VM and PCI assignment; guest configuration automation owns
the NAS OS and service settings where supported. Record any appliance-only
settings through a versioned export and restore procedure.

The NAS is primary local storage, not the independent backup destination.
Plan encrypted off-site copies at rsync.net and verify a restore before unique
data relies on the NAS. The exact transfer method and account type remain to
be selected; a standard SSH-compatible backup account and a ZFS-receive
account have different capabilities.

## Alternatives rejected

- Keep `bulk` as a Proxmox-owned ZFS pool and export it through a small guest.
  This preserves native PVE datastore use and a simpler boot order, but does
  not deliver the NAS appliance and direct disk ownership the operator wants.
- Pass eight disks individually to a NAS VM. This leaves the host able to see
  the devices, adds per-disk mapping drift, and makes pool ownership ambiguous.
- Put PVE VM disks on a share served by the NAS VM. This creates a same-host
  startup dependency and prevents native use of the SATA capacity during NAS
  guest failure.

## Consequences

- NAS pool management and SMART visibility move inside the guest; the host
  cannot also use those eight disks as a native `bulk` datastore.
- HBA passthrough must survive VM start, stop, reset, and host reboot tests.
  The HBA must remain isolated from PVE boot and other required devices.
- NAS vendor guidance must be checked for the selected OS/version; TrueNAS
  currently cautions against virtualized critical-data deployments even when
  physical storage is passed through. The off-site restore path is therefore
  essential, not a substitute for the passthrough tests.
- The NAS needs a documented independent boot/configuration recovery path.
  Its pool can be imported on another compatible system, but the VM's shares
  and settings also need to be recoverable.
- RAIDZ2 tolerates selected disk failures, not loss of the R720 or the site.
  Off-site backup and a restore test gate unique NAS data, not creation of an
  empty NAS VM.

## Related decisions

- [ADR 0003](0003-use-tiered-storage-protection.md) retains the tier layouts.
- [ADR 0008](0008-cut-over-r720-changes-to-versioned-control.md) defines the
  versioned host and VM ownership boundaries.

## References

- [TrueNAS hardware guide](https://www.truenas.com/docs/scale/gettingstarted/scalehardwareguide/)
- [rsync.net ZFS-capable account requirements](https://rsync.net/products/zfsintro.html)
