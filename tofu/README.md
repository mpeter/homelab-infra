# OpenTofu

The Proxmox root manages the disposable lifecycle-test VM, Fedora development
VM, and TrueNAS NAS VM. Fedora VM 100 uses 8 vCPU, 32 GiB RAM, and a 300 GiB
boot disk; it currently has no unique data. TrueNAS Community Edition 25.10.7
is installed on NAS VM 200's 32 GiB boot disk. The installer ISO is detached,
and the VM boots from `scsi0`. NAS VM 200 uses 4 vCPU and 16 GiB fixed RAM.

All eight intended Crucial MX500 SSD serials are visible in the guest, and
read-only SMART overall-health checks passed for each. The VM is running with
the `nas-hba` mapping on the SAS2308; the live host check confirms the HBA is on
`vfio-pci` and the Proxmox pools do not include the existing `array` pool. The
existing SATA contents remain unchanged; the guest pool has not been created.

At the latest capacity read-back, the host reported 125 GiB RAM total and 98
GiB available; `fast-vm` had 962,530,536 KiB available. These are observed
headroom figures, not fixed reservations for later guests. Re-measure and
budget IdM, AAP, and OpenShift when their versions and recovery prerequisites
are selected. A host cold boot with VM 200 stopped and the NAS guest's managed
start/stop/reset checks have passed. HBA detach rollback remains open, the guest
pool remains gated on off-target GPT and ZFS-label captures plus the reviewed
pool plan, and unique data remains gated on the independent backup and restore
milestone. See
the [implementation plan](../docs/implementation-plan.md) and [R720
change-control contract](../docs/r720-change-control.md) for current gates.

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
or prove that an apply uses the same saved plan file. The `--nas-detach` mode
accepts only removal of the exact `nas-hba` mapping from stopped VM 200 while
preserving its other configuration. `--nas-attach` accepts the installer
state, while `--nas-reattach` accepts only the installed-guest state with the
installer ISO detached and `scsi0` first; both require the VM to stay stopped
and preserve every other VM property.
