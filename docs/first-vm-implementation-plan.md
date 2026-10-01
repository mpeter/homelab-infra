# First VM implementation plan

This is the executable sequence from the 2026-10-01 R720 code-first cutoff to
the primary Fedora development VM. It is for an operator resuming with no chat
history. Follow the [R720 change-control contract](r720-change-control.md) and
the broader [implementation plan](implementation-plan.md). Do not treat a
planned gate as already implemented or passed.

## Starting point

The R720 has passed two cold boots after its host-ID repair. `rpool` is healthy.
The two serial-identified 1 TB NVMe drives form the online `fast-vm` mirror;
the read-only `fast-vm` baseline check passed on 2026-10-01. There are no VMs
or containers. The Fedora Cloud Base image has been verified off-host but not
uploaded. The machine currently reports 128 GiB; 256 GiB is a later target,
not a prerequisite for the first VM. Recheck these volatile facts before a
write. The project handoff holds the detailed evidence and recovery locations.

The worktree contains unrelated operator edits. Preserve them. No host
repository correction, PVE upgrade, OpenTofu backend, automation identity, or
VM has been completed under this plan.

## 0. Resolve bootstrap dependencies

Choose and record the off-host state backend and key custody, the independent
VM-backup target, and the Fedora image-import and cloud-init paths before
building the VM root. The laptop remains a permanent break-glass machine: it
must retain a repository clone, PVE and iDRAC access, state-backend credentials
and recovery key, and backup decryption material independently of the R720.
Prove that a plan can run from it while the Fedora VM is absent. Do not make
the managed VM the only place where its own recovery tools live.

Host maintenance code owns image staging and checksum read-back on the
appropriate source storage. If the provider instead performs the upload,
include that storage in its narrowly scoped effective-permission tests.
Use the same image-import path, bridge, cloud-init mechanism, guest agent, and
disk workflow for the disposable test and the Fedora VM. Verify the chosen
provider's current requirements against its documentation and a live test. If
it requires SSH in addition to an API token, scope that SSH identity separately
and demonstrate its effective limits; do not claim token isolation covers an
unrestricted SSH path. Stage the verified image on storage that accepts its
content type, then import the VM disk onto `fast-vm`; a qcow2 file is not a ZFS
volume. Do not add image content to `fast-vm` merely to fit a provider example.

Exit gate: these choices, locations, credential owners, and recovery tests are
recorded without putting secret values in Git. Repository work in stage 1 can
proceed while these choices are being resolved, but the disposable VM cannot.

## 1. Normalize PVE package repositories

Owner: workstation-runnable, versioned host maintenance code. This step changes
repository configuration only; package upgrades are a separate change.

1. Read back the live PVE version, Debian suite, repository files, subscription
   status, installed keyring, `rpool` health, and the current recovery path.
2. Add an idempotent check/apply path for PVE 9 deb822 `.sources` files that
   disables unsubscribed enterprise
   PVE and Ceph entries and enables the matching PVE no-subscription repository.
   Keep Debian base repositories intact. The check must show the exact proposed
   file delta without writing to the host.
3. Commit and review the versioned source without staging unrelated or secret
   files. Record the Git revision in the apply evidence. Save the original
   repository files off-host with restrictive permissions and record checksums.
   Apply only the reviewed repository delta.
4. Read back the files, run the same check to no-change, refresh package indexes,
   and simulate an upgrade. Record any errors or proposed package removals.

5. Decide explicitly whether to upgrade PVE before the first VM or defer it.
   An upgrade is a separate reviewed change with package-removal review, both
   ESPs checked, a maintenance window, and a verified cold boot afterward.
   Whether upgraded or deferred, cold-boot the currently empty host once and
   confirm `fast-vm` imports, its drift check passes, and PVE storage is active.
   Refresh the off-host host-configuration bundle and test extraction, including
   boot, network, PVE cluster/storage configuration, and ZFS import metadata.

Exit gate: the host resolves the expected PVE repository without enterprise
authentication errors; the code check reports no drift; the upgrade decision
and preview are recorded; and post-boot pool and storage checks pass. Restore
the saved source files if the repository change cannot be validated. The
recovery bundle is not considered tested merely because it decrypts.

## 2. Establish the Proxmox OpenTofu control plane

Owner: the Proxmox OpenTofu root. Keep it separate from the future UniFi root.

1. Select and document an encrypted off-host backend that provides locking and
   an independently tested state restore. It must remain usable when the R720
   and its future AAP VM are down. Do not place state or backend credentials in
   Git or on `fast-vm` as their sole copy.
2. Create a dedicated PVE automation identity with only the VM permissions
   needed by the selected provider and storage workflow. Verify the token
   cannot administer the host, create a storage entry, or create a pool. Record
   the effective permissions, not merely the intended role definition. Version
   the role, ACL, resource-pool, and any backup-registration configuration in
   host maintenance code, with a read-only check path. Scope VM permissions to
   a dedicated pool and storage to `fast-vm`, rather than global `/vms` access.
3. Pin the OpenTofu and provider versions. Add a Proxmox root and small VM
   module. Keep host pools, repositories, and network foundation out of this
   state. Store guest secrets outside source and state wherever supported.
