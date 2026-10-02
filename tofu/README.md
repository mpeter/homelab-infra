# OpenTofu

The Proxmox root manages the disposable lifecycle-test VM and Fedora development
VM. Fedora VM 100 is deployed and protected; it currently has no unique data.
The NAS is not deployed, and unique data remains gated on the backup and restore
milestone. See the [implementation plan](../docs/implementation-plan.md) and
[R720 change-control contract](../docs/r720-change-control.md) for current gates.

[ADR 0009](../docs/decisions/0009-bootstrap-proxmox-state-on-break-glass-workstation.md)
chooses encrypted local state on the laptop for bootstrap. An independent
encrypted state copy and its recovery passphrase are stored in separate private
Google Drive folders. The current Drive ciphertext was fetched, byte-compared
with the local state, restored into an isolated scratch backend, decrypted, and
used to list the managed Fedora and NAS VMs. The live plan gate, scoped
identity, and disposable-VM lifecycle test have passed; VM backup recovery
remains a gate before unique data is introduced.

OpenTofu owns Proxmox resources, not configuration inside guests. Plans are
reviewed before apply, and existing resources are imported before management.

Proxmox and UniFi use separate roots, state backends, locks, credentials, and
apply jobs. A compute plan must never be able to change the router, switches,
WLANs, DHCP, DNS, or firewall policy. A UniFi provider is added only after the
live controller version and API pass the compatibility gate described in
[the UniFi management contract](../network/unifi/README.md). Existing UniFi
objects must produce a no-change plan after import before any desired-state edit
is applied.

The Proxmox plan gate accepts only explicitly allowed VM resource changes and
rejects deletes or replacements by default. Review each saved plan, then pipe
`tofu show -json` into `bash tofu/proxmox/check-plan.sh` without writing the
JSON to disk. The `--disposable-destroy` mode accepts only deletion of the exact
disposable VM address during the lifecycle test. Run gate behavior tests with
`bash tofu/proxmox/tests/test-check-plan.sh`; the gate does not replace review
or prove that an apply uses the same saved plan file.
