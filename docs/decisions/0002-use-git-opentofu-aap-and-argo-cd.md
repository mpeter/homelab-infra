# 0002. Use Git, OpenTofu, AAP, and Argo CD with explicit ownership

Date: 2026-09-19

## Status

Accepted

## Context

The environment spans physical management, Proxmox resources, guest operating
systems, and OpenShift resources. A single tool would either manage some layers
poorly or rely on imperative scripts without useful state and reconciliation.

## Decision

Use a private Git repository as the desired-state and decision record. OpenTofu
owns Proxmox resources, AAP configures operating systems and orchestrates
cross-layer workflows, cloud-init or Ignition bootstraps guests, and OpenShift
GitOps/Argo CD owns resources inside OpenShift.

## Alternatives rejected

- Use Ansible for every layer. Ansible is effective for configuration but does
  not provide OpenTofu's resource graph and durable infrastructure state.
- Use OpenTofu for guest configuration. Provisioners would blur ownership and
  make routine configuration changes dependent on infrastructure state.
- Use GUI configuration as the primary interface. It lacks reviewable intent,
  repeatable rebuilds, and reliable drift reconciliation.
- Use Flux for Kubernetes. Flux is capable, but OpenShift GitOps provides the
  Red Hat-aligned Argo CD experience desired for this lab.

## Consequences

- Cross-layer changes require clear workflows and credentials for several APIs.
- Each resource has one declared owner, reducing tool conflict.
- OpenTofu state and encryption keys become recovery-critical assets.
- Operators can inspect and approve infrastructure plans before mutation.
