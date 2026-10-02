## 1. Refresh the host baseline

- [x] 1.1 Recheck PVE/iDRAC versions, boot and management access, `rpool` and `fast-vm`, memory/SEL health, and inventory timestamps against the Phase 0 evidence.
- [x] 1.2 Verify the off-host host-configuration bundle, console/rescue access, and `fast-vm` serial-specific drift check; record discrepancies before further live changes.
- [x] 1.3 Review the deferred PVE upgrade as a separate maintenance decision; keep the versioned repository configuration at a no-drift read-back.

## 2. Establish the Proxmox control plane

- [x] 2.1 Complete ADR 0009's encrypted laptop-local Proxmox state bootstrap; test local lock contention, ciphertext, and recovery of a second encrypted state copy and passphrase from a separate location. Record that local locking does not coordinate other machines and defer any remote-backend migration to a reviewed, tested change.
- [x] 2.2 Implement and verify a scoped PVE automation identity and versioned host check/apply path; prove allowed VM operations and denied host/storage-admin operations.
- [x] 2.3 Pin OpenTofu/provider versions, implement the Proxmox VM root/module, and test plan-JSON resource/action safeguards with positive and negative cases.
- [x] 2.4 Confirm the Git remote and protected-branch review policy; scan the reviewed source and saved plans for secrets and state before the first VM apply.
- [x] 2.5 Recheck image, cloud-init, bridge, guest-agent, and `fast-vm` paths; apply a reviewed disposable-VM plan, verify boot and no-change plan, then review its destroy and check for orphans.

## 3. Deploy the reproducible Fedora VM

- [x] 3.1 Reconcile live memory, SEL, boot-device health, datastore headroom, address/DNS, and the staged Fedora image; record the final VM allocation from observed capacity. Stop creation on an uncorrectable memory error, rising correctable count, SEL memory event since the last DIMM change, or unattributed iDRAC Critical condition; record disposition of the current Critical alert. User waived the broken chassis-intrusion sensor alert as a blocker after fresh read-back isolated it as the sole asserted sensor; no safely scoped iDRAC control was available to disable only that alert.
- [x] 3.2 Define and create an initially empty Fedora VM in OpenTofu; verify live CPU, memory, boot disk, network, guest access, and a no-change plan.
- [x] 3.3 Add laptop-runnable guest configuration with check mode and live read-back; keep unique development data off the VM until task group 5 passes.

## 4. Deploy the NAS without conflating VM and disk gates

- [ ] 4.1 Refresh all eight SATA serials, signatures, SMART data, by-id paths, HBA/IOMMU membership, host boot path, and recovery console evidence. The operator has authorized disposal of the existing contents on all eight SSDs; preserve that decision and verify each exact serial before any destructive action. Stop if a disk identity is uncertain or the IOMMU group includes a host-required device.
- [ ] 4.2 Select and verify the NAS OS/release and image; implement reviewed HBA binding preview/check/apply/rollback in versioned host maintenance code. Test whether the scoped PVE identity can assign PCI through a resource mapping or needs a separate privileged host step; do not widen routine token scope.
- [ ] 4.3 Budget pinned NAS RAM and `fast-vm` capacity alongside Fedora and later important VMs; define the NAS VM with whole-HBA passthrough, apply a gated plan, and verify guest serials/SMART, host exclusion, and denied mapping-administration operations for the routine identity.
- [ ] 4.4 Test NAS VM start/stop/reset and host cold boot; verify `rpool`, `fast-vm`, HBA assignment, guest serials, and rollback without writing SATA data. Test that the host check fails closed on incorrect HBA binding; repeat binding and host-import checks after a kernel change.
- [ ] 4.5 Reconfirm every exact SATA serial, save and hash-check off-target header/signature captures before clearing, and review the destructive guest pool plan. Treat header captures as metadata evidence, not full data backups.
- [ ] 4.6 Create the eight-disk RAIDZ2 pool in the guest; verify topology, health, mountpoints, usable capacity, scrubs, SMART scheduling, snapshots, and alert behavior. Confirm the host does not import or register the guest pool.
- [ ] 4.7 Define datasets and SMB/NFS shares with permissions/quotas; test allowed and denied clients, representative I/O, and guest/host restart recovery using reproducible data.

## 5. Prove off-host recovery before unique data

