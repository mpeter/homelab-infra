# Backup and recovery

## Objective

A disk mirror is not a backup, and a backup stored only inside the R720 does not
protect against loss of the host. The eventual recovery system must be usable
when PVE, its pools, AAP, and OpenShift are all unavailable. Its full
implementation is deferred to the [independent-recovery backlog item](../.backlog/2026-10-03-implement-independent-second-site-backup-and-tested-recovery.md).

## Backup destination

ADR 0013 selects a local ZFS receiver at another site for encrypted NAS data
and infrastructure recovery artifacts. On 2026-10-03 the operator confirmed
no receiver exists. Receiver provisioning, remote copies, independent restores,
and their design decisions belong to the deferred backlog item. TrueNAS VM 200
and its RAIDZ2 pool remain on the R720 and do not satisfy the host-loss
requirement. Local Proxmox staging is an intermediate copy, never the sole
destination for unique data.

## Interim same-host TrueNAS backup plan — 2026-10-03

The operator selected TrueNAS VM 200 as a possible interim destination until
an off-site receiver exists. This section is the current Group 5 deliverable:
an implementation plan for an on-demand copy of reproducible Fedora VM 100
and the already encrypted PVE host-configuration bundle. No job, transfer,
restore, or retention schedule has been implemented by this plan. A future
same-R720 copy could help with an isolated local failure, but cannot protect
against loss of the host, power, or site or authorize unique-data migration.

Do not use the existing `tank/nfs_test` or `tank/smb_test` setup shares. A
read-only export query on 2026-10-03 found only `/mnt/tank/nfs_test`, restricted
to workstation `192.168.0.183`; no backup export is configured. Create a
dedicated dataset and access path only after a fresh TrueNAS configuration
export and a trusted endpoint identity are available. The prior TrueNAS UI
certificate evidence remains untrusted (`CN=localhost`, SAN `DNS:localhost`,
hostname mismatch), and current guest certificate and alert status remain
unverified. Do not send credentials or backup contents to that endpoint yet.

The interim run must remain on-demand. VM 200 is OpenTofu-managed and has
`on_boot=false` so its HBA ownership stays explicit. A backup helper must
require VM 200 to already be running, confirm `tank` is healthy and the HBA is
assigned to the guest, and refuse to start or change the VM. Do not register a
permanently mounted backup storage or schedule a job while the NAS guest is
normally off.

### Owners and implementation sequence

Versioned `host/pve/` automation owns PVE preflight, archive creation,
encryption, transfer, verification, and the local restore-test procedure.
OpenTofu owns VM 200 power and HBA configuration; TrueNAS owns its dataset,
export, and restricted transfer identity. The operator holds decryption keys
in the workstation keyring. A future implementation needs a reviewed
versioned change under [R720 change control](r720-change-control.md) before
any live write, then follows this order:

1. Recheck VM IDs, VM 200 `on_boot=false`, HBA ownership, `tank` health, and
   TrueNAS certificate and alert state. Export and verify a fresh TrueNAS
   configuration archive. Establish a trusted endpoint name and certificate;
   test authentication without disabling TLS verification. Stop if identity
   or health is uncertain.
2. Define a dedicated, quota-limited backup dataset and restricted transfer
   path in versioned TrueNAS configuration. Limit access to the intended PVE
   source, verify allowed and denied access, and exclude setup shares. Budget
   space for a full archive, temporary ciphertext, a known-good copy, and free
   reserve. Do not stage a full VM archive on the workstation.
3. Implement an on-demand PVE helper with a read-only preflight. Require VM
   200 to be running already; prove HBA assignment and `tank` health; verify
   endpoint identity, target path, local and target free space, encryption
   recipient, and key recovery. Refuse to start or stop VM 200, attach
   permanent storage, or schedule a job.
4. Create a compressed VM 100 `vzdump` archive on measured PVE staging or a
   verified encrypted stream, using a separate VM-backup key. Transfer only
   ciphertext to a new temporary target name. Transfer the existing encrypted
   host bundle without decrypting it on PVE or TrueNAS. Do not overwrite the
   known-good recovery point. Report failure on creation, encryption,
   transfer, or verification failure, leaving that point intact.
5. Read the retained ciphertext back from TrueNAS and compare source and
   destination SHA-256. Check GPG integrity with the workstation-held key.
   Record hashes, file size, source/target names, timestamp, and exit status
   in a private run record. Hash agreement proves byte integrity only. Review
   a retention/delete rule before enabling it; never delete the prior point
   merely because transfer returned success.
6. With separate restore-test authorization and fresh versioned preflight,
   restore to a disposable VM ID outside OpenTofu's range with no NIC or a
   link-down NIC. Boot and inspect it, then remove it through the versioned
   procedure and verify no orphan disk or VM configuration. Separately prove
   the host bundle decrypts and extracts in isolated scratch space without
   altering live PVE configuration. Record local restore evidence without
   calling it host-loss recovery.

Stop before any write if endpoint identity, disk ownership, capacity, key
recovery, the prior recovery point, or restore isolation cannot be verified.
Preserve failed artifacts for diagnosis until ownership and retention are
clear. Rollback removes only the new unaccepted temporary copy and isolated
restore resources after checking exact identity; it does not roll back live
VM, HBA, pool, or network configuration. A future live run needs its own
reviewed plan and read-back. This plan is not evidence of execution.

