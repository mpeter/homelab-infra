# 0004. Run AAP outside OpenShift

Date: 2026-09-19

## Status

Accepted

## Context

AAP will orchestrate Proxmox provisioning, RHEL configuration, iDRAC management,
and OpenShift bootstrap and recovery. Hosting the only AAP instance inside the
Single Node OpenShift cluster would remove that automation during a cluster
failure.

## Decision

Install supported containerized Ansible Automation Platform on a dedicated RHEL
VM. Use AAP workflows and execution environments as the primary automation
control plane. Manage AAP's own declarative configuration with the
`ansible.platform` collection.

## Alternatives rejected

- Install AAP through the OpenShift Operator. This is useful to learn later but
  creates a circular recovery dependency for the primary automation service.
- Run AWX. Employee subscriptions make supported AAP available, including
  Private Automation Hub and Event-Driven Ansible.
- Run playbooks only from the workstation. This lacks shared scheduling,
  credentials, RBAC, workflow approvals, and durable audit history.

## Consequences

- AAP consumes a dedicated RHEL VM and PostgreSQL-backed service footprint.
- OpenShift can be diagnosed or rebuilt while AAP remains available.
- The initial AAP installation still requires an external bootstrap procedure.
- AAP backup and restore become part of the platform recovery plan.
