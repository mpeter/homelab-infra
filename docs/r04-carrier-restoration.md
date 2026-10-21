# R04 carrier restoration — offline correction and live gates

Status: **offline correction reviewed and verified; no live retry authorized**.
The [October 18 ledger](closure-ledger-2026-10-18.md#r04--current-source-r8-and-rollback--retained-p1)
owns R04 acceptance. Source preparation does not establish live qualification.

## Observed defect and scope

The retained October 16 attempt changed primary carrier to Up. Its automatic
inverse applied the qualification-only primary-down guard and stopped before
the first inverse journal append, despite exact configuration and six-VLAN
membership checks passing. Attempt-specific recovery restored exact baseline
running/startup hash
`01b4a646e764f2874a2310b7e0efd1622f779f230d1d77a41a176b720a327eff`.
That is failed-and-restored evidence, not qualification or a physical diagnosis.

The existing private `r04-actual-replay.json` binds three failure captures,
36 restoration receipts and 91 input path/hash references. The original replay
and historical packets remain immutable. Corrected-source verification must
identify its own source revision and must not repin historical receipts.

## Restoration contract

- Initial, forward and held qualification remain primary Down/None only.
- Explicit restoration context applies at every normal and emergency inverse
  boundary, including the first inverse precheck and final read-backs.
- Restoration permits primary Down/None or Up/Forward with exact speed, duplex,
  tag and PVID requirements. Other active paths must remain forwarding.
- Up/Listen never authorizes a write. Only a fully validated Listen observation
  may trigger a fresh read: exact configuration/startup/state, complete interface
  table, all six VLAN tables, source, custody and budget checks must first pass.
- At most two extra full observations are allowed across the entire restoration
  attempt, not per command or session. No sleep, send retry, authorization-callback
  replay, deadline reset or reserve extension is permitted. Persistent Listen,
  any drift, or budget exhaustion stops further writes and retains custody.
- Existing phase deadlines bound each read. Count limits do not guarantee
  settling completion or imply a fixed per-read duration. The 600-second inverse,
  212-second guest-proof and 20-second cleanup reservations are not enlarged.
- Receipt admission distinguishes inverse/final evidence from the strict held
  boundary, even where they share a command position. A completed receipt must
  not accept Listen or replace either guest proof with middleware success.

## Source custody and baseline checks

The dedicated task worktree adopts the required import-time source/pin closure,
not the dirty recovery checkout wholesale: 61 hash-identical public files,
29,527 lines, including all 37 resident pins. The private adoption inventory
records each path and original hash. Baseline verification passed 252 principal
tests and five selected resident regressions before behavior changes.

Private evidence is retained outside Git at
`/home/mpeter/work/homelab-infra-audit-evidence/closure-continuation-2026-10-21/`:
`r04-source-adoption-inventory.json` and
`r04-source-adoption-verification.json`. Private captures and credentials must
not be added to the repository.

## Corrected-source verification — October 21

Only five adopted production files differ from the retained baseline: the cycle,
observer and receipt validator implement the correction; the runner and resident
update their dependent source pins. The strict qualification validator's AST is
unchanged. A separate 47-case regression module covers restoration boundaries,
Listen exhaustion across boundaries, drift, protected deadlines, retained custody
and rejected restart. Allowing a third extra read causes three regression failures.

- Original-behavior red run: four failures, including integrated Up/Forward and
  Up/Listen inverse rejection. No live failure injection was used.
- Corrected suites: 366 passes with the then-45-case regression module, followed
  by a complete 47-case regression pass after two additional cases. These counts
  overlap and must not be summed as distinct tests.
- Transport suites: 309 passes. Resident budget selection: five passes. The
  original five selected carrier-recovery resident regressions also pass against
  the corrected source.
- Independent Python review found no blockers; all five production files passed
  its type check. Focused lint/format checks passed. Cycle-wide lint still reports
  the unchanged, preexisting E731 lambda; no clean whole-tree lint claim is made.
- New corrected-source replay checks all three retained failure captures, all
  36 restoration receipts and both carrier transitions with exact configuration,
  state and six-VLAN invariants. It checks 521 unique retained input hashes.
  Strict qualification still rejects all three failed Up samples. Restoration
  accepts both Up/Forward samples; Up/Listen remains pending without a write.
  All 36 restoration receipts satisfy the restoration guard.

Source-bound private receipt SHA-256 values:

- `r04-restoration-implementation-verification.json`:
  `9347a8704d2a2b3dc7b5c20bd05c508c11b67b38a999ec894edc5c15a99a5eee`.
- `r04-corrected-source-replay.json`:
  `98a576e8a29bee4352f6b4dbd0c542246e1dea4c8cd129db8f52701cce89758a`.

Replay proves the parser/guard layer; integrated caller tests separately exercise
budgets, both guest-proof callbacks and receipt admission. Neither proves live
guest traffic on the corrected revision. Existing observation ordering, including
interface brief not being the final read in a multi-command observation, remains
unchanged. Preliminary replay-harness failures were corrected without production
edits and are recorded in the final private replay's limits. No live operation,
physical-cause diagnosis or R04 closure is claimed.

## Gates before any live proposal can be approved

1. Replay all retained failure captures and both carrier transitions through the
   corrected source, enforcing exact configuration and all six VLAN invariants.
   Independently review the corrected caller, receipt semantics, current source
   pin chain and offline regressions, including the integrated resident budget
   and held/post-inverse guest proofs. Record failures and limits explicitly.
2. Bind the proposed run to the reviewed source revision, exact command preview,
   execution environment and fresh read-only preflight. An old packet's source
   approval does not transfer to corrected code.
3. Preserve the original pending/runtime artifacts. Establish their ownership
   and approved disposition without deleting or silently adopting old custody.
4. Preserve current recoverable configuration backups and capture running/startup
   plus all six VLAN tables. Verify exact baseline and a tested out-of-band rescue
   path independent of the primary link before proposing any network write.
5. Present the operator with the exact bounded change/recovery commands, deadline,
   stop conditions, evidence destination, guest-proof requirements and independent
   final read-back. Obtain a separate live window and any primary-link exception.

No switch operation is authorized by this document. Do not repeat accepted
persistence, SMART acceptance or cleanup to validate this correction. Physical
carrier cause, wider Group 7 obligations, historical coverage limits, independent
backup, boot/DIMM and Groups 8/9 remain separate open or gated work.

## Live-plan preparation — October 21, 22:26–22:30 UTC

**Not executable or approved.** Source is merged PR #36,
`883a7c157522fea69001056baf663726dbc27faa`. The candidate preview is
`ec1f21d495699de95bc8eab437dbb966256cbb6dca8af525cf0190c51f389dd9`;
current cycle source binding is
`53723cb056744b23ececa602e40b3c79b6eca1621ecae0cfb0388818662e3dc5`.
Future source changes invalidate these identities and require review.

The generated command plan removes only port `1/2/2`'s native VLAN 1 and tagged
VLANs 40, 10, 20 and 30, then restores them. There are 17 forward and 17 normal
inverse CLI commands, including context entry/exit. A source-generated exact
inverse is recorded for each of 18 forward boundaries. No save, reload, link
shutdown, active-member move, UniFi change or accepted persistence test is included.

| Step | Forward commands | Normal inverse commands |
| --- | --- | --- |
| Enter configuration | `configure terminal` | `configure terminal` |
| Native membership | `interface ethernet 1/2/2`; `no dual-mode 1`; `exit` | After tagged restoration: `interface ethernet 1/2/2`; `dual-mode 1`; `exit` |
| Tagged membership | For VLANs **40, 10, 20, 30**: `vlan <id>`; `no tagged ethernet 1/2/2`; `exit` | For VLANs **10, 20, 30, 40**: `vlan <id>`; `tagged ethernet 1/2/2`; `exit` |
| Leave configuration | `exit` | `exit` |

Do not manually dispatch the table: only the reviewed resident supplies durable
custody, per-command admission, guest proofs and bounded recovery. Its writer
entrypoint is `network/config-backup-preflight/native-trunk-resident.py
--r8-full-trunk --pin <accepted-private-pin> --preflight-receipt
<fresh-private-schema-2-receipt>`, with optional `--pve-credential-fd`. These are
required private inputs, not values to guess. Switch root/audit credentials use
stdin; PVE credentials use the existing private keyring or descriptor, never argv
or logs. The resident runs on the workstation; the admission observation runs in
the pinned EE. The expected-image field alone does not attest to container execution.

### Observed readiness and blocking conditions

- The local Brocade image ID
  `7eb690b9bbac7dd602ad4eac7b1a537a1f3d8e54d6178e764b0e4df96813c2e2`
  is present. A network-disabled, read-only container probe reports Python 3.14.7,
  ansible-core 2.21.4, Paramiko 4.0.0 and cryptography 50.0.2. An image ID and an
  OCI repository digest are different identities.
- At 22:26:31 UTC, the actual corrected-source audit observer in that pinned EE
  passed exact running/startup baseline, initial state, all six VLAN tables and
  the strict primary-down guard. No configuration write occurred. This observation
  expires after ten minutes; it is not reusable admission for a later window.
- The existing native export and Drive-readback ciphertext files both still hash
  to `3cdf42da0af330eccfe8c1b4f0595dc71a4ab2a0cfbfe7f2afabe2d2072ddbef`.
  Fresh switch configuration matches their dated canonical baseline binding.
  Decryption/key recovery and remote readback remain October 16 evidence; no new
  import, reboot test, decryption or remote backup download is claimed.
- A fresh source-pinned PiKVM `--check` verifies the fixed serial owner/descriptor.
  It does **not** send a serial command or establish fresh `show version`, rescue
  control or restore acceptance. The latest serial command proof remains dated.
  PiKVM Ethernet was confirmed to bypass Brocade, but still depends on UniFi;
  no dead-UDM rescue is claimed.
- The actual PVE parent collector fails its unchanged bounded contract. A
  diagnostic with the same SSH options identifies connection timeout to
  `10.72.10.10:22`; independent TCP probes also time out at the former LAN
  address `192.168.0.188:22`. This does not diagnose host failure, filtering or
  routing. No trust bypass, route change or service enablement was attempted.
- Subsequent read-only workstation route lookup selects `tun0` for both
  `10.72.10.10` and `10.72.10.11`, not the home-LAN interface. A lookup constrained
  to the existing home interface selects gateway `192.168.0.1`, source
  `192.168.0.183`. This is a concrete route-selection conflict to investigate,
  not proof of a failed PVE/iDRAC service. The ordinary iDRAC CA/name check also
  times out before TLS, so no fresh chain result is available.
- The original active root
  `/home/mpeter/.cache/agent-scratch/m7-r8-live/` is now absent. The retained
  operation snapshot and failed/restoration evidence remain in native private
  custody. **Absence is not a verified pending-slot release or permission to
  create a new attempt.** Its disappearance has not been attributed. Preserve
  the snapshot for operation
  `e8a53069b33dc67f75a5e8002804eb4769eba01c6acb23e9fbe2ad2bf59cb4a8`;
  obtain an explicit reviewed custody disposition before another attempt.

Private preparation evidence is under the continuation evidence base above in
`r04-live-preparation/`. `candidate-command-plan-v2.json`, SHA-256
`b47db3a3ad93d153032ef4414c218ae26ff519ab7e7c6cee7000e53c197eb302`,
contains all commands, emergency boundaries, source bindings and stop conditions.
Readiness receipts retain the failed PVE path, actual switch observation, dated
backup hashes, and hash-verified private PiKVM check artifacts.

### Required resource and operator decisions

1. Establish working PVE SSH on the existing USB-management route so the unchanged
   paired host/VM collector can pass; do not substitute a different path or fake
   its active-member/default-route result. The earlier prepared client-side
   proposal would add two temporary `/32` routes, for `10.72.10.10` and
   `10.72.10.11`, via `192.168.0.1`, device `enp34s0u2u1u2`, source
   `192.168.0.183`, protocol `static`, metric `42721`. Exact route preimages are
   empty. Apply and exact reverse-order deletion argv are retained privately in
   `proposed-workstation-host-routes.json`. **This approach is withdrawn:** the
   operator requires the work VPN to remain undisturbed and requested a homelab
   address replan instead. Preserve the file only as historical preparation;
   do not apply it, disconnect/edit the VPN or weaken host trust.
2. Resolve the absent active marker versus retained historical custody explicitly,
   without declaring the failed operation qualified, rewriting its source binding,
   clearing evidence or silently minting another attempt.
3. Refresh current recoverable-backup and actual serial-rescue evidence, confirm
   exclusive console ownership and unchanged bypass topology, and assemble the
   schema-2 preflight only after all components genuinely pass.
4. Approve one explicit start/end window, naming timezone or UTC and any exception
   to the recorded 00:00–05:00 local maintenance policy, the primary-link limitation,
   the one-attempt unsaved scope and exact recovery authority. The old timing
   override is consumed. Preserve the existing 1,800/600/212/20-second budget
   contract; on uncertainty stop, retain custody and do not retry forward commands.

Until these gates are satisfied, no live qualification approval is requested and
the writer must not be invoked. R04 and the broader session objective remain open.

## Successor address replan

The operator requested that the homelab avoid the work VPN's `10.0.0.0/8` route.
The proposed [addressing design](../openspec/changes/avoid-work-vpn-address-overlap/design.md)
selects five checked `172.27` `/24`s, preserving household `192.168.0.0/24`,
existing confirmed household management interfaces, VLAN IDs, stable names and
separate ownership. It is a proposal, not an approved network change.

Physical R720 access and a separate admin computer are available for planning,
but current PVE/iDRAC addresses and each recovery path must still be verified.
Historical `10.72` observations and failed TCP probes do not refute or establish
the operator's current `192.168` management view. The R8 live attempt stays on
hold while the accepted successor topology and source bindings are established.
Do not repin the old packet, manufacture preflight success or repeat persistence
to make the proposal appear qualified.
