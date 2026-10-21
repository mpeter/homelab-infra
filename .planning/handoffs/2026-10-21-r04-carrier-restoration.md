---
status: open
---
# R04 restoration carrier contract

## Objective and boundaries

Resume the retained October 18 closure work at R04: implement and independently
review the narrow offline recovery guard fix, then prepare (not execute) a live
recovery plan. Any live network/recovery retry needs separate operator approval.
Keep qualification strict, exact configuration and six-VLAN invariants intact,
and protect inverse, guest-proof and cleanup budgets. Do not repeat SMART work,
accepted disruptive tests, or reopen backup/boot/DIMM/Groups 8/9 deferrals.

## Verified state

- Current branch worktree: `fix/r04-carrier-restoration`, created from main
  `43ad0ab0b0ba88d86521f2a71ff03996379bf778`. Offline implementation and
  independent Python review are complete. Source is stable; result docs and
  append-only ledger reconciliation are prepared for delivery.
- R02 SMART acceptance/result delivery is complete: PRs #34/#35 merged, all eight
  short/long tests passed, native cleanup verified. Its task worktree and branches
  were removed. Do not resurrect its timer, transport, tests or cleanup.
- Primary `/home/mpeter/work/homelab-infra` remains dirty on
  `feat/group-7-network-plan`; native recovery worktree
  `/home/mpeter/work/homelab-infra.worktrees/feat-group-7-native-recovery` is dirty
  and valuable. Neither is owned by this task; preserve both.
- Private evidence base:
  `/home/mpeter/work/homelab-infra-audit-evidence/closure-continuation-2026-10-21/`.
  Existing `r04-actual-replay.json` verifies 91 path/hash bindings, three failed
  captures and 36 restoration receipts. Do not repeat this completed replay.
  Exact configuration/VLAN checks pass while primary Up/Listen or Up/Forward
  fails the primary-down guard before automatic inverse's first journal append.
  During restoration primary transitions Up to Down; physical cause is unknown.

## Verified source adoption

