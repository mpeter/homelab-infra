# ADR 0020: Propose VPN-compatible lab addressing

Date: 2026-10-21

## Status

Proposed. The operator requested replanning, not implementation. This proposes
superseding ADR 0015's `10.72` address selection only after the successor is
approved; it does not supersede VLAN segmentation, stable naming or ownership.
ADR 0015 is preserved in the native-recovery checkout and is not rewritten here.

## Context

The active work VPN installs `10.0.0.0/8`, which captures the lab's `10.72` routes.
The operator requires the VPN to remain undisturbed. The original overlap check
did not establish compatibility with this active VPN route.

Current read-only collection covers all workstation IPv4 routing tables/rules,
interface addresses and configured Podman networks. `172.27.0.0/16` does not
intersect that observed set. This is a dated result, not a claim about inactive,
remote or future networks. The operator can provide physical R720 access and a
separate admin computer, but current endpoint addresses and recovery paths still
require verification before any cutover.

## Proposed decision

Use only `172.27.{10,20,30,40,50}.0/24` for the corresponding lab VLAN targets.
Retain routed `.1` UDM gateways and VLAN 50's static, unrouted/no-gateway contract.
Keep the household LAN, current `192.168.0.x` management interfaces, lab VPN client
pools and stable DNS names unchanged unless separately approved.

Apply the absolute non-overlap rule to every lab pool, including unrouted storage
and future cluster pod/service networks. Propose `172.28.0.0/16` and
`172.29.0.0/16` as checked future pod/service reservations instead of conflicting
defaults; deployment and platform-specific sizing remain deferred.

Do not change or disconnect the work VPN, add workstation route exceptions or
renumber unrelated container networks. Recheck actual prefix intersection before
application and when VPN/site requirements change. Reserve rather than deploy
future lab/service endpoints.

The [OpenSpec design](../../openspec/changes/avoid-work-vpn-address-overlap/design.md)
owns the proposed map, source inventory, staged migration and recovery gates.
There is no authorization to execute it merely because the proposal validates.

## Alternatives considered

- Keep `10.72` and override the VPN for selected hosts: rejected; this changes
  work-route selection and is contrary to the operator's constraint.
- Put every lab endpoint on `192.168.0.0/24`: rejected; it abandons segmentation
  and needlessly changes a working household network.
- Use a checked portion of `192.168.0.0/16`: viable fallback, but existing home,
  Teleport, WireGuard and common remote-client LANs require explicit exclusions.
- Use another checked `172.16/12` subset: viable, but offers no demonstrated
  advantage over `172.27`; never treat the whole `/12` as an available lab route.

## Consequences

- Normal lab routing can coexist with the currently observed work VPN without
  workstation exceptions; future route compatibility still requires admission.
- Confirmed deployed `10.72` endpoints require reviewed, bounded migration and
  baseline-correct rollback. Already-working household management is not moved
  just to match a target table.
- Consumer destinations, tests and current source bindings must follow approved
  moves. DNS-name certificates need not be replaced for an IP-only change.
- Historical inventory, the October 18 snapshot and old acceptance receipts stay
  immutable. Replanning is not runtime acceptance, credential remediation or
  completion of R04/R06/R07 or deferred platform work.