- [ ] 5.1 Select the rsync.net account and NAS transfer format and decide the full-VM backup method, including off-host destination, local staging budget, encryption, first-seed time/bandwidth, retention, and restore steps. Keep credentials and decryption material recoverable from a second location outside both the R720 and laptop's sole disk.
- [ ] 5.2 Configure NAS dataset and appliance-configuration backups; verify the destination copy and restore a file and NAS configuration from an independent recovery host using only the remote copy and separately held keys.
- [ ] 5.3 Configure a full Fedora VM backup and verify its archive at the independent destination. Through the versioned restore-test exception, restore to a scratch ID outside OpenTofu's range with no NIC or a link-down NIC; boot and inspect it, then remove it and verify no orphans. Record that this same-host test does not prove host-loss recovery.
- [ ] 5.4 Configure versioned host ZFS/SMART/capacity and backup-failure alerts, plus NAS missed-job/stale-copy/capacity alerts; verify live configuration and delivered test alerts, and refresh and extraction-test the off-host host bundle before unique data migration.
- [ ] 5.5 Migrate unique data incrementally only after the respective remote-copy and restore gates, retaining an authoritative copy elsewhere throughout the trial. Exercise Fedora repositories, container build, and remote access for at least 14 days; require successful scheduled backups, no new OOM/ZFS/SMART/SEL memory errors, `fast-vm` at least 20% free, and CPU/drive temperatures below iDRAC warning thresholds. Investigate sustained swap or available host memory below 16 GiB before primary-workspace promotion.

## 6. Expand and test physical resilience

- [ ] 6.1 After a fresh backup and in a planned outage, install and diagnose the remaining matched RDIMMs; verify 256 GiB in iDRAC and the OS with no new memory errors before increasing VM allocations.
- [ ] 6.2 Add a second firmware-visible boot SSD with versioned recovery procedure; prove a cold boot with each boot device independently unavailable.
- [ ] 6.3 Create the disposable `scratch` tier only after serial-specific classification and reviewed storage preflight; verify it cannot be mistaken for durable data storage.
- [ ] 6.4 Measure pool health, scrubs, SMART tests, quotas, capacity thresholds, and representative device-failure procedures for each implemented host tier.

## 7. Build the managed network foundation

- [ ] 7.1 Decide and record the internal domain, VLANs, subnets, reservations, naming, and required access boundaries.
- [ ] 7.2 Capture and recovery-test encrypted off-host Brocade and UniFi configuration backups; prove read-only automation identities against the live firmware/controller.
- [ ] 7.3 Select and test a compatible UniFi provider in a separate locked state; import existing objects and obtain a no-change plan.
- [ ] 7.4 Validate the pinned Brocade execution environment and audit/backup workflow without switch writes; prepare reviewed apply/verify/rollback jobs.
- [ ] 7.5 Apply the reviewed PVE bond with fallback management access and prove management survives either bonded link being disconnected.
- [ ] 7.6 Apply the VLAN-aware bridge and routed/firewalled boundaries with current backups and rescue access; test permitted and denied paths.
- [ ] 7.7 Establish DNS, trusted certificates, and VPN administration; verify PVE/iDRAC remain off the public internet and test access from allowed and denied networks.

## 8. Add Red Hat platform services

- [ ] 8.1 Verify current capacity and recovery prerequisites, then provision RHEL templates and `idm01` with versioned first boot and guest configuration.
- [ ] 8.2 Bootstrap containerized AAP on a dedicated RHEL VM from the laptop; manage its inventories, credentials definitions, execution environments, templates, and workflows as code.
- [ ] 8.3 Prove an audited AAP workflow can provision, configure, verify, and remove a disposable VM; add OpenManage inventory/configuration export before iDRAC writes.
- [ ] 8.4 Confirm OpenShift entitlement, release compatibility, DNS, addressing, capacity, and backup design; provision the Single Node OpenShift VM.
- [ ] 8.5 Bootstrap OpenShift GitOps, verify reconciliation/self-healing and a rebuild path, and add optional Operators only for identified needs.

## 9. Complete independent operations

- [ ] 9.1 Extend encrypted off-host backup and destination-side freshness checks to important VMs, AAP, IdM, OpenShift, network exports, state, recovery keys, bootloader reconstruction instructions, and rescue media.
- [ ] 9.2 Integrate UPS signaling and test orderly guest/NAS/PVE shutdown without an extended power outage.
- [ ] 9.3 Verify alert delivery for disks, ZFS, memory/SEL, backups, capacity, thermals, power, certificates, and platform services.
- [ ] 9.4 Exercise file, representative VM, NAS, AAP, IdM, and OpenShift recovery. Rehearse bare-metal boot and pool import against a reviewed non-destructive target with live data devices protected; record pass criteria, recovery order, and measured capacity before declaring the overall build complete.
