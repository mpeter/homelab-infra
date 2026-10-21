# Design

Status: **proposed addressing and migration design; no implementation or cutover approved**.

## Context

See [proposal](proposal.md) for the conflict. Current read-only route/rule and
configured Podman-network inspection found no intersection with `172.27.0.0/16`.
It also found no intersection with `172.28.0.0/16`, `172.29.0.0/16` or
`192.168.64.0/18`. The ordinary home default route is not a competing allocation;
a work-VPN default or policy catch-all selecting the tunnel would fail admission.
A subsequent complete IPv4/IPv6 table/rule inspection also found no intersection
between the proposed IPv4 prefixes and work-VPN address space. The observation
covers this workstation now, not every future VPN or remote-client LAN.

The retained October 16 actual PVE sample reports management `10.72.10.10/24`
and default gateway `10.72.10.1` on standalone USB interface `nic1`, while the
guest bridge uses the bond with active member `nic5`. The iDRAC record identifies
`10.72.10.11`. Those are dated observations, not current device read-backs.
Historical PVE `192.168.0.188`/`.190` aliases and current connection timeouts do
not resolve the operator's question about today's management addresses.

The operator can provide physical R720 access and a separate admin computer.
The current PiKVM controls Brocade serial, not the R720 console. Its Ethernet
bypasses Brocade but depends on UniFi. Neither its owner check nor the presence
of a second computer proves an independent recovery path for every endpoint.

Related accepted decisions remain in the preserved native-recovery checkout:
ADR 0014 names, ADR 0015 VLAN/address selection, ADR 0017 management DNS and
ADR 0018 standalone USB management. That checkout is not overwritten or silently
published by this proposal. Proposed ADR 0020 changes address selection only.

## Goals / Non-Goals

**Goals:**
- Allocate the lab outside the work VPN's observed routes without changing the VPN.
- Preserve household LAN service and already-working `192.168.0.x` interfaces.
- Separate deployed endpoint migration from unimplemented target corrections.
- Keep management recovery, default-deny policy and standalone USB ownership.

**Non-Goals:**
- Work VPN edits, route exceptions, hosts-file workarounds or new trust roots.
- A blanket move of household devices, NAS/Fedora LAN interfaces or VPN pools.
- New services, AAP/OpenShift activation, storage migration or independent backup.
- A zero-downtime promise, hardware redesign, redundant restore/reboot test or R8 run.

## Decisions

### 1. Propose five subnets under `172.27`, not a routed aggregate

| VLAN | Role | Proposed subnet | Gateway / reserved examples | Deployment scope |
| --- | --- | --- | --- | --- |
| 10 | Management | `172.27.10.0/24` | UDM `.1`; PVE `.10`; iDRAC `.11` | Renumber only confirmed deployed `10.72.10.x` interfaces |
| 20 | Development | `172.27.20.0/24` | UDM `.1` | Update desired targets; observe clients before claiming any live move |
| 30 | Disposable lab / future OpenShift | `172.27.30.0/24` | UDM `.1`; reserved `ocp01` `.10` | Do not deploy deferred workloads |
| 40 | Services | `172.27.40.0/24` | UDM `.1`; reserved IdM `.2`, AAP `.3`, files `.10` | Do not infer existing services from reservations |
| 50 | PVE–NAS storage | `172.27.50.0/24` | PVE `.10`, NAS `.11`; **no gateway** | Plan only unless an active path is confirmed and separately approved |

Routed-network stable infrastructure remains `.2–.99`, DHCP `.100–.199`, with
`.200–.254` reserved. VLAN 50 has no DHCP. Existing reservations for switch `.2`,
NAS administration `.12` or UPS `.20` on management remain future allocations,
not instructions to move their current household addresses during this change.

Keep household `192.168.0.0/24`, Teleport `192.168.1.0/24`, WireGuard
`192.168.4.0/24`, legacy VLAN 132 and existing working LAN endpoints unchanged.
Keep `*.lab.kcd.one` names. Do not announce the entire `/16` or widen firewall
rules to it; use the five exact subnet objects and named destination services.