Independent inventories completed in agent sessions
`ses_e9fb29209ffe1TlR2aJH1cs6Pk` and `ses_e9fb0ac1effeTowpRpLuIwXB7M`.
The latter verified the focused required set against replay scratch manifest
`/home/mpeter/.cache/agent-scratch/closure-r04-replay-20261021/source-manifest.json`,
with no unknown per-file provenance. The adoption agent subsequently counted
37 resident pins (correcting the earlier inventory's 36); all are preserved.
Adoption completed in agent `ses_e9faf43c5ffeRHYyRo6tsSnXz9`: 61 exact files,
29,527 lines. The complete import-time dependency set exceeded the initial size
estimate but contains no unrelated 155-file blanket import. It includes three
required public `ansible/network-audit` pin files. Private inventory and verification
receipts are `r04-source-adoption-inventory.json` and
`r04-source-adoption-verification.json`; inventory SHA-256
`9d5fbcd9469f573765c7add589bbead91f0b230805c2857ef87c214ca668e458`.
Application deviation: adoption agent used system patch rather than the required
dedicated patch tool; all destination hashes were independently checked by it.
Subsequent edits must use the dedicated patch tool. Independent adoption review
`ses_e9fa6545fffeE5NnTe8iSUrB83` verified all 61 baseline hashes against retained
scratch and the manifest, the additions-only patch payloads, the 37 pins and the
required import/test closure. No adoption blockers or copied private data found;
94 unrelated manifest files were excluded. Final Python review separately verified
exactly five authorized production differences and the new regression module.
Baseline identities remain:

- `ansible/network-jobs/empty_vlan_cycle.py` hash
  `a5723f5bd71ea66b63178e5acd78b3eba11e7b9dc4b438b761eda9c0aeff94dc`;
  `native_trunk_observation.py` baseline hash
  `b5ecc0827f3fe65925edd881d5684dc8d38b6df1374701e653683717eb5d42b5`.
  Existing replay binds these to the failed attempt.
- Tests are untracked in native tree: `test_empty_vlan_cycle.py` hash
  `136eb9e52ee82cb8fd2c0739e77afa7387fc69c1f7fcce8ba741fdb8c1ad412a`,
  `test_native_trunk_observation.py` hash
  `141ccf2a92a42873838f7b8698a9bdd58ee46628e72f6041043ae83e63b9ecf9`.
  These are adoption baselines, not hashes of the corrected revision. Corrected
  identities are in the implementation and corrected-source replay receipts below.
- Main does not contain the active network-jobs implementation. The cycle's
  import-time `SOURCE_MANIFEST` reads every `SOURCE_PATHS` file (lines 115–165),
  including inherited `exercise.SOURCE_PATHS`, guest artifacts and resident.
  Copying only the two modules does not test the real integrated caller.
- The private deterministic adoption inventory now binds each selected baseline
  file to retained replay hashes; preserve it rather than regenerating history.
- Resident: `network/config-backup-preflight/native-trunk-resident.py` verifies
  `SOURCE_PINS` at import. Pending restorer/reconcile and probe admission are
  separate consumers; trace which call sites must use restoration vs qualification.

## Accepted offline contract and verification

Strict `require_r8_full_trunk_operational_state` remains AST-identical to baseline.
New `require_r8_full_trunk_restoration_operational_state` accepts only Down/None
or Up/Forward after complete interface checks; valid Up/Listen raises specialized
`R8PrimaryListening`, never write authorization. The cycle validates exact state,
configuration and all six VLAN tables first. Explicit restoration context covers
every inverse boundary and receipt admission, including the ambiguous first
inverse/last forward position; the held boundary remains strict.
The implemented bounded policy allows at most two extra full observations across
the whole restoration attempt, shared across all boundaries/sessions, with no
sleep, command retry or deadline reset. Validate exact configuration, complete
interface table and all six VLAN tables before classifying Listen as retryable;
all other drift fails immediately. Strict initial/forward/held observations stay
unchanged. Receipt admission must use restoration validation for inverse/final
evidence while its held boundary remains strict. Only current source chains were
repinned, never historical evidence. Exactly five adopted production files changed:
cycle, observer, receipt admission, runner pin and resident pins.

Existing R8 reads use the phase deadline, NOT the resident's OBSERVE_SECONDS=50
constant. Count limits plus existing protected deadlines prove fail-closed bounds,
not guaranteed settling completion in 100/150 seconds. Do not claim that timing.
The first other-vendor consult timed out. A second bounded description-only
Claude design consult completed with exit 0: private
`r04-other-vendor-design.txt` and `.exit`. Its task-owned tmux session was closed.
It supports the direction but emphasizes safety versus liveness, coherent fresh
reads, no ambiguous-write replay and no restart replenishment. Implementation
tests verify existing pending custody blocks restart rather than introducing a
resume facility. Existing reader order/freshness limits
and risk of writes against an Up/Forward path belong in the live plan; generic
STP topology assumptions from that consult are not established lab facts.

Baseline verification: 252 principal passes and five resident passes. Corrected
verification: meaningful RED four failures; mutation allowing a third extra read
causes three failures; GREEN 366 focused passes (then 45 new cases), followed by
47 complete new regression cases, 309 transport passes and five resident-budget
passes. Counts overlap. Parent reran the original five carrier-focused resident
tests on corrected code: five passed, 356 deselected. Independent Python review
`ses_e9f7f1998ffeABNKr6rQF2Slxk` approves the offline fix, checks pin chains and
strict AST, and reports mypy passing for all five production files. Whole-cycle
Ruff retains preexisting E731; focused lint/format passes.

Private implementation receipt `r04-restoration-implementation-verification.json`
SHA-256 `9347a8704d2a2b3dc7b5c20bd05c508c11b67b38a999ec894edc5c15a99a5eee`.
New `r04-corrected-source-replay.json` SHA-256
`98a576e8a29bee4352f6b4dbd0c542246e1dea4c8cd129db8f52701cce89758a`:
all three actual failures (strictly rejected; two Up/Forward restoration-ready,
one Listen pending/no write), 36 restoration receipts ready, both carrier
transitions, exact state/configuration/six-VLAN invariants, 521 retained input
hashes checked. Preliminary replay-harness errors are recorded in its limits;
they caused no production edits or live calls. Parser replay and integrated caller
regressions are distinct from live guest-traffic qualification. Do not rerun
unchanged passing checks merely to validate prose edits.

## Next action

Finish reviewed delivery of the offline correction/result record. All private
evidence stays outside Git; staged paths are public source/test/docs only and
scoped Gitleaks/whitespace checks pass. Then prepare, but do not execute, the exact
source-bound live plan: fresh preflight, current recoverable configuration backups,
tested out-of-band rescue independent of primary link, preserved old pending
custody, exact command/recovery preview, protected deadlines and live guest proofs.
Obtain a separate operator window/primary-link approval. R04 remains open and no
corrected-source live retry or qualification is claimed. See
`docs/r04-carrier-restoration.md` for current result and live gates.
