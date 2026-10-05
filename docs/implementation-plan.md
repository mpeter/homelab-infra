# Implementation plan

Each phase leaves the environment recoverable and produces evidence before the
next phase depends on it.

Current Group 5 work completes the
[interim backup implementation plan](backup-recovery.md#interim-same-host-truenas-backup-plan--2026-10-03).
The
[second-site backup and restore implementation](../.backlog/2026-10-03-implement-independent-second-site-backup-and-tested-recovery.md),
including unique-data promotion, is deferred until a receiver solution exists.
The gates below remain conditions for future promotion, not claims that those
backups or restores have run.

Planned changes from 2026-10-01 onward follow the
[R720 change-control cutoff](r720-change-control.md). The existing `fast-vm`
pool passed its serial-specific drift check, and the OpenTofu control-plane
gates are complete. The Fedora VM and reproducible NAS test shares are
deployed; refresh live evidence before relying on them.
The [first-VM implementation plan](first-vm-implementation-plan.md) gives the
ordered work and exit evidence from this cutoff through Fedora deployment.
The [NAS implementation plan](nas-implementation-plan.md) gives the separate
HBA, guest-pool, share, and off-site recovery gates.

## Staged first workload

The first development workload is the Fedora VM. The NAS VM is the next local
storage service; it can be built empty without waiting for the Fedora trial or
the off-site backup account.
The R720's 256 GiB
memory configuration remains the eventual capacity target, not a prerequisite
for this VM. Verify the currently installed DIMMs with iDRAC, the operating
system, and diagnostics before allocating memory; do not infer capacity from
the target population or a previous boot screen.

The deployed Fedora VM uses 8 vCPU, 32 GiB RAM, and a 300 GiB boot disk.
Recheck live headroom before changing its allocation. Keep AAP, IdM, OpenShift,
and other substantial VMs deferred until their memory and storage budgets are
measured and approved.

This staging changes the order, not the safety gates: complete the Phase 0
recovery and stable-boot evidence; establish and verify the `fast-vm` mirror
from serial-resolved devices under the storage plan; prepare recoverable
OpenTofu state and a tested disposable-VM workflow; and provide independent
off-host backup before treating the Fedora VM as primary, then test its restore.
Network automation can follow separately if the VM's required
management, DNS, and remote access already work safely on the existing
network. The scratch-tier write completed later under the reviewed storage
plan; see Phase 2 and the dated inventory evidence. This overview does not
authorize another storage write or disruptive host change.

## Phase 0: stabilize the installed host

Status on 2026-10-01: host-ID repair, repository normalization, recovery
bundle creation, and repeated cold-boot checks passed. The PVE package upgrade
was explicitly deferred as separate kernel/ZFS maintenance. Refresh live
evidence before treating any of these observations as current.

- Capture current PVE, iDRAC, storage, network, and boot state.
- Retain the recorded ZFS host-ID repair and verify it after later boots.
- Remove stale installer media after the recovery path is prepared.
- Keep the versioned no-subscription repository configuration in sync with the
  live host; review any future PVE upgrade as separate maintenance.
- Build an off-host recovery bundle.
- Complete two unattended cold boots and verify PVE, storage, networking, and
  management access after each.

Completion evidence: clean `zpool status`, no failed services, expected package
repositories, HTTPS management access, and two recorded boot validations.

## Deferred: optional DIMM expansion

The optional expansion from eight to sixteen 16 GB RDIMMs is outside the
active OpenSpec change and is tracked in the [DIMM backlog item](../.backlog/2026-10-05-complete-r720-dimm-expansion-after-module-identification.md).
The installed eight-DIMM configuration remains the current baseline. Inventory
retains the dated host observations and unresolved capacity discrepancy; the
purchased upgrade modules and historical failed-POST report are not individually
mapped or qualified. Any future installation requires module identification,
compatibility checks, a fresh verified backup, a planned outage, and passing
post-install diagnostics before VM allocations change.

## Phase 2: boot and storage

- Defer alternate boot-path and recovery-media validation to the [boot/recovery backlog item](../.backlog/2026-10-05-document-and-prove-independent-r720-boot-and-recovery.md).
  In plain language, it asks whether Proxmox can cold-boot if the current
  Kingston SATA boot SSD is unavailable. EFI entries and files on the NVMe
  mirror are not proof that either path boots.
- Fix or remove stale ZFS labels only by recorded serial number.
- Adopt the verified `fast-vm` mirror. The serial-resolved `scratch` stripe
  was created on 2026-10-04 from the two operator-approved disposable front
  NVMe devices; it is non-redundant and holds no unique data. See
  `pve_scratch_tier_readback_143840` in `inventory/storage.yaml`.
- Inventory all eight SATA disk serials and signatures. Confirm the SAS2308
  remains isolated in its IOMMU group and that no host boot device is behind
  it. Stage the versioned host HBA-binding and recovery procedure, but do not
  create a Proxmox `bulk` pool on those disks.
- Configure scrubs, SMART tests, snapshots, quotas, capacity thresholds, and
  notifications.
- Test boot-device failure and a representative pool-device failure procedure.

Completion evidence: host-owned pools match the storage plan; the NAS HBA and
disk boundary is recorded without a host claim on those disks; monitoring and
the relevant recovery tests pass for each implemented tier.

## Phase 3: network foundation

- Select the internal domain, VLANs, subnets, reservations, and naming scheme.
- Record the Brocade model, firmware, console recovery method, and current
  running configuration.
- Record the UniFi controller product, version, API surface, object IDs, and a
  controller backup.
- Store raw Brocade and UniFi backups encrypted and off-host.
- Prove read-only access with dedicated Brocade and UniFi automation identities.
- Test the pinned Brocade execution environment against the live firmware; use
  generic CLI automation if the archived ICX collection is incompatible.
- Test current UniFi providers against the live controller and record the
  selection in an ADR update before creating state.
- Introduce the redundant PVE bond while preserving fallback management access.
- Create the VLAN-aware bridge and routed/firewalled network boundaries.
- Issue trusted certificates and establish VPN-based remote administration.

Completion evidence: encrypted backups and rescue procedures are restorable,
read-only automation succeeds, management survives either bonded link being
disconnected, DNS and certificates work, and firewall rules are tested from
permitted and denied networks.

## Phase 4: configuration-as-code bootstrap

- Confirm the Git remote and protected default-branch policy.
- Configure an encrypted off-host OpenTofu state backend with locking.
- Create separate Proxmox and UniFi state backends and apply identities.
- Create narrowly scoped PVE and iDRAC automation identities.
- Import existing UniFi objects and reach a no-change plan before managing them.
- Implement reusable OpenTofu VM modules and RHEL/Fedora cloud-init templates.
- After the disposable VM lifecycle passes, create a TrueNAS Community Edition
  25.10.7 NAS VM booting from `fast-vm` with the complete SAS2308 passed
  through. Keep initial VM creation HBA-free and stopped; verify the recovery
  console before installation. Verify repeated VM
  start/stop/reset cycles, guest disk serials, host disk exclusion, and the
  recovery path before creating its eight-disk RAIDZ2 pool and file shares.
  Start with a measured RAM allocation within the verified 128 GiB host,
  leaving headroom for Fedora; 256 GiB is not a NAS prerequisite.
  Follow the NAS plan's separate serial, passthrough, guest-pool, and recovery
  gates; do not treat VM creation as permission to clear the SATA disks.
- Before unique data enters the NAS, complete the deferred second-site copy
  and restore a representative file and appliance configuration from off-site.
- Create the base AAP execution environment with pinned collections and tools.
- Create a separate Brocade execution environment plus audit, backup, apply,
  verify, and rollback job templates.
- Import any pre-existing resource before declaring it managed.

Completion evidence: a reviewed plan creates and destroys a disposable VM,
UniFi produces a no-change plan after import, a Brocade audit and backup job
succeeds without changing the switch, no secret or state file appears in Git,
and both state backends can be recovered off-host. The NAS substage additionally
requires a no-change VM plan, guest pool and share read-back, and a host reboot
test before carrying unique data.

## Phase 5: primary development environment (promotion deferred)

- Provision the Fedora development VM on `fast-vm`.
- Restore configuration through chezmoi without transferring host-specific
  infrastructure ownership into the dotfiles repository.
- Migrate projects and unique data in stages only after their independent
  backup and restore path passes. An empty Fedora VM may be used earlier for
  reproducible work.
- Validate interactive performance, containers, builds, remote access, backup,
  and rollback before treating it as primary.

Completion evidence: normal development work succeeds for a trial period and a
full VM restore is demonstrated.

## Phase 6: Red Hat platform services

- Provision RHEL templates and `idm01`.
- Deploy containerized AAP on `aap01`, outside OpenShift.
- Manage AAP organizations, inventories, projects, credentials definitions,
  execution environments, templates, workflows, and schedules as code.
- Add Private Automation Hub and Event-Driven Ansible deliberately; begin EDA
  automations in notification/diagnostic mode.
- Use the Dell OpenManage collection to inventory iDRAC and export its Server
  Configuration Profile before enabling write operations.

Completion evidence: AAP can provision a disposable VM, configure it, validate
it, and remove it through an audited workflow.

## Phase 7: OpenShift

- Confirm entitlement and supported release compatibility.
- Create required `api`, `api-int`, and wildcard application DNS records.
- Provision a Single Node OpenShift VM with persistent addressing and adequate
  CPU, memory, and storage.
- Bootstrap OpenShift GitOps and move cluster/application resources under Argo
  CD ownership.
- Add Pipelines, Quay, or other Operators only for an identified use case.

Completion evidence: cluster upgrades, GitOps self-healing, backup, and a
documented rebuild from Git are exercised.

## Phase 8: independent recovery (deferred) and operations

The second-site backup and restore work in this phase belongs to the backlog
item linked above. Continue independent operational work only when its own
preconditions and change-control gates pass.

- Extend the earlier independent NAS and Fedora recovery paths to the remaining
  important VMs and infrastructure artifacts. Keep encrypted copies, retention,
  and alerting verified against the remote destination, not only local NAS
  snapshots. Confirm the receiver supports the selected transfer methods and
  required retention model.
- Integrate UPS shutdown behavior.
- Centralize alerts for ZFS, disks, backups, thermals, power, certificates,
  PVE, AAP, IdM, and OpenShift.
- Run file, VM, AAP, IdM, OpenShift, and bare-metal recovery exercises.
- Record measured capacity and adjust reservations instead of relying on initial
  estimates.

Completion evidence: an off-host recovery exercise succeeds without depending
on a service hosted only on the R720.
