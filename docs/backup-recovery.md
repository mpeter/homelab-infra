# Backup and recovery

## Objective

A disk mirror is not a backup, and a backup stored only inside the R720 does not
protect against loss of the host. The recovery system must be usable when PVE,
its pools, AAP, and OpenShift are all unavailable.

## Backup destination

Use rsync.net as the planned off-site destination for encrypted copies of NAS
data and selected infrastructure recovery artifacts. Choose the transfer
method and account type before writing backup automation: ordinary SSH-based
file backup and native ZFS receive are distinct products. Keep the encryption
key and account recovery material independently recoverable from the R720.
The NAS VM and its RAIDZ2 pool remain on the R720 and do not satisfy the
host-loss requirement. If local Proxmox VM backup staging is added, it is an
intermediate copy, not the sole backup destination.

Initial retention target:

- 7 daily recovery points
- 4 weekly recovery points
- 6 monthly recovery points

Retention is a starting policy and should be adjusted after observing dataset
size and change rate.

## What must be recoverable

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

## Verification

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
The rsync.net destination is off-site and does not depend on this UPS; local
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
