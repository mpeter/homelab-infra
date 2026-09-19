# Backup and recovery

## Objective

A disk mirror is not a backup, and a backup stored only inside the R720 does not
protect against loss of the host. The recovery system must be usable when PVE,
its pools, AAP, and OpenShift are all unavailable.

## Backup destination

Deploy Proxmox Backup Server on separate hardware or use an independent storage
target with equivalent isolation. A PBS VM whose datastore is in the same R720
does not satisfy the host-loss requirement.

Initial retention target:

- 7 daily recovery points
- 4 weekly recovery points
- 6 monthly recovery points

Retention is a starting policy and should be adjusted after observing dataset
size and change rate.

## What must be recoverable

- Fedora development VM and important RHEL VMs
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
- Alert on missed jobs, verification failures, repository capacity, and stale
  recovery points.

## Power protection

Place the R720, active switch path, router, and backup target on an appropriately
sized UPS. Integrate NUT or the vendor network agent so guests stop first, PVE
stops after them, and the backup target remains consistent. Test the shutdown
sequence without relying on an actual extended outage.

## Recovery order

1. Network, DNS, time, and required certificates.
2. PVE boot and storage imports.
3. AAP and IdM.
4. Fedora development environment.
5. OpenShift and its GitOps bootstrap.
6. Remaining workloads by documented priority.
