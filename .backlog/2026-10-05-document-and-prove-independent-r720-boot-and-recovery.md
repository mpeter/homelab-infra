---
title: Document and prove independent R720 boot and recovery paths
type: enhancement
severity: medium
status: open
created: 2026-10-05
labels: []
---
OpenSpec Task 6.2 was removed from the active `build-r720-homelab` plan on 2026-10-05 because its purpose was unclear. In plain language, it asks whether Proxmox can still start if its current Kingston SATA boot SSD is unavailable, and whether there is usable recovery media and a serial-specific rebuild procedure if it cannot. This is a deferred reliability exercise, not a current failure or a prerequisite for ordinary operation.

The 2026-10-03 readbacks found `/boot`, `/boot/efi`, and `BootCurrent` on Kingston SATA serial `50026B7767031A82`. They also found UEFI entries and EFI directory entries on two NVMe mirror devices, `BTHH95021LD4512D` and `BTHH8122061E512D`, but no independent cold boot proved either path. Read-only FAT inspection found a dirty bit and a primary/backup boot-sector difference on both ESPs; no repair was made. Both NVMe controllers are behind the shared PCI4 adapter, and the physical connector labels are not mapped. Off-host recovery media and serial-bound reconstruction steps are not verified. See `inventory/storage.yaml` observations `pve_esp_inspection_readback_1840` and `pve_boot_nvme_pcie_readback_1858`, plus the preparation matrix in `docs/storage-plan.md`.

When resumed, refresh all live identities and firmware state, map each physical connector to its serial, prepare recovery media and a reviewed rollback procedure, and verify the ESP payloads and firmware entries. Only then schedule a controlled outage to cold-boot with each intended alternate path tested independently while preserving a known-good rollback path. Do not remove the shared PCI4 adapter to isolate a device. If the existing paths fail, document the evidence and seek a separate decision before adding hardware.

**Done when:** Two independent, serial-identified boot paths each complete an accepted cold boot with the other path unavailable, and the recovery media and target-specific reconstruction procedure are verified and recorded. If that cannot be achieved with existing hardware, record the blocker and the exact hardware decision needed.
