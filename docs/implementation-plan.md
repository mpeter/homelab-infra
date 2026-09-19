# Implementation plan

Each phase leaves the environment recoverable and produces evidence before the
next phase depends on it.

## Phase 0: stabilize the installed host

- Capture current PVE, iDRAC, storage, network, and boot state.
- Correct the ZFS pool/system host-ID mismatch through a planned maintenance
  operation.
- Remove stale installer media after the recovery path is prepared.
- Replace inappropriate enterprise package repositories or attach the intended
  subscription, update PVE, and record the resulting versions.
- Build an off-host recovery bundle.
- Complete two unattended cold boots and verify PVE, storage, networking, and
  management access after each.

Completion evidence: clean `zpool status`, no failed services, expected package
repositories, HTTPS management access, and two recorded boot validations.

## Phase 1: physical maintenance

- Gracefully power down and remove AC power.
- Reseat the expected DIMM in A2.
- Install the purchased eight matching 16 GB RDIMMs in A5-A8 and B5-B8.
- Run lifecycle diagnostics and an extended memory test.
- Verify 256 GB with balanced CPU/channel population and refresh inventory.
- Optionally replace both processors with a supported matched v2 pair after the
  memory change has been validated separately.

Completion evidence: iDRAC and the operating system agree on DIMM inventory,
memory diagnostics pass, and no new SEL entries appear.

## Phase 2: boot and storage

- Add a second firmware-visible boot SSD and implement the boot resilience plan.
- Fix or remove stale ZFS labels only by recorded serial number.
- Create `fast-vm`, then `scratch`, then `bulk`, verifying each independently.
- Configure scrubs, SMART tests, snapshots, quotas, capacity thresholds, and
  notifications.
- Test boot-device failure and a representative pool-device failure procedure.

Completion evidence: target topology matches `docs/storage-plan.md`, monitoring
is active, and recovery tests succeed.

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
- Create the base AAP execution environment with pinned collections and tools.
- Create a separate Brocade execution environment plus audit, backup, apply,
  verify, and rollback job templates.
- Import any pre-existing resource before declaring it managed.

Completion evidence: a reviewed plan creates and destroys a disposable VM,
UniFi produces a no-change plan after import, a Brocade audit and backup job
succeeds without changing the switch, no secret or state file appears in Git,
and both state backends can be recovered off-host.

## Phase 5: primary development environment

- Provision the Fedora development VM on `fast-vm`.
- Restore configuration through chezmoi without transferring host-specific
  infrastructure ownership into the dotfiles repository.
- Migrate projects and unique data in stages.
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

- Deploy the independent backup target and retention policy.
- Integrate UPS shutdown behavior.
- Centralize alerts for ZFS, disks, backups, thermals, power, certificates,
  PVE, AAP, IdM, and OpenShift.
- Run file, VM, AAP, IdM, OpenShift, and bare-metal recovery exercises.
- Record measured capacity and adjust reservations instead of relying on initial
  estimates.

Completion evidence: an off-host recovery exercise succeeds without depending
on a service hosted only on the R720.
