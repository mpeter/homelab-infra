# Tasks

Planning validation is not design approval or permission to implement/apply.
Every task below remains open. Do not change the work VPN or use the withdrawn
workstation route-exception proposal.

## 1. Approve allocation and establish current endpoint truth

- [ ] 1.1 Obtain operator approval of the proposed five `172.27` subnets, future `172.28` pod/`172.29` service reservations and preserved household/lab-VPN scope; verify exact prefixes and the absolute prohibition on work-VPN overlap or changes.
- [ ] 1.2 Capture every IPv4/IPv6 routing table/rule, configured container network, home/lab VPN pool and declared remote network; verify every proposed lab pool is disjoint from work-VPN routed space, reject work-VPN catch-all selection and document unknown networks.
- [ ] 1.3 Observe PVE addresses, default route, USB interface and guest bridge/bond from local console or an authorized trusted client; verify the endpoint ledger distinguishes current management from `.188`/`.190` aliases and preserves confirmed `192.168` interfaces.
- [ ] 1.4 Observe iDRAC NIC/IP/gateway and current UniFi network/DNS/firewall/VPN objects; verify endpoint MAC/interface/port bindings and record deployed versus reserved entries without inferring clients from target plans.
- [ ] 1.5 Test the available physical console and separate admin source against their permitted paths; verify each proposed endpoint/gateway step has independently usable recovery, current recoverable backup references and no circular PVE/iDRAC dependency.

## 2. Prepare reviewed successor configuration and recovery

- [ ] 2.1 Map affected owned source and consumers without altering history; verify a source-bound inventory covers UniFi, PVE USB/backup, iDRAC transport, DNS, lab VPN destinations, monitors and R8 assertions while excluding unchanged household interfaces.
- [ ] 2.2 Import/reconcile existing UniFi object identities and prepare exact successor subnet/policy/DNS deltas; verify the baseline no-change plan and negative plan tests reject unexpected replacement, destruction and widened access.
- [ ] 2.3 Verify the separate admin computer's authorized new-subnet L2 access on a specific existing VLAN 10 port, endpoint-specific physical recovery and the installed controller's gateway transaction; review the serialized iDRAC/PVE/gateway-last packet, permitted interruption and combined rollback without duplicate networks, extra old-subnet allocations or untested dual gateways.
- [ ] 2.4 Prepare baseline-correct PVE management-only check/apply/rollback and iDRAC address procedures; verify offline tests preserve USB/default-route ownership, guest bridge/bond/VM state and observed old addresses rather than the obsolete `.190` rollback.
- [ ] 2.5 Prepare changed consumer destinations, tests and source bindings; verify stable names and valid DNS-name certificates are preserved, successor positive/negative checks pass and historical receipts remain byte-identical.
- [ ] 2.6 Obtain independent review of each changed layer and the exact maintenance packet; verify approval names endpoints, command order, rollback authority, permitted interruption, client controls and start/end timezone before any write.

## 3. Execute approved management stages only

- [ ] 3.1 Refresh all live admission and backup/rescue gates immediately before the approved window; verify unchanged work VPN, clear concurrent-change ownership and explicitly dispositioned historical pending custody, then stop on any unmet gate.
- [ ] 3.2 For an iDRAC interface confirmed on the conflicting subnet, execute its approved endpoint-only move first while physical PVE recovery remains available; verify new-subnet L2 access, identity and usable virtual console before continuing, or perform only its approved rollback.
- [ ] 3.3 For PVE USB management confirmed on the conflicting subnet, execute its approved move second with tested physical recovery and iDRAC virtual console available; verify new-subnet L2 access, exact USB/default-route configuration and unchanged bridge/bond/VM state before proceeding.
- [ ] 3.4 Execute the approved existing UniFi gateway/subnet transition last, then publish DNS after routed address reachability; verify ordinary named-client TLS and intended source access, or stop and restore the affected gateway/endpoint/DNS/policy combination.
- [ ] 3.5 Retire old live policy/address/DNS references only after all dependent consumers pass; verify no unapproved access, stale consumer destination or IPv6 management bypass remains and retain dated rollback/evidence records.

## 4. Reconcile other targets without activating deferred services

- [ ] 4.1 Update undeployed VLAN 20/30/40 and future service allocations; verify desired-state plans introduce no unapproved workloads or client migrations and documentation labels reservations as planned.
- [ ] 4.2 If active development/service endpoints are confirmed, prepare and obtain separate approval for their serialized migration; verify source-specific service/egress and denied-management controls for each changed network.
- [ ] 4.3 If an active VLAN 50 storage path is confirmed, prepare and obtain its separate window; verify its endpoint/service baseline, exact recovery and unchanged static L2-only/no-gateway/no-DHCP contract before any implementation.

## 5. Integration acceptance and reviewed delivery

- [ ] 5.1 Verify new management selects the home path with the work VPN connected and unchanged, without route/hosts-file overrides; retain normal DNS, permitted/denied client controls, intended lab-VPN access and required service receipts.
- [ ] 5.2 Prove successor desired/live no-change reconciliation and reassess R04/source-bound guest assertions against the resulting baseline; verify no old receipt is repinned or reused as changed-address qualification and no redundant persistence/restore/reboot test is performed.
- [ ] 5.3 Append current acceptance and remaining limits to the closure ledger, independently review accepted source/docs, merge scoped PRs, update local main and safely remove only task-owned worktrees; verify historical ledger prefixes, private custody and unrelated checkout changes remain preserved.

## Workflow follow-up

- Mark ADR 0015's address selection superseded only after the successor decision is approved; retain its original rationale and do not silently supersede segmentation or management ownership.
- Archive this change only after its approved scope is independently accepted; proposal creation or a valid planning schema does not close Group 7 or deferred Groups 8/9.
