# Storage plan

## Policy

Backups recover prior state. Redundancy maintains service through a device
failure and gives ZFS another valid copy from which to repair corrupted blocks.
The lab uses redundancy for durable daily work and capacity-efficient or
disposable layouts for reproducible data.

## Target pools

| Pool | Devices | Layout | Approximate usable capacity | Purpose |
|---|---|---|---:|---|
| `rpool` | 2 × 512 GB front NVMe | Mirror | 512 GB | PVE system and local metadata |
| `fast-vm` | 2 × 1 TB internal NVMe | Mirror | 1 TB | Fedora development VM, AAP, IdM, important VMs |
| `scratch` | Remaining 2 × 512 GB front NVMe | Stripe | 1 TB | Build cache, disposable VMs, reproducible labs |
| NAS bulk pool | 8 × 1 TB MX500 SATA SSD behind passed-through SAS2308 HBA | RAIDZ2 in NAS VM | About 6 TB | Shared files, archives, NAS datasets |

The scratch pool may be recreated from code or backups after either device
fails. It must not hold unique state.

RAIDZ2 is selected for the NAS pool because capacity is more valuable there
than maximum random-write IOPS. The NAS VM boots from `fast-vm`; it owns the
SATA disks and pool, which Proxmox must not import. Do not host Proxmox VM
disks on a share exported by the NAS VM. [ADR 0010](decisions/0010-run-the-bulk-nas-as-a-vm-with-hba-passthrough.md)
records the ownership decision. Reconsider mirrored vdevs through a new ADR
if measured NAS workloads need substantially more random-write performance.

Before passing through the HBA, refresh the disk serials and by-id paths,
signatures, SMART data, and connection map. Read-only checks on 2026-10-01
found the SAS2308 alone in its IOMMU group and the PVE boot SSD on a separate
SATA controller. Recheck both before a host write. Test HBA binding, VM
start/stop/reset, disk visibility and serials inside the guest, and host
reboot/import behavior before creating the pool. The SATA SSDs reported zero
discard granularity through the current host HBA path; verify and document
guest behavior rather than assuming TRIM is available.

## Boot resilience

The firmware-visible EFI and `/boot` filesystems currently live on one Kingston
SATA SSD. The NVMe root pool can remain healthy while failure of that SATA SSD
leaves the server unable to boot.

Add a second firmware-visible SATA SSD and maintain an independently bootable
copy of EFI and `/boot`. The implementation must include:

1. Documented partition and filesystem creation.
2. Automatic or explicit synchronization after bootloader updates.
3. A boot entry for each device.
4. Successful cold boots with each device independently unavailable.
5. Recovery media and the exact reconstruction procedure stored off-host.

## Safe creation sequence

The `fast-vm` mirror was created on 2026-10-01 from serials
`PHHH829001A91P0E` and `PHHH828600761P0E`. Before creation, the first held
an old boot layout with an XFS `root` filesystem, and the second held a VMFS
volume-member signature. The operator classified both as disposable. Their
first and last 8 MiB were saved and hash-checked off-host before the old
partition tables were cleared. These snapshots preserve headers, not the old
filesystems' data. The resulting mirror and Proxmox storage both read back as
active and error-free; `rpool` remained ONLINE.

For later pools, including the NAS pool before handing its disks to the guest,
repeat this safety sequence:

1. Refresh `inventory/storage.yaml` immediately before any write.
2. Confirm the corrected `rpool` host ID and pool health through cold boots.
   Two verified cold boots passed on 2026-10-01 without a mismatch warning.
3. Capture `zpool status -P`, `lsblk`, `blkid`, SMART/NVMe health, and by-id links.
4. Confirm the serial of every target device.
5. Capture the target partition tables and signatures, and retain recoverable
   header copies off the target disks before clearing them.
6. For the separate NVMe `scratch` pool only, remove the old ZFS label from
   `front-nvme-c` after resolving that alias to its current serial number and
   receiving approval. This is not part of NAS disk preparation.
7. Create one pool at a time in its designated owner and verify topology,
   ashift, health, and mountpoints.
8. Configure scheduled scrubs, SMART tests, capacity alerts, and snapshots.
9. Run representative I/O tests before placing important workloads.

Linux device names in the inventory are observations, not persistent identity.
Pool definitions and destructive commands must use `/dev/disk/by-id`.
