# 0009. Bootstrap encrypted Proxmox state on the break-glass workstation

Date: 2026-10-01

## Status

Accepted; encrypted state and key recovery tested for the disposable VM lifecycle

## Context

The R720 cannot be the sole home of state used to rebuild it. The future Fedora
and AAP VMs are not available, and the operator has deferred selecting an
independent VM-backup destination. The laptop is the current break-glass
machine. OpenTofu 1.13 supports encrypted local state and local file locking.

## Decision

Use a separate Proxmox OpenTofu root with encrypted local state under the
workstation's private homelab directory, outside Git and off the R720. Enforce
encryption for both state and saved plans. Pin the OpenTofu and Proxmox provider
versions. Keep the encryption passphrase outside source. Before any VM apply,
demonstrate lock contention, ciphertext at rest, state restoration, and
independent recovery of the passphrase and a second encrypted state copy.
Keep the local backend for now. Local locking protects concurrent processes on
this laptop only; it does not coordinate other machines. Reconsider migration
to a versioned, locked remote backend through a reviewed, tested change.

## Alternatives rejected

- Put state on the R720 or a VM it manages. Host failure would remove both the
  infrastructure and the means to repair it.
- Create an S3 backend now. It would require choosing an external account,
  bucket, credential, and billing arrangement before the operator has selected
  a backup destination. Native remote locking and versioning remain attractive
  later.
- Keep unencrypted local state in the checkout. State can contain credentials,
  and ordinary Git staging could disclose it.

## Consequences

The laptop can plan without the R720 hosting its own control plane. Local
locking protects concurrent processes on this laptop, not agents on other
machines. The passphrase remains in the desktop keyring and has an independent
copy in a private Google Drive recovery folder alongside the encrypted state
copy. Both were retrieved and byte-compared; the state was restored from that
copy and used to list the disposable VM before destruction, then the final
empty state was restored. The Drive copy is an independent recovery location,
not a remote backend or a source of cross-machine locking.
