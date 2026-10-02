## ADDED Requirements

### Requirement: Recoverable network changes
Network automation SHALL begin from current Brocade and UniFi inventories, encrypted off-host configuration backups, proven read-only access, and a tested management rescue path.

#### Scenario: Network cutover planned
- **WHEN** a bond, VLAN, routing, firewall, or switch change is proposed
- **THEN** the exact controller/switch configuration and recovery route are verified before application and management reachability is tested afterward

### Requirement: Layered network ownership
Supported UniFi resources SHALL be imported into a separate OpenTofu state before managed application, while Brocade configuration SHALL be managed through a firmware-tested AAP execution path.

#### Scenario: Existing UniFi object adopted
- **WHEN** an existing UniFi object is placed under code ownership
- **THEN** its identity is imported and a no-change plan is obtained before any desired-state update

### Requirement: Protected remote administration
PVE and iDRAC SHALL remain off the public internet, with remote administration provided through a tested private access path and explicit permitted/denied network checks.

#### Scenario: Remote access acceptance
- **WHEN** remote administration is enabled
- **THEN** access succeeds through the authorized path and is denied from an unauthorized network