4. Add a plan-JSON gate that rejects resource types outside the reviewed VM
   allow-list. Reject delete or replace actions on a named protected VM or disk
   unless an explicit address-specific exception is reviewed with a fresh
   backup and pre-change snapshot. Do not use `-target` as an approval device.
   Protect the primary VM and its persistent data disk against routine destroy
   in the OpenTofu configuration. Run the live `fast-vm` drift check before any
   plan using that storage.

Exit gate: backend lock contention and off-host state recovery are tested from
the laptop;
credential scope is demonstrated through permitted and denied API operations;
the plan gate has positive and negative tests; source and state scans find no
secrets committed to Git. A `tofu plan` alone is not this gate.

## 3. Prove the lifecycle with a disposable VM

Owner: the Proxmox OpenTofu root, with first boot from cloud-init.

1. Recheck no existing VM ID or disk will be adopted or overwritten. Review a
   saved plan that creates only a small disposable VM on `fast-vm`, using the
   exact image, cloud-init, bridge, guest-agent, and disk-import paths intended
   for Fedora.
2. Apply that exact plan. Read back its VM configuration and storage mapping,
   boot it, and verify console or network access as designed.
3. Run a no-change plan after first boot. Then review and apply an OpenTofu destroy plan scoped
   to the disposable VM. Verify no orphan VM configuration or disk remains and
   the state matches the live environment.

Exit gate: create, read-back, boot, no-change plan, destroy, and orphan check
all pass. On failure, preserve state and the VM for diagnosis; do not use a
manual delete merely to make the next plan green.

## 4. Deploy the Fedora development VM

Owner: OpenTofu for the VM and disks; cloud-init for first boot; guest
configuration automation for subsequent OS state. The host remains an
appliance.

1. Before VM creation, reconcile iDRAC and OS memory inventory, review current
   SEL and memory-error counters, and record any untested-DIMM risk. Check
   boot-device status, host headroom, datastore free space, the active LAN
   bridge, planned address and DNS name, and the verified Fedora image. Access
   is LAN-only until a separately tested VPN exists. Start from the
   proposed 8 vCPU, 32 GiB RAM, 300 GiB disk, then adjust only from measured
   capacity. Do not reserve against the hoped-for 256 GiB configuration.
2. Define an initially empty VM in versioned OpenTofu and review the gated plan. Apply it and
   verify the VM's live CPU, memory, disk, boot, network, and console state.
3. Before any non-reproducible data enters the VM, use versioned `host/pve/`
   check/apply paths to configure ZFS and SMART health and capacity alerts,
   backup-failure alerts, the backup storage entry, and the backup job. Verify
   their live configuration and alert delivery. Refresh and extraction-test the
   off-host host bundle. Complete a full backup of the empty VM to the
   independent off-host destination and verify it from that destination. Use
   the documented restore-test exception through a versioned `host/pve/`
   procedure with a read-only preflight: restore under a scratch VM ID outside
   OpenTofu's range, with no NIC or a link-down NIC. Boot and inspect it without
   creating a new bridge or duplicating the primary VM's address or MAC. Remove
   the temporary VM through that procedure and confirm no orphan disk or
   configuration remains. A same-host restore proves backup format and
   procedure, not host-loss recovery.
4. Configure the guest through a minimal versioned Ansible role runnable from
   the laptop, with check mode and live read-back; AAP can adopt it later.
   Restore development configuration and migrate unique data incrementally,
   keeping a current off-host copy throughout. Keep workstation dotfiles
   separate from R720 infrastructure ownership.
5. Exercise normal work, including the main repositories, a container build,
   and remote LAN access, for at least 14 days. Require zero new OOM, ZFS,
   SMART, or SEL memory errors; successful scheduled backups; `fast-vm` at
   least 20% free; and CPU/drive temperatures below their iDRAC warning
   thresholds during the named workload. Investigate sustained swap use or
   available host memory below 16 GiB before declaring the trial passed.
   Retain the laptop as a permanent recovery/control path, even after the VM
   becomes the primary workspace. Back up before later memory or network
   maintenance that would interrupt the VM.

Exit gate: the VM boots and supports the named work; a no-change plan and live
read-back agree; alerts reach the operator; off-host backup and full restore
have been exercised; and measured host capacity remains healthy through the
trial. Only then treat Fedora as the primary development machine.

## Order and stop conditions

Each numbered stage depends on the preceding exit gate. A failed drift check,
unrecoverable or unlocked state, excessive token privileges, unexpected plan
resource type, or missing off-host restore path stops the next apply. Record the
failure and reconcile source with observed state before continuing. Physical
memory expansion, other storage pools, AAP, IdM, and OpenShift remain separate
work and do not block the first Fedora VM unless fresh capacity or access checks
show a real dependency.

Stage 4 VM creation also stops on any uncorrectable memory error, a rising
correctable-error count, a SEL memory event since the last DIMM change, or an
unattributed iDRAC Critical condition. Record the evidence and disposition of
the current Critical alert before proceeding; do not silently treat it as
cleared. A later DIMM expansion is an outage for the primary VM and requires a
fresh backup and planned maintenance window.
