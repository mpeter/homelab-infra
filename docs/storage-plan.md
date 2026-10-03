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

## Pool health and device-failure response

The read-only PVE snapshot from 2026-10-03 08:03 EDT is recorded in the
component-dated `rpool`, `fast_vm`, and `pve_storage_monitoring` sections of
[`inventory/storage.yaml`](../inventory/storage.yaml). The file-level date
and NAS/SATA sections retain their earlier observation dates; this PVE readback
does not refresh guest-owned disk or pool evidence. `rpool` and `fast-vm`
were ONLINE mirrors with no recorded read, write, checksum, or known data
errors. The versioned `host/pve/check-fast-vm.sh` check passed against the
live host. ZFS automatic periodic scrub is enabled by the PVE package's monthly
second-Sunday cron schedule; the pools' effective property is `auto`, but
`zpool status -v` showed no scan entry at the time of the snapshot. `smartd` was
active and its `DEVICESCAN` health checks passed for host-visible NVMe devices
and the boot SSD. The active `smartd.conf` line defines monitoring but no
scheduled SMART self-test. PVE ZFS datasets report no quota or refquota.

For a storage alert, first capture `zpool status -P -v`, `zpool events -v`,
`pvesm status`, and SMART health for the exact `/dev/disk/by-id` member. Match
the persistent path to its serial in `inventory/storage.yaml`; never select a
replacement from a transient `/dev/nvme*` name. Do not offline, detach, or
replace a device until a reviewed maintenance plan confirms the failing and
replacement serials, recovery path, and expected resilver outcome. After an
approved repair, verify the pool state, member identity, errors, and PVE
storage read-back before returning workloads to normal.

For `rpool` and `fast-vm`, both mirrors, identify the faulted leaf by its
persistent path and serial, preserve the healthy mirror member, and use a
reviewed replacement plan. Wait for resilver completion, then verify member
identity, pool errors, and PVE storage status. For RAIDZ2 `tank`, identify the
failed SATA serial and physical slot through the trusted TrueNAS guest before
replacing it through the guest-owned pool workflow; never operate on these
HBA disks from PVE. `scratch` is not implemented and has no current failure
procedure. No device was faulted, offlined, or replaced during this read-only
pass; representative failure-procedure results remain open.

`tank` belongs to the TrueNAS guest and must only be inspected or repaired
through a trusted guest-management path. Its current health, scrub result,
SMART-test history, dataset quotas, and alert thresholds were not re-read in
this pass because its certificate identity remains unresolved. The 20%-free
`fast-vm` criterion applies to Fedora promotion; no configured capacity alert
threshold or accepted device-failure exercise is evidenced yet. OpenSpec task
6.4 remains open until the NAS tier and these operational gates are verified.

Linux device names in the inventory are observations, not persistent identity.
Pool definitions and destructive commands must use `/dev/disk/by-id`.
