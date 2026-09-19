# ADR 0006: Split network management between AAP and OpenTofu

- Status: Accepted
- Date: 2026-09-19

## Context

The lab depends on an existing Brocade switch and UniFi control plane. Both must
be recoverable and reviewable, but they expose different automation surfaces.
The Brocade platform is CLI-oriented and its historical Ansible ICX collection
is archived. UniFi exposes object APIs suited to declarative state, while its
provider ecosystem has multiple successors to an archived original provider.
An incorrect network change can also remove access to Proxmox and AAP.

## Decision

AAP manages Brocade discovery, configuration backups, reviewed CLI changes,
verification, and rollback. Brocade automation runs in a dedicated, pinned
execution environment after a compatibility test against the exact model and
firmware.

OpenTofu manages supported UniFi objects after a live compatibility test and an
import-first adoption. UniFi uses state, credentials, locks, and apply jobs
separate from Proxmox. AAP captures UniFi backups and orchestrates approval,
plan, apply, and post-change validation.

Raw backups remain encrypted and off-host. Git contains reviewed desired state
and normalized evidence without credentials or sensitive controller exports.

## Alternatives considered

### Manage both systems only through their GUIs

This preserves vendor workflows but provides no reviewable desired state,
repeatable rebuild, or reliable drift signal.

### Manage both systems entirely with Ansible

This fits the Brocade CLI but gives up OpenTofu's state and import model for
UniFi objects. It would require custom imperative reconciliation for resources
that already have suitable APIs.

### Manage the Brocade switch with OpenTofu

There is no suitable mature provider for the installed legacy switch. Wrapping
CLI commands as resources would create state without trustworthy lifecycle
semantics.

### Put UniFi and Proxmox in one OpenTofu state

One plan and credential boundary would be convenient, but a provider or review
failure could change both access and compute in the same operation.

## Consequences

- Network adoption starts with inventory, backup, and read-only access.
- The exact UniFi provider remains a recorded compatibility decision rather
  than an assumption in the scaffold.
- Brocade support may require a pinned legacy collection or a small maintained
  adapter with captured-output tests.
- Cross-layer changes are staged AAP workflows, not atomic transactions.
- Write automation depends on tested out-of-band rescue and rollback paths.
