---
status: open
---
# Continue retained closure acceptance

## Objective and boundaries

Finish the currently actionable obligations in the October 18 closure ledger,
without changing its snapshot, repeating accepted disruptive tests, or reopening
backup/boot/DIMM/Groups 8–9 deferrals. Preserve both unrelated dirty checkouts.
This task works only in `feat-closure-smart-acceptance`.

## Current accepted state

- PR #33 is merged at `b05e367`; PR #34 fixes whole-command SMART suppression,
  merged at `3507195`. Local `main` contains both. The updated eight-scenario
  shell regression fails on the predecessor and passes on the correction.
- Private continuation evidence:
  `/home/mpeter/work/homelab-infra-audit-evidence/closure-continuation-2026-10-21/`.
  The original 40-entry audit manifest was hash-verified; no history gap closed.
- An earlier approved precheck and amended cleanup completed. Temporary cron 5
  and its files are independently absent; retain the receipts, not the old task.

## Completed SMART acceptance — do not repeat live work

The operator explicitly said `approve SMART window` for exact v4 packet SHA-256
`0020a28a7c861744c1492c55c7203922260104e7fe0845955c3ad9a0027303e7`.
The window began **2026-10-21T20:04:33.951550Z**. Final native checks completed
at **20:43:38.039740Z**, before its one-hour deadline. The authorization has
been consumed; no test, cleanup or timer needs repeating. Receipts are in
`approved-live-v4/` under the private base above.

- Fresh precheck job 20092: all eight expected serials, PASSED, acquisition 0,
  no active tests, short/long durations 2/30 minutes. Capture hash/custody and
  cleanup verified (job 20096).
- Permanent cron IDs 1/2 now equal source `3507195`; all non-command fields
  remained unchanged. See `permanent-jobs-source-readback.json`.
- Short starts: job 20104, eight actual start acknowledgements and exit 0,
  aggregate 0. Short completion readback job 20114: all eight latest short logs
  completed without error, no active test, acquisition 0. Capture cleaned up.
- Long starts: job 20122, eight actual start acknowledgements and exit 0,
  aggregate 0. Completion readback job 20191 reports all eight latest extended
  tests completed without error, PASSED, query/status 0 and no active tests.
- Final raw native readbacks establish all five used directories absent,
  exact disabled cron 6 deleted and independently absent, permanent commands
  matching source with other fields unchanged, eight disk identities and
  `tank` ONLINE/healthy with its scan FINISHED.
- Task-owned Python REPL, credential process and orphan socket directory have
  been removed. `transport-closed.json` records that result. Do not recreate
  the old tmux socket/session or wait for the cancelled monitor.
- Independent final evidence review found original R02 technical criteria met,
  with no blockers. `final-evidence-review.json` SHA-256:
  `b56c84cb13aa4cc59ea6d377a674cae7564fb0e4de76db6eaf1c5b3341d5965c`.

## Next decisive action

Review/integrate the result docs, update local main, and safely remove only this
task's worktree after private custody checks. Then resume the retained R04
carrier/recovery source fix and integrated offline acceptance; source delivery
and a separately approved bounded live qualification remain distinct gates.
Select only path-owned, source-bound accepted code from the dirty native tree.

## Evidence limitations and remaining work

An existing RESTAPIUsage deprecation warning was not dismissed. Subsequent API
access uses native WebSocket with normal CA/name TLS and a process-only DNS
override to observed 192.168.0.186; system DNS remains unresolved.

Earlier phase metadata/ENOENT checks were asserted but not all raw responses
were retained. Fixed cleanup commands plus successful native jobs support
their cleanup; final raw responses independently prove current absences and
health. Do not repeat tests to fill that historical provenance gap. This is
manually dispatched exact-command acceptance, not natural cron firing or
notification-delivery proof. Preserve scheduling versus completion distinction.

R04 exact replay is saved as `r04-actual-replay.json`, SHA-256
`bec68667a5ecc6f7ad699df84040570e8e8f693dc172fbced3815d410faf3017`.
All 91 referenced path/hash bindings independently matched. Three failed
captures have exact command-15 config and six VLAN invariants but fail the
primary-down guard (Up/Listen then Up/Forward); automatic inverse reused that
guard before its first journal row. Thirty-six restoration receipts and the
unjournaled tag capture show Up→Down during inverse; final baseline matches.
No R04 source fix or live retry has occurred. Recovery-only carrier semantics,
bounded Listen settling, integrated guest/budget regressions and separate
operator live approval remain. R05–R07/R11 still need the ledger's specific
restore/client/external-vantage/TLS/credential decisions. G1–G5 stay explicit.
