## Context

The R720 is a single-host Proxmox lab intended to become a Fedora development platform and a Red Hat automation/OpenShift learning environment. Phase 0 recovery and cold-boot checks and the `fast-vm` mirror have documented success as of 2026-10-01, but all live facts must be refreshed before writes. The host has eight 16 GB DIMMs (128 GB nominal); 256 GB is a later hardware target. The reproducible Fedora development VM is deployed, but it holds no unique data and no production VMs are in service. The repository's [implementation plan](../../../docs/implementation-plan.md), [first-VM plan](../../../docs/first-vm-implementation-plan.md), [NAS plan](../../../docs/nas-implementation-plan.md), and ADRs remain the detailed source for per-stage procedures.

## Goals / Non-Goals

**Goals:**

- Make the dependency order and exit evidence explicit across host, VMs, NAS, network, platform services, and recovery.
- Deliver useful empty/reproducible Fedora and NAS services before optional memory expansion or the full network/platform build.
- Keep control and recovery usable from the laptop when the R720 and all guests are unavailable.
- Promote unique data and later services only after their own recovery and capacity gates pass.

**Non-Goals:**

- Claim high availability from a single R720, a mirror, or the local NAS.
- Choose a transfer product, UniFi provider, internal domain, or final VM sizes without the required compatibility and live-capacity evidence.
- Treat this planning change as approval for a disk wipe, HBA binding, host reboot, or network cutover.

## Decisions

1. **Use gated dependency tracks, not a literal phase-number queue.** Establish host recovery and the OpenTofu control plane before real VMs. Empty Fedora and NAS VMs may then advance independently; the NAS guest pool has a separate destructive gate. Memory expansion and full network automation can follow when needed. A rigid phase-number sequence would defer useful VMs for unrelated hardware and network work; an ungated parallel build would hide recovery dependencies.
2. **Keep explicit layer ownership.** Versioned `host/pve/` procedures own host configuration, OpenTofu owns Proxmox VMs and supported UniFi resources in separate states, the NAS guest owns the eight SATA disks/pool/shares, AAP owns guest and Brocade configuration, and GitOps owns OpenShift resources. This follows [ADR 0002](../../../docs/decisions/0002-use-git-opentofu-aap-and-argo-cd.md), [ADR 0006](../../../docs/decisions/0006-split-network-management-between-aap-and-opentofu.md), [ADR 0008](../../../docs/decisions/0008-cut-over-r720-changes-to-versioned-control.md), and [ADR 0010](../../../docs/decisions/0010-run-the-bulk-nas-as-a-vm-with-hba-passthrough.md). Direct GUI configuration is reserved for recovery and then reconciled.
3. **Separate local availability from independent recovery.** `fast-vm` remains a host-owned mirror. The NAS VM boots there, receives the complete SAS2308 HBA, and builds RAIDZ2 inside the guest only after serial-specific disposition and passthrough tests. Neither mirror nor RAIDZ2 substitutes for an encrypted off-host restore. Other VMs must not boot from the same-host NAS export. A host-managed SATA pool was considered and rejected by ADR 0010 because it blurs disk and share ownership.
4. **Use TrueNAS Community Edition 25.10.7 for the NAS guest.** The operator accepts the home-lab support tradeoff described in ADR 0011. Keep the VM stopped and without HBA access during initial creation; require verified console access before installation and retain the independent-backup gate for unique data.
5. **Keep the break-glass control path independent.** [ADR 0009](../../../docs/decisions/0009-bootstrap-proxmox-state-on-break-glass-workstation.md) selects encrypted local Proxmox state on the laptop for bootstrap, with local locking and an independently recoverable second state copy and passphrase; it does not select a remote backend yet. The laptop retains a repository clone and access, while a separate recoverable location holds the second state/key and backup decryption material so laptop loss does not destroy recovery. Local locking does not coordinate other machines. A disposable VM proves the provider, identity, image, state, and lifecycle path before Fedora or NAS is relied upon. Proxmox and UniFi state and identities remain separate; migration to a locked remote backend is a later tested decision.
6. **Stage promotion, not just creation.** An empty Fedora VM can be used for reproducible work and an empty NAS can be tested before the second-site ZFS receiver is ready. Unique data or primary-workspace status requires a remote copy verified at its destination and a restore using independently held material; an on-host VM restore alone proves format and procedure, not host-loss recovery. Later IdM/AAP/OpenShift require measured capacity, network/DNS prerequisites, and their own recovery paths.

## Risks / Trade-offs

- **Single-host outage affects every local service** → Keep off-host configuration, state, secrets recovery, and backups; rehearse host-loss recovery.
- **DIMM or iDRAC alerts invalidate capacity assumptions** → Reconcile iDRAC/OS memory and SEL before VM allocation; investigate uncorrectable or rising errors before important VM creation.
- **Passthrough mistakes can strand the host or expose wrong disks** → Recheck PCI group and host boot path, preserve console access and rollback, verify guest serials before any pool write.
- **A provider may require more privilege for PCI assignment than for ordinary VM changes** → Test effective permissions and the provider path; use a narrowly scoped mapping if supported or a separate versioned host step, never broaden the routine VM identity to host administration merely to pass a plan.
- **Broad automation permissions or state loss can amplify a mistake** → Scope effective API permissions, test denied operations and state recovery, gate plans by allowed resource/action, and verify no-change read-back.
- **The current single firmware-visible boot SSD can fail before boot redundancy is installed** → Retain tested recovery media, the off-host host bundle, and reconstruction procedure; schedule the second boot device as separate maintenance. This risk is temporarily accepted for empty/reproducible VMs and must be revisited before declaring the full platform resilient.
- **Second-site receiver and transfer method are not yet ready** → Continue empty/reproducible services only; do not promote unique data until remote restore succeeds.
- **One umbrella change is large** → Treat each task group as a separately verifiable milestone. Do not mark the whole change complete from an early VM or NAS success.

## Migration Plan

1. Refresh Phase 0 and inventory evidence; preserve current `rpool`/`fast-vm` and test the recovery route.
2. Finish versioned host checks, ADR 0009 bootstrap state and independent second-copy/key recovery, scoped identity, plan gates, and a disposable VM lifecycle.
3. Deploy empty Fedora and NAS VMs from reviewed plans. Before changing HBA binding, resolve and classify every SATA serial and prepare the host rollback. Before clearing any SATA signature, capture off-disk recovery evidence and review the exact destructive plan.
4. Establish and restore-test independent backups. Only then migrate unique data and promote Fedora/NAS.
5. Complete memory and boot-resilience maintenance, network foundation, IdM/AAP, OpenShift, and operational recovery in dependency order, with fresh evidence at each disruptive step.

Rollback is stage-specific: use saved host configuration and console recovery for host changes, reconcile OpenTofu state/live resources for VM changes, and restore off-host data rather than assuming pool redundancy repairs data loss. Preserve failed state for diagnosis rather than forcing a plan green.

## Open Questions

- Which second-site ZFS receiver, NAS replication format, retention, and full-VM backup method will be used? The VM method must account for staging capacity, encryption, first-seed time, and a destination-verified restore.
- What live memory/SEL state, final VM allocations, internal domain/VLAN plan, UniFi provider, and OpenShift entitlement are confirmed at their respective gates?
