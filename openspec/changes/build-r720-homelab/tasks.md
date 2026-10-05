## 1. Refresh the host baseline

- [x] 1.1 Recheck PVE/iDRAC versions, boot and management access, `rpool` and `fast-vm`, memory/SEL health, and inventory timestamps against the Phase 0 evidence.
- [x] 1.2 Verify the off-host host-configuration bundle, console/rescue access, and `fast-vm` serial-specific drift check; record discrepancies before further live changes.
- [x] 1.3 Review the deferred PVE upgrade as a separate maintenance decision; keep the versioned repository configuration at a no-drift read-back.

## 2. Establish the Proxmox control plane

- [x] 2.1 Complete ADR 0009's encrypted laptop-local Proxmox state bootstrap; test local lock contention, ciphertext, and recovery of a second encrypted state copy and passphrase from a separate location. Record that local locking does not coordinate other machines and defer any remote-backend migration to a reviewed, tested change.
- [x] 2.2 Implement and verify a scoped PVE automation identity and versioned host check/apply path; prove allowed VM operations and denied host/storage-admin operations.
- [x] 2.3 Pin OpenTofu/provider versions, implement the Proxmox VM root/module, and test plan-JSON resource/action safeguards with positive and negative cases.
- [x] 2.4 Confirm the Git remote and protected-branch review policy; scan the reviewed source and saved plans for secrets and state before the first VM apply.
- [x] 2.5 Recheck image, cloud-init, bridge, guest-agent, and `fast-vm` paths; apply a reviewed disposable-VM plan, verify boot and no-change plan, then review its destroy and check for orphans.

## 3. Deploy the reproducible Fedora VM

- [x] 3.1 Reconcile live memory, SEL, boot-device health, datastore headroom, address/DNS, and the staged Fedora image; record the final VM allocation from observed capacity. Stop creation on an uncorrectable memory error, rising correctable count, SEL memory event since the last DIMM change, or unattributed iDRAC Critical condition; record disposition of the current Critical alert. User waived the broken chassis-intrusion sensor alert as a blocker after fresh read-back isolated it as the sole asserted sensor; no safely scoped iDRAC control was available to disable only that alert.
- [x] 3.2 Define and create an initially empty Fedora VM in OpenTofu; verify live CPU, memory, boot disk, network, guest access, and a no-change plan.
- [x] 3.3 Add laptop-runnable guest configuration with check mode and live read-back; keep unique development data off the VM until task group 5 passes.

## 4. Deploy the NAS without conflating VM and disk gates

- [x] 4.1 Refresh all eight SATA serials, signatures, SMART data, by-id paths, HBA/IOMMU membership, host boot path, and recovery console evidence. The operator has authorized disposal of the existing contents on all eight SSDs; preserve that decision and verify each exact serial before any destructive action. Stop if a disk identity is uncertain or the IOMMU group includes a host-required device.
- [x] 4.2 Select and verify the NAS OS/release and image; use versioned Proxmox PCI resource mapping with preview/check/apply/rollback and a fail-closed live driver-state check. Verify that the scoped PVE identity can assign PCI through the resource mapping; do not widen routine token scope. See [ADR 0012](../../../docs/decisions/0012-keep-nas-hba-on-demand-vfio.md).
- [x] 4.3 Budget pinned NAS RAM and `fast-vm` capacity alongside Fedora and later important VMs; define the NAS VM with whole-HBA passthrough, apply a gated plan, and verify guest serials/SMART, host exclusion, and denied mapping-administration operations for the routine identity.
- [x] 4.4 Test NAS VM start/stop/reset and host cold boot; verify `rpool`, `fast-vm`, HBA assignment, guest serials, and rollback without writing SATA data. The host check fails closed on incorrect HBA binding; post-cold-boot binding and host-import checks pass, with no kernel change since that test.
- [x] 4.5 Reconfirm every exact SATA serial, save and hash-check off-target GPT and ZFS-label metadata captures, and review the destructive guest pool plan. These captures are metadata evidence, not full data backups; see `docs/nas-implementation-plan.md` and the private capture record.
- [x] 4.6 Create the eight-disk RAIDZ2 pool in the guest; verify topology, health, mountpoints, usable capacity, scrubs, SMART scheduling, snapshots, and alert behavior. Confirm the host does not import or register the guest pool. `tank` is ONLINE with `ashift=12`; the initial scrub and short SMART test passed, scheduled SMART and snapshot tasks were created and read back, and Proxmox does not import the guest pool. Alert UI state is clear; TrueNAS SMTP delivery remains disabled pending trusted certificate-identity verification. PVE email delivery is recorded in task 9.3.
- [x] 4.7 Define `tank/smb_test` and `tank/nfs_test` with explicit ACLs and 5 GiB quotas; expose SMB/NFS test shares to the authorized workstation only; verify authenticated and denied access, 64 MiB I/O, and matching data after guest and PVE host restarts. Remove the reproducible test file afterward. The DHCP address, trusted certificate identity, and final client boundary remain open under task 7.1; these test shares carry no unique data.

## 5. Prepare a backup implementation plan within current constraints

No second-site receiver exists. This group prepares an executable plan for
on-demand same-R720 copies of the reproducible Fedora VM and encrypted PVE host
bundle; it does not run a backup or satisfy host-loss recovery. The
[deferred independent-recovery backlog item](../../../.backlog/2026-10-03-implement-independent-second-site-backup-and-tested-recovery.md)
owns receiver provisioning, remote copies and restores, wider coverage, and
unique-data promotion. Until that work passes, Fedora and NAS hold only
reproducible/test data.

