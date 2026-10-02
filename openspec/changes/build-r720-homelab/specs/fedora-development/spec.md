## ADDED Requirements

### Requirement: Reproducible first development VM
The Fedora development VM SHALL be defined in OpenTofu, boot from `fast-vm`, use first-boot configuration, and fit verified host capacity. The 256 GiB memory target SHALL NOT be a prerequisite for creating an empty VM.

#### Scenario: Initial deployment
- **WHEN** the control-plane and disposable-VM gates pass and current hardware health permits the allocation
- **THEN** a reviewed plan creates an initially reproducible Fedora VM whose CPU, memory, disk, network, and boot state match live read-back

#### Scenario: Hardware health blocks VM creation
- **WHEN** an uncorrectable memory error, rising correctable-error count, SEL memory event since the last DIMM change, or unattributed iDRAC Critical condition exists
- **THEN** Fedora creation stops until the condition is investigated and its disposition recorded

### Requirement: Primary-workspace promotion
Fedora SHALL NOT become the primary location for unique development data until an independent backup, destination verification, full isolated restore, delivered host and backup alerts, and a representative work trial pass. During migration and the trial, any unique work SHALL retain a current authoritative copy outside Fedora.

#### Scenario: Promotion review
- **WHEN** the operator considers Fedora the primary workspace
- **THEN** off-host backup and full-VM restore evidence and at least 14 days of normal repository, container-build, and remote-access work are available; scheduled backups succeeded, `fast-vm` stayed at least 20% free, no new OOM/ZFS/SMART/SEL memory errors occurred, CPU/drive temperatures stayed below iDRAC warning thresholds, and sustained swap or available host memory below 16 GiB was investigated
