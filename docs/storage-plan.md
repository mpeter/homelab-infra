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

`scratch` is reproducible, but loss of either striped member makes the pool
unavailable. The current manager has no recovery path for a completed pool; a
rebuild requires a reviewed versioned procedure and confirmation of every
workload's disposition. It must not hold unique state.

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

The `/boot` and `/boot/efi` filesystems were still mounted from Kingston SATA
SSD serial `50026B7767031A82` at the strict-host-key read on 2026-10-03 at
14:29 EDT. Firmware reported `BootCurrent` as `Boot000B Proxmox SATA Boot` and
the order prefix `Boot000B, Boot000A, Boot0009`. The two configured NVMe ESPs
map to distinct `rpool` mirror members: serial `BTHH95021LD4512D` maps to
filesystem UUID `929D-9F5B`, PARTUUID
`a6ab2778-6cfa-4764-864d-4c63bb08364e`, and `Boot0009`; serial
`BTHH8122061E512D` maps to UUID `929E-65B4`, PARTUUID
`c0096bb5-4bfc-4fc0-ad5b-156a16e0a9ab`, and `Boot000A`. Both entries point to
`\EFI\systemd\systemd-bootx64.efi`. `rpool` and `fast-vm` reported ONLINE
and all pools healthy. The current read-only evidence is recorded as
`pve_boot_readback_1429` in [`inventory/storage.yaml`](../inventory/storage.yaml).

The earlier `pve_boot_readback` record is retained with its caveat because it
ran `proxmox-boot-tool status`, which may mount ESPs. The 14:29 capture used
`findmnt`, the configured UUID file, `lsblk`, and `efibootmgr`; it did not call
that helper, mount an ESP, or change host state. Read-only inspection of
`proxmox-kernel-helper` 9.1.0+fde2 found post-install and post-removal hooks
that iterate the configured ESP UUIDs and copy/configure kernels, plus an
initramfs post-update hook that requests `proxmox-boot-tool refresh`. These
hooks mount ESPs and may write boot files when run; none was executed. Their
strict failure handling defaults off, so hook presence does not prove an ESP
was successfully updated. At the 14:29 read, the NVMe ESP directory entries
had not been inspected and `mdir` was not installed on PVE. A strict-host-key
read-only check at 18:39–18:40 EDT used the installed `fsck.fat 4.2 -n -l`
directly on the serial-bearing `/dev/disk/by-id/` partition paths, without
mounting either ESP. The tool listed `EFI/systemd/systemd-bootx64.efi`, the
fallback `EFI/BOOT/BOOTX64.EFI`, and the Proxmox 7.0.2-6-pve kernel, initrd,
and loader entries on both ESPs. Both checks exited 1, reporting a set dirty
bit and a primary/backup boot-sector difference at offset 65 (`01`/`00`); the
no-op mode reported that both filesystems were left unchanged. This verifies
directory entries only, not binary contents, synchronization, or successful
firmware boot. The result is recorded as
`pve_esp_inspection_readback_1840` in
[`inventory/storage.yaml`](../inventory/storage.yaml). The attached PVE
installer USB is not evidence of off-host recovery media. Neither NVMe entry
has passed a cold-boot test, so both remain candidates.

A strict-host-key PCIe topology read at 18:58 EDT maps SMBIOS system slot
`PCI4` (bus address `0000:42:00.0`) to a PLX PEX8632 switch. Both boot NVMe
controllers are downstream of that switch: serial `BTHH95021LD4512D` is at
downstream bridge `0000:43:04.0` / endpoint `0000:44:00.0`, and serial
`BTHH8122061E512D` is at `0000:43:05.0` / endpoint `0000:45:00.0`. The
software topology does not identify the corresponding physical connector
labels on the adapter. Map each connector to its serial before an outage; do
not remove the shared `PCI4` adapter to isolate one NVMe, because that would
remove both boot candidates. The readback is recorded as
`pve_boot_nvme_pcie_readback_1858` in [`inventory/storage.yaml`](../inventory/storage.yaml).

**Scope update (2026-10-05):** The alternate boot-path and recovery-media exercise
described here was removed from the active OpenSpec change and moved to the
[boot/recovery backlog item](../.backlog/2026-10-05-document-and-prove-independent-r720-boot-and-recovery.md).
This matrix is reference for later work; it does not schedule a cold boot or
authorize a device change.

### Versioned cold-boot recovery procedure — preparation only

Run this procedure only in a planned outage after a fresh serial-bound
read-back, verified recovery console, and off-host recovery media plus exact
reconstruction instructions are available. The read-back must confirm the
same partition UUIDs and UEFI entries below, both mirror members, and healthy
pool status. Do not use Linux device names as physical identities.

#### Recovery readiness checklist

| Gate | Evidence required before a boot-device test | Current status |
| --- | --- | --- |
| Recovery media | Bootable PVE recovery medium kept off the R720, with its version and checksum recorded; verify it reaches a recovery environment without starting installation | `pve_boot_readback_1429` records the PVE installer USB attached to the R720 as serial `KT20200000000975`; no off-host recovery medium is verified |
| Boot metadata | Off-host, hash-checked copies of the boot UUID list, firmware entries, serial-to-device map, physical adapter/connector location for each serial, and both boot-device partition tables | Firmware entries, system slot `PCI4`, and PCIe downstream addresses are inventoried; exact physical adapter-connector labels remain unverified, and partition-table and EFI-payload recovery copies are not verified |
| Reconstruction | Reviewed sequence bound to current serials and `/dev/disk/by-id/` paths, with installed bootloader mode, target partition fit, and expected ZFS resilver and post-repair checks confirmed | The linked Proxmox procedure is a vendor reference only; exact R720 commands and successful EFI synchronization are unverified |
| Console and rollback | Verify iDRAC/physical console access and retain the known-good Kingston SATA boot path through both tests | The Kingston path is inventoried; recovery-console readiness for these tests is not verified |

Record each gate's evidence before scheduling either cold boot. A same-host
installer USB does not satisfy the off-host-media gate, and a successful
generic procedure description does not substitute for a target-specific
reconstruction sequence. Record the physical adapter/connector position for
each serial before attempting to isolate either device.

| Test target | Expected serial and ESP | Expected firmware entry | Independent test condition |
| --- | --- | --- | --- |
| NVMe A | `BTHH95021LD4512D`, UUID `929D-9F5B`, PARTUUID `a6ab2778-6cfa-4764-864d-4c63bb08364e` | `Boot0009` | Cold boot with NVMe B unavailable |
| NVMe B | `BTHH8122061E512D`, UUID `929E-65B4`, PARTUUID `c0096bb5-4bfc-4fc0-ad5b-156a16e0a9ab` | `Boot000A` | Cold boot with NVMe A unavailable |

For each row, first map the serial to its physical adapter connector. Shut down
cleanly, isolate only the opposite NVMe module at that verified connector while
the host is powered off, then use the firmware's one-time boot selection for
the target entry. Both NVMe devices are behind the same `PCI4` switch; removing
that adapter would remove both, so do not use it as the isolation step. Keep
the Kingston SATA boot
device connected as the recovery path. After boot, require `BootCurrent` to
equal the target entry; a fallback to `Boot000B` does not pass. Verify PVE
management access, expected `rpool` mirror degradation with the peer absent,
and no new pool errors. Power down, restore the removed device to its original
connection, boot through the known-good Kingston path if needed, and wait for
any resilver before returning to service. Record serials, selected entry,
`BootCurrent`, pool status, and recovery outcome for each case. Do not alter
permanent firmware order or ESP contents during these tests.

The runbook is versioned here, but not yet executable as a complete recovery
procedure: off-host recovery media and exact reconstruction steps have not
been verified, the live contents and successful synchronization of the EFI
payloads have not been verified, and neither cold-boot test has run. If either
current NVMe entry fails, stop and prepare a separately reviewed second-device
plan. Do not infer that a new SATA SSD is needed until both candidate paths
have been tested.

### Failed-boot-device recovery reference — preparation only

