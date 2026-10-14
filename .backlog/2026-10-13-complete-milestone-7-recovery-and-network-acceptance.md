---
title: Complete Milestone 7 recovery and network acceptance
type: chore
severity: high
status: open
created: 2026-10-13
labels: []
---
Milestone 7 remains open at 26/38 OpenSpec tasks. Group 7 tasks 7.2, 7.6 and 7.7 are incomplete. The active checkout is `/home/mpeter/work/homelab-infra.worktrees/feat-group-7-native-recovery`, branch `feat/group-7-native-recovery`, at `21745465133e8b20cd5be5a13e26c1021c1e3004`; it contains extensive prior edits that must be preserved. Resume from `.planning/handoffs/2026-10-13-m7-closure.md` and the ordered plan `.planning/docs/milestone-7-goal.md`.

Accepted work to retain: iDRAC VLAN 10 isolation, PVE IPv6 management isolation, R8 installed persistent target acceptance, and prior R7/R8 recovery evidence. Do not repeat accepted R8 persistence. Update OpenSpec only when each criterion has current passing evidence.

The R8 source-bound guest parent and synthetic cycle tests are present. A focused host-Python run passed 354 tests. The pinned execution environment has Python 3.14.7 but no pytest, so those host tests are not evidence that its test suite ran in the pinned image. The live gap is decisive: the audited R8 candidate has no executable live caller; the existing resident CLI supports only `--check` and routes its old lifecycle through the old `plan.FORWARD` path. The R8 cycle also needs mandatory post-inverse guest/management proof before admission and a source-bound caller that enforces the 1800-second total, 600-second inverse reserve and 20-second cleanup reserve. Keep custody pending on any failure. Do not write to the switch until this integrated path, authorized verified PiKVM/serial access, and recovery route are ready. The last verified Brocade baseline was ICX6610 firmware `08.0.30uT7f3`, running/startup hash `01b4a646…327eff`, with primary `1/2/2` down; refresh all live state before resuming.

Other open acceptance includes the real-client routed/firewall matrix and desired/live reconciliation (VLANs 20/30/40 and clients were absent in the last controller read), current management DNS reconciliation, a real UniFi backup/restore with verified identity/access/configuration/traffic, VPN administration and denial checks, iDRAC certificate lifecycle, and public WAN exposure checks. Recheck current evidence and dependencies at pickup; no live controller backup/apply or switch write was made in the last continuation. Keep private receipts under `~/.cache/agent-scratch/`; never commit secrets or receipts.

**Done when:** OpenSpec tasks 7.2, 7.6 and 7.7 are closed using current passing evidence; applicable recovery and route/access checks succeed; owned changes complete normal repository delivery and merged-revision verification; and no M7 acceptance gap remains. Stop before Milestone 8 and deferred Group 5 backup work.
