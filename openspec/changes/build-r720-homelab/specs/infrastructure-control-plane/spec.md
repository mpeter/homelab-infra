## ADDED Requirements

### Requirement: Independent recoverable state
Proxmox and UniFi OpenTofu resources SHALL use separate encrypted state and identities. Proxmox bootstrap SHALL follow ADR 0009's laptop-local locking with an independently recoverable second ciphertext copy and passphrase; any later remote backend SHALL preserve and test state during migration.

#### Scenario: R720 is unavailable
- **WHEN** the R720 and its guests are offline
- **THEN** the operator can recover state and keys from the independent second copy and produce a plan without relying on a hosted VM or the laptop's sole disk

### Requirement: Scoped declarative changes
Planned infrastructure changes SHALL use versioned ownership, narrowly scoped identities, reviewed plans, and live read-back; pre-existing objects SHALL be imported before management.

#### Scenario: Proxmox VM plan
- **WHEN** OpenTofu proposes a VM change
- **THEN** the plan is checked for permitted resource types and protected delete/replace actions, effective permissions are verified, and the resulting VM/storage state is read back after apply

#### Scenario: NAS PCI assignment exceeds routine token scope
- **WHEN** the selected provider needs privilege beyond the scoped VM identity to assign the HBA
- **THEN** a separately reviewed, versioned host step or a tested scoped mapping is used and the routine identity remains unable to administer host storage or mappings

### Requirement: Disposable lifecycle proof
The first important VM SHALL wait until a disposable VM has completed creation, boot, no-change planning, reviewed destroy, and orphan checks using the intended image, cloud-init, bridge, and storage workflow.

#### Scenario: Disposable VM test completes
- **WHEN** the disposable VM is created on `fast-vm`
- **THEN** it boots and is inspected, a subsequent plan is unchanged, and its reviewed removal leaves no orphan VM or disk