The [Proxmox VE Administration Guide's boot-device replacement procedure](https://pve.proxmox.com/pve-docs/pve-admin-guide.pdf)
is a vendor reference for identifying the bootloader, reproducing a healthy
device's partition layout, regenerating disk identifiers, and replacing the
failed ZFS member. Its `proxmox-boot-tool` guidance distinguishes formatting
an EFI System Partition from initializing it in the appropriate bootloader
mode; initialization refreshes configured ESPs and may write boot files to
each one.

This reference does not establish the R720's current loader mode, partition
fit, live EFI payloads, or an executable serial-bound recovery sequence. Before
preparing commands, verify those facts against the installed PVE version and
fresh `/dev/disk/by-id/`/serial read-back, and provide off-host recovery media,
a verified recovery console, a recoverable copy, and a planned outage. Generic
example device paths are not targets. Do not run partition-table copying,
`sgdisk`, `proxmox-boot-tool format`/`init`, or `zpool replace` during read-only
inventory or either cold-boot test. No replacement command has run.

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

The serial-specific read-only scratch-candidate snapshot from 2026-10-03
09:57 EDT is recorded in `scratch_candidate_readback` in
[`inventory/storage.yaml`](../inventory/storage.yaml). It found that
`front-nvme-c` (`PHHH8505034Q512H`) had a GPT, an EFI VFAT partition, and an old
ZFS member with pool GUID `14828205673918207700` and label
`rpool-OLD-14828205673918207700`; `front-nvme-d` (`BTHH8244042V512D`) had no
partition or wipefs signature at that observation. A strict-host-key read at
12:51 EDT is recorded separately in `scratch_candidate_readback_1251`; it
confirmed the serial mappings, refreshed the partition and SMART details, and
found the same GPT/EFI/ZFS member on `front-nvme-c` and no child partition or
`blkid -p` signature on `front-nvme-d`. The later read did not inspect pool
membership, mounts, holders, boot references, sector hashes, or data
disposition, and it is not an executable preflight. Both observations reported
SMART health as PASSED. Neither classifies the old contents as disposable or
authorizes clearing metadata or creating the scratch pool.

### Scratch candidate preflight gate

Before any scratch-disk write, capture one fresh read-only snapshot on PVE and
bind every result to the current boot ID, time, exact serial, canonical whole-
disk path, and all matching `/dev/disk/by-id` aliases. Require the independent
`lsblk` serial and by-id name to agree, and require exactly one whole disk for
each expected serial. Missing, partition-only, duplicate, or conflicting
identity is `UNKNOWN` and blocks the gate.

The preflight must distinguish `CLEAR`, `BLOCK`, and `UNKNOWN`; only `CLEAR`
may pass a current-state check, and any `BLOCK` or `UNKNOWN` blocks the pool
plan. Establish positive controls before interpreting an empty result: `rpool`
and `fast-vm` must be visible in imported ZFS status, `fast-vm` must be present
in the mounted `/etc/pve/storage.cfg`, and both recorded `rpool` ESP filesystem
UUIDs (`929D-9F5B` and `929E-65B4`) must appear in the read-only
`/etc/kernel/proxmox-boot-uuids` configuration and independently map to VFAT
partitions in `lsblk` output. Match their corresponding PARTUUIDs
(`a6ab2778-6cfa-4764-864d-4c63bb08364e` and
`c0096bb5-4bfc-4fc0-ad5b-156a16e0a9ab`) against every firmware `Boot####`
device path. Do not call `proxmox-boot-tool status` during preflight: its
implementation can mount ESPs. A missing control, unmounted `/etc/pve`,
unavailable command, or command error is `UNKNOWN`, not evidence of no
reference.

For both whole disks and every child partition, check partition tables,
filesystem and ZFS labels, whole-device and partition signatures, and the
first and last 8 MiB. Non-zero unsigned bytes are `BLOCK` for review, not proof
that data is disposable. Resolve active pool membership by canonical device
identity and inspect both imported and importable ZFS pools without importing
anything. Check mounts, swap, sysfs holders, PVE VM/CT configuration and PCI
mapping, `storage.cfg`, `/etc/fstab`, `/etc/crypttab`, the ZFS cache, firmware
boot order and every boot entry, and Proxmox ESP references by UUID. Check the
host and versioned OpenTofu source for an existing `scratch` pool or storage ID.
SMART evidence must include overall health, critical warning, media/data-
integrity errors, and available spare against the drive-reported threshold;
failed or unavailable health evidence blocks the gate.

The evidence collector must use probes whose device opens have been verified
read-only in the pinned PVE environment. `wipefs --no-act` is not accepted as a
preflight probe until its actual open mode has been verified. Do not use a
command that writes, rereads partition tables, imports a pool, starts a SMART
self-test, mounts a candidate, or triggers udev. Keep collected output on the
workstation. A workstation-driven run may stage its hash-verified source bundle
in a unique mode-0700 directory under PVE `/run`; the remote wrapper removes it
on exit, and it keeps preflight output in memory. Do not stage evidence or
temporary files on candidate disks or persistent PVE storage.

A workstation-local three-state checker is implemented at
[`host/pve/check_scratch_preflight.py`](../host/pve/check_scratch_preflight.py)
with behavioral tests at
[`host/pve/tests/test_check_scratch_preflight.py`](../host/pve/tests/test_check_scratch_preflight.py).
It rejects `proxmox-boot-tool status`, checks every imported pool, binds each
configured ESP filesystem UUID to its expected unique EFI partition and
PARTUUID, and reports malformed SMART fields as `UNKNOWN`. The installed PVE
probe open modes were traced on 2026-10-03 before the first accepted live run.
`lsblk` opened sysfs entries read-only; `blkid`, `blockdev`, both `dd` boundary
reads, and `smartctl` opened candidate block devices read-only. `zpool import`
opened candidate devices read-only while scanning. The `zpool list` and
`zpool status` commands opened `/dev/zfs` read-write for the ZFS control
interface, without opening candidate block devices. The earlier checker run
that called `proxmox-boot-tool status` is still rejected as read-only evidence because
that command may mount ESPs.

The accepted read-only scan at 14:06 EDT is recorded as
`scratch_candidate_preflight_140648` in
[`inventory/storage.yaml`](../inventory/storage.yaml). It confirms that
`front-nvme-c` remains `BLOCK` because its GPT, EFI, and old ZFS member are
present and its old pool is importable. `front-nvme-d` has no partitions or
recognized signature and its first 8 MiB are zero, but its final 8 MiB contain
non-zero bytes, so it is also `BLOCK` and is not classified as blank. The full
serial-bound scan found no mount, swap, holder, imported-pool,
host-configuration, or firmware references to either disk; required positive
controls were present. A separate 14:13 EDT workstation scan of all five
versioned OpenTofu source files found no `scratch` pool or storage reference.
A future `CLEAR` result is a time-bound preflight, not
an operator classification, metadata capture, approval to erase, or
authorization to create a pool. Before a write, separately record the
operator's disposition of existing contents, preserve the required headers
off-target, review the full clearing scope (including the old GPT, EFI
partition, and ZFS label on `front-nvme-c`), and obtain write approval. Repeat
the serial-bound preflight immediately before the authorized write and verify
each disk afterward. Keep the pool task open until the resulting `scratch`
storage is documented as disposable and cannot be selected for durable VM or
backup data.

A fresh serial-bound read-only preflight at 17:20:22 EDT again returned
`BLOCK`, with all probes completing and no `UNKNOWN` findings. `front-nvme-c`
(`PHHH8505034Q512H`) still has three child partitions, signatures on its whole
disk and partitions, non-zero bytes at both boundaries, and an importable old
ZFS pool. `front-nvme-d` (`BTHH8244042V512D`) has no child or recognized
signature and a zero first 8 MiB, but its final 8 MiB remain non-zero. Both
serial-to-by-id checks, required host/storage/ESP positive controls, and
read-only SMART health/error/spare probes passed; neither candidate has a
mount, swap, holder, imported-pool, host-configuration, or firmware reference.
The host still has no `scratch` pool or storage ID. This refresh does not
classify either disk's contents, preserve metadata off-target, or authorize any
write. The raw output is in local task scratch, and the full result is recorded
as `scratch_candidate_preflight_172022` in
[`inventory/storage.yaml`](../inventory/storage.yaml). Task 6.3 remains
open pending operator content disposition and the required write/recovery
gates.

A strict-host-key serial-bound preflight at 20:10:45 EDT on 2026-10-03 again
returned `BLOCK` with no `UNKNOWN` findings. It confirmed `front-nvme-c`
(`PHHH8505034Q512H`) still has three partitions, GPT/EFI/ZFS signatures, and an
importable old pool; `front-nvme-d` (`BTHH8244042V512D`) still has a non-zero
last 8 MiB even though its first 8 MiB are zero and no partition or recognized
signature was reported. SMART and required positive controls passed; neither
candidate has a mount, swap, holder, imported-pool, host-configuration, or
firmware reference. The host has no `scratch` pool or PVE storage ID. The
checker output is retained in private workstation task scratch and recorded as
`scratch_candidate_preflight_201045` in
[`inventory/storage.yaml`](../inventory/storage.yaml).

At 20:13:19–20:13:22 EDT, after rechecking each serial-bearing `/dev/disk/by-id`
alias, canonical path, and 512110190592-byte device size, the first and last
8 MiB of each candidate were read with the previously verified read-only
`dd` probes and saved only to private workstation scratch. SHA-256 values and
the local artifact path are recorded as
`scratch_boundary_metadata_capture_201319` in
[`inventory/storage.yaml`](../inventory/storage.yaml). The boundary bytes were
not parsed or classified; these captures are not a full data backup, do not
establish that either disk is disposable, and do not authorize clearing or pool
creation. Task 6.3 remains open pending operator content disposition, reviewed
clearing scope, and separate write/recovery gates.

### Operator disposition and reviewed apply plan — 2026-10-04

The operator authorized discarding contents on exactly these two scratch
candidates: `PHHH8505034Q512H` (`/dev/nvme4n1`,
`/dev/disk/by-id/nvme-INTEL_SSDPEKKF512G8_PHHH8505034Q512H_1`) and
`BTHH8244042V512D` (`/dev/nvme5n1`,
`/dev/disk/by-id/nvme-INTEL_SSDPEKKF512G8_BTHH8244042V512D_1`). This is an
operator-approved data-loss disposition, not a claim that the devices contain
no data. It does not extend to any other disk. The 2026-10-03 captures preserve
only first/last 8 MiB boundaries and are not a restore path.

The first destructive apply must begin with a fresh strict-host-key read on PVE
and bind the exact boot ID, candidate serials, canonical paths, capacity, logical
sector size, partition identity, all six current boundary-capture hashes, and
the source bundle. Continue only if the preflight returns the same nine
serial-specific BLOCK findings and no UNKNOWN findings, all positive controls
are CLEAR, the exact monitor v1 files and marker match their reviewed hashes,
and the `scratch` pool/storage ID and ownership path are absent. A changed
finding, boot ID, source, capture, alias, partition, SMART result, or host
reference stops the apply for a new review.

Before its first disk write, the apply manager records the reviewed plan hash,
boot ID, and serials in a root-owned transaction journal on PVE. A same-plan
retry requires an unchanged boot ID and a fresh serial, reference, and layout
check. For the interrupted 2026-10-04 create attempt only, a one-time journal
migration accepts the exact predecessor plan hash
`9ecdfefbb0fdf8961491a76b6e309814d77c2a921fd6997f2b78983d6d0af762`, its exact
findings hash, the two recorded serials, and `phase=labels-cleared`. Before
any recovery write, both disks must independently classify as either clean or
the exact generated OpenZFS GPT layout from that attempt. The generated layout
is pinned by both partition UUIDs, types, starts, sizes and labels; `wipefs`
must show only that disk's GPT/PMBR signatures and no signatures on either
partition. This permits a retry after power loss between clearing the two
GPTs. The manager durably replaces the predecessor journal with the newly
reviewed plan before clearing only the remaining exact GPT metadata. It then
settles udev and verifies both serial-bound disks are partition-free and have
no signatures, pools, mounts, or host references before pool creation. Any
UNKNOWN, unexpected BLOCK, mixed partition table, new ZFS label, changed boot
ID, or other journal phase stops without another disk write.

That predecessor corresponds to a failed `zpool create` rejected because its
comment exceeded OpenZFS's 32-character limit. The command left the matching
GPT tables on both candidates but created no pool; a fresh read-only import
and PVE storage check confirmed only `rpool` and `fast-vm` were present.

The first resume then created the intended `scratch` stripe, but its read-back
stopped because the topology parser rejected PVE's tab-plus-space indentation.
A second resume created `scratch/vm`, installed the v2 capacity monitor, and
registered `scratch`. The manager stopped because Proxmox canonicalized the
content set as `rootdir,images`, while the read-back expected the equivalent
`images,rootdir` order. A read-only check found the storage active and its
volume list empty. The topology-validator continuation used a one-time
migration pinned to plan hash
`fb832d1e722ece4eec3ed068a86b67d31f60f40ae4acd3a10c8fe1ade4217c8d`, findings
hash `ec484023e39a961d2e7af45a8e9b2fe9eb6e4c2df5fc5c5524e6e42a5a3ebcd7`, the
same two serials, and `phase=zpool-create-started`. Before that continuation,
read-only verification confirmed the already-created pool was the exact ONLINE
two-member stripe with the reviewed properties. It did not repeat disk cleanup
or recreate the pool.

For the current `monitor-installed` journal, a separate one-time migration is
pinned to plan hash
`e2b9109814b8fa292c11aaa95439e092c79b26b173df724bf07adbce844a7cfd`, findings
hash `ec484023e39a961d2e7af45a8e9b2fe9eb6e4c2df5fc5c5524e6e42a5a3ebcd7`, and
both candidate serials. The updated storage read-back accepts exactly one
`content` directive with either ordering of the `images` and `rootdir` set;
extra, duplicate, or backup content is rejected. The existing storage entry is
verified in place and is not added again.

If the pool already exists, recovery instead requires its exact two generated
`-part1` members, ONLINE state, ashift, and pool properties; this post-pool
continuation does not repeat the pre-creation reference scan and never clears
or destroys the existing pool or dataset. Each journal replacement is synced
before the manager advances to the next destructive phase. A durable
`zpool-create-started` phase precedes every create call. If a later create
attempt stops before producing the exact healthy pool, or the boot ID changes,
recovery stops for a new review; it is never force-imported, force-created, or
destroyed automatically.

The reviewed write sequence is narrowly scoped: run `zpool labelclear -f` on
candidate C partition 3 only; run `wipefs --all` on candidate C partition 2
and then candidate C's whole-disk by-id path to clear its old GPT/PMBR; verify
the remaining whole-disk signatures and removed child partitions; then run
`zpool create` without `-f` on the two whole-disk by-id paths. Candidate D's
non-zero tail is not described as blank and is not separately wiped; the
operator's disposition covers it, and pool creation must still refuse any
signature OpenZFS considers unsafe. Create a two-device stripe with `ashift=12`,
`failmode=continue`, automatic expansion/replacement/TRIM disabled, the exact
short comment `DISPOSABLE: no unique data` (within OpenZFS's 32-character
limit), and no root mountpoint. Create only
`scratch/vm` at `/scratch/vm` with `lz4` and `atime=off`.

Register PVE storage `scratch` for `images,rootdir` only, with no backup
content. Upgrade the existing, exact managed capacity-monitor v1 installation
to v2 so the journal-only 80% warning / 90% critical policy evaluates
`rpool`, `fast-vm`, and `scratch` every five minutes. The monitor upgrade is
refused unless its current marker, previous source hash, service, and timer
match the reviewed v1 installation.

After the writes, read back the exact two generated partition members (`-part1`)
in the ONLINE stripe and its ashift,
pool and dataset properties, absence of known data errors, the PVE storage
config/content boundary and active status, the v2 monitor sources/marker and
enabled timer, and a successful collector run that records scratch. The
OpenTofu plan gate must continue rejecting disposable VM disks on `scratch`.
Do not run backups or place unique data there. If a scratch member becomes
unreadable, the capacity monitor records a critical `pool_unreadable` state for
that pool and continues reporting each readable pool among `rpool`, `fast-vm`,
and `scratch`. The stripe has no
redundancy; loss of either member loses the pool. Configuration-only rollback
may remove the PVE registration only while no VM/CT references or volumes
exist; the reference scan must complete successfully and the `pvesm list`
output must have its expected header and contain no volume rows. Malformed
output or read errors stop rollback. It must leave labels, the pool, and its
contents in place. Task 6.3 completed after the serial-bound live read-backs
and storage-boundary verification recorded as
`pve_scratch_tier_readback_143840` in
[`inventory/storage.yaml`](../inventory/storage.yaml). This completion does
not establish a completed-pool rebuild path or device-failure recovery.

## Pool health and device-failure response

The read-only PVE snapshot from 2026-10-03 08:03 EDT is recorded in the
component-dated `rpool`, `fast_vm`, and `pve_storage_monitoring` sections of
[`inventory/storage.yaml`](../inventory/storage.yaml). A follow-up capture at
09:36 EDT is recorded in `pve_storage_health_capture`; a further read-only
capture at 11:17 EDT is recorded separately in `pve_storage_health_readback_1117`.
The file-level date and
NAS/SATA sections retain their earlier observation dates; neither PVE readback
refreshes guest-owned disk or pool evidence. In the follow-up, `rpool` and
`fast-vm` were ONLINE mirrors with no recorded read, write, checksum, or known
data errors. The versioned `host/pve/check-fast-vm.sh` drift check and
`host/pve/capture-storage-health.sh` evidence collector both passed against the
live host. The collector reports raw read-only pool, dataset, PVE storage,
scrub, smartd, and serial-bearing SMART evidence; command success is not a pool
health assessment. It does not evaluate capacity alert thresholds or exercise
a device-failure procedure. ZFS automatic periodic scrub is enabled by the PVE
package's monthly second-Sunday cron schedule; the pools' effective property
is `auto`, but `zpool status -v` showed no scan entry at capture time. `smartd`
was active with an active `DEVICESCAN` health-monitoring line. No scheduled
SMART self-test was configured, and the boot SSD's self-test log was empty.
PVE ZFS datasets report no quota or refquota.

The 11:17 EDT capture again found both host mirrors ONLINE with no known data
errors and all five queried host-owned devices reporting SMART overall health
PASSED. The active `smartd` policy has no scheduled self-test directive, and
none of those five devices had a self-test logged. `pvesm status` reported
`fast-vm` at 0.61% used, `local` at 0.94%, and `local-zfs` at 0.00%. This
read-only collector still does not evaluate capacity thresholds or exercise a
device-failure procedure; the current inventory records the measurements and
their limits.

A focused read-only PVE check at 11:51 EDT found only `rpool` and `fast-vm` in
the host's imported-pool list; `zpool status -x` reported all pools healthy.
Their exact size, allocation, free-byte, and PVE storage-usage read-backs are
recorded separately in `pve_storage_status_readback_1151` in
[`inventory/storage.yaml`](../inventory/storage.yaml). This check did not
refresh SMART details or scrub configuration, and it does not evaluate alert
thresholds or exercise failure procedures.

### PVE host pool capacity monitoring — 2026-10-04

The operator selected a warning at 80% and critical at 90%, evaluated every
five minutes for host-owned pools `rpool`, `fast-vm`, and `scratch`. The versioned monitor
at [`host/pve/storage-capacity-monitor.sh`](../host/pve/storage-capacity-monitor.sh)
records severity transitions, unreadable-pool transitions, and recovery in the local system journal;
it does not send mail or prove alert delivery. The workstation-runnable
`host/pve/manage-storage-capacity-monitor.sh` owns preview, check, apply, and
rollback for the monitor and its systemd timer.

The source was previewed, applied, and checked over strict pinned SSH on
2026-10-04. At the 10:50 EDT service read-back, both pools were ONLINE at 1%
and 0%; the monitor completed with exit status 0 and saved `normal` for both.
The enabled timer fired at 10:55:13 EDT; that run also completed with exit
status 0, and the next run was scheduled for 11:00 EDT. This verifies the
installed policy, a real read-only monitor execution, and one scheduled
firing, but not a live threshold crossing, delivery, or a device-failure
procedure. See
`pve_storage_capacity_monitor_readback_105054` in
[`inventory/storage.yaml`](../inventory/storage.yaml). Task 6.4 remains open,
including the TrueNAS certificate and SMART access gaps.

A fresh strict-host-key read-only PVE capture at 16:05:58 EDT found `rpool` and
`fast-vm` ONLINE mirrors and `scratch` an ONLINE two-member stripe, all with
zero read, write, checksum, and known data errors. All six host-pool NVMe
devices and the Kingston boot SSD reported SMART PASSED; NVMe critical-warning,
media-integrity, and error-log counters were zero, and no host device showed a
logged self-test. `smartd` remained active without a scheduled self-test
directive. The monthly second-Sunday scrub schedule is configured, but none of
the three `zpool status` outputs contained a `scan:` line, so active scrub
status is not established. Host pool dataset quotas and refquotas remain unset;
PVE storage use was 0.73% for `fast-vm`, 0.94% for `local`, and 0.00% for
`local-zfs` and `scratch`. The capture returned exit status 0. Exact values and
provenance are in `pve_storage_health_readback_160558` in
[`inventory/storage.yaml`](../inventory/storage.yaml).

At 16:09:05 EDT the monitor manager check passed. A strict-host-key runtime
read at 16:09:11 confirmed the timer active and waiting, with a 16:05:12 last
firing and 16:10:00 next firing. The journal showed five successful scheduled
service runs at five-minute intervals from 15:45:12 through 16:05:12. No
threshold transition was produced because all pools remained below 80%.
`pvesm list scratch` returned no volumes. This verifies repeated scheduled
execution and the current empty PVE volume list, not a live threshold crossing
or device-failure exercise. The monitor's policy is local-journal only; remote
notification delivery is a separate Task 9.3 gate. See
`pve_storage_health_readback_160558` in
[`inventory/storage.yaml`](../inventory/storage.yaml).

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
HBA disks from PVE. `scratch` is a two-member stripe with no redundancy; losing
either member makes the pool unavailable, and it has no in-place resilver or
single-member replacement path. On a suspected scratch failure, stop new
placements and capture pool events, exact by-id paths/serials, SMART, PVE
storage status, and `pvesm list scratch`. The old pre-pool disk-disposition
authorization does not authorize deleting data later placed on the pool. Do
not offline, detach, clear, destroy, or recreate the live pool ad hoc. The
current manager does not implement recovery of a completed scratch pool; a
rebuild requires a reviewed versioned recovery path, a fresh serial/reference
preflight, and current confirmation that every affected workload may be
discarded. No device was faulted, offlined, or replaced during this read-only
pass; representative failure-procedure results remain open.

#### Non-live scratch member-loss drill

Run `bash host/pve/tests/test-scratch-failure-drill.sh` for a local synthetic
check. It feeds the versioned topology validator a representative `UNAVAIL`
scratch stripe with one unavailable member and one online member, and passes
only when the validator refuses that state. The test invokes no `zpool`, PVE,
device, or recovery command; it verifies fail-closed classification, not live
failure detection, data recovery, or a rebuild.

For an actual unreadable-member alert, preserve the read-only evidence above,
stop new placements, and treat the whole stripe as unavailable. Do not run a
single-device replace, offline/detach, `zpool clear`, forced import, destroy,
or recreate command. Recover affected workloads from their authoritative
source or a separately verified backup. If neither exists, stop for an
operator data-disposition decision. Recreating `scratch` requires a new
reviewed versioned procedure, fresh serial-bound identity/reference checks,
and confirmation that all affected contents can be discarded; the current
manager deliberately has no completed-pool rebuild operation.

`tank` belongs to the TrueNAS guest and must only be inspected or repaired
through a trusted guest-management path. On 2026-10-03 a managed personal Chrome
session selected VM 200 in the authenticated PVE UI and displayed its local
console through a noVNC frame on the same PVE origin. A later read-only guest
query found `boot-pool` and `tank` ONLINE with no known data errors, an eight
member RAIDZ2 topology, and a completed 2026-10-02 scrub with zero repairs or
errors; `midclt call alert.list` returned an empty list. The current 5 GiB
quotas on `tank/nfs_test` and `tank/smb_test` were also read back. Provenance
and limits are in `truenas_storage_health_readback` in
[`inventory/storage.yaml`](../inventory/storage.yaml). This output did not
identify pool members by serial or verify SMART test scheduling/history,
capacity thresholds, alert delivery, or the guest certificate identity. An
11:57 EDT console retry reached the Linux shell prompt but could not deliver
Enter through the noVNC frame, so it ran no guest command and did not refresh
alert or certificate evidence; see `truenas_console_input_attempt_1157` in the
inventory. A 13:54 EDT retry again showed the Linux root prompt, but Chrome-use
still delivered Enter to the outer iframe; the console returned to View Only
after the attempt. It did not refresh guest state. See
`truenas_console_input_attempt_1354` in the inventory. A 14:27 EDT retry began
from the root prompt after the operator selected Linux CLI option 8;
chrome-use could not type into noVNC's hidden input, so no command was
submitted and View Only was restored. See
`truenas_console_input_attempt_1427` in the inventory. Independently, a
14:28 EDT TLS handshake to the recorded guest address returned an iXsystems
self-signed certificate with `CN=localhost` and only `DNS:localhost` in its
SAN; the leaf fingerprint and IP mismatch are recorded in
`truenas_tls_identity_readback_1428`. This captures the served certificate,
but does not verify the certificate configured in TrueNAS or establish a
trusted endpoint. A read-only PVE guest-agent interface query also failed
because the VM's QEMU guest agent is not running, so the current
IP-to-VM attachment was not independently confirmed. A 15:21 EDT authenticated
PVE configuration read later showed VM 200 has `agent=enabled=0`; no agent was
enabled or invoked. At the 15:21 checkpoint, the current alert list had not yet
been refreshed; the 17:00:36 readback below supersedes that status and returned
`[]`. The earlier empty alert list is historical only. The
20%-free `fast-vm` criterion applies to Fedora promotion; no configured
capacity alert threshold or accepted device-failure exercise is evidenced yet.
OpenSpec task 6.4 remains open until the remaining NAS and operational gates
are verified.

A read-only TrueNAS WebUI review on 2026-10-04 confirmed the selected GUI
certificate is `truenas_default`; the Certificates page lists `CN=localhost`
and `SAN=DNS:localhost`. The GUI settings show HTTPS on port 443 with TLS 1.2
and 1.3. A strict OpenSSL verification of the served leaf still fails with
`verify error:num=18:self-signed certificate`, and the certificate SAN does
not name `192.168.0.186`; the UI was reachable in personal Chrome, but its
identity is not trusted. The browser showed no interstitial in this attempt,
and no browser policy was changed. The endpoint's current ARP MAC matches the
VM 200 `net0` MAC from the earlier PVE configuration read, but the PVE config
was not re-read in this turn.

The same UI read found `tank` online with no errors, a RAIDZ2 data vdev, and
usable capacity of 5.03 TiB (23.75 MiB used). Its last scrub finished on
2026-10-02 with zero errors; the configured schedule is Sunday at 00:00 and
Auto TRIM is off. The disk table maps all eight Crucial MX500 serials to
`tank`. The dashboard showed no active alerts and temperatures from 25 to
33 °C. A focused follow-up inspected Storage > Disks, Data Protection,
System > Services, and Reporting > Disk. The disk details showed device model
and configuration but no SMART health or test history; the service search
returned no SMART match, and disk reporting offered I/O and temperature only.
Guest SMART health and test schedule/history remain unverified. Data Protection
showed an enabled local `tank` snapshot task with seven-day retention and a
daily 23:00 schedule; its last run was FINISHED about 23 hours before the
00:59 EDT observation; the TrueNAS UI timezone was not established. Local
snapshots are not independent backup or restore evidence. The exact point-in-time UI and PVE evidence is recorded as
`truenas_webui_health_readback_0035`,
`truenas_webui_followup_readback_0100`, and
`pve_storage_health_readback_000930` in
[`inventory/storage.yaml`](../inventory/storage.yaml).

A follow-up visit to System > Shell at 01:07 EDT did not provide a usable
read-only command route: the terminal snapshot rendered CSS-like text rather
than a prompt, and screenshot capture timed out twice. No command was sent.
Guest SMART health and test history therefore remain unverified; see
`truenas_webui_shell_attempt_0107` in `inventory/storage.yaml`.

A focused read-only UI pass at 02:53–03:00 EDT revisited Storage > Disks and
Data Protection; expanded disk details showed model/configuration only, and no
SMART test table appeared. The UI's `SMART` search returned no UI result. The
Certificates page and GUI Settings independently showed `truenas_default`
selected, with `CN=localhost`, `SAN=DNS:localhost`, HTTPS port 443, and TLS
1.2/1.3. The Alerts drawer again showed no alerts. This pass did not re-read
the served leaf fingerprint or run strict TLS verification, so the endpoint
IP identity and trust remain unresolved; the prior object-to-leaf fingerprint
match is preserved in `truenas_certificate_object_match_0221`. See
`truenas_webui_followup_readback_0253` in
[`inventory/storage.yaml`](../inventory/storage.yaml). No SMART query or test
was attempted, and no settings or schedules changed.

A workstation TCP check at 03:07:36 EDT found `192.168.0.186:22` refused the
connection while port 443 accepted it. The current neighbor entry resolves to
`BC:24:11:87:F2:2B`, matching the earlier VM 200 `net0` MAC readback; PVE
configuration was not refreshed in this pass. No SSH authentication or guest
command was attempted. This makes SSH unavailable at the tested address and
port, not proof that no SSH route exists elsewhere. See
`truenas_ssh_port_probe_0307` in
[`inventory/storage.yaml`](../inventory/storage.yaml).

A focused authenticated System > Shell read at 03:21 EDT returned the eight
Crucial MX500 device serials, `zpool status -x` reported `all pools are
healthy`, and the WebUI Alerts drawer displayed “There are no alerts.” The
device listing does not by itself map Linux names to pool members. SMART access
as `truenas_admin` returned `Permission denied`; `sudo -n` reported that a
password is required. No password was entered and no self-test was started.
Guest SMART health/history therefore remain unverified. This session did not
perform strict TLS validation, so certificate identity remains unresolved.
Exact output and serials are in `truenas_guest_shell_readback_0321` in
[`inventory/storage.yaml`](../inventory/storage.yaml).

A read-only guest follow-up at 03:34:58 EDT matched each of `tank`'s eight
RAIDZ2 PARTUUID members to the corresponding Crucial serial. `tank` and
`boot-pool` were ONLINE with zero known data errors; the last displayed scrub
finished 2026-10-02 with 0 bytes repaired and zero errors. `zpool list` reported
7,971,459,301,376 bytes total and 37,871,616 allocated; `zfs list` reported
5,529,743,635,232 bytes available. Both test shares retain their 5 GiB
refquota. The WebUI still showed no alerts. Exact device mappings and dataset
quota output are in `truenas_guest_storage_detail_readback_0334` in
[`inventory/storage.yaml`](../inventory/storage.yaml). SMART remains blocked
for the unprivileged shell user, and this pass did not verify strict TLS
identity or a scrub schedule.

A fresh strict-host-key PVE collector at 03:29:36–03:29:39 EDT found `rpool`
and `fast-vm` ONLINE mirrors with zero known data errors, all four pool NVMe
members and the boot SSD SMART PASSED, no logged self-tests, and no active
scrub scan. PVE storage usage was 0.67%, 0.94%, and 0.00% for `fast-vm`,
`local`, and `local-zfs`; `smartd` remained active without a scheduled
self-test directive. The versioned `check-fast-vm.sh` baseline passed. A
separate strict-host-key read at 03:37 EDT found VM 200 running, the HBA bound
to `vfio-pci`, and only `rpool`/`fast-vm` imported on PVE. Exact measurements
and provenance are in `pve_storage_health_readback_032936` and
`pve_nas_ownership_readback_0337` in
[`inventory/storage.yaml`](../inventory/storage.yaml). Neither collector
evaluates a capacity threshold or exercises a device-failure procedure; task
6.4 remains open.

One earlier console attempt ran `midclt call system.general.config` without a
filter, and its response included private-key and certificate-PEM fields. The
local screenshot containing that response was deleted; no values were copied
into the repository or handoff. Do not run that command unfiltered. Use the
filtered pipeline below and the explicit public-field selection instead.

A fresh read-only host capture at 14:52 EDT found both PVE mirrors ONLINE with
no known data errors, all four host-pool NVMe members reporting SMART PASSED,
and the boot SSD reporting PASSED. `fast-vm`, `local`, and `local-zfs` were at
0.62%, 0.94%, and 0.00% used. The monthly second-Sunday scrub remains
configured, with no scan entry in either pool's status at 14:53; `smartd` is
active without a scheduled self-test directive. The remote `check-fast-vm.sh`
baseline passed. Exact measurements and serial-level SMART evidence are in
`pve_storage_health_readback_1452` in the inventory. No configured host-pool
capacity alert threshold was verified, and no failure procedure was
exercised.

A 14:47 EDT personal-Chrome recheck reached the PVE VM 200 details page but
did not open a noVNC console view; no guest command was submitted. See
`truenas_console_access_recheck_1447` in the inventory. At that checkpoint,
TrueNAS alert status was historical, and the certificate uncertainty was
unchanged.

At 14:58 EDT the noVNC console showed the TrueNAS root prompt after the
operator reset the shell and selected Linux CLI option 8. The read-only
`midclt call alert.list` attempt did not produce visible output: Chrome-use
routed Enter to the outer iframe, and a child-frame key event did not yield a
verifiable result. The hidden keyboard buffer still held the command at the
final read. View Only was restored to checked. Treat command execution as
unconfirmed; at the 14:58 checkpoint the active alert list had not yet been
refreshed. See
`truenas_console_input_attempt_1458` in the inventory. The certificate
configured in TrueNAS remains unverified.

After the operator reset the shell and selected Linux CLI option 8 again, a
15:23 EDT retry used the same-origin noVNC frame and still could not deliver
Enter: chrome-use reported the outer PVE iframe as the keyboard target. The
read-only `midclt call alert.list` command was not observed running. View Only
was restored and verified checked; the hidden input no longer contained the
command, although the final console screenshot was black and did not re-show
the root prompt. A same-origin PVE API GET confirmed `agent=enabled=0`, so no
existing guest-agent read path is available without changing VM configuration.
See `truenas_vm_config_readback_1521` and
`truenas_console_input_attempt_1523` in the inventory.

A fresh strict OpenSSL handshake to `192.168.0.186:443` failed trust validation
with return code 18 (self-signed leaf). The served certificate had SAN only
`DNS:localhost`; its SHA-256 fingerprint was
`41:18:AF:D3:FB:DD:24:27:99:3F:C7:5B:5C:9F:9C:73:1B:01:07:BC:CC:6C:E8:F2:70:EB:5E:90:30:E1:7B:30`.
That differs from the 14:28 observation despite the same recorded serial,
subject, issuer, and validity dates. At 15:31 EDT, one read-only ARP probe to
`192.168.0.186` returned MAC `BC:24:11:87:F2:2B`, matching VM 200's current PVE
`net0` MAC. This corroborates the current endpoint-to-VM NIC attachment. The
14:28 attachment was not checked then, so the fingerprint change cannot be
assigned conclusively to a certificate replacement on this VM. The TrueNAS
certificate selection remains unverified. See
`truenas_tls_endpoint_readback_1523` and
`truenas_endpoint_mac_readback_1531` in the inventory. The leaf is still
self-signed and does not identify the endpoint IP; do not use it as verified
TrueNAS identity. At the 15:31 checkpoint the active alert list also remained
unrefreshed; the 17:00:36 readback below supersedes that status.

At 15:45 EDT, one more read-only console attempt used the fresh noVNC
frame-local references. Chrome-use still routed Enter to the outer PVE iframe,
and the post-attempt screenshot did not show command output. The noVNC DOM
confirmed View Only was restored to true and its keyboard textarea held only
the underscore placeholder after clearing. Treat execution as unconfirmed;
the alert list remained unavailable at the 15:45 checkpoint. See
`truenas_console_input_attempt_1545` in the inventory.

At 15:54 EDT, after the operator reported resetting the shell and selecting
Linux CLI option 8, one final focused attempt again sent Enter to the outer PVE
iframe despite selecting noVNC frame 1 and targeting its keyboard textbox.
The fresh screenshot was black and showed no command result. View Only was
restored and verified true. Clearing the hidden input caused noVNC to refill
its underscore placeholder; a DOM read confirmed the command text was gone.
Treat execution as unconfirmed; the alert list remained unknown at the 15:54
checkpoint. See
`truenas_console_input_attempt_1554` in the inventory.

At 16:46 EDT, the VM 200 screenshot initially showed the TrueNAS root prompt,
but chrome-use could not enter `midclt call alert.list`: the hidden keyboard
field remained at its underscore placeholder and focus was reported on the
iframe. No Enter was sent, so execution is unconfirmed. The noVNC View Only
setting was briefly enabled during cleanup, which blocked operator input; it
was then returned to false and verified so the operator can use the shell.
Leave the console alone while the operator enters the read-only query. The
At the 16:46 checkpoint the alert list was still unknown; the 17:00:36 readback
below supersedes that status. The configured TrueNAS certificate remains
unverified. See `truenas_console_input_attempt_1646` in
[`inventory/storage.yaml`](../inventory/storage.yaml).

At 17:00:36 EDT, the operator entered `midclt call alert.list` in the VM 200
noVNC Linux Shell. The console showed the command followed by `[]` and a new
root prompt, confirming an empty alert list at that read. A trailing `fff` was
visible as unsubmitted prompt text in the same screenshot and was left
untouched. This confirms that operator keyboard input works with View Only
disabled. The configured TrueNAS certificate remains unverified, and this
point-in-time alert result does not close the other guest health or
failure-procedure gates.
See `truenas_alerts_readback_170036` in
[`inventory/storage.yaml`](../inventory/storage.yaml).

A fresh read-only PVE capture at 17:13:57 EDT used the versioned collector
through the desktop keyring password, with strict host-key checking and no
file written on PVE. `rpool` and `fast-vm` were ONLINE mirrors with zero device
errors and no known data errors; each of the four NVMe pool members and the
Kingston boot SSD reported SMART PASSED. The NVMe critical-warning, media/data
integrity, and error-log counts were zero, and no device self-tests were logged.
The active `smartd` configuration has no scheduled self-test directive, while
the PVE monthly second-Sunday scrub remains configured; neither pool's status
showed a scan entry. A separate 17:17:32 EDT quota read confirmed `quota` and
`refquota` are `none` on the host pools' datasets. `pvesm status` reported
`fast-vm` at 0.63%, `local` at 0.94%, and `local-zfs` at 0.00% used, and the
`check-fast-vm.sh` baseline passed. The host boot ID remained
`b478c236-f6fe-4490-852e-868339e84ffd`. Exact serial-level readings and limits
are in `pve_storage_health_readback_171357` in
[`inventory/storage.yaml`](../inventory/storage.yaml); raw collector output
remains in private workstation task scratch. This did not verify any capacity
alert threshold or exercise a device-failure procedure, so task 6.4 remains
open.

At 18:11:48 EDT, a new strict-host-key read-only capture using
`host/pve/capture-storage-health.sh` found both `rpool` and `fast-vm` ONLINE
mirrors with zero device errors and no known data errors. SMART health passed
for all four pool NVMe members and the Kingston boot SSD; NVMe critical warnings,
media/data integrity errors, and error-log counts were zero. `smartd` was active
with no scheduled self-test directive, and no self-tests were logged for these
devices. The monthly second-Sunday scrub remained configured, with no scan entry
in either pool's status. A separate strict-host-key follow-up confirmed no
`quota` or `refquota` on the listed `rpool` and `fast-vm` datasets. PVE storage
usage was 0.64% for `fast-vm`, 0.94% for `local`, and 0.00% for `local-zfs`;
`check-fast-vm.sh` passed and the boot ID remained unchanged. Exact serial-level
readings are in `pve_storage_health_readback_181148` in
[`inventory/storage.yaml`](../inventory/storage.yaml); raw output remains in
private task scratch. No host-pool capacity alert threshold was verified, and
no device-failure procedure was exercised, so task 6.4 remains open.

An 18:08:32 EDT screenshot of the VM 200 Linux Shell showed `fffc` as
unsubmitted prompt input, with the earlier `midclt call alert.list` result `[]`
still visible and no certificate-query output. This confirms that text reached
the shell but does not refresh alert status or verify the configured
certificate. See `truenas_console_input_recheck_180832` in
[`inventory/storage.yaml`](../inventory/storage.yaml). Leave the shell
untouched until the operator replaces the pending text and reports the query
output.

At 19:02 EDT, after the operator reported typing the prepared query, a fresh
noVNC screenshot still showed a blank root prompt and only the older
`midclt call alert.list` output `[]`; no query echo or result was visible. This
cannot establish whether the keystrokes reached noVNC. No further console
input was sent. The configured certificate identity remains unverified, and
the 17:00:36 EDT alert-list result is still the latest confirmed guest alert
read. See `truenas_console_recheck_1902` in
[`inventory/storage.yaml`](../inventory/storage.yaml). Before retrying, focus
the guest console itself and confirm the query text is visibly echoed at the
root prompt before submitting it.

A second screenshot at 19:08:15 EDT still showed the blank root prompt and no
new command output. The last confirmed guest alert result remains the empty
17:00:36 EDT read, and the configured certificate identity remains
unverified. See `truenas_console_recheck_190815` in
[`inventory/storage.yaml`](../inventory/storage.yaml).

A strict-host-key PVE configuration read at 18:27:22 EDT found the default
notification matcher in `all` mode targeting `mail-to-root` and
`cloudflare-email`; `zfs-zed` was active and a ZED email setting was configured.
The inspected host had no `/etc/pve/status.cfg`, no capacity-related systemd
timer or root crontab entry, and no threshold-related file match under
`/etc/pve`, `/etc/zfs/zed.d`, `/etc/cron.d`, `/etc/systemd/system`,
`/usr/local/sbin`, or `/usr/local/bin`. This bounded read establishes a
notification route, not a storage-capacity threshold. Proxmox documents
notification targets, matchers, and event sources as separate configuration
areas ([Administration Guide, §§17.2–17.4](https://pve.proxmox.com/pve-docs/pve-admin-guide.pdf)); that structure likewise does not make the current mail route evidence of a capacity trigger. No alert configuration was changed. The numeric capacity threshold and measurement cadence remain open; keep the 20%-free Fedora promotion criterion distinct unless the operator selects it separately as an alert policy. See `pve_capacity_notification_policy_readback_182722` in
[`inventory/storage.yaml`](../inventory/storage.yaml).

A fresh strict-host-key PVE capture at 19:09:39 EDT again found `rpool` and
`fast-vm` ONLINE mirrors, zero read/write/checksum errors, and no known data
errors. All four pool NVMe members and the Kingston boot SSD reported SMART
PASSED. NVMe critical warnings, media/data integrity errors, and error-log
counts were zero; no device self-tests were logged. `smartd` was active without
a scheduled self-test directive, the monthly second-Sunday scrub remained
configured, and neither pool showed a scan entry. Host dataset quota and
refquota values remained `none`; PVE storage use was 0.64% for `fast-vm`,
0.94% for `local`, and 0.00% for `local-zfs`. The separate `check-fast-vm.sh`
baseline passed, and a strict-host-key read confirmed the boot ID and kernel
were unchanged. The Kingston SMART output also showed `SSD_Life_Left` normalized
to 94 with raw value 6; no interpretation is assigned here. Exact readings
are recorded as `pve_storage_health_readback_190939` in
[`inventory/storage.yaml`](../inventory/storage.yaml); raw output remains in
private task scratch. This point-in-time collector did not evaluate capacity
thresholds or exercise a device-failure procedure, so task 6.4 remains open.

A strict-host-key read at 19:20:57 EDT found `smartmontools.service` active
with package version `7.5-pve2`; its status reported the next scan of 15
devices at 19:49:38. The captured startup journal shows `DEVICESCAN` (implied
`-a`) monitoring nine ATA/SATA and six NVMe devices. It added all eight
Crucial SSD serials assigned to the TrueNAS `array` to the PVE monitor list at
15:19:38 on October 2, then logged those ATA devices as absent at 15:49:38.
`DEVICESCAN` scans found devices, and `-d removable` makes missing devices
tolerable and suppresses repeated removal warnings; it does not exclude NAS
disks from the scan ([smartd.conf manual](https://github.com/mirror/smartmontools/blob/master/smartd.conf.5.in)).
A separate current read found VM 200 running, the passed-through HBA bound to
`vfio-pci`, and only `fast-vm` and `rpool` imported on PVE. The journal does
not establish why the disks disappeared or tie that event to an exact VM
start. This confirms host-side monitoring while the disks were visible and
later absence from PVE's view; it does not establish that TrueNAS monitors the
disks or schedules tests. See `pve_smartd_scope_readback_192057` in
[`inventory/storage.yaml`](../inventory/storage.yaml).

At 19:22:40 EDT, a fresh VM 200 noVNC screenshot taken after the operator
reported typing the prepared query still showed only the earlier
`midclt call alert.list` result `[]` and an empty root prompt. No new command
echo or output was visible. The latest confirmed alert read therefore remains
the 17:00:36 EDT result, and the configured TrueNAS certificate identity
remains unverified. No guest input was sent by the observer; see
`truenas_console_recheck_192240` in
[`inventory/storage.yaml`](../inventory/storage.yaml).

At 19:40:29 EDT, a fresh screenshot after the operator again reported typing
the query showed option 8 selected, an empty TrueNAS root prompt, and only the
earlier `midclt call alert.list` output `[]`. No certificate-query echo or
result was visible. The latest confirmed alert read remains 17:00:36 EDT, and
the configured certificate identity remains unverified. The screenshot was
retained privately; no guest input was sent. See
`truenas_console_recheck_1940` in [`inventory/storage.yaml`](../inventory/storage.yaml).

At 19:53:04 EDT, a fresh strict-host-key read-only run of
`host/pve/capture-storage-health.sh` found `rpool` and `fast-vm` ONLINE mirrors
with zero device errors and no known data errors. The four pool NVMe members
and the Kingston boot SSD reported SMART PASSED; critical warnings, media/data
integrity errors, and error-log entries were zero for the NVMe devices, and no
self-tests were logged for the five queried host devices. The second-Sunday
monthly scrub remains configured with no active scan listed; the active
`smartd` configuration has no self-test schedule directive. `pvesm status`
reported 0.64%, 0.94%, and 0.00% use for `fast-vm`, `local`, and `local-zfs`.
Separate strict-host-key readbacks at 19:54–19:58 confirmed VM 200 running,
the HBA bound to `vfio-pci`, host imports limited to `fast-vm` and `rpool`, no
quota/refquota on either host pool, and `check-fast-vm.sh` PASS. The current
`smartd` status reported its next check at 20:19:38; its journal had no entries
since 19:45, which does not establish the scan result or NAS-device presence.
Exact values and provenance are recorded as
`pve_storage_health_readback_1953` in [`inventory/storage.yaml`](../inventory/storage.yaml).
This does not refresh TrueNAS guest evidence or establish a capacity threshold
or accepted failure procedure; task 6.4 remains open.

At 20:07:24 EDT, after the operator reported typing the prepared command, a
fresh screenshot showed the same console pixels and SHA-256 as the 19:40:29
screenshot: option 8, a blank root prompt, and only the earlier
`midclt call alert.list` output `[]`. No new command echo or result was
verified. The latest confirmed alert query therefore remains the 17:00:36 EDT
read, and the configured certificate identity remains unverified. The
screenshot is retained in private workstation scratch as
`truenas_console_recheck_200724`; no guest input was sent by the observer. See
[`inventory/storage.yaml`](../inventory/storage.yaml).

At 20:23:16 EDT, the noVNC Settings panel showed `View only` unchecked. This
rules out that toggle as the input blocker but does not prove the guest canvas
has keyboard focus. After the panel was closed, the screenshot showed a black
console canvas with no readable prompt; no guest keys were sent. The latest
confirmed alert-list result remains 17:00:36 EDT, and the configured
certificate identity remains unverified. See
`truenas_console_settings_recheck_202316` in
[`inventory/storage.yaml`](../inventory/storage.yaml).

At 20:37:07 EDT, after the operator reported typing the prepared read-only
command, a fresh personal-Chrome screenshot showed the TrueNAS root prompt,
`midclt call alert.list`, and its `[]` result. This confirms that the operator's
input reached the guest shell and that the alert query returned no entries in
that run; the console does not include a guest execution timestamp. The exact
cause of the earlier focus failures remains unresolved. The screenshot also
contains a separate PVE task-error banner dated 16:37:33 and 16:38:33 EDT for a
VM 200 powerdown timeout; this read did not investigate that prior PVE task.
Configured TrueNAS certificate identity remains unverified because no
certificate query was entered or visible. See
`truenas_alerts_readback_203707` in
[`inventory/storage.yaml`](../inventory/storage.yaml).

At 20:45–20:46 EDT, one focused chrome-use attempt to enter the prepared
certificate-reference query displayed altered punctuation in the TrueNAS
shell: `|` became `\`, `_` became `-`, and `{}` became `[]`. Enter was not sent,
so the malformed command did not run. Two attempts to send Ctrl+C landed on
the outer Proxmox iframe; a fresh 20:46:10 screenshot still showed the
unsubmitted line. This identifies a keyboard-translation problem in the
chrome-use typing path and does not establish why earlier operator typing
initially lacked focus. The configured certificate identity remains
unverified. The operator should press Ctrl+C directly in the guest console to
clear the pending line before entering another command. See
`truenas_cert_query_input_recheck_204610` in
[`inventory/storage.yaml`](../inventory/storage.yaml).

At 20:55:10 EDT, a fresh strict-host-key read-only run of
`host/pve/capture-storage-health.sh` found `rpool` and `fast-vm` ONLINE mirrors
with zero device errors and no known data errors. The four pool NVMe members
and Kingston boot SSD reported SMART PASSED; the NVMe critical warnings,
media/data integrity errors, and error-log counts were zero, and no SMART
self-tests were logged for the five host-owned devices. No SMART self-test
schedule directive is active. The second-Sunday monthly scrub schedule remains
configured at 00:24, while neither `zpool status` output showed a scan entry.
The host pool datasets have no finite quota/refquota, and `pvesm status`
reported 0.65%, 0.94%, and 0.00% use for `fast-vm`, `local`, and `local-zfs`.
The raw collector output is retained in private workstation scratch; exact
serial-level readings and provenance are in
`pve_storage_health_readback_205510` in
[`inventory/storage.yaml`](../inventory/storage.yaml). This capture does not
evaluate a capacity threshold, query TrueNAS guest health, or exercise a
failure procedure, so task 6.4 remains open.

At 21:10:52 EDT, another fresh strict-host-key read-only run of
`host/pve/capture-storage-health.sh` again found `rpool` and `fast-vm` ONLINE
mirrors with zero read, write, and checksum errors and no known data errors.
All four host-pool NVMe members and the Kingston boot SSD reported SMART
PASSED; NVMe critical warnings, media/data integrity errors, and error-log
counts were zero, with no self-tests logged for any of the five queried host
devices. No SMART self-test schedule directive is active. The monthly
second-Sunday scrub remains configured for 00:24, with no scan entry in either
pool status. Host datasets still have no finite quota/refquota, and PVE storage
use was 0.65%, 0.94%, and 0.00% for `fast-vm`, `local`, and `local-zfs`. Raw
output and serial-level details are in
`pve_storage_health_readback_211052` in
[`inventory/storage.yaml`](../inventory/storage.yaml). This read does not
evaluate alert thresholds, query TrueNAS guest state, or test device-failure
procedures; task 6.4 remains open.

A fresh noVNC screenshot at 20:58:44 EDT confirmed the malformed certificate
query is still on the guest shell's current line without output or a new prompt.
The line now ends in two additional `c` characters after the failed Ctrl+C
attempts; their exact input event cannot be proven. No Enter was sent. The
operator must clear the line directly in the console before another command.
See `truenas_cert_console_recheck_205844` in
[`inventory/storage.yaml`](../inventory/storage.yaml).

At 21:04:10 EDT, after the operator reported typing the requested input, a
fresh screenshot showed the same pending malformed line. Its bytes and
SHA-256 exactly match the 20:58:44 capture, so no visible console change or
command execution was verified. No keys were sent by the observer. The latest
confirmed alert result remains the earlier `[]`; configured certificate
identity remains unverified. See `truenas_console_recheck_210410` in
[`inventory/storage.yaml`](../inventory/storage.yaml). Clear the prompt line
directly in the guest console and verify it is empty before entering another
query.

At 21:26:08 EDT, a fresh screenshot showed an empty TrueNAS root prompt after
the operator cleared the previous line. A subsequent `chrome-use keyboard
inserttext` attempt to enter the prepared certificate-reference query visibly
altered its punctuation. Enter was not sent, and no query result appeared. The
later Ctrl+C attempts were reported by chrome-use as landing on the parent PVE
iframe, so they did not reach the guest; a 21:30:48 screenshot still showed
unsubmitted shell input without output or a fresh prompt. Certificate identity
remains unverified, and the latest confirmed alert result remains the earlier
`[]`. The operator must clear the current line directly before any further
console query. Screenshot hashes and provenance are in
`truenas_cert_console_recheck_213048` in
[`inventory/storage.yaml`](../inventory/storage.yaml).

A fresh screenshot at 21:44:37 EDT still showed unsubmitted certificate-query
text at the TrueNAS root prompt without output or a new prompt. The exact input
sequence remains uncertain, the configured certificate identity is still
unverified, and the latest confirmed alert result is unchanged. See
`truenas_cert_console_recheck_214437` in
[`inventory/storage.yaml`](../inventory/storage.yaml). No further automated
console input was sent.

Linux device names in the inventory are observations, not persistent identity.
Pool definitions and destructive commands must use `/dev/disk/by-id`.

## Read-only TrueNAS certificate identity query

The WebUI confirms that `truenas_default` is selected and shows its public
subject, SAN, and validity period. The public certificate downloaded from that
selected record has the exact SHA-256 fingerprint of the served HTTPS leaf,
verifying the selected GUI object-to-leaf association. The WebUI's displayed
validity times are local-formatted while OpenSSL reports UTC; the guest UI
timezone was not independently checked. Strict verification fails because the
leaf is self-signed and its SAN contains only `DNS:localhost`; trusted endpoint
identity remains unresolved. A 04:09–04:17 EDT authenticated WebUI Shell read
used `certificate.query` with the public-field selection below. It returned
certificate ID 1 (`truenas_default`), `CN=localhost`, `SAN=DNS:localhost`,
validity from October 2, 2026 to November 3, 2027, and `parsed: true`. This
confirms the certificate parses; it does not establish a trusted identity for
`192.168.0.186`.

For future reads, retrieve only the configured reference and public metadata:

```sh
midclt call system.general.config | jq '{ui_certificate: {id: .ui_certificate.id, name: .ui_certificate.name}}'
midclt call certificate.query '[]' '{"select":["id","name","common","san","fingerprint","from","until","parsed"]}'
```

Never print the raw result of `midclt call system.general.config`: it contains
private-key and certificate-PEM fields. The filtered first command emits only
the selected UI certificate ID and name. The `certificate.query` selection
omits both `privatekey` and certificate PEM data. These commands follow the
[TrueNAS 25.10 API reference for
system.general.config](https://api.truenas.com/v25.10/api_methods_system.general.config.html)
and [certificate.query](https://api.truenas.com/v25.10/api_methods_certificate.query.html);
the public-field `certificate.query` was run against VM 200. Read-back of the
API fingerprint and parsed status establishes public certificate metadata; it
cannot make a self-signed certificate trusted for the IP address. Do not
use the Certificates page's `Download` action for read-only inspection: it
exports the private key with the public certificate. The task-created key
download was removed without opening it; details are in
`truenas_certificate_object_match_0221` in `inventory/storage.yaml`.

## Read-only TrueNAS pool, scrub, and disk queries

These TrueNAS 25.10 queries refresh guest pool status/capacity, configured scrub
schedules, and disk-to-serial/pool mapping. The selected disk fields omit the
API's `passwd` field, and `extra.pools=true` explicitly requests the pool-name
join. They do not run a SMART test or establish capacity alert thresholds:

```sh
midclt call pool.query '[]' '{"select":["name","status","scan","healthy","warning","status_code","status_detail","size","allocated","free"]}'
midclt call pool.scrub.query '[]' '{"select":["id","pool_name","threshold","description","schedule","enabled"]}'
midclt call disk.query '[]' '{"extra":{"pools":true},"select":["name","serial","model","size","devname","enclosure","pool","zfs_guid"]}'
```

The selections are based on the TrueNAS 25.10 API references for
[pool.query](https://api.truenas.com/v25.10/api_methods_pool.query.html),
[pool.scrub.query](https://api.truenas.com/v25.10/api_methods_pool.scrub.query.html),
and [disk.query](https://api.truenas.com/v25.10/api_methods_disk.query.html).
These commands have not been run against VM 200. The result is point-in-time
read-only evidence and does not exercise device failure handling.

A fresh authenticated WebUI check at 03:43–03:44 EDT on 2026-10-04 again
showed `tank` ONLINE, 0 of 8 disks with errors, 5.03 TiB free, and no active
alerts. `truenas_default` is selected for HTTPS on port 443 with TLS 1.2/1.3.
Its `CN=localhost` / `SAN=DNS:localhost` public certificate fingerprint
matches the currently served leaf, but strict OpenSSL verification fails
because it is self-signed and the IP `192.168.0.186` does not match the SAN.
This confirms the configured object-to-leaf association while leaving endpoint
trust unresolved. See `truenas_webui_cert_alert_readback_0344` in
[`inventory/storage.yaml`](../inventory/storage.yaml). Guest SMART history,
capacity threshold/cadence, alert delivery, and representative failure
handling remain unverified; Group 6 task 6.4 remains open.

The 03:55–03:58 EDT TrueNAS System > Alert Settings readback shows pool-space alerts
above 85% at NOTICE, 90% at WARNING, and 95% at CRITICAL; each storage alert
category is configured for IMMEDIATELY frequency. E-Mail and SNMP Trap alert
services are enabled at Warning level, but neither delivery path was tested.
These are TrueNAS guest settings and do not choose the separate PVE host-pool
threshold/cadence. See `truenas_alert_policy_readback_0355` in
[`inventory/storage.yaml`](../inventory/storage.yaml). Task 6.4 remains open.

A fresh read-only TrueNAS System > Services page at 04:09–04:17 EDT on
2026-10-04 showed SSH, SNMP, FTP, iSCSI, NVMe-oF, and UPS stopped; NFS and SMB
were running. A workstation TCP probe to `192.168.0.186:22` returned
`Connection refused`, explaining why SSH is unavailable without changing the
guest. The authenticated WebUI Shell returned the selected GUI certificate
reference (`id: 1`, `truenas_default`) and a public-field `certificate.query`
showed `parsed: true`, `CN=localhost`, `SAN=DNS:localhost`, and validity from
October 2, 2026 to November 3, 2027. The API method-name list returned no
method containing `smart`, which does not establish that no SMART schedule or
history exists. No service or certificate setting was changed. Endpoint trust,
SMART history, alert delivery, PVE capacity thresholds, and failure handling
remain open; see `truenas_webui_access_readback_0409_0417` in
[`inventory/storage.yaml`](../inventory/storage.yaml). Task 6.4 remains open.

A fresh strict-host-key capture at 04:26 EDT on 2026-10-04 found `rpool` and
`fast-vm` ONLINE mirrors with zero device errors and no known data errors. All
four host-pool NVMe members and the Kingston boot SSD reported SMART PASSED;
NVMe critical warnings, media/data-integrity errors, and error-log counts were
zero, with no self-tests logged on any of the five devices. `smartd` was active
without a scheduled self-test directive, and the monthly second-Sunday scrub
was configured with no active scan entry in either pool. PVE storage use was
0.68%, 0.94%, and 0.00%; host-pool datasets had no finite quotas. The collector
does not evaluate alert thresholds or exercise device failure, so both remain
open. See `pve_storage_health_readback_042614` in
[`inventory/storage.yaml`](../inventory/storage.yaml); task 6.4 remains open.

A bounded strict-host-key PVE configuration read at 04:31 EDT found
`pvestatd`, `smartd`, and `zfs-zed` active, but `/etc/pve/status.cfg` absent,
with no capacity/threshold-matching systemd timer, root-cron entry, or file in
the inspected PVE, ZFS ZED, cron, systemd, and local-script paths. No PVE
host-pool capacity threshold or measurement/alert job was found. This does not
rule out external monitoring or differently named code outside those paths;
no threshold or notification setting changed. See
`pve_capacity_monitor_readback_043133` in
[`inventory/storage.yaml`](../inventory/storage.yaml). The numeric threshold
and cadence remain unselected, so task 6.4 remains open.

A fresh authenticated WebUI read at 04:37 EDT reconfirmed no active alerts and
that `truenas_default` is selected for HTTPS 443 with TLS 1.2/1.3. Its displayed
public subject, SAN, and validity match the 03:44 EDT readback; the current
served leaf SHA-256 also matches that prior readback, which directly verified
the selected-object fingerprint. An attempted Shell refresh timed out before
any command was entered. Strict TLS verification returns error 18 because the
certificate is self-signed, and its `DNS:localhost` SAN does not identify
`192.168.0.186`. No setting was changed. See `truenas_webui_readback_0437` in
[`inventory/storage.yaml`](../inventory/storage.yaml). Trusted endpoint
identity, alert delivery, SMART history, PVE threshold/cadence, and failure
acceptance remain open; task 6.4 remains unchecked.

At 04:54–04:55 EDT, System > Advanced Settings > Cron Jobs showed two enabled
TrueNAS SMART self-test jobs: a weekly short test at 01:00 Wednesday and a
monthly long test at 03:00 on the 15th, both run as root against the
`/dev/disk/by-id/ata-CT1000MX500SSD1_*` glob. The UI displayed next runs in 3
and 11 days, respectively. This fills the earlier schedule-visibility gap;
the glob was not enumerated against all eight serials, and the cron list does
not show execution history or test results. SMART health/history therefore
remain unverified, and task 6.4 stays open alongside PVE threshold/cadence,
alert-delivery, trusted-endpoint, and failure-procedure acceptance. No cron
entry was opened or changed and no test was started. See
`truenas_smart_cron_readback_0454` in
[`inventory/storage.yaml`](../inventory/storage.yaml). TrueNAS documents this
widget as the listing for configured recurring commands in [Managing Cron
Jobs](https://www.truenas.com/docs/scale/25.10/scaletutorials/systemsettings/advanced/managecronjobsscale/).

At 05:05 EDT, a fresh reload of System > Shell in the same authenticated
session still showed CSS-like text in the terminal and no shell prompt. No
input, command, or password was submitted. This does not establish the shell
backend state, but the page is not currently a usable path for the remaining
guest SMART read. See `truenas_webui_shell_render_readback_0505` in
[`inventory/storage.yaml`](../inventory/storage.yaml).

At 05:16 EDT, the pinned personal-Chrome tab displayed the TrueNAS sign-in
page rather than an authenticated session. The endpoint's self-signed
localhost-only certificate remains untrusted, so no credential was submitted.
This produced no new SMART or alert evidence. See
`truenas_webui_signin_recheck_0516` in
[`inventory/storage.yaml`](../inventory/storage.yaml).

At 05:40 EDT, a same-origin unauthenticated `GET /api/v2.0/alert/list` from
that tab returned `401 Unauthorized`; no credential was sent and alert status
was not refreshed. A separate strict-host-key, public-key-only SSH check to
PVE returned `Permission denied`, so the storage collector did not run. See
`truenas_webui_alert_api_unauth_readback_0540` and
`pve_storage_collector_ssh_auth_attempt_0540` in
[`inventory/storage.yaml`](../inventory/storage.yaml).

The local read-only PVE collector now separates smartctl acquisition-error
bits (`0x07`) from SMART status/history findings (`0xf8`) and returns distinct
statuses for either class or both. Its test asserts the exact five persistent
whole-device by-id paths. These changes are local preparation only; they do
not provide a fresh live host capture. The [smartctl return-code definitions](https://www.smartmontools.org/static/doxygen/smartctl_8h_source.html)
describe the underlying bitmask.

A fresh strict-host-key, password-only read-only collector at 05:50 EDT found
`rpool` and `fast-vm` ONLINE mirrors with zero device errors and no known data
errors. All four pool NVMe members and the Kingston boot SSD reported SMART
PASSED; the four NVMe devices had zero critical warnings, media/data-integrity
errors, and error-log entries. No SMART self-tests were logged, `smartd` was
active without a self-test schedule directive, and the monthly second-Sunday
scrub schedule remained configured with no active scan entry. Host-pool
datasets had no finite quotas; PVE storage use was 0.69%, 0.94%, and 0.00% for
`fast-vm`, `local`, and `local-zfs`. This does not choose a capacity threshold
or exercise device failure. See `pve_storage_health_readback_055003` in
[`inventory/storage.yaml`](../inventory/storage.yaml); task 6.4 remains open.

## 06:00–06:04 EDT TrueNAS WebUI refresh

The separate task-owned `homelab-truenas-readonly` Chrome session reopened on
the exact personal profile and loaded the authenticated TrueNAS Dashboard as
`truenas_admin`. Its Alerts drawer displayed “There are no alerts.” Credentials
> Certificates showed `truenas_default` with `CN=localhost` and only
`SAN=DNS:localhost`; System > General Settings > GUI Settings confirmed it is
selected for HTTPS 443. A read-only TLS handshake observed the served leaf
fingerprint previously matched to that public certificate object. The leaf is
still self-signed and does not identify `192.168.0.186`, so trusted endpoint
identity remains unresolved. The current IP-to-VM 200 mapping was not
refreshed. No credentials, settings, browser policy, or infrastructure state
were changed. See `truenas_webui_readback_0604` in
[`inventory/storage.yaml`](../inventory/storage.yaml). Task 6.4 remains open.

At 06:11–06:13 EDT, the authenticated System > Alert Settings Storage category
showed pool-space alert levels of 85% NOTICE, 90% WARNING, and 95% CRITICAL,
all with IMMEDIATELY frequency. E-Mail and SNMP Trap services are enabled at
Warning level, but delivery was not tested. These are TrueNAS guest settings;
they do not select a PVE host-pool capacity threshold or cadence. No setting
was saved. See `truenas_storage_alert_policy_readback_0613` in
[`inventory/storage.yaml`](../inventory/storage.yaml). Task 6.4 remains open.

## 06:26–06:35 EDT TrueNAS storage and VM identity readback

At 06:26 EDT, the read-only Proxmox VM 200 configuration showed `net0` as
`virtio=BC:24:11:87:F2:2B,bridge=vmbr0,firewall=0`. The authenticated TrueNAS
Shell reported `enp6s18` at `192.168.0.186/24` with the matching MAC, and the
workstation's neighbor table had the same IP/MAC in REACHABLE state. This
refreshes the current IP-to-VM mapping; see
`truenas_vm200_mac_mapping_readback_0626` in
[`inventory/storage.yaml`](../inventory/storage.yaml).

The TrueNAS shell read `boot-pool` and `tank` as ONLINE. `tank` was 7.25 TiB,
with 37.7 MiB allocated and 7.25 TiB free. The two setup-share datasets each
had a 5 GiB `refquota`; their quota fields were `none`. The authenticated
WebUI showed `tank` at 0 of 8 disk errors, 5.03 TiB available, the Sunday
00:00 scrub schedule, and a completed 2026-10-02 scrub with zero errors. It
reported no current alerts and disk temperatures of 25–33 °C, averaging
27.956 °C. The disk table listed all eight `tank` member serials, while Disk
Reports exposed only I/O and temperature metrics.

A focused SMART attempt in the same WebUI Shell used the noninteractive
read-only command `sudo -n smartctl -H -l selftest /dev/sdb`. `sudo` returned
`a password is required`; `smartctl` did not run and no password was entered.
The shell user is `truenas_admin`, so SMART health and self-test history remain
unverified. The earlier self-signed `CN=localhost` certificate with
`SAN=DNS:localhost` still does not establish trusted identity for the IP; this
pass did not perform a TLS trust check or change any certificate. See
`truenas_guest_storage_health_readback_0635` in
[`inventory/storage.yaml`](../inventory/storage.yaml). Task 6.4 remains open
for SMART history, a PVE capacity threshold/cadence, alert-delivery testing,
trusted endpoint identity, and representative failure handling.

At 06:49–06:52 EDT, a fresh authenticated Storage Dashboard read again showed
`tank` online with no errors, 5.03 TiB available, the Sunday scrub schedule,
and the 2026-10-02 scrub completed with zero errors. The Alerts drawer said
“There are no alerts.” A strict TLS read returned the same leaf fingerprint
seen at 06:04: `CN=localhost`, `SAN=DNS:localhost`; default `curl` verification
for `192.168.0.186` failed because the certificate has no matching IP SAN.
Trusted endpoint identity remains unresolved. See
`truenas_webui_tls_alert_readback_0652` in
[`inventory/storage.yaml`](../inventory/storage.yaml). Task 6.4 remains open.

At 06:54 EDT, a current PVE VM 200 configuration API read returned net0 MAC
`BC:24:11:87:F2:2B`; the workstation neighbor entry for `192.168.0.186` was
REACHABLE at the same MAC. This corroborates the earlier guest interface
readback and ties the current endpoint to VM 200. A 06:57–07:00 attempt to
refresh the guest interface through System > Shell did not produce visible
output: the terminal still rendered CSS-like text, and a screenshot request
timed out. Command execution is unconfirmed. See
`truenas_vm200_mac_mapping_readback_0654` and
`truenas_webui_shell_attempt_0700` in
[`inventory/storage.yaml`](../inventory/storage.yaml). No guest SMART result
or trusted certificate identity is claimed.

A strict public-key-only SSH check at 07:01–07:03 EDT found no pinned host key
for `192.168.0.186` and received `Connection refused` on TCP port 22. No
password was used and no host key was accepted or added. Together with the
unconfirmed WebUI Shell attempt, this leaves guest SMART health/history without
a verified read path; do not infer that the SSH service is permanently
disabled. See `truenas_ssh_access_attempt_0702` in
[`inventory/storage.yaml`](../inventory/storage.yaml). Task 6.4 remains open.

At 07:22–07:26 EDT, the authenticated WebUI Shell showed that the earlier read-only
interface command had executed: `enp6s18` is `192.168.0.186/24` with MAC
`bc:24:11:87:f2:2b`. A read-only `sudo -n smartctl --scan-open` attempt returned
`sudo: a password is required`; `smartctl` did not run and no password was
supplied. The Storage Dashboard still showed `tank` online with no errors, 0 of
8 disk errors, 5.03 TiB available, and a zero-error 2026-10-02 scrub. The Alerts
drawer said “There are no alerts”; E-Mail and SNMP Trap services were enabled at
Warning level, but delivery was not tested.

The unprivileged TrueNAS middleware query `midclt call disk.query` enumerated
the eight 1 TB Crucial MX500 members and the 32 GiB QEMU boot device, but did
not return SMART health or test history. A read-only method-name query showed
no `smart`-named middleware methods for this shell session. The guest SMART
gate therefore remains open.

System > General Settings > GUI Settings selected `truenas_default` for HTTPS
443. The Certificates page showed `CN=localhost` and only `SAN=DNS:localhost`.
A fresh strict TLS probe returned the same
SHA-256 leaf fingerprint recorded at 06:52, and strict `curl` verification for
`192.168.0.186` failed because no certificate SAN matches the target IP. The
endpoint IP identity therefore remains unverified. No configuration changed.
See `truenas_webui_readonly_recheck_0722` in
[`inventory/storage.yaml`](../inventory/storage.yaml). Task 6.4 remains open
for SMART history, PVE capacity threshold/cadence, alert delivery, trusted
endpoint identity, and representative failure handling.

## 2026-10-05 Group 6 read-only refresh

At 14:39 EDT, a fresh strict-host-key read-only PVE capture found `rpool` and
`fast-vm` ONLINE mirrors and `scratch` an ONLINE two-member stripe, with zero
READ/WRITE/CKSUM counters and no known data errors. All six host-pool NVMe
devices and the Kingston boot SSD reported SMART PASSED; no self-tests were
logged, and `smartd` was active without a scheduled self-test directive. The
monthly second-Sunday scrub schedule remains configured, but no captured pool
status contained a `scan:` line. Dataset quotas/refquotas remain unset. PVE
storage use was 0.81% for `fast-vm`, 0.94% for `local`, and 0.00% for
`local-zfs` and `scratch`. The capture and manager check returned status 0/PASS;
see `pve_storage_health_readback_143910` in
[`inventory/storage.yaml`](../inventory/storage.yaml).

At 14:41 EDT, strict-host-key read-back confirmed the capacity-monitor timer
enabled and active, eight successful service completions at five-minute
intervals from 14:05 through 14:40, and the next firing due at 14:45. The
configured 80% warning / 90% critical policy is evaluated every five minutes
and writes transitions to the local journal. No transition occurred because
all host pools remained below threshold. `pvesm list scratch` returned no
volumes. This verifies scheduled execution below threshold, not a live
threshold crossing or external notification delivery; delivery remains a
separate Task 9.3 gate. See
`pve_storage_capacity_monitor_readback_144130` in
[`inventory/storage.yaml`](../inventory/storage.yaml).

At 14:45 EDT, a read-only snapshot in the selected personal Chrome profile
showed the TrueNAS sign-in form. No credential was submitted. A strict TLS
handshake to `192.168.0.186:443` failed verification with error 18 because the
served leaf is self-signed. The rejected leaf is `CN=localhost`, has only
`SAN=DNS:localhost`, and matches the fingerprint last associated with the
public `truenas_default` certificate readback. The current PVE VM 200 MAC and
the workstation's REACHABLE neighbor entry both match `BC:24:11:87:F2:2B`,
which ties the endpoint to VM 200 but does not make its TLS identity trusted.
The current certificate selection and alert list were not refreshed while
signed out; the last authenticated empty-alert read is historical. See
`truenas_webui_signin_recheck_144555` and
`truenas_tls_strict_recheck_144245` in
[`inventory/storage.yaml`](../inventory/storage.yaml).

At 15:00–15:07 EDT, the operator authorized one-time read-only WebUI use despite
the failed TLS verification. The current page showed no alerts and `tank`
ONLINE with a completed zero-error October 2 scrub, Sunday scrub schedule,
capacity, temperatures, and the two 5 GiB setup-share quotas. The seven-day
daily snapshot task is local-only. The System > Cron Jobs page showed enabled
weekly short and monthly long SMART commands targeting the eight SATA disk
by-id pattern, but no SMART health or test execution history was verified and
no test was started. The selected GUI certificate was `truenas_default` for
HTTPS 443; its `CN=localhost` and `SAN=DNS:localhost` do not identify the IP.
A fresh strict probe at 15:07 still failed with error 18. The authorized read
does not clear certificate uncertainty or prove endpoint identity. See
`truenas_storage_health_readback_150007` and
`truenas_tls_strict_recheck_150700` in
[`inventory/storage.yaml`](../inventory/storage.yaml).

The PVE measurements and the local 80%/90% five-minute capacity monitor are
current; scheduled runs and synthetic threshold/failure checks are recorded
above. No live threshold crossing or device fault was performed. Task 6.4
remains open for verified TrueNAS SMART execution/history and accepted
representative failure-procedure evidence. Alert delivery remains Task 9.3.
No host, guest, pool, network, certificate, or monitor configuration changed
during this read-only refresh.

### TrueNAS SMART Cron Job target pattern — 2026-10-05

The guest's weekly short-test and monthly long-test jobs run as root against
the eight Crucial MX500 whole disks. The original
`/dev/disk/by-id/ata-CT1000MX500SSD1_*` pattern also matches partition aliases
ending in `-part1`; TrueNAS's manual Cron Job result returned exit 4, and its
configured output suppression hid the per-command detail. The read-only SMART
capture below confirmed all eight whole disks report `PASSED` and their latest
short self-tests completed without error. It also confirmed eight matching
partition aliases. Keep the existing schedules and filter those aliases from
both commands:

```sh
for d in /dev/disk/by-id/ata-CT1000MX500SSD1_*; do case "$d" in *-part*) continue;; esac; /usr/sbin/smartctl -t short "$d"; done
for d in /dev/disk/by-id/ata-CT1000MX500SSD1_*; do case "$d" in *-part*) continue;; esac; /usr/sbin/smartctl -t long "$d"; done
```

This is the versioned target for Cron Job IDs 1 and 2; apply it through the
TrueNAS API and verify command and schedule read-back. On 2026-10-05, only the
command fields for IDs 1 and 2 were updated; both remained enabled on their
original schedules. A run of corrected short-test job 1 completed successfully
as middleware job 5916. It ran against whole-disk aliases only. A preceding
run of the old command (job 5864) returned exit 4; its output was suppressed.
The read-only capture used a temporary disabled Cron Job that was removed,
along with its temporary output file, after collection. The API read does not
establish trusted HTTPS identity; the self-signed `CN=localhost` certificate
remains unverified.

The authenticated API read returned zero active alerts and `tank` ONLINE and
healthy, with an eight-member RAIDZ2 vdev whose member READ/WRITE/CKSUM counters
were all zero. The last scrub finished October 2 at 11:47 TrueNAS local time
with zero errors; the schedule is Sunday at 00:00. The root dataset has no
quota; `tank/nfs_test` and `tank/smb_test` each have a local 5 GiB `refquota`
and used 204.75 KiB. Alert policy endpoints did not expose a numeric whole-pool
capacity threshold; the 5 GiB dataset quotas are separate hard limits. E-mail
and SNMP alert services are enabled at Warning level; delivery is not tested
and remains Task 9.3.

The 16:11 EDT read-only per-drive capture mapped all eight SATA members to
serials and reported SMART overall health `PASSED`, zero
reported-uncorrectable and offline-uncorrectable counts, and latest short
self-tests `Completed without error`. `smartctl -x` returned status 4 even
while reporting those results; the [smartctl return-code bitmask](https://www.smartmontools.org/static/doxygen/smartctl_8h_source.html)
defines this as a SMART-command failure or missing ATA identify information,
so the health line and self-test log are recorded separately from that
diagnostic status. The prior short-job exit 4 is likewise recorded as a job
result, not as a disk-health verdict. The API read confirmed the NAS SSH
service is disabled; no network service was enabled for this work.

Task 6.4 is complete as a storage measurement and procedure-documentation task:
PVE and TrueNAS health, scrub state, SMART status/test history, quotas, and
capacity-monitor policy are recorded; mirror, RAIDZ2, and stripe response
procedures are versioned, and the synthetic scratch failure check passed. No
live pool fault, capacity-threshold crossing, or alert-delivery test was run.
TrueNAS has no verified numeric whole-pool threshold, and certificate identity
remains unverified; neither is represented as a passing result.
