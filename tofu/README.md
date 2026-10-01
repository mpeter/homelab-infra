# OpenTofu

This directory will contain Proxmox and UniFi provider configuration, reusable
modules, and environment composition. VM configuration is deferred until an
encrypted, recoverable off-host state backend and automation identity are
established; the Proxmox root currently has only pinned tooling, encryption
configuration, a plan gate, and its tests.

[ADR 0009](../docs/decisions/0009-bootstrap-proxmox-state-on-break-glass-workstation.md)
chooses encrypted local state on the laptop for bootstrap. It is not an apply
authorization: independent key and state recovery, effective token scope, and
the VM backup destination remain unverified or unresolved.

The [R720 change-control contract](../docs/r720-change-control.md) blocks the
first VM until state recovery, scoped identity, plan-type gating, and a
disposable-VM lifecycle test are verified. Host pools and repositories remain
outside this state.

OpenTofu will own Proxmox resources, not configuration inside guests. Plans are
reviewed before apply, and existing resources are imported before management.

Proxmox and UniFi use separate roots, state backends, locks, credentials, and
apply jobs. A compute plan must never be able to change the router, switches,
WLANs, DHCP, DNS, or firewall policy. A UniFi provider is added only after the
live controller version and API pass the compatibility gate described in
[the UniFi management contract](../network/unifi/README.md). Existing UniFi
objects must produce a no-change plan after import before any desired-state edit
is applied.

The Proxmox plan gate accepts only VM resource changes and rejects deletes or
replacements by default. Review a saved plan, then pipe `tofu show -json` into
`bash tofu/proxmox/check-plan.sh` without writing the JSON to disk. The
`--disposable-destroy` mode accepts only deletion of the exact disposable VM
address during the lifecycle test. Run its behavior tests with
`bash tofu/proxmox/tests/test-check-plan.sh`. This gate does not replace
reviewing the saved plan or proving that the apply uses that same plan file.