Rationale: `172.27` passes the observed overlap check, retains VLAN-number
mnemonics and avoids the default OpenShift service range `172.30.0.0/16`.
The strict non-overlap rule also covers internal or unrouted pools. Propose
`172.28.0.0/16` for future cluster pods and `172.29.0.0/16` for services; both
passed the current overlap snapshot. Platform-specific sizing and successor
IPv6 pools remain gated until Group 8 is reopened, but conflicting `10/8`
defaults are not acceptable in the meantime. Nothing deploys a cluster or
advertises these pools now. Recheck all pools before their eventual use.

Alternatives: keep `10.72` with workstation exceptions (rejected by the operator's
VPN requirement); flatten onto VLAN 1 (loses isolation); use a checked portion
of `192.168` (valid fallback, but home/remote LAN and existing VPN pools need
careful exclusions). No RFC1918 block is universally collision-free.

### 2. Keep VLANs and ownership; make address changes narrowly

OpenTofu continues to own supported UniFi network, firewall and DNS objects in
its separate state. Import existing objects and prove baseline no-change before
editing; stop on unintended replacement/destruction. AAP/Ansible owns guest and
Brocade configuration; versioned `host/pve/` procedures own appliance network
maintenance. Do not install workload services on Proxmox.

Lab WireGuard/Teleport destination routes and rules may need successor lab
prefixes, but their client pools stay unchanged. These are homelab VPN consumers,
not permission to change the work VPN.

### 3. Do not assume parallel gateways or replay an old cutover

The proposed execution design is a bounded, explicitly approved transition using
the separate admin computer on an identified access port in the existing VLAN 10,
with a free, explicitly reserved address in the **new** subnet and no additional
default gateway. Local L2 access to each newly addressed endpoint permits moving
the existing UDM subnet/gateway last, without claiming two UniFi networks can share
a VLAN or that two routed gateways coexist. Physical recovery remains available.

Before scheduling, verify the specific port, admin source policy, controller update
and rollback, new-subnet L2 path and physical console. Do not assign another old
`10.72` address as a workaround. If this arrangement cannot be established, stop
and revise the design; do not invent temporary VLANs or assume unsupported aliases.
The work-VPN workstation receives no address, route, DNS or policy changes.

Physical access is available, but its console path must be tested. Confirm PVE's
actual addresses from local console or a trusted authorized admin client. A
second computer's source policy must also be verified; its presence alone does
not make it an allowed administrator. No `192.168` management address is changed
merely because an older plan had a `10.72` target.

The existing USB procedure's rollback to `192.168.0.190` is not a valid rollback
for a confirmed `10.72.10.10` baseline. Prepare a successor procedure from the
observed current state before implementation. Never replace the USB path with
the guest bond to work around the transition.

## Migration Plan

### Phase 0 — approve design and establish the actual baseline

Approve or revise the proposed subnet map. Capture complete current relevant
UniFi networks, gateway/firewall/DNS/VPN destination objects and endpoint address,
interface, MAC/port, default route, service and consumer bindings. Label each item
observed, historical or planned. PVE console reads `ip -br -4 address` and
`ip -4 route` can resolve its current management assignment without changing it.
Compare iDRAC's actual dedicated-NIC settings separately.

Recheck candidate intersection against active/policy routes, configured container
networks, existing VPN pools and the separate admin client's LAN/VPN ranges.
Unknown remote networks remain explicit. Freeze tested recovery access, current
recoverable backups and exact rollback before writing a live packet.

### Phase 1 — prepare and review successor source only

Prepare changes for deployed `10.72` consumers and planned target declarations;
do not globally replace historical addresses. Affected source includes UniFi
network/firewall/DNS/VPN definitions, PVE USB management and backup collectors,
iDRAC certificate transport destinations, monitors, and R8 guest-proof addresses,
tests, source manifests and pins. Preserve valid DNS-name certificates; review
IP SANs and destination pins rather than issuing replacements automatically.

