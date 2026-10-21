# Proposal

## Why

The active work VPN routes `10.0.0.0/8`, which contains the homelab's accepted
`10.72.<VLAN>.0/24` targets. Traffic toward the recorded PVE/iDRAC `10.72`
destinations follows the VPN; their actual current management addresses still
require device verification. The operator requires the work VPN to
remain undisturbed and has requested a homelab replan.

## What Changes

- **BREAKING:** propose `172.27.{10,20,30,40,50}.0/24` as successor lab prefixes,
  subject to design approval and a fresh overlap check before application.
  Current routes, routing rules and configured Podman networks do not overlap
  the proposed block; this is not a guarantee about inactive or future VPNs.
- Apply the non-overlap rule to every lab allocation, including unrouted storage
  and future cluster pod/service networks. Reserve checked `172.28.0.0/16` and
  `172.29.0.0/16` as proposed future cluster pools rather than accepting defaults
  inside the work VPN; this does not authorize cluster deployment.
- Preserve VLAN IDs, segmentation, the household LAN, existing lab VPN address
  pools, stable DNS names and separate UniFi/Brocade/OS ownership.
- Replace the prior address selection, not the historical evidence. Record a
  proposed ADR and a staged migration with exact per-stage recovery gates.
- Withdraw the prepared workstation route-exception approach. Do not change work
  VPN configuration, routing policy, client trust, or unrelated container networks.
- Separate deployed management endpoints from undeployed targets. Do not create
  deferred services or run R8 qualification as part of planning.

## Capabilities

### New Capabilities

- `lab-addressing`: non-overlapping lab prefix allocation and recoverable address
  transitions while the work VPN remains connected and unchanged.

### Modified Capabilities

None in published `openspec/specs/` (currently empty). This proposal supplements
the active `build-r720-homelab` change's `managed-network` requirements; it does
not replace its ownership, rescue or access-control requirements or mark its
tasks complete.

## Impact

UniFi network definitions, exact firewall destinations and DNS records; PVE's
standalone USB management address/default route; iDRAC and other deployed
endpoint addresses; lab VPN destination routes and policies; supported monitors
and certificate deployment destinations; R8 guest-proof addresses, fixtures and
source bindings. VLAN 50 remains static and unrouted.

Only planning artifacts are authorized now. Implementation, network changes,
management interruption and maintenance execution require a separately reviewed
packet and explicit approval. Independent backup, boot/DIMM and Groups 8/9
deferrals remain intact.
