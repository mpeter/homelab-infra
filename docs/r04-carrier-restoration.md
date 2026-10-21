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