### Sizing and key constraints

The workstation had 11 GiB free and PVE `local` had 452 GiB free in the last
2026-10-03 read. Recheck both and measure the current VM size and destination
capacity before a run. Use the existing `host/pve/backup-host-config.sh`
encrypted bundle; keep its decryption material in the workstation keyring.
Create a separate VM-archive encryption key before the first archive, also
held in that keyring for the interim procedure. This key custody remains
dependent on the workstation and does not meet the independent key-recovery
gate.

Proxmox documents `vzdump --stdout` and zstd compression, but streamed output
has no storage-managed catalog or retention. The earlier VM 100 stream was a
sizing probe and no archive was retained. The interim procedure must record its
own result and verify the archive before transfer; it cannot satisfy
independent recovery even after a local restore. See the
[Proxmox `vzdump` documentation](https://github.com/proxmox/pve-docs/blob/master/vzdump.adoc).

## Deferred second-site recovery

The [backlog item](../.backlog/2026-10-03-implement-independent-second-site-backup-and-tested-recovery.md)
owns receiver readiness, remote NAS and VM copies, destination-side checks,
independent restore tests, wider service coverage, and any later unique-data
promotion. Its receiver and transfer choices remain undecided until a solution
exists. This Group 5 plan can finish without those choices; it cannot satisfy
their independent-recovery gate.

## Current checkpoint — 2026-10-03

- The operator confirmed there is no second-site ZFS receiver. No off-host
  backup, destination-side verification, or off-host restore has been claimed.
- The local encrypted TrueNAS configuration archive
  `truenas-config-post-share-20261002T-fresh.tar.gpg` passed GPG integrity
  verification on 2026-10-03. It contains the database and `pwenc_secret`
  members, is 46,120 bytes, and has SHA256
  `1af911d4172a6cc2eb2b959bb51b1591a014eae9d8d591a11c69e9f29f2ae4f0`.
  Its parent directories are mode 700 under the private homelab data directory
  on the laptop. This is a local artifact, not an off-host copy or restore
  test.
- `truenas.localdomain` resolved to `192.168.0.186`. A read-only TLS handshake
  presented a self-signed iXsystems certificate with subject and issuer
  `CN=localhost`, SAN `DNS:localhost`, and SHA256 fingerprint
  `1C:28:2F:58:5C:A4:BE:1F:16:12:B4:1E:B0:E0:18:D0:B5:18:53:5C:1C:5B:CC:D0:B4:A7:2D:0C:43:FB:5F:B8`.
  Verification for `truenas.localdomain` failed with hostname mismatch. This
  fingerprint records the certificate served at the address; it does not
  authenticate that certificate as the expected VM 200 identity.
- The Proxmox VM 200 noVNC page was visible in personal Chrome. Browser policy
  allowed the exact Proxmox frame in the `nas-guest-retry` session, but its
  relay detached before a read-only guest command could run. No browser policy,
  PVE, TrueNAS, or network configuration was changed. Current TrueNAS alert
  status and trusted guest-certificate identity remain unverified.
- Former OpenSpec tasks 5.1–5.5 are deferred to the backlog. Current Group 5
  consists of a plan and scope reconciliation. Do not migrate unique data
  until receiver-side copies and the required independent restores pass.

Initial retention target for the deferred second-site design:

- 7 daily recovery points
- 4 weekly recovery points
- 6 monthly recovery points

Retention is a starting policy and should be adjusted after observing dataset
size and change rate.

## Eventual recovery coverage

- Fedora development VM and important RHEL VMs
- NAS datasets, appliance configuration export, share definitions, and pool
  import procedure
- AAP database, configuration, projects, credentials backup, and execution
  environment definitions
- IdM data and documented replica/recovery procedure
- OpenShift installation assets and GitOps bootstrap material
- PVE configuration and storage/network definitions
- OpenTofu state and its independent encryption key
- SOPS/age recovery keys
- iDRAC Server Configuration Profile and Brocade/UniFi configuration exports
- The bootloader reconstruction procedure and recovery media

Git repositories are replicated independently. Caches, installer ISOs, and
reproducible scratch workloads do not need the same retention as unique data.

## Eventual independent-recovery verification

- Restore individual files regularly.
- Restore a complete representative VM on a schedule.
- Perform a bare-metal recovery exercise after boot redundancy is implemented.
- Verify backups from the destination, not only from the job status on PVE.
- Restore a representative NAS file and the NAS configuration from the remote
  copy before placing unique data on the NAS. Exercise full pool/VM recovery
  separately; a file restore alone does not prove it.
- Alert on missed jobs, verification failures, repository capacity, and stale
  recovery points.

## Power protection

Place the R720, active switch path, and router on an appropriately sized UPS.
The second-site ZFS receiver is off-site and does not depend on this UPS; local
backup staging, if added, does. Integrate NUT or the vendor network agent so
the NAS and other guests stop cleanly before PVE. Test the shutdown sequence
without relying on an actual extended outage.

## Recovery order

1. Network, DNS, time, and required certificates.
2. PVE boot and storage imports.
3. NAS guest, SATA pool import, and shares needed by other workloads.
4. AAP and IdM.
5. Fedora development environment.
6. OpenShift and its GitOps bootstrap.
7. Remaining workloads by documented priority.
