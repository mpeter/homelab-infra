# 0005. Build a Red Hat workload lab

Date: 2026-09-19

## Status

Accepted

## Context

The lab should support daily development and provide hands-on experience with
Red Hat technologies available through employee subscriptions. Replacing the
working hypervisor is not required to obtain that experience.

## Decision

Use Fedora for the development workstation, RHEL for infrastructure guests, AAP
for automation, IdM for identity, Podman ecosystem tooling for containers, and
Single Node OpenShift for Kubernetes platform learning. Prefer supported Red Hat
content where the subscription applies, while retaining Proxmox and OpenTofu at
the infrastructure layer.

## Alternatives rejected

- Build a generic Kubernetes lab with k3s. It is lighter but omits the product
  behaviors, Operators, Routes, SCCs, RHCOS, and lifecycle being studied.
- Force every component to be a Red Hat product. This would replace working
  infrastructure without improving the targeted workload-layer learning.
- Run a multi-node OpenShift control plane as several VMs on this R720. It would
  consume more resources while remaining in one physical failure domain.

## Consequences

- The lab reflects Red Hat operational patterns without claiming production HA.
- Subscription entitlements and pull secrets must be handled as recoverable
  secrets outside Git.
- Product components consume more memory than minimal community substitutes.
- OpenShift and AAP version compatibility becomes part of upgrade planning.
