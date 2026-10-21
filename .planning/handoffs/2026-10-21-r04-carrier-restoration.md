---
status: open
---
# Retained closure continuation — VPN-safe address replan

## Objective and authority

Finish currently actionable retained work in the authoritative October 18 ledger,
read from main, without rewriting its historical snapshot or repeating accepted
disruptive tests. Complete acceptance and reviewed source delivery; retain explicit
coverage limits and operator-approved deferrals. No live network/configuration
write or disruptive test is authorized by preparation. Preserve the dirty primary
and native-recovery checkouts, private evidence and secrets.

## Current operator direction

The operator requested replanning the homelab to avoid the work VPN, then made
non-overlap absolute: no lab allocation may intersect work-VPN routed address
space, with no exceptions, route overrides, disconnection or VPN policy changes.
This covers IPv4/IPv6 and internal storage/pod/service pools, not just management.
The earlier workstation host-route proposal is withdrawn, retained as history only.

Proposed targets are `172.27.{10,20,30,40,50}.0/24`, with future pod/service
reservations `172.28.0.0/16` and `172.29.0.0/16`. All are outside the currently
observed work-VPN IPv4 routes and configured Podman pools. Full IPv4/IPv6 routes
and rules were captured; no new IPv6 allocation is proposed. Recheck before any
approval/application; a future overlapping route invalidates admission, never
authorizes an exception. No address selection or cutover has been approved.

Preserve household `192.168.0.0/24`, lab VPN client pools, VLAN IDs, names and
ownership. The operator has physical R720 access and a separate admin computer,
and questions whether current R720 management is still `192.168.0.x`. Latest
actual retained PVE sample (October 16) says `10.72.10.10` on USB `nic1` with
default gateway `10.72.10.1`. Today's timeouts do not resolve current assignment.
Verify device settings from console/trusted client before any change; leave any
confirmed `192.168` management interface alone. Do not infer live state from
targets, host-key aliases, failed probes or a source summary.

Planning artifacts: `openspec/changes/avoid-work-vpn-address-overlap/` contains
proposal/design/tasks and the `lab-addressing` spec. ADR 0020 is proposed, not
accepted; native ADR 0015's rationale/status is not rewritten. All implementation
tasks remain unchecked. Strict planning validation passes. Independent design
review `ses_e9f44eb34ffeC0zxIKUFh2zJRW` found no proposal blockers; its two wording
clarifications were applied. It approves user design review, not execution.

The proposed gateway-last cutover uses a verified new-subnet L2 path on the
separate admin computer and endpoint-specific physical recovery, not a duplicate
UniFi VLAN/gateway or another old `10.72` address. No work-VPN workstation
interface/route changes. PVE/iDRAC changes stay serialized; any management/egress
interruption needs explicit approval. Current device truth and tested physical
recovery remain gates, not assertions that hardware presence proves recovery.

## Delivered and verified

- R01 source is delivered through PR #33. R02 SMART technical acceptance and
  result delivery are complete through PRs #34/#35. No SMART starts, timers,
  cleanup or accepted persistence tests need repeating.
- R04 offline carrier correction is merged PR #36 at
  `883a7c157522fea69001056baf663726dbc27faa`; local main is updated. Its task
  worktree and local/remote branches were removed. Source/test hashes match the
  independently reviewed revision. No live qualification occurred.
- Original ledger bytes remain unchanged; newer evidence is append-only.
  Historical G1–G5, R05–R07/R10/R11, independent backup, boot/DIMM and Groups 8/9
  limits remain open or gated. Do not infer universal closure.

## Current worktree and private evidence

- Preparation worktree: `/home/mpeter/work/homelab-infra.worktrees/prep-r04-live-acceptance`,
  branch `prep/r04-live-acceptance`, based on `883a7c1`.
- Primary remains on dirty `feat/group-7-network-plan`; native recovery remains
  dirty at `/home/mpeter/work/homelab-infra.worktrees/feat-group-7-native-recovery`.
  Neither is owned for edits or cleanup.
- Private continuation base:
  `/home/mpeter/work/homelab-infra-audit-evidence/closure-continuation-2026-10-21/`.
  `r04-delivery-and-cleanup.json` records PR36 delivery. The immutable adoption,
  implementation and corrected-source replay receipts are linked by
  `docs/r04-carrier-restoration.md`.
