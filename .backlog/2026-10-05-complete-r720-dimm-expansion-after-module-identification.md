---
title: Complete R720 DIMM expansion after module identification
type: enhancement
severity: medium
status: open
created: 2026-10-05
labels: []
---
OpenSpec Task 6.1 was removed from the active `build-r720-homelab` plan on 2026-10-05 at the operator's direction. The optional R720 expansion from eight to sixteen 16 GB RDIMMs remains unqualified. The recorded set of eight purchased modules has no verified part numbers, serials, speed, or rank. A historical report says one new module hung POST in A1, but the module identity and original test output were not retained. No module is cleared or identified as defective. The latest recorded PVE read found eight Samsung 16 GB 2Rx4 RDIMMs in A1-A4/B1-B4 at 1600 MT/s; A5-A12/B5-B12 were empty. OS memory, iDRAC total memory, and the per-DIMM capacity sum disagreed. See the dated evidence in `inventory/host.yaml` and the physical-maintenance section of `docs/implementation-plan.md`.

Before any installation or extended diagnostic, identify every purchased module by label/serial and map it to the failed-POST report if possible; verify module type, rank, organization, voltage, frequency, processor compatibility, and the A5-A8/B5-B8 slot population against the Dell R720 manual. Require a fresh verified backup, planned outage, clean shutdown, and current change-control preflight. Do not increase VM allocations until post-install validation passes.

**Done when:** The supported module population is installed during an approved outage after its backup and recovery gates pass; iDRAC and the OS agree on the resulting 256 GiB inventory, extended diagnostics pass without new memory errors or SEL events, and `inventory/host.yaml` records the exact modules and results. If the operator abandons the expansion, record that disposition and remove the modules from the planned capacity target.