Use exact imported UniFi resource identities and plan checks; do not rebuild
resources as a shortcut. Review offline positive/negative tests, successor source
bindings and the exact maintenance packet. Keep historical raw receipts and
the October 18 ledger snapshot unchanged.

### Phase 2 — management cutover, only for confirmed conflicting endpoints

Before scheduling, identify the supported gateway transaction, independent recovery
for **each** endpoint, command order and rollback authority. For confirmed `10.72`
management endpoints, the recommended sequence is:

1. Test local PVE console recovery and iDRAC-specific physical recovery/settings
   access without changing either address. Prepare the authorized second admin
   computer's new-subnet L2 path on the existing VLAN; verify port and source policy.
2. Change iDRAC alone through its reviewed method, retaining PVE console recovery.
   Verify the new address, intended identity and usable virtual console from the
   separate admin computer before proceeding. Do not assume PVE can repair iDRAC.
3. Change PVE USB management alone with the tested physical console available;
   verify its new address, exact interface/default-route configuration and unchanged
   guest bridge/bond/VM state from the separate admin computer.
4. Change the existing UniFi VLAN 10 subnet/gateway to its successor, then verify
   routed management and publish DNS. There is no new lab default route on the
   work-VPN workstation.

Moving an endpoint before the gateway creates a bounded period without its normal
off-VLAN management/egress. The operator must explicitly approve that interruption;
physical access is recovery, not a zero-downtime guarantee. If today's management
is confirmed on `192.168`, leave it unchanged and omit that endpoint from this
sequence rather than moving it to satisfy a historical target.

Prepare exact old/new permitted paths without broadening access. A changed
gateway can cut off still-old endpoints even when those endpoints have not yet
changed; account for that in every step's rollback. A host timer cannot undo
UniFi changes. If a safe serialized gateway transaction cannot be demonstrated,
the cutover is blocked until the design is revised and approved.

Move only the approved endpoint/interface and verify its new-subnet L2 access
and identity during staging. Such direct staged checks do not satisfy final
ordinary-DNS acceptance. After the gateway transaction, publish DNS and verify
normal named TLS and routed source-specific access. Check USB/default-route
ownership, VM/bridge/bond invariants and management access before the next step.
Remove old policy/address/DNS references only after their consumers pass.
Any uncertainty retains custody and stops further changes.

### Phase 3 — other networks and post-change acceptance

Renumber confirmed deployed development/services consumers one network at a time.
For undeployed targets, update desired state without creating workloads. Any
active VLAN 50 storage-path change gets a separate scoped window; preserve its
no-routing/no-gateway contract.

With the work VPN still connected and unchanged, prove successor management uses
the home path without route exceptions. Verify ordinary DNS, approved-client TLS,
allowed/denied source pairs with positive controls, intended lab VPN access,
required guest/service paths and IPv6 exposure policy. Retire only observed stale
references; prove desired/live no-change reconciliation.

Reassess R04 against the resulting switch/guest configuration and source identities.
Retain the prior offline correction and accepted persistence evidence, but do not
claim the old preflight qualifies changed destinations. No R8 writer is invoked
by this proposal, and the unexplained missing active pending root remains an
explicit custody decision rather than permission to retry.

## Risks / Trade-offs

- A future work VPN advertises a broader private prefix → fail compatibility
  admission and replan the lab allocation. Never override the VPN or accept an
  overlapping exception; do not advertise the entire `172.16.0.0/12`.
- Management addresses differ from old records → stop until current device evidence
  resolves them; leave confirmed household interfaces untouched.
- Gateway cutover strands an endpoint → require a tested recovery path and combined
  gateway/endpoint/DNS/policy rollback, not merely remote shell access.
- NAS traffic or guest bridge changes accidentally → exclude unaffected LAN/service
  interfaces and compare live invariants after each approved management step.
- Hard-coded destinations or source pins go stale → inventory consumer references,
  verify successor tests and rebind current source without editing history.
- Proposed planning artifacts look executable → require separate design approval,
  implementation review and an exact operator-approved maintenance packet.
