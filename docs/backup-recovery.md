# Backup and recovery

## Objective

A disk mirror is not a backup, and a backup stored only inside the R720 does not
protect against loss of the host. The recovery system must be usable when PVE,
its pools, AAP, and OpenShift are all unavailable.

## Backup destination

Use a local ZFS receiver at another site for encrypted copies of NAS data and
selected infrastructure recovery artifacts. The operator selected this
destination design. On 2026-10-03 the operator confirmed that no second-site
ZFS receiver exists yet. Off-host replication and restore are blocked until a
receiver is provisioned and verified. Decide the replication and full-VM
archive methods, encryption, access boundaries, and independently recoverable
keys before writing backup automation. Keep the encryption key and recovery
material recoverable outside the R720 and the receiver. The NAS VM and its
RAIDZ2 pool remain on the R720 and do not satisfy the host-loss requirement. If
local Proxmox VM backup staging is added, it is an intermediate copy, not the
sole backup destination.

## Receiver readiness checklist — task 5.1

Task 5.1 is ready to close after the actual receiver is identified and
provisioned, each readiness item below has evidence, and the restricted transfer
path passes a read/write check against a dedicated receiver test target. Task
5.1 records restore procedures and acceptance criteria; it does not require the
restore tests assigned to tasks 5.2 and 5.3.

- [ ] Name the physical site, its owner, and how it is independent of the R720
  site's likely power, fire, theft, and access failures.
- [ ] Identify the specific host and supported OS/OpenZFS release; record its
  pool topology, disk identities and health, usable capacity, and spare space
  for retention and temporary restores.
- [ ] Confirm receiver power, remote console or hands-on access, recovery
  access, and how the host will remain available during a site outage.
- [ ] Measure the network path, R720 upload rate, dataset size, expected first
  seed duration, and ongoing change rate. Document the firewall and routing
  boundary without exposing an administrative service to the public internet.
- [ ] Choose and test the restricted transfer identity, authentication,
  endpoint/host-key verification, and permitted receive path. Record how access
  is revoked and recovered.
- [ ] Decide where encryption occurs and how encryption and recovery keys can
  be recovered independently of both sites and the laptop's sole disk. Test
  that key-recovery path without placing key material in this repository.
- [ ] Select NAS dataset and appliance-configuration transfer methods,
  snapshot/retention policy, local staging needs, and destination-side
  freshness, capacity, and integrity checks.
- [ ] Select the full-VM archive method and retention, measure required local
  staging capacity and backup window, and document how the archive is
  transferred and independently verified at the receiver.
- [ ] Define missed-job, stale-copy, integrity, and capacity alerts and their
  delivery route; task 5.4 configures and verifies delivery.
- [ ] Document the isolated restore procedures, acceptance criteria, required
  recovery host, and separately held keys for tasks 5.2 and 5.3.

## Group 5 restore acceptance — tasks 5.2 and 5.3

These tests follow receiver readiness and are separate completion gates:

- [ ] Task 5.2 configures the NAS dataset and appliance-configuration copies,
  then restores a representative file and configuration from the receiver on
  an independent recovery host using only the remote copy and separately held
  keys.
- [ ] Task 5.3 verifies the full Fedora VM archive at the receiver, then
  restores it to an isolated scratch ID with no network, inspects it, removes
  it, and verifies no orphans. Record that this same-host test does not prove
  host-loss recovery.

The next operator decision is physical: name the separate site and any
already-available host that could serve as the receiver. If no suitable host
is available, decide whether to provision one or reopen the destination choice.
No receiver hardware or hosted service has been purchased or authorized by this
checkpoint.

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
- OpenSpec tasks 5.1–5.5 remain unchecked. Do not migrate unique data until
  receiver-side copies and the required independent restores pass.

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
