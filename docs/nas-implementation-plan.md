# NAS VM implementation plan

This plan builds the R720's local NAS without claiming that same-host storage
is a backup. It implements [ADR 0010](decisions/0010-run-the-bulk-nas-as-a-vm-with-hba-passthrough.md)
under the [R720 change-control contract](r720-change-control.md). The intended
reader is an operator resuming without this conversation. Each exit gate must
be verified against the live host before the next write; no step here is
authorization to clear a disk or change host PCI bindings without its reviewed
preflight and recovery path.

## Target

- A NAS VM boots from the existing `fast-vm` mirror. Its OS and appliance
  configuration do not depend on a share served by itself.
- The entire LSI SAS2308 HBA is assigned to the NAS VM. All eight 1 TB MX500
  SATA SSDs remain outside host ZFS and PVE storage registration. The guest
  owns the disks, a capacity-oriented RAIDZ2 pool, datasets, snapshots, SMART
  monitoring, and SMB/NFS shares.
- Other R720 VMs do not boot from NAS exports. NAS loss must not prevent PVE
  or the NAS VM itself from starting.
- Encrypted off-site copies to rsync.net, independent key custody, and a
  restore test precede unique data. An empty NAS may be built and tested
  before the off-site account is ready.

## 0. Refresh hardware and recovery evidence

1. Record PVE version, boot ID, `rpool` and `fast-vm` health, boot media, and
   current memory and SEL status. Verify the host still has no claim on the
   eight SATA drives.
2. Resolve all eight SATA disks by serial and `/dev/disk/by-id`; record size,
   SMART health, signatures, controller path, and their physical slot mapping
   where possible. Preserve any existing data unless each exact serial has
   been separately classified disposable. Header snapshots are not full data
   backups.
3. Recheck the SAS2308 PCI identity and IOMMU group, including every group
   member. On 2026-10-01 it appeared alone at `02:00.0` in group 32, and the
   Kingston PVE boot SSD was attached to the separate chipset SATA controller.
   Those are observations, not permanent identifiers.
4. Verify console/iDRAC access and the off-host host-configuration bundle.
   Prepare a tested way to undo HBA binding if the host does not boot or the
   guest cannot claim the controller.

Exit gate: disk ownership, PCI isolation, data disposition, and rescue path
are documented from current read-only evidence. Stop if the HBA group includes
a host-required device or any SATA disk contains unclassified data.

## 1. Prove VM and HBA passthrough without changing SATA data

1. Complete the Proxmox OpenTofu control-plane and disposable-VM gates in the
   [first-VM plan](first-vm-implementation-plan.md). Select the NAS OS and
   image; OpenMediaVault 8 on Debian 13 is the current candidate. Verify the
   supported installation path, exact release, and ZFS plugin behavior in an
   isolated rehearsal before connecting the HBA.
2. Add versioned host-maintenance code for HBA driver binding with `preview`,
   `check`, `apply`, and rollback. Review the exact PCI target, boot impact,
   current backups, and rescue path before its first live apply.
3. Define the NAS VM in OpenTofu with a boot disk on `fast-vm`, a reviewed PCI
   assignment, a persistent network identity, and a memory allocation based
   on the verified 128 GiB host. Do not assume the future 256 GiB upgrade.
   Prove the scoped PVE identity can make the intended VM change without
   host/storage-admin privileges; if passthrough needs a separate privileged
   host step, keep it in versioned host maintenance code.
4. Apply the reviewed, type-gated plan. Inside the guest, verify that all eight
   expected serials and SMART data are visible and that the host no longer
   binds the HBA or sees its disks. Exercise repeated VM start, clean stop,
   and reset. Cold-boot the
   host and verify `rpool`, `fast-vm`, NAS VM, HBA assignment, and disk serials.

Exit gate: the guest controls the whole HBA consistently across starts and a
host cold boot; the host's own boot/storage path remains independent. Do not
create the SATA pool if passthrough is unstable.

## 2. Build NAS storage and shares

1. Confirm each exact serial is disposable and review a pool-creation plan
   before clearing signatures or partitions. Use guest stable disk identifiers,
   not changing Linux `/dev/sd*` names. Create the eight-disk RAIDZ2 pool in
   the NAS guest only.
2. Read back topology, usable capacity, ashift, health, and mountpoints. Test
   a scrub, SMART self-test scheduling, capacity thresholds, notifications,
   and snapshots. Confirm whether discard reaches the SATA SSDs; host-side
   `lsblk -D` previously reported zero discard granularity.
3. Define datasets and shares with explicit owners, permissions, and quotas.
   Verify access from an allowed client and denial from an unintended client.
   Keep appliance configuration export and an import/rebuild procedure outside
   the NAS pool.
4. Run representative read/write workloads, a guest restart, and a host
   restart. Confirm shares return without manual pool repair. Record measured
   throughput and memory use before changing vdev layout or ARC settings.

Exit gate: pool and share behavior match the reviewed source and survive the
named restarts. Keep only reproducible test data until the off-site gate passes.

## 3. Make unique NAS data recoverable off-site

1. Select the rsync.net account and transfer format deliberately. A standard
   SSH-compatible account can hold client-encrypted file backups; native ZFS
   send/receive needs an account that supports that feature. Record cost,
   retention, bandwidth, and expected restore method before automation.
2. Store credentials and encryption keys outside Git and outside the NAS as
   their sole copy. Back up NAS datasets and configuration exports. Back up
   important VM recovery artifacts through a separately verified path; NAS
   file backup alone does not protect PVE VMs.
3. Verify the remote copy from the destination and restore a representative
   file and NAS configuration into an isolated scratch location. Alert on missed
   jobs, stale recovery points, failed verification, and capacity pressure.

Exit gate: an off-site restore succeeds and the key and procedure remain usable
without the R720. Only then place unique data on the NAS. Later test full
guest/pool recovery and host-loss recovery separately.

## Stop conditions

Stop before a write on uncertain serials, existing unclassified data, shared
IOMMU ownership, inaccessible rescue console, unexpected OpenTofu plan
resources, unrecoverable state, or new disk/memory errors. Preserve the current
state for diagnosis; do not force a pool import or bypass the plan gate merely
to complete a milestone.
