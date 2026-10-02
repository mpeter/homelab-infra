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
   where possible. The operator has authorized disposal of the existing
   contents on all eight intended SSDs. Verify that the live serial set still
   matches the recorded set before any clearing. Header snapshots are not full
   data backups.
3. Recheck the SAS2308 PCI identity and IOMMU group, including every group
   member. On 2026-10-01 it appeared alone at `02:00.0` in group 32, and the
   Kingston PVE boot SSD was attached to the separate chipset SATA controller.
   Those are observations, not permanent identifiers.
4. Verify console/iDRAC access and the off-host host-configuration bundle.
   Prepare a tested way to undo HBA binding if the host does not boot or the
   guest cannot claim the controller.

Exit gate: disk ownership, PCI isolation, the approved contents-disposal scope,
and rescue path are documented from current read-only evidence. Stop if the
live serial set differs from the approved eight drives or the HBA group
includes a host-required device.

## 1. Prove VM and HBA passthrough without changing SATA data

1. Complete the Proxmox OpenTofu control-plane and disposable-VM gates in the
   [first-VM plan](first-vm-implementation-plan.md). Install TrueNAS Community
   Edition 25.10.7 from the official SHA-256-pinned ISO selected in [ADR
   0011](decisions/0011-use-truenas-community-edition-for-the-nas-guest.md).
   Recheck release status before upgrades. Keep the VM stopped until a usable
   console path is verified; do not attach the HBA during initial installation.
2. Add the root-created `nas-hba` PCI resource mapping in versioned
   `host/pve/` maintenance code. Pin the live device, subsystem ID, and IOMMU
   group; create a host-configuration backup; and verify PVE's mapping
   diagnostics. Grant the OpenTofu user and privilege-separated token only
   `Mapping.Use` at `/mapping/pci/nas-hba`; do not grant `Mapping.Modify`.
   The one-time installer-ISO removal also needs `VM.Config.CDROM` for VMID
   200. Grant it with the VM-scoped role in `host/pve/manage-tofu-identity.sh`;
   retain `Sys.Audit` at that exact path and disable ACL propagation. Do not
   grant node-wide `Sys.Console`.
3. Add separate OpenTofu plan gates for attaching the mapping to stopped VMID
   200 and for starting the VM. Keep `on_boot=false` and `started=false` until
   the console and recovery path are proven. The attach plan must contain only
   the exact HBA mapping; the start plan must preserve that mapping and change
   only the stopped state.
   After installation, use the separate `--nas-reattach` gate for the stopped
   guest with its installer ISO detached and `scsi0` first. Keep the installer
   `--nas-attach` gate pinned to ISO-first installation state.
4. Use Proxmox's on-demand PCI resource mapping for HBA driver handoff; do not
   add a post-stop rebind hook or boot-time VFIO binding. The versioned mapping
   helper provides preview/check/apply/rollback, and the separate
   `host/pve/check-nas-passthrough.sh` validates the live VM/driver state. A
   gated start moved the HBA to `vfio-pci` and a gated stop left it there; after
   a cold host boot with the VM stopped, `mpt3sas` may bind. See [ADR
   0012](decisions/0012-keep-nas-hba-on-demand-vfio.md).
5. Define the NAS VM in OpenTofu with a boot disk on `fast-vm`, a persistent
   network identity, and a memory allocation based on the verified 128 GiB
   host. Do not assume the future 256 GiB upgrade. Keep host-side mapping
   administration outside the routine OpenTofu token.
6. Apply the reviewed, type-gated plans. Inside the guest, verify that all eight
   expected serials and SMART data are visible and that the host no longer
   binds the HBA or sees its disks while the VM runs. Exercise repeated VM
   start, clean stop, and reset. Cold-boot the host and verify `rpool`,
   `fast-vm`, NAS VM, HBA assignment, and guest disk serials.

Exit gate: the guest controls the whole HBA consistently across starts and a
host cold boot; the host's own boot/storage path remains independent. Do not
create the SATA pool if passthrough is unstable.

## 2. Build NAS storage and shares

1. Reconfirm the approved eight serials and review the exact pool-creation plan
   before clearing signatures or partitions. The existing contents are
   disposable by operator decision. Use guest stable disk identifiers, not
   changing Linux `/dev/sd*` names. Create the eight-disk RAIDZ2 pool in the
   NAS guest only.
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

Stop before a write on uncertain serials, shared IOMMU ownership, inaccessible
rescue console, unexpected OpenTofu plan
resources, unrecoverable state, or new disk/memory errors. Preserve the current
state for diagnosis; do not force a pool import or bypass the plan gate merely
to complete a milestone.
