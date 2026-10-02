## ADDED Requirements

### Requirement: Off-host encrypted recovery
Unique NAS and Fedora data, infrastructure state, recovery keys, and important configuration artifacts SHALL have encrypted copies and restoration procedures that do not depend on the R720 remaining available. No laptop disk, NAS pool, or keyring SHALL be the sole holder of material needed to decrypt or restore them.

#### Scenario: Unique data promotion
- **WHEN** unique data is to be placed on the NAS or Fedora becomes the primary workspace
- **THEN** the selected rsync.net or other independent destination is configured, the remote copy is verified at the destination, and a representative restore is performed from an independent recovery host using the remote copy and separately held credentials and keys

### Requirement: Layer-specific recovery tests
Recovery evidence SHALL include file, VM, configuration, and eventual bare-metal exercises appropriate to the layer rather than treating a successful backup job or local mirror as proof of recovery.

#### Scenario: Backup job reports success
- **WHEN** a scheduled backup completes
- **THEN** destination-side presence and freshness are checked and a separately scheduled restore exercise can demonstrate usable content

#### Scenario: Full-VM backup acceptance
- **WHEN** Fedora backup is prepared for unique data
- **THEN** a full VM archive is verified at the independent destination and restored under an isolated scratch ID with its NIC absent or down, and the test leaves no orphan VM or disk; the record distinguishes this on-host format test from host-loss recovery

#### Scenario: Bare-metal exercise planned
- **WHEN** boot redundancy and recovery media are ready for a bare-metal rehearsal
- **THEN** the exercise has a reviewed non-destructive target and isolation plan, explicit pass criteria for boot and pool import, and no overwrite of the live host's data devices

### Requirement: Operational detection and shutdown
The platform SHALL alert on storage, hardware, backup, capacity, certificate, and service failures and SHALL support an orderly guest-to-host shutdown during a tested UPS event.

#### Scenario: Recovery operations acceptance
- **WHEN** the platform is declared operational
- **THEN** alert delivery, stale-backup detection, capacity thresholds, and the orderly shutdown sequence have been exercised
