## ADDED Requirements

### Requirement: Independently bootstrapped platform services
IdM and containerized AAP SHALL run on dedicated RHEL guests outside OpenShift, with measured capacity, DNS, and recovery prerequisites satisfied before they become dependencies for other workloads.

#### Scenario: AAP bootstrap
- **WHEN** AAP is deployed
- **THEN** it can provision, configure, verify, and remove a disposable VM through an audited workflow without depending on OpenShift

### Requirement: GitOps-owned OpenShift
Single Node OpenShift SHALL be deployed only after entitlement, compatible release, required DNS, capacity, and recovery prerequisites are verified; in-cluster resources SHALL be reconciled through OpenShift GitOps.

#### Scenario: Cluster acceptance
- **WHEN** the OpenShift VM and cluster are declared operational
- **THEN** GitOps self-healing, upgrade and rebuild procedures, and the relevant backup/restore path have been exercised without an HA claim
