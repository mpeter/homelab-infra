# ICX6610 offline PoE firmware analysis

Analysis date: 2026-09-19. Scope: locate error callers and candidate controls in
the downloaded image. No image was modified or flashed, and no live memory or
switch settings were changed during this investigation.

## Image and method

Image: `FCXR08030u.bin`, SHA-256
`b28fd48deabec75fc2677f8080f815df5e2b5c3434834279a6fc3b5f3aaec407`.

Binwalk identified four bzip2 streams. Python's bzip2 decoder extracted them
in memory; Capstone decoded PowerPC 32-bit big-endian instructions. The image
retains ELF32-style symbol records and their string table, allowing function
names and bounds to be recovered without guessing from nearby strings.

| File offset | Decompressed size | Observed contents |
|---|---|---|
| `0xb0` | `0x17b6e50` | Executable and constants, load address `0x20000000` |
| `0x7a3235` | `0x5121e0` | Data, header load address `0x217b7000` |
| `0x87228c` | `0x1d01a0` | Symbol records, 16 bytes each |
| `0x935a9c` | `0x2ace08` | Symbol-name string table |

The header's two segment checksum values match standard CRC32 of the
decompressed contents: `0x46fb20a9` and `0xbad25363`. This establishes two
integrity fields, not the complete validation/repackaging contract. Other
header checks, sizes, offsets, and bootloader expectations remain unverified.

## Error and reset callers

All addresses below are virtual addresses in this exact image, not offsets in
the compressed firmware file and not instructions for writing live memory.

| Function | Address | Relevant behavior |
|---|---|---|
| `poedevProcess1stSysStatusMsg` | `0x2096e360` | Tests status bits, invokes callbacks, prints device-start failures, and can return `-124` |
| `pdsinePollResetResponse` | `0x20972820` | Processes reset status; on `-124`, checks a device field and can call hard reset |
| `pdsineResetHard` | `0x209736e0` | Prints the hard-reset message, cleans up driver state, resets hardware, and schedules completion |
| `pdsineProcessSwVersionCompletion` | `0x209793c0` | Contains a second fault-driven hard-reset path |
| `poedevProcessResetCompletion` | `0x209730e0` | Prints completion and calls reset-response polling |

The two exact device-start strings are at `0x20983290` and `0x209832c4`.
Their callers in `poedevProcess1stSysStatusMsg` call `uprintf` directly.
The repeated-recovery string at `0x20984110` has callers at `0x209728f0`
and `0x209797fc`; both lead to `uprintf` followed by `pdsineResetHard`.
The hard-reset message at `0x209843a8` is also printed through `uprintf`.

Both inspected recovery paths check a 32-bit field at offset `0x13c2` in the
device structure before initiating another hard reset. They set it to one
afterward. Reset-response polling and software-version completion can clear it
to zero. This is an internal recovery guard, not an identified configuration
option.

Ghidra established its actual lifecycle: it prevents a second reset within the
same cycle, then `pdsineProcessSwVersionCompletion` clears it after a
post-reset status pass. It is therefore intentionally reusable and explains the
unbounded loop. Forcing it nonzero would suppress both recovery paths, but it
would also bypass their controller cleanup and fault callback behavior.

### Exact observed-fault path

For the ICX6610 chassis branch, `poedevProcess1stSysStatusMsg` copies the
initial controller response into the device structure. It tests the byte at
offset `0xbf9`:

- bit `0x04` prints the Device 0 startup failure;
- bit `0x08` prints the Device 1 startup failure;
- when both bits are set (`0x0c`), it returns `-124`.

`pdsinePollResetResponse` receives `-124`, prints the repeated-recovery
message, calls `pdsineResetHard`, marks the recovery guard, and returns `-111`.
`pdsineResetHard` cleans up PoE state, toggles the relevant hardware reset path,
and schedules `poedevProcessResetCompletion` after 100 timer units. The latter
polls reset status again. `pdsineProcessSwVersionCompletion` contains a second
fault-driven reset path based on `poedevIsDeviceFaulty`.

This proves that the switch receives a controller status response with both
startup-fault bits set. It does not identify the underlying failed component,
but it rules out the narrower claim that the reset loop proves a completely
dead controller bus.

The exact `-124` assignment for this chassis branch is the four-byte PowerPC
instruction `li r25,-0x7c` at virtual address `0x2096e9d4` and derived-code
offset `0x96e9d4` in 08.0.30u. It is function-relative offset `0x674` in
`poedevProcess1stSysStatusMsg`. There are two other `-124` assignments in the
same function for different chassis/status branches. This is a patch candidate,
not a proposed modification: changing only this assignment would leave the two
direct error prints and would alter a controller-fault return contract.

## Candidate controls tested by static analysis

- `cli_dm_poe_debug_emesg_off` at `0x2024ae40` calls
  `poeEventTraceLoggingToggle(0, 0)`. This controls event tracing. The direct
  console calls above bypass that handler, so it is not evidence of a way to
  silence this loop.
- `poe_drv_rate_limit_dprintf` at `0x2096d6a0` checks debug state and uses a
  message rate-control helper. The identified error/reset call sites do not
  use it.
- `poe_print_after_loop` exists as a data symbol at `0x21cc16f0`, but a bounded
  search for direct address constructions found no references. Its name alone
  establishes neither its purpose nor a usable control.

No existing user-configurable retry-disable flag was established by this pass.
That is a bounded negative result, not proof that none exists elsewhere.

## Cross-version comparison

