---
title: Implement independent second-site backup and tested recovery
type: enhancement
severity: high
status: open
created: 2026-10-03
labels: []
---
The R720 has one compute host and site. TrueNAS VM 200 and Fedora VM 100 run there, and the operator confirmed on 2026-10-03 that no second-site ZFS receiver exists. The same-R720 TrueNAS copy planned in `docs/backup-recovery.md` can help with an isolated local failure but cannot recover from loss of the R720 or site. This full independent-backup implementation is deferred from `openspec/changes/build-r720-homelab`; the active change prepares only the bounded interim implementation plan, and must not claim a backup has run, host-loss recovery, or promotion of unique NAS/Fedora data.

ADR 0013 selects a locally operated ZFS receiver at a separate site as the destination class. It does not select a host, site, transport, retention, key-custody design, or VM archive format. Keep that decision unless a separately reviewed change supersedes it. Do not purchase hardware or a hosted service from this backlog record.

Future work:

1. Identify and provision the actual receiver and independent site. Verify owner, power, recovery access, OS/OpenZFS support, disk serials, pool health, usable capacity, and space for retention and restores. Measure R720 upload, data size/change rate, first-seed duration, and the routed/firewalled path.
2. Choose restricted transfer identities, endpoint/host-key verification, receive paths, encryption boundary, and revocation/recovery procedure. Keep credentials and decryption material outside Git and recoverable independently of the R720, receiver, and laptop's sole disk. Test key recovery.
3. Implement encrypted NAS dataset and appliance-configuration copies. Verify destination-side presence, freshness, integrity, retention, capacity, and missed-job alerts. From an independent recovery host, restore a representative file and appliance configuration using only the remote copy and separately held material.
4. Implement full Fedora VM archives with a measured staging budget and transfer window. Verify an archive at the receiver. Through the versioned restore-test exception, restore to an isolated scratch VM ID with its NIC absent or down, boot and inspect it, then remove it and verify no orphan disk or configuration. Record that a same-host format test alone does not prove host-loss recovery.
5. Extend the proven pattern to important RHEL VMs, AAP, IdM, OpenShift, network/controller exports, OpenTofu state, PVE host configuration, rescue media, and recovery keys as those services are introduced. Exercise representative file, VM, configuration, and host-loss recovery with a non-destructive target and explicit recovery order.
6. Only after the respective destination-copy and independent-restore gates pass, separately authorize incremental unique-data migration and Fedora primary-workspace promotion. Retain an authoritative copy elsewhere during the trial, and apply the health, capacity, backup, and 14-day workload gates already documented for Fedora.

Receiver readiness also includes a tested read/write path to a dedicated test target, a supported recovery host, independent power and access, measured seed bandwidth, documented retention and restore procedures, and delivered alerts for stale or missing copies. Initial retention for review is seven daily, four weekly, and six monthly points; size and change-rate measurements must determine the final policy.

The current OpenSpec change owns a same-host interim backup implementation plan and the explicit prohibition on treating that copy as independent recovery. Existing narrow OpenTofu state/key recovery and network-configuration backup gates remain in their current owners.

**Done when:** A real second-site destination holds encrypted NAS and full-VM recovery points whose freshness, integrity, retention, and alert delivery are verified; representative remote-copy restores succeed with independently held credentials and keys; later services have appropriate recovery coverage; and the evidence is recorded before any unique-data or primary-workspace promotion.
