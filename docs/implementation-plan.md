# Implementation plan

Each phase leaves the environment recoverable and produces evidence before the
next phase depends on it.

Planned changes from 2026-10-01 onward follow the
[R720 change-control cutoff](r720-change-control.md). The existing `fast-vm`
pool passed its serial-specific drift check, and the OpenTofu control-plane
gates are complete. The Fedora VM is deployed; group 4's read-only NAS
preflight is the next OpenSpec milestone.
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
Network automation and
the remaining NVMe scratch pool can follow separately if the VM's required
management, DNS, and remote access already work safely on the existing
network. No storage write or disruptive host change is implied by this plan.

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

## Phase 1: physical maintenance

- Preserve the currently booting 128 GB configuration and refresh iDRAC/OS
  agreement before another physical change. The earlier A2 reseat is not a
  pending step.
- Gracefully power down and remove AC power.
- Install the purchased eight matching 16 GB RDIMMs in A5-A8 and B5-B8.
- Run lifecycle diagnostics and an extended memory test.
- Verify 256 GB with balanced CPU/channel population and refresh inventory.
- Optionally replace both processors with a supported matched v2 pair after the
  memory change has been validated separately.

Completion evidence: iDRAC and the operating system agree on the 256 GiB DIMM
inventory, memory diagnostics pass, and no new SEL entries appear. This
capacity-expansion phase may finish after the first Fedora VM is deployed;
the VM still requires a stable, verified current memory configuration.

## Phase 2: boot and storage

- Add a second firmware-visible boot SSD and implement the boot resilience plan.
- Fix or remove stale ZFS labels only by recorded serial number.
- Adopt the verified `fast-vm` mirror; create `scratch` later from the two
  serial-resolved, disposable front NVMe devices.
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
- After the disposable VM lifecycle passes, create a NAS VM booting from
  `fast-vm` with the complete SAS2308 passed through. Select the NAS OS and
  image before writing its VM definition. Verify repeated VM
  start/stop/reset cycles, guest disk serials, host disk exclusion, and the
  recovery path before creating its eight-disk RAIDZ2 pool and file shares.
  Start with a measured RAM allocation within the verified 128 GiB host,
  leaving headroom for Fedora; 256 GiB is not a NAS prerequisite.
  Follow the NAS plan's separate serial, passthrough, guest-pool, and recovery
  gates; do not treat VM creation as permission to clear the SATA disks.
- Before unique data enters the NAS, configure its encrypted rsync.net copy
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

## Phase 5: primary development environment

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

## Phase 8: independent recovery and operations

- Extend the earlier rsync.net NAS and Fedora recovery paths to the remaining
  important VMs and infrastructure artifacts. Keep encrypted copies, retention,
  and alerting verified against the remote destination, not only local NAS
  snapshots. Native ZFS receive requires the appropriate account; a standard
  SSH-compatible backup workflow remains an option.
- Integrate UPS shutdown behavior.
- Centralize alerts for ZFS, disks, backups, thermals, power, certificates,
  PVE, AAP, IdM, and OpenShift.
- Run file, VM, AAP, IdM, OpenShift, and bare-metal recovery exercises.
- Record measured capacity and adjust reservations instead of relying on initial
  estimates.

Completion evidence: an off-host recovery exercise succeeds without depending
on a service hosted only on the R720.
