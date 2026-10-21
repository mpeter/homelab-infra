# SMART live acceptance — R02 result

**Result: R02 technical acceptance criteria met.** This records the scoped
October 21, 2026 live acceptance, replacing the former approval/runbook. It is
not standing authorization to repeat the tests or make further appliance
changes. The closure ledger remains the authoritative cross-task record:
[October 18 closure ledger](closure-ledger-2026-10-18.md).

## Scope and source

R02's technical criteria and independent review were satisfied. The accepted
source commands came from PR [#34](https://github.com/mpeter/homelab-infra/pull/34),
merged at `350719594670f743caab90f3935e1c968667a565`, following PR #33 at
`b05e3678e64f476e1e8c7caac38365ff391c420a`. The source and rationale are in
the [TrueNAS SMART cron target pattern](storage-plan.md#truenas-smart-cron-job-target-pattern--2026-10-05).

The operator approved only the exact v4 packet, SHA-256
`0020a28a7c861744c1492c55c7203922260104e7fe0845955c3ad9a0027303e7`, for
2026-10-21 20:04:33.951550–21:04:33.951550 UTC. This one-off approval is spent;
it grants no standing permission. Final native verification was at
20:43:38.039740 UTC, within the approved window.

The final native read-back confirms that only the `command` fields of permanent
cron IDs 1 and 2 changed. Their original root/enabled state, schedules
(Wednesday 01:00 and day 15 at 03:00), `America/Los_Angeles` timezone,
`stdout=true`, and `stderr=false` were preserved. The exact eight target serials
were:

- `2108E4FA8118`
- `2108E4FA82BD`
- `2108E4FA8283`
- `2108E4FA82C7`
- `2108E4FA8085`
- `2108E4FA8267`
- `2108E4FA8084`
- `2108E4FA80B6`

## Acceptance evidence

- Precheck job 20092 reported acquisition status 0 for all eight devices.
  Short-start job 20104 and long-start job 20122 each produced eight actual
  scheduling acknowledgements, individual command exits 0 and aggregate exit 0.
  Those raw results, not middleware SUCCESS alone, establish scheduling.
- Short completion job 20114 reported all eight latest tests
  `Short offline: Completed without error`. Long completion job 20191 reported
  all eight latest tests `Extended offline: Completed without error`. These are completion/history
  observations, not a claim that SMART diagnostics certify disk health.
- Raw short read-back at 20:08:23 UTC was conservatively 122.821552 seconds
  after the post-success anchor 20:06:20.178448 UTC. Raw long read-back at
  20:39:33 UTC was conservatively 1,804.618597 seconds after anchor
  20:09:28.381403 UTC.
- Each test phase added exactly one corresponding history entry per device,
  preserving preceding rows. Across both phases, all eight outputs reported `PASSED`,
  acquisition status 0, and no active test.
- The pool remained `tank` ONLINE and healthy; its scan was FINISHED. The
  existing REST API usage alert remained. No alert was dismissed.
- Five capture native-digest pairs were verified. Final raw native checks found
  all five used capture directories absent. The exact disabled temporary cron
  ID 6 was compared with its preimage and deleted; native queries confirmed its
  absence. Permanent job non-command fields remained unchanged.
- Normal WebSocket TLS verification used the system CA and hostname. Because
  system DNS still does not resolve `nas01.lab.kcd.one`, only the process-local
  resolver was overridden to observed address `192.168.0.186`. System DNS was
  not repaired and is not claimed fixed.
- Transport closure evidence confirms the local REPL credential process was
  killed and the task-owned orphan socket directory removed. No guest action
  was repeated after closure.

Source-bound receipt SHA-256 values:

- `long-readback-01/capture.txt` (drive output produced by run 20191):
  `9c8fd8b7f0c4973122e0598a80102aebffb332759b02d8bd8cb5a7c0fc8527fd`.
- `independent-drive-evidence-validation.json`:
  `88048b7cad7258149f6e80606334587c25a99f76705f0b8d7448acebab03e41a`.
- `final-acceptance-readback.json`:
  `7539f5a5bf9b6ae9aec86cf1809a7b80517feb092d26b37917be8e01506c291f`.
- `final-evidence-review.json` (no blockers against original R02 criteria):
  `b56c84cb13aa4cc59ea6d377a674cae7564fb0e4de76db6eaf1c5b3341d5965c`.

Private receipts are retained outside Git under
`/home/mpeter/work/homelab-infra-audit-evidence/closure-continuation-2026-10-21/approved-live-v4/`.
Earlier metadata, ENOENT observations, and download raw responses were not all
retained; historical bindings beyond the surviving receipts are therefore not
asserted. The final cleanup state is known from the current native read-back.
No private raw receipt or secret is staged here.

## Limits and follow-up

The eight source-bound offline short/long scenario runs cover early, late and
multiple failures, aggregate status, and continued reporting of all eight targets.
No live failure injection,
natural cron firing, or notification delivery was performed or is claimed. An
earlier precheck v2 and cleanup v3 were completed separately; a 1,024-character
command limit rejected the initial cleanup before apply, and the corrected
cleanup completed. The local repeat guard refused the phase before guest
dispatch; no start was replayed.

R02 is technically accepted; result delivery follows normal reviewed integration.
This is not broader Group 7 G1–G5 closure and does not authorize backup/boot,
DIMM, Group 8, or Group 9 changes. Do not rerun accepted tests merely to verify
this documentation.
