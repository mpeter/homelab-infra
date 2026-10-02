# 0011. Use TrueNAS Community Edition for the NAS guest

Date: 2026-10-01

## Status

Accepted

## Context

[ADR 0010](0010-run-the-bulk-nas-as-a-vm-with-hba-passthrough.md) assigns the
whole SAS2308 HBA and its eight SATA SSDs to a NAS VM. The operator prefers
TrueNAS as a home-lab software product and accepts that this is an enthusiast
deployment rather than a supported production appliance. The cited
`r/HomeServer` discussion compares NAS software generally; it is anecdotal and
does not establish virtualization behavior.

TrueNAS's hardware guidance says its developers virtualize for development,
but does not recommend ordinary virtualized deployments for production or
critical data. It calls for direct disk or whole-controller passthrough where
possible. The lab can accept the support and maintenance tradeoff, while
requiring verified HBA isolation, independent backups, and a tested restore
before unique data relies on this NAS.

## Decision

Use TrueNAS Community Edition 25.10.7 as the NAS guest, installed from the
official ISO pinned by its published SHA-256. Attach a dedicated boot disk on
`fast-vm`; pass the entire SAS2308 HBA to the guest only after the host binding
and recovery gates pass. The TrueNAS guest owns the eight SATA devices and
their RAIDZ2 pool. Keep the NAS VM's boot and configuration recovery
independent from that pool.

Do not begin with XPEnology/Arc. It boots Synology DSM on unsupported hardware
through a community bootloader, adding loader and DSM update dependencies to
the primary storage path. If explored later, run it as a separate disposable
experiment with virtual disks, no access to the SAS2308 or real SSDs, and no
unique data.

## Consequences

- The NAS uses the preferred appliance product and integrated ZFS management.
- TrueNAS's virtualized-deployment warning remains a real support and
  maintenance limitation. Home-lab status changes the acceptable risk, not the
  technical requirement to prove passthrough and restore.
- Pin an exact release artifact and checksum. Recheck release status before
  future upgrades; do not automatically track beta or nightly images.
- Pool creation remains separately gated. The operator has classified the
  existing contents on all eight intended SSDs as disposable; preserve the
  current serial mapping, capture off-target partition/ZFS metadata, and review
  the exact guest pool operation before clearing them.
- Same-host RAIDZ2 is not backup. Do not put unique data on the NAS until an
  independent encrypted copy and restore are verified.

## Related decisions

- [ADR 0010](0010-run-the-bulk-nas-as-a-vm-with-hba-passthrough.md) defines the
  HBA and disk ownership boundary.
- [ADR 0009](0009-bootstrap-proxmox-state-on-break-glass-workstation.md)
  defines the independent infrastructure recovery path.

## References

- [TrueNAS Community Edition 25.10.7 release](https://www.truenas.com/docs/scale/25.10/gettingstarted/versionnotes/#25.10.7)
- [TrueNAS software status](https://www.truenas.com/docs/softwarestatus/)
- [TrueNAS virtualization and hardware guidance](https://www.truenas.com/docs/scale/gettingstarted/scalehardwareguide/)
- [Official TrueNAS 25.10.7 ISO](https://download.truenas.com/TrueNAS-SCALE-Goldeye/25.10.7/TrueNAS-SCALE-25.10.7.iso)
- [TrueNAS 25.10.7 ISO SHA-256](https://download.truenas.com/TrueNAS-SCALE-Goldeye/25.10.7/TrueNAS-SCALE-25.10.7.iso.sha256)
- [Operator's r/HomeServer discussion](https://www.reddit.com/r/HomeServer/comments/14539vy/what_is_the_best_nas_software_option/?share_id=cPrbxGcS0rzvUiSzSYrVZ&utm_medium=ios_app&utm_name=iossmf&utm_source=share&utm_term=1)
- [Arc loader documentation](https://xpenology.tech/documentation/)
