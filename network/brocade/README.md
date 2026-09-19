# Brocade switch

AAP owns switch inventory, configuration backups, approved changes, verification,
and rollback. The desired configuration is expressed as reviewed variables and
templates after the current running configuration has been captured and
normalized.

## Compatibility gate

Before write access is enabled:

1. Record the exact model, FastIron/ICX firmware, boot image, stacking state,
   license state, SSH algorithms, and console recovery procedure.
2. Run read-only commands from a pinned Brocade execution environment.
3. Test privilege escalation and configuration parsing against captured output.
4. Back up both running and startup configuration and prove restoration through
   the rescue path.
5. Approve write-capable AAP job templates only after a lab-safe change and
   rollback both succeed.

The old `community.network.icx` platform support may be pinned only inside this
execution environment. The
[`community.network` repository](https://github.com/ansible-collections/community.network)
is archived and its
[`icx_config` module](https://docs.ansible.com/projects/ansible/10/collections/community/network/icx_config_module.html)
is deprecated, so compatibility is a fact to prove and monitor. If it fails,
use maintained
[`ansible.netcommon` CLI primitives](https://docs.ansible.com/projects/ansible/latest/collections/ansible/netcommon/)
through a tested adapter rather than patching the shared AAP environment.

## Initial adoption boundary

Port `1/2/2` is the known active R720 path. Its access/PVID behavior remains
unchanged until the second link, Proxmox bond, VLAN trunk, management reachability,
and switch rescue path have been tested. Early automation is read-only and
backs up configuration; the first write should be a reversible description or
unused-port change.
