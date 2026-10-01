# 0009. Bootstrap encrypted Proxmox state on the break-glass workstation

Date: 2026-10-01

## Status

Accepted for bootstrap; VM apply remains gated on tested state and key recovery

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
Reconsider migration to a versioned, locked remote backend when an independent
backup destination is selected; migration must preserve state and be tested.

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
machines. A keyring-only passphrase or a second file on the same disk does not
constitute independent recovery. The VM gate stays closed until state and key
loss have been rehearsed from a separate recoverable copy.
