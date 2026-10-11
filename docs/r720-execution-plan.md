# R720 execution plan after the October 11 audit

This plan narrows execution of the existing build objective; it does not change
OpenSpec acceptance or authorize resuming the paused infrastructure goal.

## Current acceptance gap: task 7.6

Establish the next concrete piece of trunk qualification. The immediate result
is an actual strict-SSH, no-console transport rehearsal of the existing frozen
R2 candidate. A passing rehearsal proves transport only, not forwarding,
restoration, persistence or completion of task 7.6.

Before that rehearsal, verify the existing successor seal and perform a focused
review of the corrected guest validator and dry-run call path. Reuse unchanged
transport evidence. Do not repeat unrelated suites or rebuild the packet merely
to obtain another progress artifact. Keep source stable during checks.

Run the existing rehearsal once and retain its actual result. It must not launch
the resident, access serial, run guest probes or change network configuration.
A failure permits a focused diagnosis and minimal repair. If that repair expands
into another service, protocol or validation framework, stop extending this
approach and compare an existing SSH/PiKVM/Ansible path or a bounded manual
procedure using the verified recovery path. Select the simplest adequate path;
seek an operator decision only for facts or tradeoffs that cannot be resolved.

After the transport checkpoint, write one explicit qualification plan with its
live acceptance and rollback boundaries. Resolve semantic admission: hash-correct
failed or old-source receipts must reject. New-source inverse/restoration evidence
must exist before persistence. Offline replay cannot substitute for these gates.
Do not add unrelated DNS, certificate or review work to this checkpoint.

## Delivery and reporting

Finish the selected acceptance slice, run its relevant validation, and commit
only independently useful verified repository changes. Push and use the normal
PR/standing-authorized merge process for those changes; partial delivery must
leave unmet OpenSpec tasks unchecked. Complete the whole milestone before
starting the next milestone. Preserve unrelated work and never stage `.planning/`,
private runtime packets, state or credentials.

Report acceptance gained, the remaining gap and the next decisive observation.
Preparation counts as intermediate work, not milestone acceptance. The local
handoff owns volatile continuation state; inventory owns dated live observations;
OpenSpec owns task completion. Maintain current state in place and link history.

## Other open boundaries

Tasks 7.2 and 7.7 retain their recorded restore, forwarding, certificate and
access acceptance gaps in `network/group-7-readiness.md`. Group 5 remains
planning-only; independent receiver backups, workload restores and unique-data
promotion stay deferred. Do not use same-host copies as recovery acceptance.
