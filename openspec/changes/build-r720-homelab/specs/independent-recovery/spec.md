## ADDED Requirements

### Requirement: Executable backup implementation plan
The active change SHALL document a bounded, on-demand same-R720 backup implementation for the reproducible Fedora VM and encrypted PVE host-configuration bundle. The plan SHALL identify ownership, trusted endpoint prerequisites, a dedicated restricted target, capacity and key custody, encryption before transfer, preflight and failure behavior, verification of retained ciphertext, an isolated local restore procedure, and rollback. The plan SHALL distinguish reviewable design from a backup or restore that has actually run.

#### Scenario: Plan accepted under current constraints
- **WHEN** no second-site receiver exists and TrueNAS endpoint identity is not yet trusted
- **THEN** the plan can still be reviewed and completed with those prerequisites and stop conditions explicit, without creating a backup job, sending credentials, or claiming recovery evidence

### Requirement: Independent-recovery boundary
Unique NAS or Fedora data SHALL NOT be promoted to this R720 until the deferred second-site backup and independent-restore gate passes. A local mirror, NAS pool, or same-host copy SHALL NOT satisfy that gate.

#### Scenario: Unique data promotion is proposed
- **WHEN** unique NAS data or Fedora primary-workspace status is proposed before the deferred independent restore passes
- **THEN** the promotion is stopped; any same-host copy is reported only as local recovery evidence if it was actually created and restore-tested

### Requirement: Operational detection and shutdown
Implemented services SHALL alert on applicable storage, hardware, capacity, certificate, and service failures and SHALL support an orderly guest-to-host shutdown during a tested UPS event. Backup-failure and stale-copy detection SHALL be added when backup jobs and their destinations are implemented.

#### Scenario: Recovery operations acceptance
- **WHEN** an implemented service is declared operational
- **THEN** its applicable alert delivery, capacity thresholds, and orderly shutdown path have been exercised at the layer actually implemented; any implemented backup job also has tested failure and age detection
