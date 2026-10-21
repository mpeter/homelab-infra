---
status: open
---
# VPN-safe migration — endpoint discovery hold

## Objective and authority

Complete `avoid-work-vpn-address-overlap`, restoring the verified pre-change
capabilities and qualifying R04 freshly against the resulting baseline. The
operator approved `172.27.{10,20,30,40,50}.0/24`, future pods `172.28.0.0/16`
and services `172.29.0.0/16`, active service/storage migrations and unrestricted
maintenance time after current backups, tested endpoint-specific recovery and
independent review pass. No work-VPN changes, route/hosts exceptions, data loss,
recovery bypass or deferred workload deployment. Preserve confirmed household
management, stable names, segmentation, storage isolation and ownership.

## Verified state

- Task-owned worktree: `homelab-infra.worktrees/feat-vpn-safe-migration`, branch
  `feat/vpn-safe-migration`, created from current main `8171e6a` (merged PR #37).
  The dirty primary `feat/group-7-network-plan` and dirty
  `feat/group-7-native-recovery` remain untouched. No live configuration write,
  secret submission, R8 invocation or pending-state release occurred.
- OpenSpec apply was ready with 22 tasks; only allocation authorization 1.1 is
  complete (1/22). No full device/consumer baseline or migration acceptance exists.
- Fresh all-table IPv4/IPv6 route/rule inspection found no intersection of the
  seven approved IPv4 pools with the connected work tunnel's routes. Every
  representative candidate lookup selected the home Ethernet interface. Work
  VPN remains connected; no workstation network, resolver or hosts edits occurred.
- Configured workstation Podman pools `10.88.0.0/16` and `10.89.0.0/24` overlap
  work space; they are unrelated workstation configuration, not silently admitted
  as lab allocations or changed. Home/lab VPN objects, separate admin ranges and
  unknown remote networks still require current evidence. Task 1.2 is incomplete.
- One bounded discovery pass: dated PVE USB SSH and iDRAC HTTPS timed out;
  historical PVE household addresses `.188` and `.190` returned “No route to host”.
  Gateway HTTPS and switch SSH TCP connected. These are access results, not
  device settings, device health, service authentication or recovery proofs.
- Ordinary workstation name resolution returned no records for both management
  names and the retained UniFi hostname. A new task-owned browser tab reported
  `DNS_PROBE_FINISHED_NXDOMAIN` for that hostname. Explicit read-only queries to
  home DNS returned the dated PVE/iDRAC addresses and the controller's home IP.
  Direct DNS queries are diagnostic only, not ordinary-DNS acceptance or a
  resolver override. No TLS bypass or process-local address mapping was used.

## Evidence and remaining gates

Private evidence base (outside Git):
`/home/mpeter/work/homelab-infra-audit-evidence/closure-continuation-2026-10-21/vpn-safe-migration/`.

- `workstation-baseline.json`, SHA-256
  `a023faf9f2ec6c4ac895c0bcc4f89ae92dcf57472ccee1d4df11519d8ac73c2f`.
- `endpoint-access-discovery.json`, SHA-256
  `e989ea641ab6c97b9ee7b265e9455388855fc906b3a871fb69415dca48bf919e`.

Both include observation times and source commit. Their workstation/network
observations are time-sensitive, not reusable live-write admission. Current
PVE/iDRAC address/interface settings and UniFi object settings remain unknown.
The dirty native worktree contains later configuration and recovery procedures
absent from main; inspect and adopt only scoped, independently reviewed source,
never run its writer or publish its unrelated changes wholesale.

The prior [carrier-restoration handoff](2026-10-21-r04-carrier-restoration.md)
and [R04 record](../../docs/r04-carrier-restoration.md) retain historical evidence.
Archived R8 operation
`e8a53069b33dc67f75a5e8002804eb4769eba01c6acb23e9fbe2ad2bf59cb4a8`
has no reviewed explicit custody disposition. Its absent active marker is not
release. Current recoverable backups and actual endpoint-specific rescue are
not established; dated backup hashes and PiKVM owner checks do not satisfy them.
Runtime was not changed by this attempt; rollback was neither needed nor tested.
Historical restored-switch evidence remains historical, not fresh qualification.
Unrelated closure, independent-backup, boot/DIMM and Groups 8/9 limits remain open.

## Next decisive action — operator console/admin evidence

Stop live migration here. From the available R720 local console or a trusted
authorized admin client, capture current PVE addresses/routes, USB identity,
bridge/bond and VM state. Read iDRAC NIC/IP/gateway/VLAN/IPv6 settings separately
from its physical settings path or established local IPMI read path; do not
reboot, install software or alter settings merely to collect this evidence.
Supply the separate admin computer's OS, authorized source, physical switch port
and usable access method. Demonstrate console login and endpoint-specific repair
access without changing network settings; hardware presence alone is not proof.
Keep raw evidence private and redact credentials/security configuration.

These read-only PVE console commands collect the first missing facts:

```sh
date -Is
ip -br address
ip -4 route show table all
ip -6 route show table all
ip -br link
cat /etc/network/interfaces
cat /proc/net/bonding/bond0
qm list
```

If `bond0` is absent, report that result rather than inventing its name or
changing topology. For iDRAC supply the observed dedicated/shared NIC, MAC,
address/mask/gateway, DHCP/static selection, VLAN and IPv6 values; do not expose
credentials or full security configuration. Establish ordinary controller
hostname resolution through permitted infrastructure, not VPN/hosts exceptions.
Then reconcile the exact current baseline, inventory active consumers and finish
backup/recovery/custody gates before preparing the reviewed cutover packet.
