# ICX6610 PoE controller failure RCA

Observed and tested on 2026-09-19 against the ICX6610-48P baseline in this
repository.

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

## Root cause

The failure is in the PoE controller hardware or its management-board power and
communication path. Both controllers fail before endpoint detection and reject
the supported firmware updater. The same failure persists on current FastIron
08.0.30u. Healthy supplies, fans, temperatures, switching ASICs, links, and
management eliminate the surrounding power and system software paths.

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

## Recovery results

1. Running and startup configuration backups matched before the change.
2. The build-004 controller image transferred successfully under FastIron
   08.0.30t, but the controller returned `Firmware Update failed` and remained
   on build 001.
3. FastIron 08.0.30u was written to secondary flash, passed its integrity check,
   and booted with the saved configuration. Primary 08.0.30t remained intact.
4. The build-004 controller image transferred successfully again under
   FastIron 08.0.30u. The controller again returned `Firmware Update failed`.
5. Both controller devices continued their initialization and hard-reset loop.
6. Layer 2 forwarding, active 1/10/40 GbE links, VLAN state, HTTP management,
   Proxmox reachability, iDRAC reachability, and NTP synchronization passed after
   the maintenance window.
7. FastIron 08.0.30u is now the configured secondary boot target. Primary
   08.0.30t remains the serial-console rollback image.

The failed controller programming is the decisive result: a software update
cannot communicate successfully with either PoE engine. PoE remains unavailable
on all copper ports.

## Recommended disposition

Continue using the switch for non-PoE Layer 2, Layer 3, 10 GbE, and 40 GbE work
if the repeated controller-reset logging is acceptable. If PoE is required,
replace the chassis or management board rather than attempting more flash writes.
Use external standards-compliant PoE injectors or a separate PoE access switch
as the lower-risk interim option.

## Rollback

Primary flash still contains 08.0.30t. From the serial console, a one-time
`boot system flash primary` returns to the previous FastIron image. The matching
post-maintenance running/startup backups protect the saved configuration. The
PoE controller itself remains on its original build 001 because both update
attempts were rejected before controller programming completed.

## References

- [Fohdeesha FCX and ICX6610 setup](https://fohdeesha.com/docs/fcx.html)
- [Ruckus community response for the exact controller error](https://community.ruckuswireless.com/discussion/38807/icx6610-48p-poe-error-device-0-1-failed-to-start-on-poe-module)
- [FastIron 08.0.30u release notes](https://fohdeesha.com/data/other/brocade/08030u_ReleaseNotes_v1.pdf)
