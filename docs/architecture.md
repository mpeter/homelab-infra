# Architecture

## Purpose

The R720 is a primary development platform and a Red Hat learning environment.
It supports a durable Fedora workstation VM, RHEL infrastructure services,
Ansible Automation Platform, OpenShift, and disposable project environments.

## Layer ownership

| Layer | Owner | Responsibilities |
|---|---|---|
| Physical hardware | iDRAC and AAP OpenManage automation | Inventory, firmware, BIOS, diagnostics, power |
| Hypervisor | Proxmox VE | VM lifecycle, local storage attachment, bridges, backups |
| Resource provisioning | OpenTofu with the Proxmox provider | VMs, containers, disks, networks, tags, startup order |
| NAS storage | NAS VM with the SAS2308 HBA passed through | SATA pool, datasets, snapshots, disk health, SMB/NFS shares |
| UniFi control plane | OpenTofu with a compatibility-tested UniFi provider | Networks, WLANs, DHCP, DNS, firewall policy |
| Brocade switching | AAP with a pinned network execution environment | Inventory, configuration backup, port and VLAN changes, verification |
| First boot | cloud-init or Ignition | Identity, SSH trust, networking, guest agent bootstrap |
| Operating systems | AAP | RHEL/Fedora configuration, packages, policy, services |
| OpenShift cluster | OpenShift Operators and AAP bootstrap | Cluster installation and platform services |
| OpenShift resources | OpenShift GitOps / Argo CD | Declarative cluster and application resources |
| Secrets | SOPS/age and AAP credentials | Encrypted values and runtime credential delivery |

No layer should silently manage a resource owned by another. Emergency GUI
changes are reconciled into the appropriate source after service is restored.

The NAS VM boots from `fast-vm`. Its eight SATA SSDs and RAIDZ2 pool belong to
the guest, not to Proxmox. The host owns the HBA passthrough boundary; OpenTofu
owns the VM and PCI assignment; guest configuration owns shares and storage
services. The guest OS is TrueNAS Community Edition 25.10.7. Other VMs do not
boot from storage exported by this same-host NAS. See [ADR
0010](decisions/0010-run-the-bulk-nas-as-a-vm-with-hba-passthrough.md) for the
storage boundary and [ADR
0011](decisions/0011-use-truenas-community-edition-for-the-nas-guest.md) for
the guest OS.

## Red Hat lab profile

- Fedora is the interactive development environment.
- RHEL hosts IdM and AAP and supplies reusable guest templates.
- Podman, Buildah, Skopeo, Quadlet, Image Builder, and `bootc` are preferred
  where they serve the workload.
- AAP provides controller workflows, execution environments, Private Automation
  Hub, Event-Driven Ansible, credentials, scheduling, RBAC, and audit history.
- Single Node OpenShift provides product-faithful cluster administration without
  claiming high availability.
- OpenShift GitOps uses Argo CD. OpenShift Pipelines and Quay are added only when
  they serve a learning or delivery requirement.

## Control-plane placement

AAP runs as a containerized installation on a dedicated RHEL VM. It is outside
OpenShift so an OpenShift failure does not remove the automation used to inspect
or rebuild the cluster. The first AAP deployment is bootstrapped from the
administrator workstation; subsequent AAP configuration is managed through the
`ansible.platform` collection.

## Failure domains

All guests, pools, networking adapters, and local replicas remain in one R720.
Mirrors and RAIDZ protect against selected disk failures, not loss of the host,
controller, rack power, switch, or site. Backups and infrastructure state must
therefore have an independent destination.

The NAS is a local source of data, not an off-host backup. A local ZFS receiver
at another site is the operator-selected independent recovery design. The
receiver and site, transfer method, retention, key custody, and tested restore
remain implementation gates before unique data depends on it.

The Brocade switch, UniFi gateway/controller, and R720 remain individual failure
domains. A NIC bond protects against a port, optic, or cable failure but not
switch failure.

OpenTofu state for Proxmox and UniFi is separated so a provider failure or
incorrect plan cannot span compute and network control planes. AAP coordinates
multi-layer work through explicit workflow stages; it does not make the stages
one transaction.

## Explicit exclusions

- No Ceph or replicated Kubernetes storage on a single physical host.
- No production high-availability claim for Single Node OpenShift.
- No application workloads installed directly on Proxmox.
- No ZFS dedup, L2ARC, or SLOG without a measured workload and suitable
  power-loss-protected devices.
- No Proxmox boot or workload storage on internal SD or vFlash.
- No direct internet exposure of PVE or iDRAC.
