# R720 change control

The code-first cutoff is effective 2026-10-01, before the first VM. The host is
an appliance, not a disposable image: physical disks, firmware, and Proxmox
updates still require controlled in-place work. "Code-first" means a planned
change has a reviewed versioned source, an explicit apply path, and runtime
read-back. An observed inventory entry alone is not desired state.

| Scope | Versioned owner | Apply boundary |
| --- | --- | --- |
| Boot, ZFS pools, PVE storage registration, repositories, host networking | `host/pve/` workstation-runnable maintenance code | Read-only drift/preflight, recovery evidence, bounded apply, live read-back |
| VMs, containers, virtual disks, supported PVE resource objects | Proxmox OpenTofu root in `tofu/` | Locked off-host state, scoped token, reviewed and type-gated plan |
| Guest first boot and configuration | `cloud-init/`, then `ansible/` | Image/test-boot and Ansible check/read-back |
| Physical repair | iDRAC plus documented procedure | Serial/slot confirmation, power and recovery plan, observed inventory refresh |

## Mechanical gates

1. A planned host write must originate from `host/pve/` source. Run its check
   path first, capture the intended delta, preserve a recovery path, apply the
   bounded change, then run the same check and a live service/health read-back.
   AAP can later invoke the same source, but the workstation must be able to
   run it when the R720 or AAP VM is down.
2. `fast-vm` is adopted, not rebuilt. Its serial-specific mirror, ashift,
   dataset properties, and PVE storage mapping must pass
   `host/pve/check-fast-vm.sh` before a VM plan uses it. A drift failure blocks
   a planned VM apply; the check never repairs or destroys a pool.
3. No GUI, `qm`, `pct`, or direct API creation or modification of managed VMs.
   Before the first disposable VM, verify encrypted off-host OpenTofu state,
   locking and state recovery; a dedicated token without host/storage-admin
   privileges; and a plan-JSON resource-type allow-list. Test that the token
   cannot create a pool or storage entry. Apply the reviewed plan, prove a
   no-change plan, destroy the disposable VM through OpenTofu, and check for
   orphan disks. The Fedora VM follows this test, not a manual prototype.
4. Keep Proxmox and UniFi in separate OpenTofu roots, state, credentials, and
   apply jobs. Do not put state, credentials, decrypted secrets, or host backups
   in Git. An off-host backup and an actual restore test are required before
   the Fedora VM becomes primary.

A backup-restore test may create one temporary, non-managed VM through a
versioned `host/pve/` procedure because OpenTofu cannot restore a vzdump archive
as a managed resource. Its preflight must reserve a VM ID outside OpenTofu's
range and disconnect its network. The procedure must remove the test VM and
verify that no configuration or disk remains. It cannot be used to create a
lasting workload.

## Recovery exception

When delay risks boot, access, or data, use the minimum direct action necessary
to stabilize the host. Capture what changed and why in the project handoff or
incident record. Before the next planned change, either make the versioned
source match the observed state or restore the intended state, then rerun the
checks. An exception is not a parallel long-lived configuration channel.

The host-ID repair, two cold boots, and creation of `fast-vm` are pre-cutoff
bootstrap history. `fast-vm` is retained because its live mirror was verified
by serial and its desired properties are checked in code. No VM has been
created outside OpenTofu.
