# ICX6610 PoE controller failure RCA

Observed on 2026-09-19 against the ICX6610-48P baseline in this repository.
This document separates the evidence gathered from the repair that still needs
a maintenance window.

## Symptom

Both internal PoE controller devices fail to initialize. FastIron hard-resets
the module and immediately repeats this sequence:

```text
PoE Error: Device 0 failed to start on PoE module.
PoE Error: Device 1 failed to start on PoE module.
Resetting module in slot 1 again to recover from dev fault
```

All 48 copper ports remain administratively enabled but operationally off for
PoE. The switch allocates and consumes no PoE power.

## Evidence

- Both AC PoE supplies report healthy, with 748 W capacity each.
- Both fans are healthy and all measured temperatures remain below the warning
  threshold.
- The management module reports healthy and detects P-ENGINE 0 and P-ENGINE 1.
- All 48 ports are admin-on; none reports a denied-power or port-level fault.
- A single-port query reports admin-on, operational-off, zero consumption, zero
  allocation, and no endpoint fault.
- The failure repeats after FastIron's automatic hard reset of the PoE module.
- Installed PoE controller firmware is `02.1.0 Build 001`.
- The current ICX6610 guide and FastIron 08.0.30u package provide
  `fcx_poeplus_02.1.0.b004.fw`.
- The exact Ruckus failure signature is documented with reinstalling PoE
  firmware as the first recovery action. Hardware replacement is the next step
  if current system and PoE firmware do not recover the controllers.

This evidence rules out total PSU loss, exhausted power budget, an individual
powered-device fault, and an individual port fault.

## Root cause assessment

The failure is at the shared controller initialization layer. The leading cause
is obsolete or corrupt PoE controller firmware because both controller devices
fail before endpoint detection and the installed build predates the documented
ICX6610 firmware. A failed PoE controller or management-board power circuit
remains the secondary hypothesis and cannot be excluded without attempting the
supported firmware recovery.

## Staged recovery payload

The recovery files came from the 2025-09-08 Brocade master archive. The archive
matched its published MD5 before extraction.

| File | SHA-256 |
|---|---|
| `fcx_poeplus_02.1.0.b004.fw` | `c6dc85d49fd12b5bc6e62cd79fb3d0f638f107f4d276391019697fa961685496` |
| `FCXR08030u.bin` | `b28fd48deabec75fc2677f8080f815df5e2b5c3434834279a6fc3b5f3aaec407` |
| `grz10100.bin` | `788dade00430503b6778b2cc24993c8fc85ead7fea1a8bc5dea13be7dc049f1d` |

The firmware binaries stay in ignored local inventory and are not committed to
this repository.

## Recovery sequence

1. Reconfirm matching running/startup configuration backups and serial-console
   access.
2. Serve only the ICX6610 PoE image from a temporary TFTP listener restricted to
   the switch management address.
3. Run the documented `inline power install-firmware` command for stack unit 1.
4. Monitor `show log` until programming finishes. Do not interrupt power or
   reload while flash programming is active.
5. Save configuration, then reload the switch during the approved outage.
6. Verify firmware `02.1.0.b004`, absence of the controller reset loop, nonzero
   PoE availability, port detection, switching, VLANs, NTP, and management.

The reload interrupts all traffic through the switch, including the current LAN
uplink and attached server links. Retain the serial console throughout recovery.

If the PoE update does not recover the controllers, stage FastIron 08.0.30u in
secondary flash and test-boot it while preserving 08.0.30t in primary flash as
the rollback image. If the error remains with 08.0.30u and PoE build 004, treat
the PoE controller hardware as failed.

## Rollback

PoE controller firmware does not have a useful in-place downgrade path. The
configuration backup and serial console protect switch configuration and boot
access, while the primary FastIron image remains untouched during any later
secondary-image test. If controller programming fails, keep the switch powered,
capture the final log, and recover through the serial console rather than
cycling power blindly.

## References

- [Fohdeesha FCX and ICX6610 setup](https://fohdeesha.com/docs/fcx.html)
- [Ruckus community response for the exact controller error](https://community.ruckuswireless.com/discussion/38807/icx6610-48p-poe-error-device-0-1-failed-to-start-on-poe-module)
- [FastIron 08.0.30u release notes](https://fohdeesha.com/data/other/brocade/08030u_ReleaseNotes_v1.pdf)
