# 0001. Use Proxmox as the infrastructure substrate

Date: 2026-09-19

## Status

Accepted

## Context

The R720 must support a primary development environment, general VMs and
containers, Kubernetes experiments, and Red Hat platform learning. Proxmox VE
9.2 is already installed with working hardware visibility and ZFS root storage.

## Decision

Keep Proxmox VE as the physical virtualization and local storage substrate.
Run Red Hat technologies in guests and manage Proxmox resources through its API
with OpenTofu and AAP orchestration.

## Alternatives rejected

- Install OpenShift directly on bare metal. This would improve product fidelity
  but dedicate the only host to one cluster and remove the general VM platform.
- Replace PVE with RHEL/KVM or OpenShift Virtualization. Either would require a
  disruptive rebuild before the development environment exists and would make
  the lab less useful for mixed workloads.
- Install workloads directly on PVE. This couples applications to the appliance
  operating system and makes upgrades and recovery harder.

## Consequences

- The host remains useful for multiple independent environments.
- Proxmox and OpenTofu remain non-Red-Hat infrastructure components.
- OpenShift on Proxmox is a lab topology and may not be a Red Hat-supported
  production hypervisor configuration.
- Loss of the R720 affects every guest regardless of guest-level redundancy.
