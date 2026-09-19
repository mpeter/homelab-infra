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
| `bulk` | 8 × 1 TB MX500 SATA SSD | RAIDZ2 | About 6 TB | Images, archives, less-active VMs, general capacity |

The scratch pool may be recreated from code or backups after either device
fails. It must not hold unique state.

RAIDZ2 is selected for the bulk pool because capacity is more valuable there
than maximum random-write IOPS. If measurements show the bulk pool becoming a
busy VM datastore, reconsider four mirrored vdevs through a superseding ADR.

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

1. Refresh `inventory/storage.yaml` immediately before any write.
2. Correct the imported `rpool` host-ID mismatch.
3. Capture `zpool status -P`, `lsblk`, `blkid`, SMART/NVMe health, and by-id links.
4. Confirm the serial of every target device.
5. Remove the old ZFS label from `front-nvme-c` only after resolving that alias
   to its current serial number and receiving approval.
6. Create one pool at a time and verify topology, ashift, health, and mountpoints.
7. Configure scheduled scrubs, SMART tests, capacity alerts, and snapshots.
8. Run representative I/O tests before placing important workloads.

Linux device names in the inventory are observations, not persistent identity.
Pool definitions and destructive commands must use `/dev/disk/by-id`.