- R04 preparation evidence is in `r04-live-preparation/`. Its command plan v2 hash is
  `b47db3a3ad93d153032ef4414c218ae26ff519ab7e7c6cee7000e53c197eb302`.
  It contains 17 forward commands, 17 normal inverse commands and exact emergency
  inverses for all 18 forward boundaries. Approval status is NOT EXECUTABLE.
- Current source binding: `53723cb056744b23ececa602e40b3c79b6eca1621ecae0cfb0388818662e3dc5`;
  preview: `ec1f21d495699de95bc8eab437dbb966256cbb6dca8af525cf0190c51f389dd9`.

## Fresh read-only preparation and real blockers

1. The pinned local Brocade image and isolated package check pass. An initial
   default-user mount permission failure occurred before audit captures; the
   rootless container user was corrected without changing trust/source policy.
2. Corrected-source Brocade audit observation in the pinned EE passed at
   22:26:31 UTC: exact running/startup baseline `01b4a646…`, initial state,
   six VLAN tables and strict primary-down guard. No configuration write. Its
   ten-minute admission lifetime is not extended by saving this handoff.
3. The PVE source-defined parent collector fails: unchanged SSH to required
   USB-management `10.72.10.10:22` times out. A diagnostic retaining the original
   SSH options confirms timeout; TCP to former LAN `192.168.0.188:22` also fails.
   Brocade SSH and NAS HTTPS TCP probes succeed. Do not diagnose a service,
   routing or firewall cause from this alone, substitute paths, or bypass checks.
4. Both dated native-backup ciphertext copies still match
   `3cdf42da0af330eccfe8c1b4f0595dc71a4ab2a0cfbfe7f2afabe2d2072ddbef`;
   current switch configuration matches their canonical baseline. Key recovery,
   remote readback and no-import/boot-test limits remain dated October 16.
5. PiKVM frozen invoker `--check` succeeds: fixed owner/descriptor verified,
   capture_admitted=false and restore_verified=false. No serial command was sent.
   Ten private artifact files were copied/hash-verified outside the worktree in
   `pikvm-owner-check-artifact/`. The task-owned local tmux session/socket were
   closed after its exit-0 completion; `rescue-check-transport-closed.json`
   records this. The source stage was removed; the remote diagnostic runtime is intentionally
   retained by the helper. Do not delete unknown remote/pending artifacts.
6. The original active `~/.cache/agent-scratch/m7-r8-live/` root is absent, not
   verified released. Archived raw pending snapshot and recovery receipts remain
   under native `inventory/local/m7-r8-authorized-now-2026-10-16/`, operation
   `e8a53069b33dc67f75a5e8002804eb4769eba01c6acb23e9fbe2ad2bf59cb4a8`.
   Do not create a new attempt merely because its active marker is missing.
   Disappearance cause and explicit custody disposition remain unresolved.

## Active work and next decisive action

Deliver the reviewed **proposed** address replan and the R04 preparation/hold
record as planning-only changes. Then obtain design approval and current PVE/iDRAC
address/interface evidence from the available physical console or authorized
separate admin client. Do not restart R8, invoke the old packet or apply route
exceptions. No migration implementation or live cutover is approved.

Private replan receipts: `address-replan-current-networks.json`,
`address-replan-work-vpn-overlap-gate.json` and
`address-replan-operator-boundaries.json`. The other-vendor description-only
consult `address-replan-other-vendor.txt` completed successfully; suggestions to
disconnect the VPN, prefer an access workaround or advertise a broad summary
route were rejected because they contradict the operator's strict constraint.
Its task-owned local tmux/socket were closed after the exit-0 result;
`address-replan-consult-closed.json` records the cleanup.

R04 still requires accepted successor topology/source bindings, explicit archived
pending disposition, fresh recoverable-backup and actual rescue evidence, both
live guest proofs, a reviewed exact window/recovery packet and operator approval.
The earlier observation has expired; never extend its admission lifetime or
reuse the spent October 16 override. R06 missing client/route rows, R07 chain/
lifecycle/external-vantage gaps and R11 identity-specific evidence remain retained.
Read-only inventories for them completed without additional closures; no external
403 error is treated as denial, and no TLS issuance proves credential rotation.
