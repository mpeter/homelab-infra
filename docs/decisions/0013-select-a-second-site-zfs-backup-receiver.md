# 0013. Select a second-site ZFS receiver for independent backups

Date: 2026-10-02

## Status

Accepted

## Context

The R720's NAS pool and Proxmox VM storage share one home-lab host and site.
Snapshots and a local staging copy cannot recover from loss of that site. The
backup comparison considered online object storage, hosted storage boxes, and
a locally operated ZFS receiver at another site. The operator selected the
local second-site ZFS direction.

## Decision

Use a locally operated ZFS receiver at a physically separate site as the
independent backup destination for NAS data and selected recovery artifacts.
This decision selects the destination type, not a particular machine, site,
transfer method, retention policy, or full-VM archive format. Those details
remain gates in OpenSpec task group 5. Do not place unique NAS or Fedora data
until an actual receiver is identified, remote copies are verified there, and
the required restores pass using separately recoverable credentials and keys.

## Alternatives considered

- Hosted object or storage-box service. This adds recurring charges and a
  provider dependency, but does not require maintaining a second physical
  server.
- A receiver in the same home. This avoids storage rental but does not protect
  against loss of the home or site.

## Consequences

- The receiver needs enough usable capacity for encrypted NAS replication,
  VM archives, retention, and temporary restore work.
- Remote power, WAN upload, firewall/NAT reachability, access security,
  encryption, and key custody must be verified before automation.
- A second ZFS pool alone is not proof of recoverability; destination-side
  verification and independent restore tests remain required.
- If no suitable second-site receiver is available, reconsider the online
  storage alternatives before unique data is introduced.

## Related decisions

- [ADR 0010](0010-run-the-bulk-nas-as-a-vm-with-hba-passthrough.md) remains the
  accepted NAS VM and HBA ownership decision. Its initial rsync.net planning
  note records the earlier direction and is superseded for destination choice
  by this ADR.

## Implementation tracking — 2026-10-03

The operator confirmed that no receiver exists yet. The receiver, remote-copy,
and restore gates originally assigned to OpenSpec Group 5 now belong to the
[independent-recovery backlog item](../../.backlog/2026-10-03-implement-independent-second-site-backup-and-tested-recovery.md).
Group 5 currently prepares an interim same-host backup implementation plan;
this does not change the destination decision or the unique-data gate above.
