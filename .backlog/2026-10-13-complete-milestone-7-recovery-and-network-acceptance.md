---
title: Complete Milestone 7 recovery and network acceptance
type: chore
severity: high
status: open
created: 2026-10-13
labels: []
---
Milestone 7 remains open at 26/38 OpenSpec tasks. Tasks 7.2, 7.6 and 7.7 are incomplete. Resume from `.planning/handoffs/2026-10-13-m7-closure.md` and the ordered execution plan `.planning/docs/milestone-7-goal.md`; the bounded Brocade qualification is `.planning/docs/native-trunk-qualification.md`.

Accepted work to retain: PVE IPv6 management isolation and R8 persistence/current-source preflight. Do not repeat accepted R8 persistence. The exact PVE DNS update plan passed `check-management-dns-plan.sh --pve-update` with one change from `192.168.0.190` to `10.72.10.10` and zero additions/deletions; no apply occurred. Before applying, obtain a fresh native UniFi backup, rerun the plan gate against current state, apply, and verify controller, gateway and workstation DNS read-back. The logged-in UI displays `sarah.matt.email@gmail.com`, which differs from the confirmed personal account `sarah.matt.mail@gmail.com`; establish the correct account/console before backup. No new backup or controller mutation was made.

Current-source Brocade read-only preflight and 691 tests passed, but the unsaved forward/inverse qualification and post-inverse guest proof require verified authorized PiKVM serial access. Workstation SSH was denied; direct PiKVM HTTPS has an untrusted certificate with no pinned fingerprint. Stop credential searches; establish the trusted access path before any switch write. The controller read-back currently shows VLAN 10 only; VLANs 20/30/40 and clients are absent, so their route/firewall matrix rows cannot be qualified against live endpoints yet. The workstation has no VPN connection. Current PVE SSH also needs a verified host-key mapping before guest-agent route probes.

Complete the remaining real-client route/firewall matrix and desired/live reconciliation; finish qualified Brocade forward/inverse recovery; complete a real UniFi backup/restore validation; and close VPN acceptance, iDRAC certificate lifecycle and WAN exposure checks for 7.7. Update OpenSpec only for criteria supported by passing evidence. Then run the repository's normal commit, PR and merge process. Stop before Milestone 8 and deferred Group 5 backup work.

Private evidence is referenced in the handoff and remains under `~/.cache/agent-scratch/`; do not commit those receipts or secrets.

**Done when:** OpenSpec tasks 7.2, 7.6 and 7.7 are closed using current passing evidence; the applicable restore/recovery checks succeed; remaining in-scope route, VPN, certificate and exposure criteria are reconciled; and the resulting change completes normal repository delivery. Do not mark Milestone 7 complete while any of these acceptance conditions lacks evidence.
