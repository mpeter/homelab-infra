# R720-class NIC and boot-failure diagnostics

A runbook for a hypervisor host where a NIC appears faulty: missing from the
operating system, missing from iDRAC's inventory, or reported down after a
reboot. It applies to the R720 and any R720-class host managed the same way.
Follow [R720 change control](r720-change-control.md)'s recovery-exception
process alongside this runbook: capture what changed and why, and reconcile
the versioned source before the next planned change.

## Do not trust an iDRAC "Information Not Available" reading alone

iDRAC's NIC inventory is read from the lifecycle controller and the NIC's own
firmware over a management side channel, not from a live PCIe or driver probe
of the running host. "Information Not Available" means that side channel did
not return a value. It can mean the NIC is physically absent or dead, but it
can equally mean the lifecycle controller cache is stale, the iDRAC-to-NIC
management path is unhealthy, or the inventory was read during or shortly
after a host state change. Treat it as **evidence requiring corroboration**,
not as proof the NIC is physically missing. Corroborate it against the host's
own view (`lspci`, `ip link`, `dmesg`) before planning a physical or
configuration response.

## Establish boot success before judging the NIC

A NIC inventory or link-state read is only meaningful if the host actually
finished booting when it was taken. Before treating any NIC symptom as
confirmed, establish whether the kernel reached a usable initramfs or full
boot on the affected boot attempt:

1. Determine the exact boot attempt the NIC symptom is attributed to. A NIC
   reported absent on an iDRAC inventory snapshot taken during a failed or
   hung boot says nothing about the NIC; it says the host never got far
   enough to enumerate it.
2. Open the iDRAC virtual console (or physical/serial console if available)
   **before** issuing any further reboot or power cycle. The evidence for
   "did this boot actually succeed" lives on that console screen and
   disappears the moment the host is power-cycled again.
3. Capture, in order:
   - the BIOS/UEFI POST screen, including any POST error codes;
   - the boot device selection and firmware-level NIC enumeration (option
     ROM output), if boot stopped there;
   - the kernel boot log through PCI enumeration and NIC driver load
     (`dmesg` equivalent on the console), if boot reached the kernel;
   - initramfs output, including whether it reached a shell, stalled, or
     dropped to an emergency prompt, if boot reached initramfs;
   - the first full-boot command-line evidence (`ip link`, `lspci -nn`
     filtered to the NIC's vendor/device ID, driver bind messages) if boot
     completed.
4. Record which of those stages was actually reached, with a screenshot or
   console log, before touching power. A NIC symptom first observed at a
   stage the console evidence shows the host never reached is not yet a NIC
   finding; it is a boot finding, and the boot failure is the thing to
   diagnose first.
5. Only after boot success is established for that specific attempt does the
   NIC's reported state (present/absent, link up/down, driver bound) become a
   fact worth acting on. If a power cycle already happened before this
   evidence was captured, say so explicitly in the record; the host's next
   boot is a new, separate data point, not a replay of the one that triggered
   the symptom.

This order matters because the natural next step on a "faulty NIC" symptom is
to reboot or power-cycle to retest it, and that destroys the console state
that would show whether the failure was ever actually in the NIC.

## Compatibility workarounds are unverified until tested and recorded

Kernel boot parameters commonly suggested for NIC enumeration or stability
issues on this hardware generation, `intel_iommu=off` in particular, are
compatibility workarounds, not confirmed fixes. Adding one to the boot
configuration is a hypothesis, not a resolution. Before recording it as a fix
anywhere (this repository, an inventory file, an operator note):

1. Record the exact symptom and the boot-evidence stages captured above
   *without* the parameter, so there is a real before state.
2. Apply the parameter as a single bounded change, reboot once, and capture
   the same console evidence sequence again: POST, boot device/NIC
   enumeration, kernel/initramfs log, and full-boot `lspci`/`ip link`
   read-back.
3. Compare the two console captures directly. "The host booted" is not
   sufficient; the NIC must be shown present, enumerated, and bound to its
   driver in the after-capture at the same or later boot stage where it was
   previously missing or stalled.
4. Repeat the boot at least once more with the parameter in place before
   calling the result stable. A single successful boot after a change can be
   coincidence, especially for an intermittent enumeration failure.
5. Record the outcome as what it is: either "tested on \<date\>, boots N/N
   with \<parameter\>, NIC enumerates at \<stage\>" or "untested" /
   "tested, did not resolve it." Do not describe an applied-but-unverified
   parameter as a fix in any committed document or the live host
   configuration source of truth; that misstatement is exactly the kind of
   unverified desired-state claim [R720 change
   control](r720-change-control.md) exists to prevent.

## Summary checklist

- [ ] Identify the exact boot attempt the NIC symptom is attributed to.
- [ ] Capture console evidence (POST, boot/NIC enumeration, kernel/initramfs
      log, full-boot read-back) for that attempt **before** any further
      reboot or power cycle.
- [ ] Confirm which boot stage was actually reached; treat an
      earlier-than-expected stop as a boot finding, not a NIC finding.
- [ ] Corroborate any iDRAC "Information Not Available" NIC reading against
      the host's own `lspci`/`ip link`/`dmesg` evidence, not iDRAC alone.
- [ ] If a compatibility workaround (for example `intel_iommu=off`) is
      proposed, test it with a before/after console-evidence comparison
      across multiple boots before recording it as resolved.
- [ ] Record the result, including an unresolved or "untested" outcome,
      rather than leaving the NIC's actual state implied.
