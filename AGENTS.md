# Agent context

This repository is the source of truth for a single-host home lab built on a
Dell PowerEdge R720 running Proxmox VE. It describes physical inventory,
recovery, Proxmox resources, Red Hat guest systems, AAP automation, and
OpenShift configuration. It does not manage the user's workstation dotfiles.

The live environment contains valuable state and has only one compute host.
Inspect current state before changing it, show a plan before destructive or
disruptive operations, and preserve a tested recovery path. Physical slot names
and Linux device names are different namespaces; use serial numbers and
`/dev/disk/by-id` for storage changes because names such as `nvme0n1` can move
between boots.

Keep ownership clear:

- OpenTofu owns Proxmox resources.
- Ansible Automation Platform configures operating systems and orchestrates
  workflows.
- cloud-init or Ignition performs first-boot initialization.
- OpenShift GitOps owns resources inside OpenShift.
- Proxmox remains an appliance; do not install workload services on the host.

Never commit passwords, pull secrets, API tokens, private keys, kubeconfigs,
decrypted SOPS files, or OpenTofu state. Secret definitions may be versioned,
but secret values belong in SOPS-encrypted files, AAP credentials, or an
external secret store. Do not put infrastructure secrets into chezmoi.

Treat the inventory files as observed evidence with an `observed_at` date.
Refresh them after physical changes. Record long-lived decisions as an ADR and
supersede prior ADRs rather than rewriting their rationale.

Verification should match the layer changed: `tofu plan` before apply, Ansible
check mode where meaningful, API read-back after controller changes, OpenShift
reconciliation status for GitOps changes, and an actual restore or boot test for
recovery changes. A successful command is not proof that the intended runtime
state exists.