- [x] 5.1 Finish the [interim backup implementation plan](../../../docs/backup-recovery.md#interim-same-host-truenas-backup-plan--2026-10-03) for VM 100 and the encrypted PVE bundle. Specify current constraints, versioned owners, trusted endpoint and dedicated-target prerequisites, capacity and key custody, ordered implementation steps, preflight/stop behavior, ciphertext verification, isolated local restore acceptance, rollback, and the remaining host-loss limitation. Reviewed as a plan only on 2026-10-03; no backup or live change was performed.
- [x] 5.2 Record the full second-site backup and restore implementation in the backlog, reconcile the active proposal, design, specs, tasks, and project plans to that scope, and retain the explicit no-unique-data promotion gate. OpenSpec strict validation, backlog schema check, local link targets, and diff check passed on 2026-10-03; no remote backup or restore was marked complete.

## 6. Storage health and capacity acceptance

Operator scope update (2026-10-05): former tasks 6.1 (optional DIMM expansion)
and 6.2 (prove Proxmox can boot if its current boot SSD is unavailable, with
recovery media and a serial-specific procedure) were removed from this active
change and moved to the [DIMM backlog item](../../../.backlog/2026-10-05-complete-r720-dimm-expansion-after-module-identification.md)
and [boot/recovery backlog item](../../../.backlog/2026-10-05-document-and-prove-independent-r720-boot-and-recovery.md).
Their dated host and EFI observations remain in inventory as evidence, not
current acceptance gates. Task 6.3 remains complete; task 6.4 remains active.

- [x] 6.3 Create the disposable `scratch` tier only after serial-specific classification and reviewed storage preflight; verify it cannot be mistaken for durable data storage. The accepted 14:06 EDT read-only scan (`scratch_candidate_preflight_140648` in `inventory/storage.yaml`) followed live `strace` verification that candidate block devices were opened read-only by `blkid`, `blockdev`, `dd`, `smartctl`, and the importable-pool scan. `front-nvme-c` (`PHHH8505034Q512H`) was BLOCK with GPT, EFI, an old ZFS member, and its old pool visible as importable. `front-nvme-d` (`BTHH8244042V512D`) had no partitions or recognized signature and a zero first 8 MiB, but its last 8 MiB contained non-zero data, so it was BLOCK and was not classified as blank. The full scan found no mounts, swap, holders, imported-pool, host-configuration, or firmware references to either candidate, and all positive controls were present. A separate 14:13 EDT workstation scan of all five versioned OpenTofu source files found no `scratch` pool or storage reference. Local three-state checker tests cover serial binding, imported-pool enumeration, ESP identity, SMART validation, and fail-closed reporting. At that scan, no data was classified disposable and no off-target metadata had been captured. At that scan, no label clearing or pool creation was performed or authorized. The historical checker run using `proxmox-boot-tool status` remains invalid because that command may mount ESPs.
  A fresh serial-bound read-only preflight at 17:20:22 EDT returned BLOCK with no UNKNOWN findings. `front-nvme-c` was still partitioned, signed, non-zero at both boundaries, and discoverable as an importable old ZFS pool; `front-nvme-d` had no partition or recognized signature but retained non-zero tail bytes. Identity checks, SMART health/error/spare probes, reference checks, and required positive controls passed; see `scratch_candidate_preflight_172022` in `inventory/storage.yaml`. The checker did not classify data, capture headers off-target, or authorize writes. At that checkpoint, 6.3 remained open pending operator data disposition and its write/recovery gates.
  A strict-host-key serial-bound preflight at 20:10:45 EDT returned BLOCK with no UNKNOWN findings; `front-nvme-c` still had three partitions, GPT/EFI/ZFS signatures, and an importable old pool, while `front-nvme-d` still had non-zero bytes in its last 8 MiB. All identity, SMART, reference, and positive-control checks passed; see `scratch_candidate_preflight_201045` in `inventory/storage.yaml`. At 20:13:19–20:13:22, the first and last 8 MiB of each serial-verified candidate were captured with read-only `dd` to private workstation scratch; hashes and permissions are recorded as `scratch_boundary_metadata_capture_201319`. The bytes were not parsed or classified and are not a full backup. At that checkpoint, task 6.3 remained unchecked pending operator content disposition, reviewed clearing scope, and separate write/recovery gates; no candidate write or pool creation had occurred yet.
- [x] 6.4 Measure pool health, scrubs, SMART tests, quotas, capacity thresholds, and representative device-failure procedures for each implemented host tier. A strict-host-key read-only capture at 11:17 EDT on 2026-10-03 found `rpool` and `fast-vm` ONLINE with no known data errors, all five host-owned SMART health results PASSED, no scheduled host SMART self-tests or logged tests, no active scrub scan, and PVE storage usage below 1%. A focused read-only PVE check at 11:51 EDT found only `rpool` and `fast-vm` imported on the host and `zpool status -x` reported all pools healthy; it did not refresh SMART details or scrub configuration. A fresh 14:52 EDT read-only host collector again found both mirrors ONLINE with no known data errors; all four pool NVMe members and the boot SSD reported SMART PASSED, PVE storage usage was 0.62%, 0.94%, and 0.00%, and `smartd` had no scheduled self-test directive. A 14:53 status read found no active scrub scan. The `check-fast-vm.sh` baseline passed; see `pve_storage_health_readback_1452` in `inventory/storage.yaml`. At the 2026-10-03 checkpoint, no host capacity alert threshold or device-failure exercise was verified. A 14:47 personal-Chrome recheck reached VM 200 details but not noVNC and submitted no guest command; see `truenas_console_access_recheck_1447`. At 14:58 EDT the noVNC root prompt was visible after the operator reset the shell and selected option 8; `midclt call alert.list` produced no visible result, Enter handling remained misrouted, and execution is unconfirmed. View Only was restored; see `truenas_console_input_attempt_1458`. A managed PVE VM 200 console read on 2026-10-03 found `boot-pool` and `tank` ONLINE with zero known data errors, a zero-error scrub on 2026-10-02, an empty alert list at that historical read, and 5 GiB quotas on both setup shares. The operator reset the shell and selected Linux CLI option 8; a 14:27 EDT focused chrome-use attempt could not target noVNC's hidden input, did not submit a guest command, and restored View Only. A 14:28 EDT read-only TLS handshake to the recorded TrueNAS address `192.168.0.186:443` observed a self-signed iXsystems leaf with `CN=localhost`, SAN `DNS:localhost`, and a hostname mismatch for the IP; see `truenas_tls_identity_readback_1428` in `inventory/storage.yaml`. This records the served certificate but does not verify TrueNAS's configured certificate or provide a trusted identity. At 15:21 EDT a PVE VM 200 config GET showed `agent=enabled=0`, and the 15:23 EDT noVNC retry still could not deliver the alert query; no guest command ran and View Only was restored. A fresh strict OpenSSL check at `192.168.0.186:443` failed trust validation (self-signed) and returned a different certificate fingerprint from the 14:28 observation despite the same serial, subject, issuer, and dates. The 15:31 EDT ARP reply for `192.168.0.186` matched VM 200 net0 MAC `BC:24:11:87:F2:2B`, corroborating the current endpoint-to-VM link. The earlier 14:28 endpoint mapping was not checked, so the fingerprint difference cannot be conclusively assigned to a certificate replacement on this VM; see `truenas_vm_config_readback_1521`, `truenas_console_input_attempt_1523`, `truenas_tls_endpoint_readback_1523`, and `truenas_endpoint_mac_readback_1531` in `inventory/storage.yaml`. As of the 15:31 EDT checkpoint, the active alert list had not yet been refreshed; the 17:00:36 EDT read below supersedes that statement and returned `[]`. TrueNAS SMART schedule/history, a fresh alert read at acceptance, guest capacity, serial-specific guest member mapping, configured capacity thresholds, trusted endpoint identity, and failure-procedure acceptance remain open. A 15:45 EDT noVNC retry using fresh frame-local references still routed Enter to the parent iframe; command execution is unconfirmed, View Only was verified true afterward, and the hidden buffer was cleared. See `truenas_console_input_attempt_1545` in `inventory/storage.yaml`. At 15:54 EDT, after the operator reported resetting the shell and selecting Linux CLI option 8, a fresh screenshot was black; a focused frame-1 attempt still routed Enter to the outer PVE iframe, with no guest command result. View Only was verified true and the hidden input was cleared to its underscore placeholder; see `truenas_console_input_attempt_1554` in `inventory/storage.yaml`.
  A fresh authenticated TrueNAS WebUI read at 02:35–02:40 EDT on 2026-10-04 showed `tank` ONLINE, 0 of 8 disk errors, 5.03 TiB free, the Sunday 00:00 scrub schedule and zero-error Oct 2 scrub, and no active alerts. The disk list showed all eight tank serials but no SMART health/test history. Data Protection showed one enabled seven-day local snapshot task and no cloud or remote-replication task rows. The instance API docs identify v25.10.5 while the UI reports 25.10.7; searching `smart` found only the unrelated `SMARTCARD_LOGON` certificate field and no documented SMART-test method. This does not establish SMART history, alert delivery, capacity threshold/cadence, or failure handling; certificate trust remains unresolved despite the prior object/leaf fingerprint match. See `truenas_webui_readback_0235` and `truenas_certificate_object_match_0221` in `inventory/storage.yaml`. Keep task 6.4 open.
  A 16:16 EDT VM 200 console attempt after the operator selected Linux CLI option 8 initially showed the root prompt, but the alert query produced no visible result and execution remains unconfirmed because Enter was routed to the outer PVE iframe. View Only was restored; see `truenas_console_input_attempt_1616` in `inventory/storage.yaml`.

  At 16:46 EDT, a new screenshot showed the TrueNAS root prompt before input, but chrome-use could not enter `midclt call alert.list`; the noVNC hidden keyboard field stayed at its underscore placeholder, no Enter was sent, and execution is unconfirmed. View Only was returned to false after the operator reported typing was blocked. At that checkpoint, alerts and configured certificate identity remained unverified; the alert status was refreshed at 17:00:36 EDT as recorded below, while configured certificate identity remains unverified. See `truenas_console_input_attempt_1646` in `inventory/storage.yaml`.

  At 17:00:36 EDT, the operator entered the read-only `midclt call alert.list` command in the VM 200 Linux Shell; the console returned `[]`. This refreshes only the point-in-time alert status. The configured certificate identity, SMART schedule/history, guest capacity, serial-specific guest member mapping, capacity thresholds, and failure-procedure acceptance remain open; see `truenas_alerts_readback_170036` in `inventory/storage.yaml`.

  A fresh 17:13:57 EDT read-only PVE collector found `rpool` and `fast-vm` ONLINE with zero device errors and no known data errors; all four pool NVMe members and the Kingston boot SSD reported SMART PASSED, with no self-tests logged. The active `smartd` policy has no scheduled self-test directive, and the monthly second-Sunday scrub schedule remains configured with no scan entry in either pool's status. A separate 17:17:32 quota read found `quota` and `refquota` set to `none` on all host-pool datasets; `fast-vm` baseline passed. `pvesm status` reported 0.63%, 0.94%, and 0.00% use for `fast-vm`, `local`, and `local-zfs`. See `pve_storage_health_readback_171357` in `inventory/storage.yaml`. Host alert thresholds remain unverified, and no device-failure procedure was exercised; guest measurements and the rest of task 6.4 remain open.

  A fresh 18:11:48 EDT strict-host-key read-only collector again found `rpool` and `fast-vm` ONLINE with zero device errors and no known data errors. SMART health passed for all four pool NVMe members and the Kingston boot SSD; NVMe critical warnings, media/data integrity errors, and error-log counts were zero, with no device self-tests logged. `smartd` was active without a scheduled self-test directive; the monthly second-Sunday scrub remained configured and no scan entry appeared for either pool. A strict-host-key follow-up confirmed no `quota` or `refquota` on host-pool datasets, PVE storage use of 0.64%, 0.94%, and 0.00%, and an unchanged boot ID; `check-fast-vm.sh` passed. Exact evidence is in `pve_storage_health_readback_181148` in `inventory/storage.yaml`. The 18:08:32 EDT VM 200 screenshot still shows `fffc` unsubmitted and no configured-certificate query result; see `truenas_console_input_recheck_180832`. Capacity alert thresholds, representative device-failure procedures, and remaining TrueNAS health/certificate evidence are open; task 6.4 remains unchecked.

  An 18:27:22 EDT strict-host-key PVE read found the default notification matcher in `all` mode targeting `mail-to-root` and `cloudflare-email`, with `zfs-zed` active and its email setting configured. The inspected host had no `/etc/pve/status.cfg`, matching capacity-related systemd timer or root cron entry, or threshold-related file under the listed PVE/ZFS/cron/systemd/local-script paths. This establishes a notification route only, not a storage-capacity threshold. See `pve_capacity_notification_policy_readback_182722` in `inventory/storage.yaml`. A numeric threshold and measurement cadence still need to be selected and implemented/tested; keep the 20%-free Fedora promotion criterion separate unless selected as an alert policy. The later 18:21:44 EDT VM 200 screenshot still showed `fffc` unsubmitted and no certificate-query output; see `truenas_console_input_recheck_182144`. Task 6.4 remains unchecked.

  A 17:48:12 EDT screenshot recheck still showed the TrueNAS Linux Shell with unsubmitted prompt text `fffc` and no certificate query result; Chrome-use's Ctrl+C landed on the parent PVE frame and did not reach the guest. See `truenas_console_input_recheck_174812` in `inventory/storage.yaml`. The read-only configured-certificate query is prepared in `docs/storage-plan.md`, using only the TrueNAS 25.10 API's selected public metadata fields; it has not run against VM 200. Keep configured and served certificate identity unverified until the selected certificate ID and metadata are read back and compared.
  An 18:50 EDT screenshot shows a blank TrueNAS root prompt with only the earlier `midclt call alert.list` output `[]` visible; no configured-certificate query or fresh alert query has run. See `truenas_console_recheck_1850` in `inventory/storage.yaml`. The next console action is to submit the configured-certificate query already prepared in `docs/storage-plan.md`.
  At 19:02 EDT, after the operator reported typing the prepared query, a fresh screenshot still showed a blank root prompt with only the older alert query output; no query echo or result was visible. No console input was sent by the observer. This does not establish whether the reported keystrokes reached noVNC; configured certificate identity and a fresh alert status remain unverified. See `truenas_console_recheck_1902` in `inventory/storage.yaml`. Task 6.4 remains unchecked.
  A further 19:08:15 EDT screenshot still showed the blank root prompt and no new command output. No guest input was sent; the latest executed alert read remains the 17:00:36 EDT `[]`, and configured certificate identity remains unverified. See `truenas_console_recheck_190815` in `inventory/storage.yaml`.
  A strict-host-key read-only PVE capture at 19:09:39 EDT again found `rpool` and `fast-vm` ONLINE with zero device errors and no known data errors. All four pool NVMe members and the Kingston boot SSD reported SMART PASSED; NVMe critical warnings, media/data-integrity errors, and error-log counts were zero, and no device self-tests were logged. `smartd` remained active without a scheduled self-test directive, the monthly second-Sunday scrub remained configured with no scan entry in either pool, and host-pool `quota`/`refquota` remained `none`. PVE storage use was 0.64%, 0.94%, and 0.00%; `check-fast-vm.sh` passed and the boot ID/kernel were unchanged. See `pve_storage_health_readback_190939` in `inventory/storage.yaml`. This collector did not evaluate thresholds or exercise device failure. TrueNAS guest health and configured certificate remain unverified; host capacity thresholds and representative failure procedures remain open. Task 6.4 remains unchecked.
  At 19:20:57 EDT, a strict-host-key PVE read found `smartmontools.service` active (`7.5-pve2`), with a scheduled next check; its startup journal recorded all eight TrueNAS array SSDs among 15 monitored devices, then logged them absent 30 minutes later. A separate current read found VM 200 running, the HBA bound to `vfio-pci`, and only `fast-vm`/`rpool` imported on PVE. The journal does not establish why the drives disappeared or whether TrueNAS monitors them; guest SMART schedule/history remains unverified. See `pve_smartd_scope_readback_192057` in `inventory/storage.yaml` and the interpretation in `docs/storage-plan.md`. At 19:22:40 EDT, a fresh screenshot after the operator reported typing the prepared command still showed only the earlier alert output `[]` and an empty prompt; the latest confirmed alert result remains 17:00:36, and configured certificate identity remains unverified. See `truenas_console_recheck_192240` in `inventory/storage.yaml`.
  The 19:53 EDT host collector regression fixture now preserves a DEGRADED pool state, unavailable member, nonzero device errors, and permanent-error text while confirming capture continues for the other pool. A fresh strict-host-key read-only capture at 19:53:04 EDT found `rpool` and `fast-vm` ONLINE, all five queried host-owned devices SMART PASSED, no logged self-tests, no active scrub scan, no scheduled host SMART self-tests, and PVE storage usage of 0.64%, 0.94%, and 0.00%. Follow-up strict-host-key reads confirmed host-pool quota/refquota `none`, VM 200 running with the HBA on `vfio-pci`, host imports limited to `fast-vm` and `rpool`, and `check-fast-vm.sh` PASS. The current `smartd` status reported its next check at 20:19:38; no journal entries appeared since 19:45, which does not establish a scan result or NAS-device presence. See `pve_storage_health_readback_1953` in `inventory/storage.yaml`. The 19:40:29 EDT screenshot still showed no certificate query; the 17:00:36 EDT empty alert list remains the latest confirmed guest alert read. TrueNAS guest SMART, capacity, member serial mapping, certificate identity, a selected host alert threshold/cadence, and representative failure-procedure acceptance remain open. Task 6.4 remains unchecked.
  At 20:07:24 EDT, a fresh VM 200 screenshot after the operator reported typing showed the exact same image hash and console contents as the 19:40:29 capture: the old alert command and `[]`, then a blank prompt. No new guest command result was verified, so the 17:00:36 EDT alert read remains the latest confirmed result; the configured certificate identity remains unverified. No guest input was sent by the observer. See `truenas_console_recheck_200724` in `inventory/storage.yaml`; task 6.4 remains unchecked.
  At 20:23:16 EDT, the noVNC `View only` setting was read as unchecked, ruling out that toggle as the input blocker but not confirming guest keyboard focus. After closing the settings panel, the screenshot showed a black console canvas with no readable prompt. No guest keys were sent; the alert result remains the 17:00:36 EDT `[]`, and certificate identity remains unverified. See `truenas_console_settings_recheck_202316` in `inventory/storage.yaml`. Task 6.4 remains unchecked.
  At 20:37:07 EDT, after the operator reported typing `midclt call alert.list`, a fresh VM 200 noVNC screenshot showed the command and `[]` at the TrueNAS root prompt. This confirms the operator input reached the guest shell and the alert query returned no entries, though the guest output provides no execution timestamp. The exact cause of earlier focus failures remains unresolved. The screenshot also shows a separate PVE task-error banner for a VM 200 powerdown timeout at 16:37:33 and 16:38:33 EDT; it is not a TrueNAS alert and was not investigated here. Configured TrueNAS certificate identity remains unverified; see `truenas_alerts_readback_203707` in `inventory/storage.yaml`. Task 6.4 remains unchecked.
  At 20:45–20:46 EDT, a focused chrome-use attempt to enter the documented read-only certificate-reference query visibly changed shell punctuation (`|`, `_`, and `{}`), so Enter was not sent and the command did not run. Two Ctrl+C attempts were routed to the outer Proxmox iframe, and the 20:46:10 screenshot showed the unsubmitted line remained. The configured certificate identity remains unverified; the operator must clear the line directly in the guest console before another command. See `truenas_cert_query_input_recheck_204610` in `inventory/storage.yaml`. Task 6.4 remains unchecked.
  At 20:55:10 EDT, a fresh strict-host-key PVE collector found both `rpool` and `fast-vm` ONLINE with zero device errors and no known data errors. All four pool NVMe members and the Kingston boot SSD reported SMART PASSED; NVMe critical-warning, media/data-integrity, and error-log counts were zero, with no SMART tests logged and no scheduled SMART self-test directive. The monthly second-Sunday scrub remains configured; neither pool status showed a scan entry. Host datasets have no finite quota/refquota, and PVE storage use is 0.65%, 0.94%, and 0.00%. See `pve_storage_health_readback_205510` in `inventory/storage.yaml`. This read-only capture does not establish TrueNAS guest health, a selected capacity threshold/cadence, or device-failure handling; task 6.4 remains unchecked.
  A fresh 20:58:44 EDT noVNC screenshot still showed the malformed, unsubmitted certificate-query line at the TrueNAS shell prompt, with two trailing `c` characters and no output or new prompt. Their exact input event is uncertain. Enter was not sent; the operator must clear the line directly before another query. See `truenas_cert_console_recheck_205844` in `inventory/storage.yaml`. Task 6.4 remains unchecked.
  At 21:04:10 EDT, after the operator reported typing the requested input, a fresh noVNC screenshot was byte-for-byte identical to the 20:58:44 image and still showed the malformed unsubmitted line; no output or new prompt appeared. No keys were sent by the observer. The latest confirmed alert output remains `[]` from the earlier guest read, and certificate identity remains unverified. See `truenas_console_recheck_210410` in `inventory/storage.yaml`; task 6.4 remains unchecked.
  A fresh strict-host-key read-only capture at 21:10:52 EDT again found `rpool` and `fast-vm` ONLINE with zero device errors and no known data errors. All four pool NVMe members and the Kingston boot SSD reported SMART PASSED, with zero NVMe critical warnings, media/data-integrity errors, and error-log entries; no host SMART tests were logged or scheduled. The monthly second-Sunday scrub remains configured without a `scan` entry in either pool, no finite dataset quotas are set, and PVE storage use remains below 1%. See `pve_storage_health_readback_211052` in `inventory/storage.yaml`. The collector does not establish TrueNAS guest state, a selected capacity threshold/cadence, or failure handling; task 6.4 remains unchecked.

  A fresh 21:26:08 EDT noVNC screenshot showed an empty TrueNAS root prompt after the operator cleared the prior line. A 21:27:12 chrome-use insertion attempt altered punctuation in the prepared certificate query; Enter was not sent and no result appeared. Subsequent Ctrl+C input was reported as targeting the outer PVE iframe, and a 21:30:48 screenshot still showed unsubmitted shell input. Certificate identity remains unverified; the latest confirmed alert result is still the 20:37 `[]`. See `truenas_cert_console_recheck_213048` in `inventory/storage.yaml`. Task 6.4 remains unchecked.

  A screenshot-only recheck at 21:44:37 EDT still showed unsubmitted certificate-query text at the TrueNAS root prompt without output or a fresh prompt. No further automated console input was sent; configured certificate identity remains unverified and the alert-list result remains the 20:37 `[]`. See `truenas_cert_console_recheck_214437` in `inventory/storage.yaml`. Task 6.4 remains unchecked.

  A strict-host-key PVE collector at 00:09:30 EDT on 2026-10-04 again found `rpool` and `fast-vm` ONLINE with zero device errors and no known data errors; all four pool NVMe members and the Kingston boot SSD reported SMART PASSED. No SMART self-tests were logged or scheduled, the monthly second-Sunday scrub was configured with no active scan, host datasets had no finite quotas, and PVE storage use was 0.66%, 0.94%, and 0.00%. See `pve_storage_health_readback_000930` in `inventory/storage.yaml`.
  A read-only personal-Chrome TrueNAS WebUI review later in the same session confirmed the selected GUI certificate is `truenas_default`, the active alert drawer reports no alerts, and `tank` is an online RAIDZ2 pool with no errors, 5.03 TiB usable capacity, and a last scrub on 2026-10-02 with zero errors. The disk table maps all eight Crucial MX500 serials to `tank`; the inspected pages did not verify guest SMART state or test history. The served leaf is self-signed with `CN=localhost` and only `DNS:localhost` in its SAN; strict OpenSSL verification fails with error 18. The UI was reachable but is not a trusted endpoint. See `truenas_webui_health_readback_0035` in `inventory/storage.yaml`. A raw `system.general.config` response was briefly displayed in the local console view and included private-key/PEM fields; its screenshot was deleted and no values were retained in repository files.
  The UI snapshot does not select a numeric PVE capacity-alert threshold or measurement cadence, and no representative device-failure procedure was run. Guest SMART health/test history, host threshold/cadence, and failure acceptance remain open; keep task 6.4 unchecked.

  A focused read-only WebUI follow-up from 00:58–01:00 EDT on 2026-10-04 inspected Storage > Disks, Data Protection, System > Services, Reporting > Disk, and the Alerts drawer. Disk details contained model/configuration only, service search found no SMART match, and disk reports offered I/O and temperature rather than SMART status or test history; task 6.4's guest SMART evidence remains unverified. The drawer again displayed no alerts. Data Protection showed an enabled local `tank` snapshot task with seven-day retention, daily 23:00 schedule (UI timezone not established), and last state FINISHED about 23 hours earlier; this is local snapshot evidence only, not backup or restore acceptance. See `truenas_webui_followup_readback_0100` in `inventory/storage.yaml`. The WebUI was reachable without an interstitial; no browser policy or infrastructure setting changed.

  At 01:07 EDT, a read-only attempt to use the TrueNAS System > Shell page found a connected shell WebSocket, but the terminal rendered CSS-like text instead of a prompt and Chrome screenshot capture timed out twice despite selecting the owned tab and refreshing its snapshot. No command was submitted; guest SMART health/test history remains unverified. See `truenas_webui_shell_attempt_0107` in `inventory/storage.yaml`.

  At 02:21 EDT, the Credentials > Certificates page showed `truenas_default`; the downloaded public certificate's SHA-256 exactly matched the served HTTPS leaf. This verifies the selected GUI object-to-leaf association, but the self-signed `CN=localhost`/`SAN=DNS:localhost` leaf still fails strict verification and does not establish trusted endpoint identity. The UI `Download` action also exported a `.key`; it was not opened, both task-created files were removed and verified absent, and their Chrome history entries remain. The download action's output included auth-token URLs, whose values are not retained in repository files. See `truenas_certificate_object_match_0221`. No TrueNAS, PVE, network, or browser-policy configuration changed; task 6.4 remains open.

  A focused read-only UI pass at 02:53–03:00 EDT found no SMART test table in Storage > Disks or Data Protection; the UI search for `SMART` returned no UI result. Credentials > Certificates and System > General Settings showed `truenas_default` selected with `CN=localhost`, `SAN=DNS:localhost`, HTTPS 443, and TLS 1.2/1.3; Alerts again showed no alerts. The leaf fingerprint and strict TLS validation were not re-read, so endpoint identity/trust remain unresolved. See `truenas_webui_followup_readback_0253` in `inventory/storage.yaml`. No SMART query, test, or configuration change occurred. Task 6.4 remains open.

  At 03:07:36 EDT, a read-only workstation TCP check found `192.168.0.186:22` refused the connection while port 443 accepted it. The current neighbor MAC matched the earlier VM 200 `net0` readback; PVE config was not refreshed and no SSH authentication or guest command was attempted. SSH is unavailable at the tested address and port, but this does not rule out another SSH route. See `truenas_ssh_port_probe_0307` in `inventory/storage.yaml`; task 6.4 remains open.
  At 03:21 EDT, a focused authenticated TrueNAS System > Shell read mapped eight 931.5 GB Crucial MX500 devices to guest Linux names and serials; `zpool status -x` returned `all pools are healthy`, and the WebUI Alerts drawer displayed “There are no alerts.” The device enumeration does not independently map Linux names to pool members. `smartctl -H -l selftest /dev/sdb` returned Permission denied as `truenas_admin`; `sudo -n` required a password, so SMART health/history remain unverified and no test was started. Strict TLS identity, numeric capacity threshold/cadence, and failure-procedure acceptance remain open. See `truenas_guest_shell_readback_0321` in `inventory/storage.yaml`; task 6.4 remains unchecked.
  At 03:34:58 EDT, read-only `zpool status -P -v`, `lsblk -o NAME,PARTUUID,SERIAL,MODEL,SIZE`, `zpool list`, and `zfs list` in the authenticated guest mapped all eight `tank` RAIDZ2 members to serials. `tank` and `boot-pool` were ONLINE with no known data errors; the last displayed scrub on 2026-10-02 repaired 0B with 0 errors. `tank` reported 7,971,459,301,376 bytes total and 5,529,743,635,232 bytes ZFS-available; both test-share refquotas are 5 GiB. The alert drawer displayed no alerts. SMART still requires elevation and remains unverified. See `truenas_guest_storage_detail_readback_0334` in `inventory/storage.yaml`.
  A fresh strict-host-key PVE capture at 03:29:36–03:29:39 EDT found `rpool` and `fast-vm` ONLINE mirrors, all five host-owned devices SMART PASSED, no SMART tests logged or scheduled, and a monthly second-Sunday scrub configured with no active scan entry. PVE storage usage was 0.67%, 0.94%, and 0.00%; `check-fast-vm.sh` passed. A 03:37:54 EDT ownership read confirmed VM 200 running, HBA `vfio-pci`, and only `fast-vm`/`rpool` imported on PVE. The fresh evidence does not select capacity thresholds/cadence or test failure handling; TrueNAS SMART, certificate trust, and the failure gate remain unresolved. See `pve_storage_health_readback_032936` and `pve_nas_ownership_readback_0337` in `inventory/storage.yaml`; task 6.4 remains unchecked.

A 03:43–03:44 EDT authenticated WebUI and strict-TLS readback again showed `tank` ONLINE, 0 of 8 disk errors, 5.03 TiB free, and no active alerts. `truenas_default` is selected for HTTPS 443/TLS 1.2–1.3; its public-certificate fingerprint matches the served leaf, while strict verification fails because it is self-signed and its SAN is only `DNS:localhost`, not `192.168.0.186`. The configured object-to-leaf association is verified, but endpoint trust remains unresolved. See `truenas_webui_cert_alert_readback_0344` in `inventory/storage.yaml`. Guest SMART history, chosen capacity threshold/cadence, alert delivery, and representative failure handling remain open; task 6.4 remains unchecked.

A 03:55–03:58 EDT authenticated System > Alert Settings readback found TrueNAS pool-space levels at 85% NOTICE, 90% WARNING, and 95% CRITICAL; all listed storage alert frequencies are IMMEDIATELY. E-Mail and SNMP Trap services are enabled at Warning level, but delivery was not tested. These settings do not choose the PVE host-pool alert threshold/cadence. See `truenas_alert_policy_readback_0355` in `inventory/storage.yaml`; task 6.4 remains unchecked.

A 04:09–04:17 EDT read-only System > Services check found SSH stopped, which matched a workstation TCP probe to `192.168.0.186:22` returning `Connection refused`; NFS and SMB were running. The authenticated WebUI Shell and read-only `certificate.query` confirmed selected GUI certificate id 1 (`truenas_default`), parsed true, CN `localhost`, and SAN `DNS:localhost`. `core.get_methods` exposed no method name containing `smart`; SMART schedule/history remain unverified. No service or certificate setting changed. See `truenas_webui_access_readback_0409_0417` in `inventory/storage.yaml`; task 6.4 remains unchecked.

A fresh strict-host-key read-only PVE collector at 04:26 EDT found both host mirrors ONLINE with zero device errors and no known data errors. All four pool NVMe members and the Kingston boot SSD reported SMART PASSED; NVMe critical warnings, media/data-integrity errors, and error-log counts were zero, and no device self-tests were logged or scheduled. The monthly second-Sunday scrub remains configured with no active scan entry. PVE storage use was 0.68%, 0.94%, and 0.00%, with no finite host-pool dataset quotas. The capture did not select capacity-alert thresholds/cadence or test device failure. See `pve_storage_health_readback_042614` in `inventory/storage.yaml`; task 6.4 remains unchecked.

A 04:31:33 EDT bounded strict-host-key PVE read found `pvestatd`, `smartd`, and `zfs-zed` active, `/etc/pve/status.cfg` absent, and no capacity/threshold-matching timer, root-cron entry, or file in the inspected PVE/ZFS/cron/systemd/local-script paths. No host-pool capacity threshold or measurement/alert job was found; external monitoring and differently named code outside those paths were not ruled out. See `pve_capacity_monitor_readback_043133` in `inventory/storage.yaml`. Threshold/cadence selection remains open; task 6.4 remains unchecked.

A 04:37 EDT authenticated WebUI read confirmed no active alerts and `truenas_default` selected for HTTPS 443/TLS 1.2–1.3. Its displayed public subject, SAN, and validity match the 03:44 EDT readback; the current served-leaf SHA-256 also matches that earlier readback, which directly verified the selected-object fingerprint. A Shell refresh timed out before any command was entered. Strict TLS verification still fails because the leaf is self-signed and its `DNS:localhost` SAN does not identify `192.168.0.186`. No setting was changed. See `truenas_webui_readback_0437` in `inventory/storage.yaml`. This does not establish alert delivery or trusted endpoint identity; task 6.4 remains unchecked.

A read-only System > Advanced Settings > Cron Jobs view at 04:54–04:55 EDT showed two enabled TrueNAS SMART self-test jobs, both run as root against `/dev/disk/by-id/ata-CT1000MX500SSD1_*`: weekly short tests at 01:00 Wednesday and monthly long tests at 03:00 on the 15th. The UI showed next runs in 3 and 11 days. This confirms configured schedules but not that the model glob matches every pool serial, that either job has run, or any drive health/test result. No row action was opened and no job or test was run. See `truenas_smart_cron_readback_0454` in `inventory/storage.yaml`. SMART health and history, PVE threshold/cadence, alert delivery, trusted endpoint identity, and failure-procedure acceptance remain open; task 6.4 remains unchecked.

A fresh reload of the authenticated System > Shell page at 05:05 EDT still rendered CSS-like text in the terminal and no shell prompt. No input, command, or password was submitted. This records a UI-rendering limitation only; it does not establish the guest shell backend state or SMART health/history. See `truenas_webui_shell_render_readback_0505` in `inventory/storage.yaml`; task 6.4 remains unchecked.

A 05:16 EDT read-only snapshot of the pinned personal-Chrome tab found the TrueNAS sign-in page, not an authenticated session. The self-signed localhost-only certificate remains untrusted, so no credential was submitted and no new guest SMART or alert evidence was obtained. See `truenas_webui_signin_recheck_0516` in `inventory/storage.yaml`; task 6.4 remains unchecked.

At 05:40 EDT, a same-origin credential-free `GET /api/v2.0/alert/list` returned `401 Unauthorized`; no alert status was refreshed. A strict-host-key public-key-only SSH check to PVE also returned `Permission denied`, so the storage collector did not run. The local collector now separates smartctl acquisition-error and device status/history bits, and its focused test asserts the exact five persistent whole-device paths. See `truenas_webui_alert_api_unauth_readback_0540` and `pve_storage_collector_ssh_auth_attempt_0540` in `inventory/storage.yaml`. Task 6.4 remains open.

A fresh strict-host-key, password-only PVE collector at 05:50 EDT found both host mirrors ONLINE with no known data errors; all five host-owned devices reported SMART PASSED with no tests logged. `smartd` was active without a scheduled self-test directive, and the monthly second-Sunday scrub remained configured with no active scan entry. PVE storage use was 0.69%, 0.94%, and 0.00%, with no finite host-pool quotas. This still does not set a host capacity threshold, refresh TrueNAS guest status, or exercise failure handling. See `pve_storage_health_readback_055003` in `inventory/storage.yaml`; task 6.4 remains unchecked.

A fresh authenticated read at 06:00–06:04 EDT reopened the existing task-owned personal-Chrome session `homelab-truenas-readonly` on profile `5dbc8ec1-ef89-437d-81e5-a712844c5e74`. The current Alerts drawer displayed “There are no alerts.” GUI Settings showed `truenas_default` selected for HTTPS 443; the served leaf fingerprint matches the prior public-object readback, but the leaf remains self-signed with `CN=localhost` and only `SAN DNS:localhost`, so endpoint IP identity is untrusted. This pass did not refresh the current IP-to-VM 200 mapping or guest SMART history, choose a capacity threshold, or exercise failure handling. See `truenas_webui_readback_0604` in `inventory/storage.yaml`; task 6.4 remains unchecked.

A 06:11–06:13 EDT authenticated System > Alert Settings read of the Storage category found pool-space notifications at 85% NOTICE, 90% WARNING, and 95% CRITICAL, all at IMMEDIATELY frequency. E-Mail and SNMP Trap alert services are enabled at Warning level; delivery was not tested. This is TrueNAS guest policy and does not set a PVE host-pool threshold or cadence. No setting was changed. See `truenas_storage_alert_policy_readback_0613` in `inventory/storage.yaml`; task 6.4 remains unchecked.

A fresh read-only mapping at 06:26 EDT matched TrueNAS `enp6s18` (`192.168.0.186`, MAC `bc:24:11:87:f2:2b`) to PVE VM 200 `net0` and the workstation's REACHABLE neighbor entry; see `truenas_vm200_mac_mapping_readback_0626` in `inventory/storage.yaml`. The authenticated 06:27–06:32 EDT TrueNAS WebUI showed `tank` ONLINE, 0 of 8 disk errors, 5.03 TiB available, the Sunday 00:00 scrub schedule, the 2026-10-02 scrub with zero errors, no active alerts, and disk temperatures from 25–33 °C. Its disk reports expose I/O and temperature only. Read-only guest shell output confirmed both pools ONLINE and the 5 GiB setup-share refquotas, but the shell is `truenas_admin`; `sudo -n smartctl -H -l selftest /dev/sdb` returned `sudo: a password is required` and no SMART query ran. See `truenas_guest_storage_health_readback_0635` in `inventory/storage.yaml`. Certificate trust remains unresolved: the prior self-signed `CN=localhost`/`SAN DNS:localhost` evidence does not authenticate the IP, and this pass made no new TLS trust claim. SMART health/history, PVE threshold/cadence, alert delivery, and failure handling remain open; keep task 6.4 unchecked.

A fresh 06:49–06:52 EDT authenticated WebUI read showed `tank` online with no errors, a completed zero-error scrub on 2026-10-02, and “There are no alerts.” A strict TLS check returned the same `CN=localhost`, `SAN=DNS:localhost` leaf fingerprint as the 06:04 read; default certificate verification for `192.168.0.186` failed on the missing IP SAN. Endpoint identity remains unverified. See `truenas_webui_tls_alert_readback_0652` in `inventory/storage.yaml`. Task 6.4 remains unchecked.

A 06:54 EDT PVE API read returned VM 200 `net0` MAC `BC:24:11:87:F2:2B`; the workstation neighbor entry for `192.168.0.186` was REACHABLE at that MAC, corroborating the earlier guest interface read. The 06:57–07:00 guest WebUI Shell retry still rendered CSS-like text; although the read-only interface command was entered and Enter sent, no output was visible and execution is unconfirmed. See `truenas_vm200_mac_mapping_readback_0654` and `truenas_webui_shell_attempt_0700` in `inventory/storage.yaml`. Do not treat this as a fresh guest-side read; task 6.4 remains unchecked.

A 07:01–07:03 EDT strict-host-key, batch-mode, public-key-only SSH preflight found no pinned host key for `192.168.0.186` and received `Connection refused` on TCP port 22 before authentication. No password was used or host key accepted. This does not establish a verified guest command route; see `truenas_ssh_access_attempt_0702` in `inventory/storage.yaml`. Guest SMART history remains open.

Partial task 6.4 progress on 2026-10-04: the operator confirmed the 80% warning /
90% critical policy and five-minute cadence. It is evaluated by the journal-only
`host/pve/storage-capacity-monitor.sh`. The host-owned manager previewed,
applied, and verified the service and timer; a manual run and its first
scheduled firing completed successfully with both pools ONLINE below
threshold. Evidence is
`pve_storage_capacity_monitor_readback_105054` in `inventory/storage.yaml` and
the operating details are in `docs/storage-plan.md`. Task 6.4 remains open for
TrueNAS SMART/certificate trust, live threshold crossing, alert delivery, and
representative device-failure acceptance.

Operator deferral on 2026-10-04: defer the TrueNAS security/access work,
including rotation of the admin credential and GUI certificate private key
exposed in earlier local tool output and obtaining a trusted privileged route
for SMART history. Do not re-enter credentials or attempt privileged SMART
access while this work remains deferred. The operator confirmed the documented
PVE capacity policy; that confirmation does not demonstrate a live threshold
transition, notification delivery, or failure recovery.

Operator disposition for task 6.3 on 2026-10-04: contents on only the two
serial-bound scratch candidates, `PHHH8505034Q512H` and `BTHH8244042V512D`, may
be discarded. This authorizes loss of existing contents; it does not establish
that either device is blank or recoverable. The historical BLOCK preflight is
not a write gate. Before clearing, repeat the reviewed serial-bound preflight
with no UNKNOWN findings and verify the six off-target metadata captures.
Clear the old ZFS labels on candidate C partition 3, the VFAT signature on
candidate C partition 2, and candidate C's GPT/PMBR; create the non-redundant
`scratch` stripe on both whole-disk by-id paths without `zpool create -f`.
Before the first disk write, the host manager records the exact plan hash, boot
ID, serials, and apply phase; a same-plan retry may resume only after fresh
read-only identity/reference checks and exact validation of any pool or dataset
already created. It must not destroy a partial pool or force through a new
signature. Register only `images,rootdir` content, never backups. The final live topology,
storage boundaries, and three-pool capacity-monitor read-back passed on
2026-10-04; see `pve_scratch_tier_readback_143840` in
`inventory/storage.yaml`. Task 6.3 is complete. The stripe is disposable and
non-redundant, with no unique data; this is not backup or promotion evidence.

At 14:37:02–14:38:40 EDT on 2026-10-04, a fresh strict-host-key read-only
collector and transaction readback verified all three host pools ONLINE with
no known data errors. The new `scratch` stripe uses only serials
`PHHH8505034Q512H` and `BTHH8244042V512D`; its PVE ID is active for
`rootdir,images` only and lists no volumes. The two scratch dataset quota and
refquota values are `none`. All six host pool NVMe devices and the Kingston
boot SSD reported SMART PASSED; no self-tests are logged or scheduled, and the
monthly second-Sunday scrub schedule is configured with no active scan at
capture. The v2 monitor is enabled and active for `rpool`, `fast-vm`, and
`scratch`, with scratch state `normal`; no threshold transition was generated
because all pools were below 80%. The focused synthetic monitor suite passed,
including normal-to-warning at 80%, critical at 90%, recovery transitions,
unreadable-pool handling, and manager check/apply/rollback paths. This verifies
the policy logic without filling a live pool. See
`pve_scratch_tier_readback_143840` in `inventory/storage.yaml`. This adds
current PVE measurements but does not test a live threshold transition,
notification delivery, device-failure recovery, or TrueNAS SMART/certificate
trust. Preserve the unresolved TrueNAS identity uncertainty and keep task 6.4
open.

A fresh strict-host-key read-only PVE collector at 14:57:59 EDT confirmed
`rpool` and `fast-vm` ONLINE mirrors and the disposable `scratch` stripe
ONLINE, all with zero known data errors. All six host-pool NVMe devices and
the Kingston boot SSD reported SMART PASSED with collector status 0. The NVMe
critical warnings, media/integrity errors, and error-log counts were zero;
none of the seven devices had logged self-tests, and `smartd` has no scheduled
self-test directive. The monthly second-Sunday scrub schedule remains
configured, but this collector emitted no `scan:` line, so active scrub status
is not established by this capture. PVE storage usage was 0.73% for
`fast-vm`, 0.94% for `local`, and 0.00% for `local-zfs` and `scratch`; the
manager check at 15:00:02 confirmed the 80%/90% five-minute monitor files and
timer are installed and active. See
`pve_storage_health_readback_145759` in `inventory/storage.yaml`. This
readback adds current host status only; it does not exercise alert delivery,
a live threshold transition, or device-failure recovery. Keep task 6.4 open.

A fresh strict-host-key read-only collector at 16:05:58 EDT found `rpool` and
`fast-vm` ONLINE mirrors and the `scratch` stripe ONLINE, all with zero
READ/WRITE/CKSUM counters and no known data errors. All six host-pool NVMe
devices and the Kingston boot SSD reported SMART PASSED; all NVMe warning,
integrity-error, and error-log counters were zero, with no host SMART self-tests
logged or scheduled. The monthly second-Sunday scrub schedule remains
configured, but no `zpool status` output contained a `scan:` line, so active
scrub status is not established. Dataset quotas/refquotas remain unset; PVE
storage use was 0.73% for `fast-vm`, 0.94% for `local`, and 0.00% for
`local-zfs` and `scratch`. At 16:09:05 the capacity-monitor manager check
passed. A strict-host-key runtime read at 16:09:11 confirmed an active timer,
five successful scheduled runs at five-minute intervals from 15:45:12 through
16:05:12, and no volumes registered on `scratch`. Evidence is
`pve_storage_health_readback_160558` in `inventory/storage.yaml`. This confirms
scheduled execution below threshold, not a live capacity transition or a
device-failure exercise. Per the spec, the PVE monitor records locally and does
not imply remote notification delivery; external alert acceptance is tracked
under task 9.3. TrueNAS SMART/certificate evidence remains deferred. Task 6.4
is still open for the remaining evidence and representative failure handling.

After updating the scratch failure guidance, the read-only
`manage-scratch-pool.sh check` passed at 16:15:12 EDT against the same completed
transaction, with boot ID unchanged and the updated source-plan hash
`4bacce1aa6319e65e4e8b14035972f4446ba9a3171327195625cd7f925c0d480`. Evidence
is `pve_scratch_manager_recheck_161512` in `inventory/storage.yaml`; no live
configuration changed.

A focused read-only WebUI attempt at 16:23 EDT in the selected personal Chrome
profile reached the TrueNAS sign-in page. No credential was submitted because
the operator deferred security/access work; this attempt adds no guest health,
alert, SMART, or certificate evidence. See
`truenas_webui_signin_recheck_1623` in `inventory/storage.yaml`. Task 6.4
remains unchecked.

At 16:28 EDT the versioned capacity-monitor manager check passed, and a fresh
strict-host-key read-back found the timer enabled and active, with five
successful scheduled service runs through 16:25 and the next run due at 16:30.
`pvesm list scratch` returned no volumes. See
`pve_storage_capacity_monitor_readback_1628` in `inventory/storage.yaml`. This
verifies scheduled execution below threshold only; no live capacity transition,
remote notification, or failure procedure was exercised. Task 6.4 remains
unchecked.

A fresh strict-host-key read-only storage capture at 16:29:59 EDT found all
three PVE pools ONLINE with zero READ/WRITE/CKSUM counters and no known data
errors. All six host-pool NVMe devices and the Kingston boot SSD reported SMART
PASSED; no self-tests were logged, and `smartd` has no scheduled self-test
directive. The monthly second-Sunday scrub schedule remains configured, but no
captured pool status contained a `scan:` line. Dataset quotas/refquotas remain
unset; PVE storage use was 0.73% for `fast-vm`, 0.94% for `local`, and 0.00%
for `local-zfs` and `scratch`. See
`pve_storage_health_readback_162959` in `inventory/storage.yaml`. This does not
establish active scrub status, threshold behavior, guest health, or failure
recovery; task 6.4 remains unchecked.

A local non-live scratch member-loss drill passes at the validation layer:
`bash host/pve/tests/test-scratch-failure-drill.sh` feeds synthetic `UNAVAIL`
pool output with one unavailable stripe member to the versioned topology
validator, which rejects it. The test performs no PVE or block-device commands.
The runbook now states the stop/collect/data-recovery gates and prohibits ad hoc
replacement or recreation. This does not test a live alert or device failure,
recover pool data, or qualify a recovery implementation; Task 6.4 remains open.

A fresh strict-host-key PVE collector at 14:39 EDT on 2026-10-05 found
`rpool` and `fast-vm` ONLINE mirrors and `scratch` an ONLINE stripe, all with
zero READ/WRITE/CKSUM counters and no known data errors. All six host-pool
NVMe devices and the Kingston boot SSD reported SMART PASSED; no device had
self-tests logged, and `smartd` remained active without a scheduled
self-test directive. The monthly second-Sunday scrub schedule remains
configured, but no captured pool status contained a `scan:` line. Dataset
quotas/refquotas remain unset; PVE storage use was 0.81% for `fast-vm`,
0.94% for `local`, and 0.00% for `local-zfs` and `scratch`. See
`pve_storage_health_readback_143910` in `inventory/storage.yaml`.

At 14:41 EDT, a strict-host-key read-back confirmed the 80%/90% five-minute
monitor check passed, the timer was enabled and active, and eight scheduled
service completions succeeded at five-minute intervals through 14:40, with
the next run due at 14:45. `pvesm list scratch` returned no volumes. No
threshold transition occurred because all pools remained below 80%; no live
threshold crossing or external alert delivery is claimed. See
`pve_storage_capacity_monitor_readback_144130` in `inventory/storage.yaml`.

At 14:45 EDT, the task-owned personal Chrome session showed the TrueNAS
sign-in form, so current guest alerts and health were not refreshed and no
credential was submitted. A strict OpenSSL read at 14:42–14:44 confirmed the
current served leaf remains self-signed `CN=localhost` with only
`SAN=DNS:localhost`; IP verification for `192.168.0.186` failed with error
18. The endpoint's workstation neighbor MAC matches the current running PVE
VM 200 `net0`, but the certificate does not authenticate that IP. The last
authenticated empty-alert read is historical. See
`truenas_webui_signin_recheck_144555` and
`truenas_tls_strict_recheck_144245` in `inventory/storage.yaml`.

Task 6.4 remains open. TrueNAS current alert/SMART state and trusted endpoint
identity remain unverified, and representative live device-failure
acceptance has not been performed. Existing synthetic tests validate
threshold transitions and fail-closed handling without a live crossing or
device fault. No host, VM, pool, network, or certificate state changed during
this refresh.


  At 15:00–15:07 EDT on 2026-10-05, the operator authorized one-time read-only TrueNAS WebUI use despite failed TLS verification. The current Alerts drawer showed no alerts. The Storage Dashboard showed `tank` ONLINE (RAIDZ2, eight 931.51 GiB members), 5.03 TiB available, a zero-error scrub completed October 2 at 11:47 TrueNAS local time, and a Sunday 00:00 scrub schedule. `tank/nfs_test` and `tank/smb_test` each showed a 5 GiB applied dataset quota and 204.75 KiB used; the daily seven-day snapshot task is local-only. Enabled root Cron Jobs schedule short SMART tests weekly Wednesday at 01:00 and long tests monthly on day 15 at 03:00 for `/dev/disk/by-id/ata-CT1000MX500SSD1_*`; no SMART results or test execution history were obtained and no test was started. The selected WebUI certificate is `truenas_default`, but strict verification at 15:07 still failed with self-signed error 18 and its `CN=localhost` / `SAN=DNS:localhost` do not identify the IP. See `truenas_storage_health_readback_150007` and `truenas_tls_strict_recheck_150700` in `inventory/storage.yaml`. A later authenticated API readback and SMART capture at 15:55–16:11 EDT returned no active alerts, all eight TrueNAS member disks SMART PASSED, and each latest short self-test completed without error. The served TLS identity remains unverified. The weekly and monthly SMART job commands were then corrected to skip partition aliases; their schedules stayed unchanged, and the corrected weekly job succeeded at 16:20:47 EDT. A numeric TrueNAS whole-pool threshold remains unverified; alert delivery belongs to Task 9.3. Task 6.4 is complete as a measurement and procedure-documentation task: current pool health, scrub, SMART, quotas, host capacity policy, and documented mirror/RAIDZ2/stripe responses are recorded, with the synthetic scratch fail-closed test passing. No live device fault, capacity crossing, or alert-delivery test was run. See `truenas_storage_health_api_readback_162047` in `inventory/storage.yaml`; certificate uncertainty remains recorded in `truenas_tls_strict_recheck_150700`.

## 7. Build the managed network foundation

- [ ] 7.1 Decide and record the internal domain, VLANs, subnets, reservations, naming, and required access boundaries.
- [ ] 7.2 Capture and recovery-test encrypted off-host Brocade and UniFi configuration backups; prove read-only automation identities against the live firmware/controller.
- [ ] 7.3 Select and test a compatible UniFi provider in a separate locked state; import existing objects and obtain a no-change plan.
- [ ] 7.4 Validate the pinned Brocade execution environment and audit/backup workflow without switch writes; prepare reviewed apply/verify/rollback jobs.
- [ ] 7.5 Apply the reviewed PVE bond with fallback management access and prove management survives either bonded link being disconnected.
- [ ] 7.6 Apply the VLAN-aware bridge and routed/firewalled boundaries with current backups and rescue access; test permitted and denied paths.
- [ ] 7.7 Establish DNS, trusted certificates, and VPN administration; verify PVE/iDRAC remain off the public internet and test access from allowed and denied networks.

## 8. Add Red Hat platform services

Build these as reproducible lab services only. Do not make them authoritative
for unique state or dependent operations until their deferred independent
recovery paths have been implemented and tested.

- [ ] 8.1 Verify current capacity and recovery prerequisites, then provision RHEL templates and `idm01` with versioned first boot and guest configuration.
- [ ] 8.2 Bootstrap containerized AAP on a dedicated RHEL VM from the laptop; manage its inventories, credentials definitions, execution environments, templates, and workflows as code.
- [ ] 8.3 Prove an audited AAP workflow can provision, configure, verify, and remove a disposable VM; add OpenManage inventory/configuration export before iDRAC writes.
- [ ] 8.4 Confirm OpenShift entitlement, release compatibility, DNS, addressing, capacity, and backup design; provision the Single Node OpenShift VM.
- [ ] 8.5 Bootstrap OpenShift GitOps, verify reconciliation/self-healing and a rebuild path, and add optional Operators only for identified needs.

## 9. Complete independent operations

- [ ] 9.1 Inventory the configuration, state, keys, and recovery order for important VMs, AAP, IdM, OpenShift, network exports, bootloader reconstruction, and rescue media. Keep the actual encrypted off-host copies and destination-side checks in the deferred independent-recovery backlog item.
- [ ] 9.2 Integrate UPS signaling and test orderly guest/NAS/PVE shutdown without an extended power outage.
- [ ] 9.3 Verify alert delivery for implemented disks, ZFS, memory/SEL, capacity, thermals, power, certificates, and platform services. PVE system-mail delivery through the versioned Cloudflare target was verified; TrueNAS delivery remains gated on trusted endpoint identity. Backup-job and remote-copy alerts belong to the deferred implementation once those jobs exist.
- [ ] 9.4 Document recovery order, non-destructive targets, isolation, and pass criteria for the implemented reproducible services. Keep file/VM/NAS/AAP/IdM/OpenShift remote-copy restores and bare-metal host-loss exercises in the deferred independent-recovery backlog item; do not declare the platform independently recoverable from this planning task.
