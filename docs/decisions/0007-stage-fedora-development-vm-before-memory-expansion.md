# 0007. Stage the Fedora development VM before memory expansion

Date: 2026-09-30

## Status

Accepted

## Context

The R720 is intended to reach 256 GiB, but DIMM validation is incomplete.
The primary development VM is needed before the rest of the planned lab.
Waiting for full population couples a useful first workload to uncertain
physical maintenance; ignoring current capacity would risk host contention.

## Decision

Deploy the Fedora development VM as the first workload using only freshly
verified current capacity. Propose 32 GiB initially and revisit a 64 GiB
allocation after 256 GiB is installed and validated. Final sizing is subject
to measured host usage and storage capacity. Defer AAP, IdM, OpenShift, and
other substantial VMs. Preserve the existing host recovery, mirrored VM
storage, configuration-as-code, and off-host restore gates.

## Alternatives rejected

- Wait for 256 GiB before any VM. This preserves the original phase order but
  needlessly blocks the development environment on unfinished DIMM work.
- Deploy the full planned workload set against current memory. This assumes
  capacity that has not been validated and risks contention on a single host.

## Consequences

- The VM starts smaller and may need a planned resize after memory expansion.
- Current DIMM health, host headroom, and datastore capacity must be measured
  before the VM's resource plan is applied.
- The other lab services remain a separate capacity-planning decision.
