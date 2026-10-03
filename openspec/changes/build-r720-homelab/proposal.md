## Why

The R720 needs to become a recoverable development platform and Red Hat lab without turning a single host, local redundancy, or undocumented manual changes into hidden dependencies. The existing roadmap and first-VM/NAS plans need one staged change contract that preserves their separate safety gates while making the next work executable.

## What Changes

- Establish and maintain a verified Proxmox host, resilient boot path, storage ownership boundaries, and measured capacity; treat 256 GiB as a target rather than a prerequisite for the first VMs.
- Put planned host changes and Proxmox/UniFi resources under versioned, recoverable control, with a disposable-VM lifecycle test before important VMs.
- Deploy an initially reproducible Fedora development VM and a NAS VM with whole-HBA passthrough; gate NAS pool creation separately from VM creation.
- Build the managed network foundation, then IdM, AAP, and Single Node OpenShift as capacity and prerequisites allow.
- Provide independent encrypted backup, tested restores, monitoring, and operational recovery before promoting unique data or calling the platform complete.

## Capabilities

### New Capabilities

- `r720-host-foundation`: Verified boot, host storage, hardware capacity, and safe change control.
- `infrastructure-control-plane`: Recoverable OpenTofu state, scoped identities, gated plans, and resource ownership.
- `fedora-development`: Reproducible Fedora VM deployment and eventual promotion to the primary workspace.
- `nas-service`: Guest-owned SATA storage through whole-HBA passthrough and tested file shares.
- `managed-network`: Backed-up and recoverable Brocade/UniFi configuration, resilient host connectivity, and secure administration.
- `red-hat-platform`: IdM, AAP, and Single Node OpenShift with their respective automation owners.
- `independent-recovery`: Off-host encrypted recovery, restore evidence, alerts, and host-loss procedures.

### Modified Capabilities

None; this repository has no existing OpenSpec capability specs.

## Impact

This change spans versioned `host/pve/` maintenance, separate Proxmox and UniFi OpenTofu roots, guest bootstrap and AAP automation, NAS guest configuration, OpenShift GitOps, inventories, ADRs, and recovery documentation. It affects the live R720, iDRAC, Brocade, UniFi, and an independent backup destination only through later reviewed implementation stages. This proposal itself authorizes no disk clearing, host reboot, network cutover, or placement of unique data.