The switch's retained primary image was exported read-only through a
source-IP-restricted, one-shot TFTP receiver while the switch stayed online.
Its SHA-256 is
`28a8f908adb77d9bd23fcc156d285de29f90d6b672459b4b340f14a52bda3eda`.

The same functions exist in the retained 08.0.30t rollback image at different
absolute addresses but with matching sizes. In particular, the three `li
r25,-0x7c` assignments occur at the same function-relative offsets in both
images: `0x674`, `0x6f4`, and `0x780`. The Device 0/1 combined-fault path is
therefore not an 08.0.30u regression.

| Function | 08.0.30t address | 08.0.30u address | Size |
|---|---:|---:|---:|
| `poedevProcess1stSysStatusMsg` | `0x2096dda0` | `0x2096e360` | `0xa40` |
| `pdsinePollResetResponse` | `0x20972260` | `0x20972820` | `0x184` |
| `pdsineResetHard` | `0x20973120` | `0x209736e0` | `0xdc` |
| `pdsineProcessSwVersionCompletion` | `0x20978e00` | `0x209793c0` | `0x494` |
| `poedevIsDeviceFaulty` | `0x20981080` | `0x20981640` | `0x38` |

## Container validation contract

The FastIron `MUCH` container has two bzip2 payload records. The boot monitor
contains code that validates the `MUCH` magic and accepts the current image
family revision `0x07f3` at header offset `0x04` (it also accepts `0x07f1` and
`0x07f5`). It reads the record-table offset from header offset `0x14` and
record stride from the low halfword at `0x1e`. The record count is the high
halfword of the 32-bit packed field at `0x20`; the low halfword is still
unassigned metadata.

In this image the table begins at `0x60`, has two records of `0x28` bytes, and
each record's payload offset is at `+0x04`, output length at `+0x10`, compressed
input-size field at `+0x20`, and expected CRC32 at `+0x24`. The boot monitor
passes the record to its decoder and compares its computed result with `+0x24`.
For both retained images, this input size exactly matches the bytes consumed by
the corresponding bzip2 stream.

For 08.0.30u the first code stream begins at file offset `0xb0`; its decoded
CRC32 is `0x46fb20a9`, matching record 1. The second stream begins at
`0x7a3235`; its decoded CRC32 is `0xbad25363`, matching record 2. This explains
the two verified header checksums.

Several top-level metadata fields still vary between the valid 08.0.30t and
08.0.30u files and have not yet been fully assigned a meaning. A candidate
patched image must preserve or correctly regenerate every one of them. The
validated contract is sufficient to parse and verify the payload records, but
not sufficient to declare a newly packaged image flash-safe.

## Revised interpretation and patch feasibility

These paths can report device faults after processing controller status, so the
earlier claim that firmware cannot communicate with either engine was stronger
than the evidence supports. The observed faults and failed firmware programming
still support a hardware/controller-path problem, but do not identify a failed
component or establish complete bus loss.

An offline patch to suppress these specific print calls is technically plausible:
the callers and symbols are available. It would leave recovery attempts running.
A patch to stop retries is a different change requiring a complete state-machine
and cleanup analysis. Simply returning success or skipping hardware reset is not
a validated solution. Neither approach restores PoE hardware functionality.

Before proposing a flashable image, trace the higher-level callers' handling of
`-124` and `-111`, timer cleanup, and firmware-upgrade callbacks. Separately
establish the remaining top-level metadata fields and test repacking an
unchanged image through the boot monitor's verification path. No patched
artifact has been produced.

## Validated patch-plan boundary

The evidence supports an offline engineering plan, not a safe firmware change:

1. Preserve the unmodified 08.0.30u image, its SHA-256, and the working primary
   rollback image. Run `network/brocade/firmware-analysis/verify_much_container.py`
   against each before every analysis step; it verifies the observable `MUCH`
   record table, decoded sizes, and CRCs without writing any file.
2. Treat `0x2096e9d4` / derived-code offset `0x96e9d4` as a *loop-suppression
   candidate only*. A change there would alter the combined Device 0/1 fault
   return from `-124`; it does not silence the direct messages and it does not
   cover the second reset path in `pdsineProcessSwVersionCompletion`.
3. First trace every caller and return-value use for `-124` and `-111`, then
   identify an existing terminal fault/PoE-disable state that preserves driver
   cleanup and invokes the normal fault callback. The acceptance criterion is a
   bounded transition to that state with no hard-reset timer scheduled.
4. Independently trace every top-level `MUCH` metadata field and reproduce the
   boot monitor's complete verification behavior with an unchanged repack. The
   acceptance criterion is byte-for-byte reproducibility or a verified
   boot-monitor-equivalent validator, including all header checks.
5. Only after steps 3 and 4 should a disposable lab switch receive a candidate
   image. Confirm normal boot, primary-image rollback, no watchdog reset, normal
   non-PoE forwarding, and an explicit terminal PoE-fault state. Do not use the
   production switch as that first target.

Current status: steps 1 and the relevant state-machine trace are complete;
steps 3 and 4 are open. A flashable image is therefore intentionally out of
scope.

## References

- [Fohdeesha hidden diagnostics](https://fohdeesha.com/docs/hidden.html)
- [Fohdeesha hidden command list](https://fohdeesha.com/docs/store/FastIron-Hidden.txt)
- [Fohdeesha firmware extraction](https://fohdeesha.com/docs/firmware.html): its FIT-image instructions concern newer firmware; this image instead contains the bzip2 segments described above.
