## ADDED Requirements

### Requirement: Verified host baseline
The R720 host SHALL retain a documented, independently accessible recovery path and SHALL pass live boot, pool, management, and hardware-health checks before planned disruptive changes.

#### Scenario: Planned host change preflight
- **WHEN** a planned host change could interrupt boot, storage, or management
- **THEN** current PVE, iDRAC, pool, boot-device, memory, SEL, and recovery evidence is recorded and the exact change and rollback are reviewed before application

### Requirement: Versioned host ownership
Planned Proxmox host configuration SHALL have a versioned check/apply path and live read-back; direct emergency changes SHALL be reconciled into source before the next planned change.

#### Scenario: Host configuration applied
- **WHEN** a reviewed host change is applied
- **THEN** the corresponding source revision, preflight result, and post-change live state are recorded and the check path reports no drift

### Requirement: Distinct storage and capacity gates
The host SHALL keep boot, important VM, scratch, and guest-owned NAS storage in their documented ownership boundaries and SHALL size VMs from observed, healthy capacity rather than the 256 GiB target.

#### Scenario: Capacity or storage expansion
- **WHEN** a new VM, DIMM population, boot device, or storage tier is introduced
- **THEN** current capacity and device identities are verified, the relevant diagnostic or failure test passes, and no unclassified disk is overwritten

### Requirement: Host pool capacity threshold monitoring
The host SHALL evaluate `rpool`, `fast-vm`, and `scratch` every five minutes, record severity transitions and recovery in the local system journal, warn at 80% capacity, and report critical at 90% capacity. Saved state SHALL represent each pool's last evaluated alert severity, not a capacity measurement. Repeated samples within one severity SHALL NOT create repeated transition records. This local policy does not imply notification delivery.

#### Scenario: Host pool crosses or recovers from a capacity threshold
- **WHEN** a pool crosses 80% or 90%, or falls below its current severity threshold
- **THEN** valid readings update per-pool alert severity; a failed pool query records and saves one critical `pool_unreadable` transition until recovery, while malformed output fails the run and leaves saved severity unchanged
