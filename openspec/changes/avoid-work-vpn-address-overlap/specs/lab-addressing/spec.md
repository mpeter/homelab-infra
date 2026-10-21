# Lab addressing

## Purpose

Allocate homelab networks that coexist with the operator's work VPN and change
deployed addresses without losing management recovery or weakening isolation.

## ADDED Requirements

### Requirement: Non-overlapping lab allocations
Every lab IPv4/IPv6 allocation, including storage and cluster pools, SHALL be
disjoint from work-VPN routed address space. Allocation checks SHALL include all
routing tables/rules, configured container networks, home/lab VPN pools and
declared remote networks, and SHALL be repeated before cutover. No exception is allowed.

#### Scenario: Work VPN captures a broader prefix
- **WHEN** the work VPN advertises `10.0.0.0/8`
- **THEN** a proposed `10.72.10.0/24` lab network is rejected as overlapping
- **AND** the work VPN is not modified to make the lab reachable

#### Scenario: A candidate passes a dated snapshot
- **WHEN** the proposed `172.27` lab subnets do not overlap the captured networks
- **THEN** the plan records that evidence and its date
- **AND** does not claim compatibility with unknown or future VPN routes

#### Scenario: A work-VPN catch-all route captures a candidate
- **WHEN** a work-VPN default or policy route would select the tunnel for the candidate
- **THEN** coexistence admission fails rather than silently excluding that route

#### Scenario: A future cluster default conflicts
- **WHEN** a future lab cluster proposes a pod or service pool inside work-VPN address space
- **THEN** that pool is rejected even if it is not exposed outside the cluster

### Requirement: Work VPN preservation
Lab changes SHALL leave the work VPN's connection, configuration, routes, DNS
and security policy unchanged. Workstation route exceptions and VPN disconnection
SHALL NOT be used to satisfy lab acceptance.

#### Scenario: Lab management follows the work tunnel
- **WHEN** a management destination is routed into the work VPN
- **THEN** the migration addresses the lab's allocation and deployment
- **AND** does not add a more-specific workstation route to override the VPN

### Requirement: Observed endpoint scope
Before renumbering, the migration SHALL distinguish current observed addresses,
historical aliases and undeployed reservations. Existing household LAN and
confirmed `192.168.0.x` management interfaces SHALL remain unchanged unless a
separate endpoint migration is explicitly approved.

#### Scenario: Operator identifies an existing household management address
- **WHEN** the device's actual current management address has not been confirmed
- **THEN** no address change is authorized from a plan, alias or timeout alone
- **AND** a trusted client, controller or local console establishes the baseline

#### Scenario: A target network has no deployed endpoint
- **WHEN** an allocation exists only as a future target
- **THEN** its desired prefix changes without deploying the deferred workload

### Requirement: Segmentation preservation
The migration SHALL retain the management, development, lab and services isolation
boundaries and existing configuration owners. Storage VLAN 50 SHALL remain static,
L2-only and without a gateway, DHCP or routed access.

#### Scenario: Storage prefix changes in the plan
- **WHEN** VLAN 50 receives a successor subnet
- **THEN** no default gateway, DHCP service or inter-VLAN route is introduced

### Requirement: Recoverable management cutover
Each deployed management-address change SHALL have current recoverable backups,
a tested recovery path that survives that specific change, a bounded interruption
and exact rollback of endpoint, gateway, DNS and policy state. PVE and iDRAC SHALL
NOT change concurrently or rely solely on each other for recovery.

#### Scenario: Only Brocade serial has been tested
- **WHEN** the available PiKVM controls Brocade serial rather than the R720 console
- **THEN** it is not accepted as proof of PVE or iDRAC recovery access

#### Scenario: Existing rollback targets a superseded address
- **WHEN** a procedure restores an address that differs from the observed baseline
- **THEN** the procedure is rejected until a reviewed baseline-correct rollback exists

### Requirement: Stable names and verified administration
Stable management DNS names SHALL be retained. After an approved endpoint move,
normal DNS and the intended approved client's certificate verification SHALL
succeed without hosts-file overrides, added trust roots or disabled verification.
An IP-only change SHALL NOT require replacing an otherwise valid DNS-name certificate.

#### Scenario: A management address changes
- **WHEN** a named endpoint has passed reachability at its new address
- **THEN** its DNS record is updated and named-client identity is verified
- **AND** existing certificate-chain limitations remain explicit

### Requirement: Standalone PVE management
PVE management SHALL retain its accepted standalone USB transport and sole intended
default gateway. Renumbering SHALL NOT move management onto the guest bond or
change guest bridge, active bond member or VM addressing as a side effect.

#### Scenario: PVE management is renumbered
- **WHEN** the approved management-only change completes
- **THEN** observed USB address and default gateway match the target
- **AND** guest bridge, bond state and unaffected VM configuration match their baselines

### Requirement: Source-bound successor evidence
Changed consumers and address assertions SHALL be reviewed and verified against
the successor configuration. Historical snapshots, accepted receipts and prior
source bindings SHALL remain immutable; acceptance SHALL distinguish unchanged
dated evidence from new tests required by changed addresses.

#### Scenario: R8 guest-proof destinations change
- **WHEN** a successor proof uses new management addresses or source bytes
- **THEN** it receives newly reviewed bindings and changed-layer verification
- **AND** prior R8 evidence is neither repinned nor claimed to qualify the successor

### Requirement: Separate cutover approval
A valid proposal SHALL NOT authorize network writes. Execution SHALL require an
approved address map and a separately reviewed per-stage packet naming current
state, exact changes, recovery, test clients, maintenance window and stop conditions.

#### Scenario: Planning validation passes
- **WHEN** proposal, design, specifications and tasks pass planning validation
- **THEN** no route, gateway, endpoint or policy change occurs without the separate approval
