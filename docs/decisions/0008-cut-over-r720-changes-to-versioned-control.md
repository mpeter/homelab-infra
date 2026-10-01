# 0008. Cut over R720 changes to versioned control

Date: 2026-10-01

## Status

Accepted

## Context

Recovery work and the first `fast-vm` pool were performed directly on the only
Proxmox host. The first VM has not been created. Continuing with ad hoc host and
VM changes would make the repository an incomplete account of a machine that
must be rebuildable after a single-host failure. OpenTofu state and the future
AAP controller cannot be the only means of repairing the host they depend on.

## Decision

Effective 2026-10-01, planned R720 changes begin in versioned desired state and
pass the relevant read-only preflight before application. Host foundation
(boot, pools, storage registration, package repositories, and host networking)
uses workstation-runnable, versioned maintenance code with live assertions.
OpenTofu owns VM and container resources, their disks, and supported Proxmox
resource objects once its off-host state and scoped identity are verified.
Guest configuration remains with cloud-init and AAP. AAP may orchestrate the
host maintenance code later but must not be required to recover the host.

The existing `fast-vm` mirror is adopted by recording its desired serials and
properties and passing a live drift check. It is not destroyed and recreated
merely to claim code ownership. Direct live writes are reserved for an urgent
loss-of-service or data-protection response; before the next planned change,
record the exception, capture the resulting state, and reconcile the versioned
source or restore the intended state. The operational contract is in
[R720 change control](../r720-change-control.md).

## Alternatives rejected

- Put the ZFS pools and host storage entries in the same OpenTofu state as VMs.
  A pool replacement could destroy data beneath every VM, and importing the
  existing pool would not itself prove its physical topology or recoverability.
- Destroy and recreate `fast-vm` from new code. Its current mirror has already
  been verified by serial and read-back; recreation would add destructive risk
  without improving the future change boundary.
- Defer the cutoff until AAP exists. AAP will run on this R720, leaving the
  host and first VM unmanaged during the most consequential bootstrap period.
- Rely on documentation alone. It records intent but neither detects drift nor
  prevents an unrelated resource type from appearing in a VM plan.

## Consequences

- Planned host changes require versioned application code and a live check;
  the first repository correction will use this path.
- The first disposable VM is blocked until OpenTofu has encrypted, locked,
  off-host state; a scoped PVE identity; a reviewed plan; and an allow-list
  gate for managed resource types. The Fedora VM follows a successful
  disposable-VM lifecycle test.
- Physical repairs and emergency recovery remain possible without AAP or
  OpenTofu, but must be reconciled before routine work resumes.
- Inventory remains observed evidence, separate from the desired baseline.

## Related decisions

- [ADR 0002](0002-use-git-opentofu-aap-and-argo-cd.md) defines the tool owners;
  this decision sets their bootstrap boundary on the R720.
- [ADR 0007](0007-stage-fedora-development-vm-before-memory-expansion.md) stages
  the first VM while retaining its recovery and code-as-configuration gates.
