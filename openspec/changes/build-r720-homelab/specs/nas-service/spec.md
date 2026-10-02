## ADDED Requirements

### Requirement: Guest-owned HBA and boot independence
The NAS VM SHALL boot from `fast-vm`, receive the complete SAS2308 HBA, and own all eight intended SATA SSDs; Proxmox SHALL NOT import their pool or require NAS exports to boot other VMs.

#### Scenario: Passthrough validation
- **WHEN** the HBA is bound and the NAS VM starts or the host cold-boots
- **THEN** the guest sees the expected eight disk serials and SMART data, the host does not claim the HBA disks, and host boot and `fast-vm` remain healthy

#### Scenario: HBA binding drifts
- **WHEN** a reboot or kernel change leaves the HBA bound to the host instead of the NAS assignment
- **THEN** the host check fails closed, the guest pool is not imported by Proxmox, and pool work stops until binding is reconciled

### Requirement: Separate destructive pool gate
The eight-disk RAIDZ2 pool SHALL be created in the NAS guest only after current serial-specific data disposition before HBA binding, off-target header/signature captures before clearing, guest stable identifiers, a reviewed pool plan, and a tested HBA recovery path. Header captures SHALL NOT be treated as full data backups.

#### Scenario: Unclassified disk discovered
- **WHEN** a SATA disk has an unexpected signature, identity, or data disposition
- **THEN** no signature is cleared and no pool is created until that exact serial is classified and the preflight is repeated

#### Scenario: HBA preflight finds host dependency
- **WHEN** the HBA IOMMU group includes a host-required device or a target disk remains unclassified
- **THEN** HBA binding and NAS pool creation stop until the dependency or data disposition is resolved

### Requirement: Recoverable shares
NAS datasets and SMB/NFS shares SHALL have explicit access policy, monitoring, snapshots, and tested restart behavior; they SHALL contain only reproducible test data until off-site restoration passes.

#### Scenario: Share acceptance
- **WHEN** a share is put into service
- **THEN** an allowed client can use it, an unintended client is denied, and the pool and shares return after guest and host restarts
