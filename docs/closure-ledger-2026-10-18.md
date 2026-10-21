# Repository closure ledger — 2026-10-18

## Outcome and authority

**Closure is not established for the repository as a whole.** At the snapshot,
two storage review findings reproduced locally; sections 7–9 record their
subsequent local fixes and commits. Milestone 7 has genuine remaining
acceptance work, but several previously reported blockers have since been
resolved. Delivery, runtime acceptance, and historical evidence coverage are
different states; none substitutes for another.

This ledger is for the operator and the next implementing engineer. Use it to
choose retained work and its acceptance test, not to restart every historical
experiment. No infrastructure writes, restores, publication, merges, credential
use, branch cleanup, or edits to other checkouts were performed for this audit.
Recommendations below are not operator decisions. The operator subsequently
approved the two local defect fixes; their October 20 verification is recorded
in section 7. This does not change the historical snapshot or authorize live
schedule/storage changes.

The audit branch began clean at `b6dd0b563f6a36c235b4a2caf25fae7c84cc181f`.
It is behind remote main, `168779606167377706bbcd30fa2faadef6374b55`.
Newer evidence in the dirty native-recovery checkout was inspected read-only.
References prefixed **N/** mean that checkout, not the older audit checkout:

- **P/**: `/home/mpeter/work/homelab-infra`
- **N/**: `/home/mpeter/work/homelab-infra.worktrees/feat-group-7-native-recovery`
- **A/**: the checkout containing this ledger, branch `kinetic-koala`
- **S/**: `inventory/local/closure-audit-2026-10-18/` in A, ignored private
  enumeration/receipt data. The single obligation ledger is this document;
  S contains evidence, not another task tracker. Do not publish S automatically.
  Links into S are machine-local and unpublished; they will not resolve in other clones.

## 1. Source coverage and snapshot

Snapshot cutoff: **2026-10-18T18:25:00.429944Z**. Enumeration began before this
cutoff; later reads validate earlier evidence or discover coverage limits.
The snapshot is not an atomic snapshot of GitHub, every file, and every harness.
Collection times, file hashes, and exact complete lists are retained in
[the evidence manifest](../inventory/local/closure-audit-2026-10-18/manifest.json).
Changes after the cutoff are not presumed part of the audited historical set.

Sources were enumerated before their contents were assessed. A coverage count
does **not** mean every underlying obligation has been verified closed.

| Source | Enumerated population and receipt | Coverage/disposition |
| --- | --- | --- |
| GitHub issues and PRs | S/forge-issues.txt and S/forge-prs.txt; PRs #1–#32, all merged; no standalone issues or open PRs | Complete returned connections; GraphQL `hasNextPage=false`, including nested review/comment connections |
| Review discussions | Three threads: #28 one, #31 two; two review submissions; six issue comments across #27–#32 | All three threads unresolved on forge; assessed below, not assumed closed by merge |
| CI | S/forge-runs.txt: zero Actions runs; all 32 PR-head status rollups null | CI closure evidence unavailable, not passing CI |
| Remote branches | S/forge-branches.txt: main, feat/group-7-native-recovery, fix/nas-installed-reattach-plan-gate | Exact live API heads retained; main is not protected at read time |
| Local refs | S/git-refs.txt: four local branches and five remote-tracking refs | All refs retained; remote-tracking refs are not an authoritative remote inventory |
| Registered worktrees | S/git-worktrees.txt: P, N, A | Three enumerated; ownership preserved |
| Stashes | S/git-stashes.txt empty | Zero at snapshot, not inferred from worktree cleanliness |
| Dirty/untracked work | S/primary-status.txt: 182 paths; S/native-status.txt: 423; S/audit-status.txt: zero before audit outputs | Complete `status --porcelain=v1 -uall`; path/content bindings in S/dirty-path-bindings.json |
| Ignored local material | S/primary-ignored.txt: 2,848 paths; S/native-ignored.txt: 2,936 | Names enumerated, not all contents audited. Includes private state and recovery material; no blanket cleanup authorized |
| Trackers and deferred notes | S/primary-trackers.txt: 75 Markdown paths; S/native-trackers.txt: 108 | Includes backlog, OpenSpec, ADRs, plans, active and archived handoffs. Discovery inventories, not universal closure proof |
| OpenSpec | One active `build-r720-homelab` change, proposal/design/tasks and seven capability specs | N records 26/38 tasks complete, 12 open. Checkboxes are discovery claims only |
| Backlog | Three items in A/P; N adds M7 acceptance item dated October 13 | All four open; M7 duplicates tasks 7.2/7.6/7.7, not a fifth milestone |
| Private runtime receipts | S/native-local-receipt-inventory.json: 2,554 files | Names/sizes enumerated. October 16 relevant receipts inspected selectively; no claim that all receipt contents were validated |
| Published ctx generation | S/ctx-enumeration.json: 448,871 events, 4,656 sessions, terminal=true, truncated=false | Complete metadata enumeration for generation `cb951a1a58e5441279344ca154bb1168754cc6798a5e07eeb7f06958dbfa9a5c`; not all-project semantic analysis |
| ctx provider coverage | 287,902 Claude events; 155,573 OpenCode-bridge; 5,104 Codex-agent-message-recovery; 292 Codex-completion-recovery | No native Codex events in this enumerated generation |
| ctx repository discovery | Workspace-filter enumeration, repository-name search, and complete notice enumeration with cwd/title discovery | Workspace filtering alone found only two Claude sessions; that result was not treated as the whole history |
| ctx notice enumeration | S/ctx-candidate-sessions.json: six historical candidates, including outside-repository cwd paths | Completed notice enumeration at generation `6a83f157332c28850596aff4f9c356a99a11d0f528de8b292eb9d937d28765a2`; first paged attempt failed because its generation was no longer retained, then restarted to terminal in one invocation |
| Native transcripts | S/native-repo-sessions.json: 291 files, 289 Codex and two Claude; current and archived Codex roots included | All matching native files enumerated; original requests and focused tool results inspected directly rather than trusting missing ctx hits |
| Native/ctx overlap | S/ctx-native-overlap.json: only the two Claude session IDs | All 289 native Codex session IDs absent from inspected ctx snapshot. Source availability is not indexing coverage |
| Worker-message limits | S/native-session-index.json: 283 sessions contain an encrypted task-message payload within the inspected first 100 records | Payloads not decrypted. Worker names/lineage can identify a topic, but cannot certify its instructions or closure |
| Cross-path predecessor | `/home/mpeter/work/homelab`, no commits or remote; S/prototype-status.txt and S/prototype-files.txt | Separate uncommitted August prototype discovered from original OpenCode requests; not silently treated as this repository or deleted |
| Unregistered DNS copy | `/home/mpeter/work/homelab-infra-m7-pve-dns-20261013`; S/dns-scratch-files.txt | Preparation copy, not a registered worktree; retain until its edits are reconciled |
| Live infrastructure | No fresh device/controller read in this audit | Operational conclusions are dated October 16 or earlier, not assertions of October 18 health |

### Coverage gaps that prevent a universal closure claim

**G1 — history admission:** `ctx sources` reports available Codex roots, but
the complete inspected generation does not contain the 289 native repository
session IDs. Recovery-source events are not presumed equivalent transcripts.
Direct raw reads mitigate discovery, not the indexing discrepancy. No import,
store deletion, exporter change, or harness repair was performed.

**G2 — unreadable task payloads and incomplete provenance:** the partial worker
disposition map in S/native-session-disposition.json leaves 285 sessions
unclassified. A later structural check positively identifies encrypted payloads
in 283 sessions; these numbers describe different checks, not contradictory
counts of obligations. The remaining root messages, code changes and tool results
do not justify claiming every worker instruction satisfied. Recover readable
original task material through its owning harness, or explicitly accept this
scope limitation; do not invent obligations from worker names.

**G3 — cross-path/history completeness:** relevant original OpenCode sessions
were found under `/home/mpeter/work`, chezmoi and an old OpenChamber chat path.
The bridge/API inventory is not proof that every frozen/legacy OpenCode record
or unnamed/deleted checkout is covered. Current OpenChamber `session.list` for
P returned no sessions. The live bridge changes during export; current audit
sessions appearing later are not historical obligations.

**G4 — acceptance receipts:** not every historical host/guest result behind
Groups 1–6 or accepted Group 7 checkboxes was independently reopened. Those
entries are marked delivered/recorded, not newly verified operational closures.
No CI exists to fill this gap. Retained private receipt paths are machine-local.

**G5 — unknown file ownership:** 25 tracked skill/command deletions occur in
each dirty checkout; their removal intent is not established here. Do not restore
or commit them as part of M7 without provenance. Every other dirty path remains
enumerated even when grouped by subsystem below.

## 2. Primary evidence index

Original Codex references below use **native session UUID + physical JSONL line**,
not a completion summary. S/native-repo-sessions.json gives each exact pathname.
They remain source references even though ctx has not admitted these IDs.

| Key | Original evidence |
| --- | --- |
| U1 | `01a0f925-76f6-7611-a023-fa0a4b1f6ac2`: L3642 authorizes normal PR ceremonies without requiring repeated operator review; branch protection optional, not proof it exists |
| U2 | Same session L35369, L38692, L38751, L39426, L39497, L40357–40380: second-site class selected, receiver absent, interim Fedora/bundle plan selected, then explicit planning-only completion and no backup execution |
| U3 | Same session L70486: numbered deferral/discard/policy answers; N/tasks.md:153–178 records their interpretation. Do not infer the first three question identities from the reply alone |
| U4 | `01a12bfb-52fb-7951-b83b-9718849bd29f`: L349, L359, L977, L1035, L25031: M7 closure requested and full OpenSpec review requested |
| U5 | `01a133fb-e134-7441-bb04-920cdb2427a8`: L24254 hold/backlog request; L24814, L24846, L25437–25516 later M7 resumption; L49816 and L51005 correct PiKVM serial lead to Brocade; L72146 explicit stop; L75310 Fedora working/persistence question |
| U6 | `01a13fed-fd03-77b0-b1fc-9e9286c13170`: L10 diagnosis-only request, superseded by L222 implementation instruction; L928 bypass route, exposed UniFi-key replacement, cellular test availability, restore-window preparation; L2117 apply/verify permission; L3360 all three post-restore client tests pass; L3407 Site Magic research request; L3702 selected VPN deny result confirmed; L4346 exact R8 authorization |
| R8 | Same session **tool outputs** L5106 restored/pending-retained; L5127/L5134 independent port reads; L5141 independent exact configuration restoration, six VLAN tables pass, qualification=false, save=false; L5162 custody copies verified. N/inventory/local/m7-r8-authorized-now-2026-10-16 and N/.planning/docs/r8-authorized-attempt-2026-10-16.md:14–64 |
| UR | N/inventory/local/m7-restore-readiness-2026-10-16/restore.json:2–20 and readback.json:219–280; successful restore, selected no-op and client checks, explicit fidelity limitations |
| NB | N/inventory/local/m7-current-native-backup-2026-10-16/native-export-structure.json:1; 1,790-byte current native export, baseline binding, cleanup. N/tasks.md:328 distinguishes this from import/reboot acceptance |
| AM | N/inventory/local/m7-admin-readonly-2026-10-16/{iphone-vpn-deny-operator.json:2–13,local-dns-tcp-tls.json:2–51,idrac-managed-tls.json:2–52,external-exposure.json:5–23} |
| F28 | [PR28 review](https://github.com/mpeter/homelab-infra/pull/28#discussion_r4172237664), later commit `1863090`, A/docs/backup-recovery.md:61–70,96–97 |
| F31a | [PR31 recovery-layout review](https://github.com/mpeter/homelab-infra/pull/31#discussion_r4188525716); A/host/pve/check_scratch_apply_plan.py:455–469; check_scratch_preflight.py:236–247; manage-scratch-pool.sh:422–425 |
| F31b | [PR31 SMART review](https://github.com/mpeter/homelab-infra/pull/31#discussion_r4188525727); A/docs/storage-plan.md:1462–1473,1488–1494 |
| O0 | ctx event `09699051-b84f-88df-9b9e-39ec645ba874`, session `bb16a40b-57a7-8121-9e42-1cba3512cd9b`: original August scaffold request. Event `955817bb-d626-82d9-a623-6541492eacd6`: purpose is concurrent agent workloads, not token generation |

## 3. Reconciled items and recommended dispositions

Priorities are recommendations: **P1** recovery/security correctness before another
dependent live change; **P2** current acceptance or delivery; **P3** later gated
work. Owner **operator** means a hardware, risk-acceptance, maintenance or scope
decision is required; it does not assign implementation to an absent person.

### R01 — Generated-GPT scratch recovery rejection — locally fixed; delivery open, P1

- **Obligation:** F31a requires interrupted `labels-cleared` recovery to accept
  the exact generated layout with clear child signatures, without weakening
  rejection of unexpected signatures or identity changes.
- **Snapshot evidence:** the classifier requires empty child `wipefs`; preflight
  consequently emits `CLEAR` child `blkid` findings. The validator instead
  requires child `BLOCK` findings. An offline adaptation of the existing
  generated-layout fixture reproduces `PlanError: recovery preflight contains
  unexpected findings`. The existing test passes with contradictory `BLOCK`
  child fixtures (`tests/test_check_scratch_apply_plan.py:351–369,395–411`).
- **Contradiction:** merged PR31 and passing existing fixture do not close this
  review. It remains unresolved on forge and reproducible in committed code.
- **Delay consequence/dependency:** a legitimate recovery can be blocked after
  interruption. Resolve before depending on this recovery path; no disk write
  is needed to reproduce or fix it.
- **Owner/next action:** implementing engineer; narrow the expected findings to
  match the actual accepted generated layout and add the realistic regression.
- **Closure criterion:** regression fails on present code, passes on the fix;
  unexpected child signatures, wrong serials and unrelated findings still fail;
  focused/full checker tests pass and delivered revision is identified. Live
  storage recovery is a separate, explicitly authorized operation.
- **October 20 result:** the local validator now requires the whole-disk
  signature and clear child signatures. Realistic generated/mixed layouts pass;
  signed children, absent whole-disk signatures, wrong serials and unrelated
  findings remain rejected. Source verification passes; no deployed or delivered
  revision is claimed. See section 7.

### R02 — SMART scheduling loop hides earlier failures — local target fixed; live acceptance open, P2

- **Obligation:** F31b requires failures from every intended SMART target to
  propagate and per-serial scheduling evidence, not just middleware job success.
- **Current evidence:** documented loop at storage-plan.md:1462–1464 lacks
  failure aggregation. Offline fake: first target exits 1, final target exits 0,
  loop exits 0. Reported job 5916 `SUCCESS` is therefore insufficient.
- **Uncertainty:** later independent per-drive health/short-test captures support
  those observed results, but do not prove this cron invocation scheduled all
  disks, or that the live schedule has since been corrected.
- **Delay consequence/dependency:** a scheduled test may silently omit a disk;
  this is not evidence of present disk failure. Depends on reviewing the live
  job through the authorized trusted route, not filling a pool or rebooting.
- **Owner/next action:** implementing engineer prepares aggregate-exit/per-target
  command and offline regression; operator controls any live schedule update.
- **Closure criterion:** early and multiple failures produce nonzero overall
  result, all targets still run and receive individual results; source and live
  job agree after any authorized apply. Keep historical job-success claims
  separate from verified individual drive results.
- **October 20 result:** both versioned short/long commands now aggregate any
  failure, continue through all whole-disk targets and print each target's exit
  code. The test executes those exact documented commands with fake devices and
  smartctl; early, late, multiple failures and all-success cases pass for both
  test types. Guest Cron Job IDs 1/2 were not read or updated; deployment and
  per-serial live acceptance remain open.

### R03 — Backup-plan review — completed but forge-unrecorded

- **Obligation:** F28 requires versioned ownership/preflight/read-back before
  creating the dedicated target dataset/share.
- **Evidence/disposition:** commit `1863090` adds versioned configuration,
  allowed/denied access checks and preflight; current backup-recovery.md:61–70,
  96–97 contains these requirements. **Plan-level review substantively closed**;
  unresolved forge thread is stale, not proof the dataset exists.
- **Closure criterion/next action:** keep the original discussion and later
  commit linked; an authorized forge reply/resolution may record the closure.
  Do not implement backups to close a planning-only review. Owner: repository
  maintainer; priority P3, no runtime consequence from the stale thread itself.

### R04 — Current-source R8 and rollback — retained, P1

- **Obligation:** U4/U6 and task 7.6 require current-source qualification and
  exact restoration, with guest proofs, source binding and bounded recovery.
- **Evidence:** October 16 exact authorized attempt failed after primary carrier
  changed Up. Automatic inverse reused the primary-down guard and admitted no
  inverse rows. Attempt-specific bounded recovery restored running/startup
  SHA `01b4a646e764f2874a2310b7e0efd1622f779f230d1d77a41a176b720a327eff`
  and all six VLAN tables (R8 tool outputs); pending custody remains retained.
- **Disposition:** **failed and restored, not qualified**. The older claim that
  no executable live caller exists is superseded by this actual attempt.
  Physical cause of carrier transitions remains unresolved; do not diagnose a
  cable from a parser failure. Prior accepted persistence is not undone.
- **Delay consequence/dependency:** another unsupervised attempt could again
  lose automatic rollback. Retain original pending/runtime artifacts; no retry
  until the carrier contract is corrected and recovery tested.
- **Owner/next action:** implementing engineer fixes only the observed recovery
  contract; operator decides any primary-link exception and exact live window.
- **Closure criterion:** replay all retained failure captures and both carrier
  transitions while enforcing exact configuration/VLAN invariants; integrated
  caller proves held-trunk and post-inverse guest state within its budgets.
  One authorized bounded current-source qualification then restores and is
  independently read back. Do not repeat already accepted persistence.

### R05 — Network backup/recovery acceptance — retained, P2

- **Obligation:** task 7.2 and U6, consolidated with the M7 backlog item.
- **Proven slices:** NB verifies fresh current-native Brocade export/binding,
  encrypted custody and cleanup; UR verifies an actual UniFi native restore,
  Owner/Protect/adoption observations, 39 managed-resource no-op comparison and
  selected client checks. U6 L3360 independently records operator Wi-Fi Internet
  and cellular NAS/iDRAC passes.
- **Remaining uncertainty:** selected settings are not exhaustive application
  data/credential fidelity. Site Magic keys differ with zero configured tunnels;
  baseline was captured after the backup. Stable current keys do not establish
  regeneration or a defect. The refreshed Brocade point was not import/boot
  tested; older native restore acceptance is for an older point.
- **Delay consequence/dependency:** full recovery confidence and M7 closure
  remain limited. Site Magic uncertainty need not block independent R04/R06.
- **Owner/next action:** operator fixes acceptance scope: retain full-scope
  fidelity requirement, or explicitly accept the unused-key difference as an
  exception. Engineer then checks only missing representative forwarding and
  agreed restore-scope evidence. No automatic rerun of a disruptive restore.
- **Closure criterion:** agreed restore-scope comparisons and forwarding
  positive/negative controls pass against the actual recovered point; limitations
  are accepted explicitly or remain unresolved. No new self-written summary
  substitutes for recovery evidence.

### R06 — Remaining route/firewall and administration matrix — retained, P2

- **Obligation:** tasks 7.6/7.7, not every historical network experiment.
- **Evidence:** AM selected VPN deny test passes with an iDRAC positive control;
  DNS/admin TCP reads pass. N/tasks.md:376–391 separates accepted PVE IPv4/IPv6
  and iDRAC isolation from remaining routed/client rows. VLANs or clients absent
  from the observed inventory cannot have passing traffic tests inferred.
- **Contradiction/disposition:** do not repeat the selected cellular tests as
  though unperformed; do not call one passing deny test the whole matrix.
- **Delay consequence/dependency:** untested sources/routes may violate intended
  boundaries. Depends on the accepted topology and R04 where trunk-dependent.
- **Owner/next action:** engineer extracts missing rows from N/network/group-7-readiness.md
  and N/.planning/docs/milestone-7-goal.md; operator supplies absent test clients
  or decides explicit exceptions before implementation.
- **Closure criterion:** each retained row has source, destination, protocol/port,
  expected/actual result, positive control and dated raw receipt; UniFi, switch
  and PVE desired/live states reconcile without importing destructive drift.

### R07 — iDRAC TLS lifecycle and public exposure — retained, P1/P2

- **Obligation:** task 7.7 requires trusted administration, lifecycle evidence
  and management services not reachable from the public internet.
- **Evidence:** AM iDRAC managed TLS succeeds only with client-supplied
  intermediates; ordinary client trust and immutable EE/browser acceptance are
  not established. External October 16 probes returned HTTP 403 at the probe
  service: these are unavailable tests, not management-service denials.
- **Uncertainty:** October 14 multi-node timeouts and earlier single-node 443
  success do not identify the public responder, upstream/NAT or IPv6 exposure.
  PVE/TrueNAS production identity and renewal have later recorded accepted
  slices; this audit did not reopen all of their receipts (G4).
- **Delay consequence/dependency:** ambiguous endpoint trust/exposure remains;
  it is not a confirmed public iDRAC/PVE compromise. No extra root CA or trust
  bypass is authorized by this ledger.
- **Owner/next action:** engineer prepares exact existing-design client-chain
  acceptance and renewal checks; operator selects any client exception and an
  independent external test vantage.
- **Closure criterion:** named ordinary/approved clients validate intended
  identity and renewal/failure notifications; external IPv4/IPv6 checks with
  positive controls and effective upstream policy identify any responder and
  prove the specified management ports inaccessible.

### R08 — Deferred independent data backup and recovery — retained/deferred, P1 gate

- **Obligation/provenance:** U2, ADR0013, and the October 3 second-site backlog.
- **State:** destination class chosen, no receiver established in the audited
  implementation. Interim same-host plan is complete **as a plan**. It is not
  an independent backup or restore. Old Group5 implementation goal is superseded.
- **Delay consequence/dependency:** unique-data/workspace promotion stays
  prohibited. Depends on an operator-selected, available independent receiver
  and key custody. This is not part of immediate M7 execution.
- **Owner/next action:** operator provisions/selects receiver when reopening
  that backlog; engineer then plans only its reviewed bounded implementation.
- **Closure criterion:** encrypted destination copies and independent restores
  of the retained coverage, with key recovery and failure alerting, pass before
  promotion. No same-R720 copy can satisfy host-loss acceptance.

### R09 — Independent boot and DIMM expansion — two retained deferred obligations

- **Boot (P2):** October 5 boot/recovery backlog and tasks.md:46–52. Observed
  alternate paths are not two cold-boot tests. Operator/hardware window required;
  delay retains the current boot-device dependency. Next: identify exact serials,
  rescue media and recovery procedure before the separate test. Close only on
  the backlog's two independent boot results and verified recovery media/path,
  or explicit **not pursued**, never because Group6 advanced.
- **DIMM (P3):** October 5 DIMM backlog, ADR0007. Purchased module identity and
  supported population remain unqualified, not a diagnosed hardware failure.
  Operator identifies modules; then gated physical installation, matching
  capacity/inventory and clean diagnostics, or explicit **not pursued**. Delay
  constrains future capacity but does not negate the smaller Fedora VM.

### R10 — Undelivered work and conflicting checkout records — retained, P2

- **Obligation:** normal reviewed delivery requested in U1/U4/U6.
- **Evidence:** N tip `b886a6f4ee2c11fc877165ece46a19ab3f70a8d4` differs from
  merged PR32 head `20f6cf5ffa76e2203ef8ebc485e9639aef0216e9`: two later commits
  (`2174546`, `b886a6f`) are not delivered to main. N also has 423 dirty paths;
  P has 182, not the same revision. Primary branch is feat/group-7-network-plan,
  not main. Remote branch remnants alone do not imply unfinished behavior.
- **Backward tracing:** untracked network-audit/jobs, Brocade recovery/transport,
  UniFi provider/state/import/policy/DNS, bond/USB/bridge and certificate paths
  implement Group7 preparation/acceptance, not unrelated new features. AAP
  controller registration belongs to 8.2, not unfinished 7.4. The 25 instruction
  deletions per checkout and independent DNS copy have unresolved exact ownership.
- **Delay consequence/dependency:** runtime may depend on code not reproducible
  from main. Do not consolidate by overwriting either dirty checkout.
- **Owner/next action:** originating engineer/maintainer maps path-level ownership
  using S/dirty-path-bindings.json, selects only accepted source and receipts,
  then validates and prepares focused delivery. Unknown paths remain excluded.
- **Closure criterion:** accepted behavior is tied to reviewed delivered commit
  hashes and retained private recovery evidence; all other edits have explicit
  ownership/disposition. No cleanup of ignored recovery material or merged
  branches whose local tip differs from merged head.

### R11 — Historical credential exposure — unresolved, P1

- **Obligation:** October 4 TrueNAS admin/key exposure and later exposed UniFi
  key replacement are separate credential events, not one certificate task.
- **Evidence:** A/tasks.md:153–159 records the TrueNAS deferral; U6 L928 authorizes
  UniFi replacement. N/inventory/network.yaml:11483–11492 points to
  `inventory/local/m7-decisions-2026-10-15/key-rotation.json` for the latter.
- **Disposition:** no secret values copied. Later TLS issuance does not alone
  prove the old admin credential and old private key unusable. The continuation
  inspected the existing UniFi receipt's non-secret fields: authorized UI
  revocation observed, zero keys after removal, replacement stored/read back,
  ordinary TLS verification, and old keyring entry cleared without reading or
  reusing the exposed secret. This is dated rotation evidence, not a fresh
  predecessor-authentication test or proof of TrueNAS credential rotation.
  Source hash and limits are retained in S/rotation-receipt-check.json. Do not reopen the
  old trusted-access blocker as though later privileged checks never occurred.
- **Delay consequence/dependency:** possibly still-valid exposed credentials;
  operator/key custodian owns scope and trust route. Next: inspect non-secret
  rotation/revocation receipts and establish which original identities they cover.
- **Closure criterion:** replacement usable, predecessor invalid, client/key
  custody and required dependent configuration verified without disclosing values;
  explicit deferred/not-pursued state for anything the operator excludes.

### R12 — Historical experiments and successor scope — no automatic new work

- **PoE:** `ed206ab`, docs/brocade-poe-rca.md:62–85,100–114 record unsuccessful
  recovery and conditional replacement if PoE is needed. Outcome is **failed
  investigation**, not repaired hardware. No current replacement requirement
  was established. Owner/operator may explicitly retire or reopen it when PoE
  is needed; no new firmware or hardware redesign proposed.
- **Firmware patch:** `e7ac792`, docs/brocade-firmware-analysis.md:155–202 exclude
  a flashable patch from delivered analysis. **Not pursued in that scope**, not
  a missing promised flashed artifact. Rejected future ideas in
  brocade-projects.md are not all historical obligations.
- **Old workbench prototype:** O0 and `/home/mpeter/work/homelab/docs/agent-workbench.md:5–32`
  establish purpose and a proposed 80-GiB/12-vCPU hypothesis. ADR0007 supersedes
  sizing/order with measured-capacity Fedora. No benchmark or full harness
  migration closure was located. Keep the prototype intact; operator decides
  whether any original workload-migration request survives beyond Fedora setup.
- **PVE upgrade / remote state:** task1.3 and ADR0009 keep the upgrade and remote
  backend migration separate/deferred. Do not invent migration or upgrade work
  to close the accepted local bootstrap.
- **Fedora operational question:** U5 L75310 had a current-health caveat. Later
  October 16 guest/PVE receipts cited by R8 show both VMs running and Fedora
  DNS/verified HTTPS at that time. This answers a later point-in-time working
  state, not a guarantee against future teardown or unique-data promotion.
- **Stop/hold history:** U5 hold is superseded for later M7 work by U6, with
  a specific October 16 attempt authorized. That does not retrospectively make
  work after an earlier stop authorized, or authorize another attempt now.

## 4. Complete OpenSpec crosswalk

Each of the 38 current task IDs is accounted for here. **Recorded/delivered**
means source or forge delivery exists but operational closure has not been
independently re-established in this audit (G4). It does not reopen a task for
live re-execution. Original criteria remain in the referenced spec/task files.
For retained later work the owner is the operator for prerequisites and an
implementing engineer after that decision; no execution is scheduled here.

| Task | Audit disposition / exact discovery reference | Observable closure or retained next decision |
| --- | --- | --- |
| 1.1 | Recorded baseline; tasks.md:3, inventory/host.yaml | Dated version/access/pool/memory/SEL readbacks; locate original raw acceptance, not checkbox |
| 1.2 | Recorded recovery checks; tasks.md:4, `afaadc2` | Verify original off-host bundle/console/drift receipts; not a new recovery operation |
| 1.3 | Accepted deferral recorded; tasks.md:5 | Locate version/repository no-drift result and upgrade disposition; no upgrade implied |
| 2.1 | Local encrypted bootstrap recorded; tasks.md:9, ADR0009 | Original lock/ciphertext/separate-key recovery results; remote migration remains deferred |
| 2.2 | Delivered scoped control path; tasks.md:10, `020e5fa` | Original allowed/denied identity results plus source-bound check/apply evidence |
| 2.3 | Delivered VM module/gates; tasks.md:11, `9bda0bf`, PR4/9/10 | Positive/negative plan tests for pinned source; not inferred VM runtime |
| 2.4 | Delivery policy exists; tasks.md:12, CONTRIBUTING.md:9–20, U1 | Manual PR policy is not server branch protection; current API reports unprotected. Original secret/plan scans not reopened |
| 2.5 | Disposable-VM exercise recorded; tasks.md:13 | Original boot/no-change/destroy/orphan readbacks needed for independently verified closure |
| 3.1 | Capacity/sensor disposition recorded; tasks.md:17, ADR0007 | Original fresh health results and explicit chassis-sensor waiver; do not infer waiver for other faults |
| 3.2 | Fedora delivered; tasks.md:18, first-vm plan | Original create/no-change; October16 runtime slice is distinct, see R12 |
| 3.3 | Guest config delivered `e55d49c`; tasks.md:19 | Original check-mode/apply/readback; unique-data gate R08 remains |
| 4.1 | Serial/destruction disposition recorded; tasks.md:23 | Original per-serial SMART/signature/IOMMU/rescue evidence, not reusable write permission |
| 4.2 | Mapping/HBA policy delivered; tasks.md:24, PR5–7, ADR0012 | Pinned image/mapping denial and live binding receipts; UI success insufficient |
| 4.3 | NAS guest delivered `dc3c035`; tasks.md:25, PR3/18 | Original guest serial/capacity/host-exclusion/permission results |
| 4.4 | NAS cycle/cold-boot recorded; tasks.md:26, PR11–13 | Original boot/driver/import/rollback results; not independent boot-device test R09 |
| 4.5 | Off-target metadata custody recorded; tasks.md:27, PR21 | Original serial/hash captures; metadata is not a full data backup |
| 4.6 | Pool/protection recorded; tasks.md:28, PR22 | Original topology/scrub/SMART/snapshot results; delivery and scheduling gaps remain R02/9.3 |
| 4.7 | Share/restart validation recorded; tasks.md:29, PR23 | Allowed/denied/I/O/hash/restart/cleanup outputs; final client boundary R06 |
| 5.1 | Plan-only delivered; tasks.md:41, PR28/29, R03 | Versioned bounded plan exists; do not execute backup to close this task |
| 5.2 | Scope deferral delivered; tasks.md:42, U2, PR29 | Backlog and explicit no-promotion gate exist; implementation retained as R08 |
| 6.3 | Scratch created/recorded; tasks.md:54,161–198 | Original serial/topology/storage-content readbacks; recovery defect R01 is separate |
| 6.4 | Narrow measurement/procedure completion recorded; tasks.md:317, PR31 | Historical “remains open” entries are chronology. Synthetic procedures are not live faults/threshold crossing/delivery; R01/R02 and 9.3 remain |
| 7.1 | Target decisions recorded in N/tasks.md:326, ADR0014/15 | Decision artifact scope, not live network acceptance; uncommitted delivery R10 |
| 7.2 | Retained R05, P2; N/tasks.md:327–368 | Missing agreed restore-scope/forwarding evidence; operator exception decision first |
| 7.3 | Provider/state/import no-op recorded; N/tasks.md:369 | Original locked-state recovery/import/no-change receipts and source delivery R10 |
| 7.4 | Pinned EE/jobs recorded; N/tasks.md:370 | Fixed jobs scoped exercise/recovery receipts; AAP registration belongs to 8.2 |
| 7.5 | Bond/fallback tests recorded; N/tasks.md:371 | Both controlled link results and recovery source binding; not proof R04 qualified |
| 7.6 | Retained R04/R06, P1/P2; N/tasks.md:372–380 | Carrier-correct recovery, agreed matrix and desired/live reconciliation |
| 7.7 | Retained R06/R07/R11, P1/P2; N/tasks.md:382–391 | Client/lifecycle/external/access evidence, no inferred acceptance from missing tests |
| 8.1 | Retained later, P3; N/tasks.md:402 | Delay: no IdM/RHEL template service. Dependency: capacity/recovery and M7. Next: operator reopens group, then tested reproducible template/IdM boot/config |
| 8.2 | Retained later, P3; N/tasks.md:403 | Delay: laptop bootstrap remains. Dependency: RHEL/capacity. Next: AAP VM/bootstrap and as-code objects, independently read back |
| 8.3 | Retained later, P3; N/tasks.md:404 | Delay: no accepted controller lifecycle workflow. Dependency: 8.2. Next: audited disposable create/config/verify/remove and export-before-iDRAC-write proof |
| 8.4 | Retained later, P3; N/tasks.md:405 | Delay: OpenShift absent. Dependency: entitlement/release/DNS/capacity/recovery. Next: operator prerequisites decision, then verified SNO provisioning |
| 8.5 | Retained later, P3; N/tasks.md:406 | Delay: no in-cluster reconciliation proof. Dependency: 8.4. Next: GitOps reconciliation/self-healing/rebuild evidence; optional Operators not presumed work |
| 9.1 | Retained later, P2; N/tasks.md:413 | Delay: incomplete recovery order/custody inventory. Dependency: actual implemented services. Next: enumerate owners/artifacts/order without copying secrets; remote copies remain R08 |
| 9.2 | Retained later, P2; N/tasks.md:414 | Delay: orderly power-loss shutdown unproved. Dependency: operator UPS/test window. Next: signal-driven guest/NAS/PVE shutdown with recovery and without extended outage |
| 9.3 | Retained, P2; N/tasks.md:415, PR26, R02/R07 | Delay: some failures may not notify. Dependency: trusted endpoints and implemented services. Next: missing delivery cases only; PVE email is a recorded accepted slice, not universal alert acceptance |
| 9.4 | Retained later, P2; N/tasks.md:416 | Delay: reproducible-service recovery instructions incomplete. Dependency: service inventory/9.1. Next: isolation/order/pass criteria for implemented services; host-loss/remote restores remain R08/R09 |

Former 6.1 and 6.2 are not part of the 38 current IDs: they map to the two
distinct R09 backlog obligations. They are deferred, not done. M7 backlog maps
to R04–R07/R10; it is not independently counted as more implementation.

## 5. Bounded plan and decision boundary

Recommended order, **not authorization to change live state**:

1. **R01/R02 local fixes are verified:** retain only source delivery and the
   separately authorized guest schedule/read-back acceptance. Reuse the
   source-bound checks while their inputs remain unchanged; do not restart
   implementation or treat offline verification as deployed recovery evidence.
2. **R04:** repair only the carrier transition/recovery defect demonstrated by
   retained captures. Integrated recovery tests precede a proposed exact live
   operation; budgets, rescue path and pending custody must remain intact.
3. **R05–R07:** first fix acceptance decisions: full versus selected restore
   fidelity, any primary-link exception, absent matrix clients, approved iDRAC
   client-chain behavior and independent external vantage. Reuse unchanged
   accepted evidence. Do not rerun successful disruptive restores by default.
4. **R10:** reconcile and deliver accepted source by owned paths after relevant
   checks, private-artifact exclusion and exact revision review. No blanket
   staging, overwrite, cleanup, force-push or merge.
5. **R08/R09 and Groups8/9:** retain existing prerequisite/deferred boundaries.
   Plan their implementation only when reopened; no new receiver, platform,
   UPS or hardware work is created by this audit.

The operator approved local R01/R02 implementation on October 20; section 7
records that bounded result. Other acceptance-scope changes remain decisions,
not implementation instructions.
Publication, merges, storage/network operations and disruptive tests remain
separate bounded actions under the repository's change control.

## 6. Reconciliation and limits

### Verification after the October 20 server restart

The saved October 18 snapshot was preserved rather than recollected. Evidence
manifest hashes passed for all 34 then-retained files. A source-bound offline
reproduction receipt was subsequently added as the 35th evidence file:
[offline-reproductions.json](../inventory/local/closure-audit-2026-10-18/offline-reproductions.json).
It records the exact in-memory fixture substitutions, source SHA-256 values,
validator exception and fake SMART loop/output. This confirms R01/R02 without
device access or source edits; it does not move the historical cutoff.

An independent cold-reader checked the crosswalk, review-thread accounting,
snapshot/status distinctions and decision boundary. The final numeric check
confirmed six issue comments, two reviews and three threads. Local Markdown
links resolved. Whitespace and retained-evidence hash checks are the applicable
document gates; no infrastructure apply or recovery test was used to validate
this prose. The ledger and private evidence remain local, not published.

### Final dispositions

- **Independently established closures/slices:** R03 plan correction; October16
  failed R8 attempt exactly restored with pending custody retained; current
  native export binding; actual UniFi restore and the specifically observed
  post-restore client tests; selected cellular VPN deny with positive control.
  None alone closes task7.2,7.6 or7.7.
- **Superseded/not pursued:** old off-site active goal superseded by U2;
  original workbench sizing superseded by ADR0007; flashable firmware patch not
  pursued in the delivered analysis. A failed PoE repair is not reported done.
- **Retained:** source delivery and live acceptance of the two locally corrected
  storage findings, R04–R11, later OpenSpec8/9
  requirements and explicitly deferred backup/boot/DIMM work. Recommendations
  have not advanced any tracker status.
- **Unresolved:** G1–G5, exact residual legacy/prototype obligations, credential
  revocation coverage, Site Magic difference cause, physical carrier cause,
  full restore fidelity and effective external exposure. Unclassified worker
  instructions are a coverage gap, not 285 invented tasks or 285 closures.
- **Source accounting:** every enumerated PR is retained in S/forge-prs.txt;
  all three review threads map to R01–R03. All 38 task IDs map above; all four
  backlog items map to R04–R09. All local/remote refs, worktrees, stashes,
  dirty/untracked/ignored paths and discovered native sessions remain in the
  named complete inventories. Grouping does not discard their provenance.
- **Completion claim:** this is a usable but **coverage-limited closure audit**.
  Neither all historical obligations nor all open work can be declared closed.
  A universal closure claim requires resolving every coverage gap and
  independently establishing every obligation's disposition. Operator acceptance
  of a coverage limitation can narrow the declared scope; it cannot establish
  universal historical completeness.

## 7. Authorized local fixes — October 20

The operator's “go” approved the proposed two local fixes, not infrastructure
apply, publication or merge. Changes are confined to:

- `host/pve/check_scratch_apply_plan.py`: exact generated-layout findings now
  agree with the preflight's clear child signatures, retaining disk GPT and all
  reference/state/identity checks.
- `host/pve/tests/test_check_scratch_apply_plan.py`: realistic child findings and
  negative signed-child, missing-disk-signature and wrong-serial regressions.
- `docs/storage-plan.md`: corrected aggregate/per-target short and long cron
  commands; historical job 5916 no longer implies every disk was scheduled.
- `host/pve/tests/test-truenas-smart-cron.sh`: executes both documented commands
  in a private fake-device environment with eight whole-disk and eight partition
  aliases, checking early/late/multiple failures and complete success.

Red verification before the fixes rejected realistic recovery layouts and
reported `FAIL: short test masks failure(s) on disk1`. After the fixes:

| Check | Result |
| --- | --- |
| Both scratch Python test modules | 64 tests passed |
| Actual documented short/long cron commands against fake targets | All eight scenario runs passed; every whole disk reported, partition aliases excluded |
| Synthetic scratch member-loss drill | Passed; unavailable stripe still rejected |
| Bash syntax | Passed |
| Ruff lint, both changed Python files | Passed |
| Strict mypy, production validator | Passed |
| Whitespace | Passed |
| Ruff whole-file formatting | Existing failures outside the changed lines; same two files fail against HEAD. Unrelated formatting preserved |

[Source-bound verification receipt](../inventory/local/closure-audit-2026-10-18/local-fix-verification.json)
records exact commands, outputs, exit codes, baseline formatter results and source
SHA-256 values. No live SMART tests, cron updates, storage operations, commits,
forge-thread resolutions or publication occurred. R01/R02 are locally corrected,
not independently deployed or delivered; broader audit coverage gaps persist.
Independent Python/code review found no blockers and independently confirmed the
64-test suite, shell regression, syntax, lint, strict production types and
whitespace checks.

## 8. Continuation reconciliation — evidence accounting, not universal closure

This pass preserves the October 18 snapshot. The independent comparison receipt
is timestamped `2026-10-21T01:01:09Z` (October 20 local time). It does not assert
fresh operational health. Existing original U2/U6/R8 JSONL line references were
checked against their expected request/result markers. All 291 original native
transcript paths still exist; missing index coverage is not transcript loss.

### Exhaustive accounting within the captured source set

[Inventory reconciliation](../inventory/local/closure-audit-2026-10-18/inventory-reconciliation.json)
assigns each enumerated source record a source reference, ledger reference,
disposition and explicit assessment limit. Structured JSON inventories are
parsed as objects, not counted by physical lines. Exact source-unit counts are
checked mechanically, with unique mapping IDs. The map includes 15,062 source
records, including global ctx discovery identities and evidence containers;
**that is not a count of distinct obligations or closures**. Duplicate paths in
two checkouts and PR mirrors retain their separate provenance.

| Captured set | Reconciled result | Outstanding semantic limit |
| --- | --- | --- |
| 32 PRs, three review threads, six issue comments, two review submissions | All individually referenced; review findings map to R01/R02/R03 | Merge proves delivery of those heads, not runtime acceptance; no thread was resolved by this audit |
| 38 current task IDs and four backlog obligations | All task IDs have the section 4 disposition; former 6.1/6.2 map to R09; M7 backlog consolidates R04–R07/R10 | Backlog/checklist existence is not closure evidence |
| All refs, three registered worktrees, three remote branches, zero stashes | Recorded in their snapshot inventories and R10 | No branch/worktree cleanup authorized; later native-recovery commits differ from merged PR32 head |
| 605 dirty-path occurrences, 183 tracker-path occurrences, 758 source-file inventory occurrences | Every captured occurrence mapped; snapshot content bindings preserved | Known subsystem association is not authorship or proof every edit meets its request; G5/R10 remain |
| 5,784 ignored paths and 2,554 receipt paths | Every path preserved as source-only coverage evidence | Contents are not universally inspected or accepted; do not count these as thousands of implementation tasks |
| 291 native sessions, six historical ctx candidates, all 4,656 global ctx identities | Every identity mapped, with all eight roots/283 worker sessions structurally distinguished in the native index | Global metadata does not establish project relevance; encrypted/unclassified instructions remain G1–G3 |
| Unregistered DNS copy and predecessor prototype | All 25 DNS-copy paths, ten prototype paths and ten prototype status occurrences retained | No automatic migration, deletion or benchmark obligation inferred |
| CI/issue/source inventory containers | Zero Actions runs, zero standalone issues in the issue API's 32 PR mirrors, configured source availability recorded | No CI is not passing CI; available source is not an indexed or assessed transcript |

No source record lacking semantic evidence is silently promoted to completed,
abandoned or harmless. Retained-evidence classification means preserve and
account for the record; it does not mean implement the file or accept its code.

### Independent closure evidence for the two fixes

[Independent fix comparison](../inventory/local/closure-audit-2026-10-18/independent-fix-closure.json)
materializes isolated original/corrected layouts with **identical current tests**.
The original production bytes come from `b6dd0b5`; corrected bytes are bound to
six source/test hashes. The comparison made no source edits or live calls.

| Item | Original source under current regressions | Corrected source | Accepted boundary |
| --- | --- | --- | --- |
| R01 scratch recovery | Two generated-layout acceptance errors and one dependent assertion failure | 64/64 tests pass; signed children, missing disk signatures, wrong serials and unrelated/UNKNOWN/duplicate findings remain rejected | Local source correctness verified; delivery remains open. Do not run a real disk recovery merely to verify this fix |
| R02 SMART loop | Exact documented command masks the first disk's failure | Eight short/long scenario runs pass: early, late, multiple failures and success; all eight whole disks attempted, partition aliases excluded, individual exit results asserted | Local versioned target verified; delivery and live cron agreement/scheduling acceptance remain open |

The previously passing lint/type receipts match unchanged source hashes and
were reused. Baseline formatter failures remain outside the changed lines, not
reported as a formatting pass. Live TrueNAS output suppression was documented,
not refreshed: locally printing per-disk exit codes does not prove the guest
retains or exposes them. The already-retained live acceptance must obtain
observable per-target results through an approved mechanism as well as command
and unchanged-schedule read-back. Do not declare R02 fully closed from its shell
exit status alone.

### Every reconciled obligation has a bounded disposition

| Ledger item | Verified closure or slice | Retained work / unresolved limit |
| --- | --- | --- |
| R01 | Independent local source regression closure | Deliver identified source revision; no deployed recovery claim |
| R02 | Independent local versioned-command regression closure | Delivery; authorized live command/schedule agreement and observable per-disk scheduling results |
| R03 | Later versioned backup plan meets the review's plan-level requirement | Forge thread remains unresolved; recording its substantive closure is not backup execution |
| R04 | October 16 exact restoration of the failed attempt | Qualification/recovery carrier contract and physical cause remain open; no fresh retry |
| R05 | Current native export/custody binding, real UniFi restore and specifically observed client tests | Full restore-scope fidelity and representative forwarding; unused Site Magic key difference needs agreed disposition, not an invented regeneration diagnosis |
| R06 | Specifically observed isolation and cellular VPN cases | Remaining agreed route/firewall/admin rows and desired/live reconciliation |
| R07 | Managed-client identity slice only | Ordinary approved-client/EE/browser chain and lifecycle, effective external IPv4/IPv6 exposure and responder attribution |
| R08 | Planning-only scope decision and destination class | Independent backup/restore implementation remains deliberately deferred; unique-data promotion gate stays closed |
| R09 boot | No new closure | Deferred independent boots, recovery media and serial-specific reconstruction; observed paths are not tested boots |
| R09 DIMM | No new closure | Deferred module identification and gated capacity/diagnostics, or explicit not-pursued decision |
| R10 | Complete captured artifact/ref accounting | Undelivered code, two later commits and unknown edit ownership remain; do not overwrite shared work |
| R11 UniFi | Existing receipt inspected: dated authorized revocation/replacement/custody observations | Preserve identity/provenance limits; not a new authentication test and not TrueNAS rotation proof |
| R11 TrueNAS | No independently established credential/private-key rotation closure | Operator/key custodian identifies corresponding non-secret revocation/replacement receipts before any further action |
| R12 PoE | Failed investigation recorded | Not repaired, not abandoned by age; operator decides whether PoE is still required before reopening hardware work |
| R12 firmware patch | Not pursued within the delivered analysis scope | No flashed artifact promised by that scope; no new firmware project created |
| R12 workbench sizing | Original sizing/order superseded by accepted ADR0007 | Do not implement the obsolete 80-GiB hypothesis |
| R12 prototype benchmark/migration | No closure located | Operator decides whether a surviving original workload/benchmark request exists; no new benchmark is presumed |
| R12 PVE upgrade / remote state | Existing deferrals preserved | Not prerequisites invented for the accepted local bootstrap; reopen only through their separate decisions |
| R12 Fedora question | Later dated running/DNS/HTTPS slice answers point-in-time usability | No future no-teardown guarantee or unique-data promotion inferred |
| R12 stop/hold history | Later specific resumption/attempt authority identified | Earlier stops are not retrospectively invalidated and another live attempt is not authorized |
| Groups 8/9 | Every individual task remains in section 4 | Later platform/operations work remains retained behind its existing prerequisites; not retired by M7 focus |

### Every coverage gap remains explicit

| Gap | Reconciled state | Owner and next decisive action | What would close or narrow it |
| --- | --- | --- | --- |
| G1 index admission | Confirmed snapshot mismatch; 289 native Codex identities absent, originals present | Audit engineer/history maintainer: compare owning-source identity/receipts, using direct originals without altering stores | A complete readable source-to-index or direct-source accounting; no harness repair is a prerequisite invented for infrastructure acceptance |
| G2 unreadable/unclassified task provenance | 283 encrypted task payloads identified; partial disposition map still leaves 285 sessions unclassified | Operator/owning harness: supply readable original task material if available; otherwise retain the limitation | Evidence-backed worker-request-to-result accounting, or an explicitly narrower audit claim; no decryption guessing or final-message closure |
| G3 cross-path/legacy coverage | Known candidates and all saved global metadata identities accounted for; unnamed/deleted/legacy scope still unproved | Audit engineer/operator: establish the owning repository/path lineage and readable history boundary | Exhaustive source lineage within a declared boundary; title/path absence alone cannot close it |
| G4 independent acceptance evidence | Selected raw proofs and local fixes verified; many historical receipt contents, CI and runtime claims remain unqualified | Implementing engineer: locate original acceptance outputs for a retained criterion, not rerun every old check | Source-bound independent evidence for that criterion; unavailable CI/live evidence stays unavailable rather than green |
| G5 ownership | All 605 dirty-path occurrences retained; 50 skill/command deletion occurrences are two copies of 25 paths with unproved removal intent | Originating engineer/operator: establish intent and ownership before selective delivery | Explicit provenance/disposition for each selected edit; no reset, restoration or blanket cleanup from filename inference |

### Reportable outcome

**Verified closures:** two local source/target defects and one plan-level review
requirement, plus the bounded dated runtime slices named above. Their delivery,
deployment and whole-milestone limits are separate.

**Deliberately retired/superseded scope:** the stale active off-site execution
goal and original workbench sizing/order. The firmware patch was not pursued in
the analysis scope. **The independent-backup obligation itself was not retired.**

**Retained work:** delivery/live acceptance limits of R01/R02, R04–R11 and later
Groups 8/9, with the existing backup/boot/DIMM deferrals and operator decisions.
No unrelated implementation was added by this reconciliation.

**Unresolved uncertainty:** G1–G5 and the specifically named fidelity, carrier,
external-exposure, credential and prototype-scope limits. Every captured record
is accounted for, but semantic historical coverage remains incomplete. Neither
“all obligations closed” nor “all source gaps resolved” is a supported claim.

## 9. Local delivery preparation — October 21

The operator approved proceeding with separate fix commits and audit
documentation, preparing for integration without publication, merge or live
changes. The two source revisions are now identified:

- `71f17b2` — `fix(storage): accept cleared children in scratch recovery` (R01).
- `976d99e` — `fix(storage): preserve per-disk SMART scheduling failures` (R02).

Both commits contain their corresponding regression tests. The committed source
bytes match the independently reviewed and verified evidence hashes. After both
commits, the 64-test Python suite and eight SMART regression scenarios passed
again. The existing source-bound lint/type/syntax evidence remains applicable;
the pre-existing whole-file formatting limitation is unchanged.

A fresh fetch found `upstream/main` still at `1687796`. A non-checkout
`git merge-tree --write-tree HEAD upstream/main` preview succeeded without
conflicts. Its only upstream changes since the audit base concern
`docs/r720-execution-plan.md`; no merge, rebase or primary-checkout write was
performed. This checks mergeability, not integrated runtime acceptance.

The audit documentation is a separate commit from the fixes. Ignored private
inventories and receipts remain local and are not staged. Earlier statements of
“no commits” describe the audit/fix-verification phase, not this later delivery
preparation. Local commits identify the source revisions; publication and
integration remain pending, and R02 live command/schedule read-back and
observable per-disk acceptance remain open. All G1–G5 limits and backup/boot/DIMM
deferrals survive this step.

## 10. Post-merge continuation — October 21

PR [#33](https://github.com/mpeter/homelab-infra/pull/33) merged at
`b05e3678e64f476e1e8c7caac38365ff391c420a`; local `main` contains all four task
commits. This closes the source-delivery portion of R01/R02, not R02 runtime
acceptance or R04–R11. Sections 1–9 retain their original dated claims.

The former audit worktree has been removed. Its private evidence is preserved
at `/home/mpeter/work/homelab-infra-audit-evidence/closure-audit-2026-10-18/`.
All 40 manifest entries matched their hashes on this continuation; 41 files
are present including the manifest. Earlier S links remain historical
machine-local references, not missing files to fabricate or republish.

Fresh read-only TrueNAS queries confirm Cron IDs 1/2 still use the predecessor
commands; their enabled state and original schedules remain intact. All eight
expected Crucial serials are reported in `tank`. Normal CA/name TLS succeeds
with a process-local address override; local DNS resolution currently fails.
At that initial read-only checkpoint no guest writes or SMART starts occurred.
Subsequently, operator-approved temporary precheck job 18191 captured all eight
serials with acquisition status 0, no active self-test, and two-/thirty-minute
short/long durations. The downloaded 24,772-byte capture matched its native
digest. An oversized cleanup command was explicitly rejected without applying;
an independently reviewed, operator-approved shortened amendment then cleaned
the files (job 20014). Independent native read-back confirms temporary cron ID 5
and its directory absent, permanent jobs unchanged, and `tank` healthy/ONLINE.
One REST-API deprecation warning remains; it was not dismissed. No task SMART
starts, DNS changes or service enablement occurred.

PR [#34](https://github.com/mpeter/homelab-infra/pull/34), merged at
`350719594670f743caab90f3935e1c968667a565`, additionally fixes middleware stdout
suppression for the aggregate commands. The original command fails the updated
suppression regression; the grouped command passes all eight scenarios. The
installed constructor's actual redirection suffix was independently checked.
Source review, shell syntax, whitespace and scoped secret scan passed. Local
`main` contains that merge. At this preparation checkpoint, live cron command
fields still used the predecessor.

See [SMART live acceptance](smart-live-acceptance.md) for source binding,
precheck receipts, exact v4 packet, bounded window and recovery requirements.
At this preparation checkpoint, the full command update and short/long window
were unapproved. Section 11 records the subsequent authorized acceptance.
Local preparation or middleware job success alone does not satisfy R02.

Five hash-bound focused resident regressions passed from an isolated source
copy for R04. Those synthetic tests address a different layer from the actual
October 16 caller and do not establish its carrier-recovery fix. Hash-identical
copies of the historical failure triplets were located in retained native
`inventory/local` custody after their old scratch paths disappeared. Subsequent
current-source replay confirmed the actual defect and both carrier transitions;
section 11 records that result. No live retry or persistence test was repeated.

The primary checkout and the dirty native-recovery worktree remain untouched.
G1–G5, restore fidelity, route/client, carrier, TLS/exposure and credential
limits remain open. Independent backup, boot/DIMM and Groups 8/9 remain gated.

## 11. Authorized SMART acceptance and retained recovery gap — October 21

**R02 technical acceptance is established.** The operator approved the exact
v4 packet, SHA-256
`0020a28a7c861744c1492c55c7203922260104e7fe0845955c3ad9a0027303e7`.
The window began at `2026-10-21T20:04:33.951550Z`; final native verification
completed at `20:43:38.039740Z`, before its one-hour deadline. No disk fault,
SMART abort, reboot, service enablement or network write occurred.

The live commands in TrueNAS Cron IDs 1/2 now exactly match merged source
`350719594670f743caab90f3935e1c968667a565`. Only command fields changed;
root ownership, enabled state, descriptions, original schedules and stdout/
stderr settings remain unchanged. Source-bound offline regressions establish
early/multiple failure propagation and continued individual target reporting;
no live failure injection was performed.

| Accepted live slice | Source-bound evidence |
| --- | --- |
| Eight exact Crucial serials; fresh idle/health/duration admission | Precheck native job 20092; all acquisition statuses 0, health PASSED, short/long durations 2/30 minutes |
| Short scheduling, independently of middleware status | Job 20104; eight actual start acknowledgements, per-serial exit 0 and aggregate 0 |
| Short completion | Job 20114; all eight latest short logs completed without error, health PASSED, query/status 0 and no active test |
| Long scheduling, independently of middleware status | Job 20122; eight actual start acknowledgements, per-serial exit 0 and aggregate 0 |
| Long completion | Job 20191; all eight latest extended logs completed without error, health PASSED, query/status 0 and no active test |
| Exact command/settings, final health and cleanup | Raw native reads confirm source agreement, unchanged non-command fields, `tank` ONLINE/healthy with scan FINISHED, all five used capture directories ENOENT, and exact disabled temporary Cron ID 6 deleted and independently absent |

Both self-test histories gain one corresponding entry per serial while
preserving prior rows. Actual short read-back begins at `20:08:23Z`,
122.821552 seconds after its conservative post-success anchor. Long read-back
begins at `20:39:33Z`, 1804.618597 seconds after its conservative anchor.
All five actual capture/native-digest pairs match. Private receipts remain at
`/home/mpeter/work/homelab-infra-audit-evidence/closure-continuation-2026-10-21/approved-live-v4/`:

- `independent-drive-evidence-validation.json`, SHA-256
  `88048b7cad7258149f6e80606334587c25a99f76705f0b8d7448acebab03e41a`.
- `final-acceptance-readback.json`, SHA-256
  `7539f5a5bf9b6ae9aec86cf1809a7b80517feb092d26b37917be8e01506c291f`.
- Long raw capture SHA-256
  `9c8fd8b7f0c4973122e0598a80102aebffb332759b02d8bd8cb5a7c0fc8527fd`.
- `final-evidence-review.json`, SHA-256
  `b56c84cb13aa4cc59ea6d377a674cae7564fb0e4de76db6eaf1c5b3341d5965c`.

Independent evidence review found the original R02 criteria met, without live
calls or repeated tests. This is **manually dispatched exact-command
acceptance**, not natural cron firing or notification delivery. The existing
RESTAPIUsage deprecation warning remains undismissed. Normal CA/name TLS used a
process-local address override; system DNS is not reported repaired.
Earlier admission metadata/download/ENOENT responses were not all retained.
Successful checked cleanup commands and final raw read-backs establish current
cleanup, not reconstructed earlier provenance. The task-owned credential
transport process and orphan socket were also removed. Result documentation
still follows normal reviewed integration; this technical result does not
close the larger ledger or turn unavailable historical CI into passing CI.

**R04 remains open with a reproduced, source-bound defect.** The offline
`r04-actual-replay.json` receipt SHA-256 is
`bec68667a5ecc6f7ad699df84040570e8e8f693dc172fbced3815d410faf3017`;
all 91 referenced path/hash bindings independently matched. All three failed
command-15 captures pass exact configuration and six-VLAN invariants, then
reject primary Up/Listen or Up/Forward under the qualification-only Down guard.
Automatic inverse calls that same guard before its first journal append.
Thirty-six restoration receipts plus the unjournaled tag transition confirm
primary Up→Down during inverse while exact invariants hold; final running and
startup match baseline `01b4a646e764f2874a2310b7e0efd1622f779f230d1d77a41a176b720a327eff`.

Single-pass source review recommends separating strict qualification from a
state-parametric restoration guard at every inverse boundary, with bounded
fresh-read settling rather than treating Listen as forwarding. Settle bounds,
protected recovery/proof budgets and integrated consumer regressions are not
yet accepted. No corrected caller, widened qualification, new live attempt or
physical-cause diagnosis is claimed. R05–R07/R10/R11 and all historical coverage
limits remain separate retained work; existing deferrals remain gated.
