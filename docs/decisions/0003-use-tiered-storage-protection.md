# 0003. Use tiered storage protection

Date: 2026-09-19

## Status

Accepted

## Context

The host has six NVMe devices and eight 1 TB SATA SSDs. Mirroring every device
would reduce usable capacity even for reproducible workloads. Striping every
device would turn a single failure into a full restore. Backups and local
redundancy address different recovery objectives.

## Decision

Mirror PVE root and important fast VM storage, stripe the explicitly disposable
NVMe tier, and use RAIDZ2 for bulk capacity. Maintain independent backups for
unique data regardless of local redundancy.

## Alternatives rejected

- Mirror every pool. This provides strong random I/O and quick resilvering but
  spends half of all capacity on availability that scratch data does not need.
- Stripe every pool. This maximizes capacity and speed but makes routine device
  failure cause unnecessary host and development downtime.
- Use RAIDZ2 for every pool. The two-device NVMe tiers cannot use RAIDZ2, and
  important VM workloads benefit from mirrored random I/O and simple recovery.

## Consequences

- The scratch pool can be lost after one device failure and must contain only
  reproducible or backed-up data.
- The bulk pool favors capacity and two-device fault tolerance over maximum VM
  random-write performance.
- Dataset placement becomes an intentional operational decision.
- This policy does not protect against loss of the host or site.
