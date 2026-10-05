## Why

The R720 needs to become a recoverable development platform and Red Hat lab without turning a single host, local redundancy, or undocumented manual changes into hidden dependencies. The existing roadmap and first-VM/NAS plans need one staged change contract that preserves their separate safety gates while making the next work executable.

## What Changes

- Establish and maintain a verified Proxmox host, storage ownership boundaries, and measured capacity; treat 256 GiB as a target rather than a prerequisite for the first VMs. The optional DIMM expansion and alternate firmware boot-path exercise are deferred to the [DIMM backlog item](../../../.backlog/2026-10-05-complete-r720-dimm-expansion-after-module-identification.md) and [boot/recovery backlog item](../../../.backlog/2026-10-05-document-and-prove-independent-r720-boot-and-recovery.md).
- Put planned host changes and Proxmox/UniFi resources under versioned, recoverable control, with a disposable-VM lifecycle test before important VMs.
- Deploy an initially reproducible Fedora development VM and a NAS VM with whole-HBA passthrough; gate NAS pool creation separately from VM creation.
- Build the managed network foundation, then IdM, AAP, and Single Node OpenShift as capacity and prerequisites allow.
- Prepare an executable implementation plan for a bounded same-host backup of reproducible Fedora and host-configuration data. Keep backup execution, unique-data promotion, and any host-loss recovery claim outside this change until their respective prerequisites and deferred second-site work pass.

## Capabilities

### New Capabilities

- `r720-host-foundation`: Verified boot, host storage, hardware capacity, and safe change control.
- `infrastructure-control-plane`: Recoverable OpenTofu state, scoped identities, gated plans, and resource ownership.
- `fedora-development`: Reproducible Fedora VM deployment and eventual promotion to the primary workspace.
- `nas-service`: Guest-owned SATA storage through whole-HBA passthrough and tested file shares.
- `managed-network`: Backed-up and recoverable Brocade/UniFi configuration, resilient host connectivity, and secure administration.
- `red-hat-platform`: IdM, AAP, and Single Node OpenShift with their respective automation owners.
- `independent-recovery`: A reviewable interim backup implementation plan and an explicit gate that prevents a same-host copy from being treated as independent recovery.

### Modified Capabilities

None; this repository has no existing OpenSpec capability specs.

## Impact

This change spans versioned `host/pve/` maintenance, separate Proxmox and UniFi OpenTofu roots, guest bootstrap and AAP automation, NAS guest configuration, OpenShift GitOps, inventories, ADRs, and recovery documentation. Full second-site backup implementation and unique-data promotion are tracked in the [deferred recovery backlog item](../../../.backlog/2026-10-03-implement-independent-second-site-backup-and-tested-recovery.md), outside this change. This proposal itself authorizes no disk clearing, host reboot, network cutover, or placement of unique data.
