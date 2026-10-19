# Repository Markdown source audit — 18 October 2026

[English](documentation-audit-2026-10-18.md) · [Türkçe](documentation-audit-2026-10-18_TR.md)

Audit baseline: `7830d04fb7794f541004f4289931a7e649ebd9a9` (master). All **92 tracked Markdown files** were inventoried and reviewed, including **44 EN/TR pairs**, three intentionally English technical/historical references and one internally bilingual screenshot-assets README.

Review covered current user flows, API/command contracts, identifiers, constants/limits, installer defaults, records, source links, local targets/anchors, executable examples and translation coverage. Historical observations and intermediate totals remain dated evidence, not current acceptance summaries.

## Findings and corrections

| ID | Documents | Correction | Source boundary |
|---|---|---|---|
| D01 | tests/README*, CONTRIBUTING* | Branch CI incorrectly described as master-only; documented signing and all-branch CI gate. | `.github/workflows/regression.yml`, `sign-commits.yml` |
| D02 | maintenance-backend*, read-executor* | Removed six-reader/no-UI/pending-integration claims; documented production registries, local readers and M07 exception. | `maintenance_executor.py`, `maintenance_controller.py`, `ui_maintenance.py` |
| D03 | maintenance-test-catalog*, test-planner*, safety*, runtime*, guided* | Separated pure module responsibilities from implemented controller/UI composition; added F02/F12 registrations. | `maintenance_catalog.py`, `maintenance_planner.py`, `maintenance_guided.py` |
| D04 | maintenance-discovery* | Reconciled READY probing with the exact six endpoints, including Spoolman and roots; removed obsolete pre-merge wording. | `maintenance_services._ENDPOINTS` |
| D05 | maintenance-profiles*, pulse*, physical* | Replaced universal 950-ms/single-pixel/dim-effect claims with feature-specific timing and 1–32-pixel RGB contracts. | `maintenance_pulse.py`, `maintenance_physical.py` |
| D06 | maintenance-stage8-acceptance*, test-recording* | Replaced old Self Tests routing, three-second operator deadline and legacy deployment/profile instructions. | `ui_maintenance.py`, `maintenance_physical.py` |
| D07 | maintenance-thermal*, reference-printer-acceptance* | Replaced seven separate H trials and stale pending summaries with grouped H01 and recorded procedure acceptance; FAILED_METRIC preserved. | `maintenance_heater.py`, acceptance JSON ledger |
| D08 | maintenance-thermal* | Added the missing English counterpart to the Turkish 16 October troubleshooting section; labeled historical scope. | Dated source/trace context retained in both guides |
| D09 | maintenance-acceptance-2026-10-17*, audit-fixes*, resonance* | Labeled dated evidence as historical; removed current instructions to preserve the retired ceiling or manually disable MMU for parked E11. | `maintenance_thermal.py`, `maintenance_filament.py` |
| D10 | maintenance-pi-acceptance* | Kept the worktree until measurements finish; generalized the Python path and distinguished real revision A/B from identical master checkouts. | `tools/validate_maintenance_pi.py`, `tools/measure_petrel_resources.py` |
| D11 | user-guide*, installation*, README*, docs/README* | Added discoverable startup grace/recovery and guarded restart behavior. | `ui_recovery.py`, `klipper_recovery.py`, `petrel_ui.py` |
| D12 | print-controls*, user-guide* | Moved time semantics to a dedicated section; documented total elapsed, distinct Remaining/ETA, unknown values and day offsets. | `print_estimates.py`, `printerInterface.py`, `ui_print_focus.py` |
| D13 | user-guide*, ui-emulator*, screenshots* | Documented Info scrollbar; removed fixed gallery-count/exhaustive-screen claims and clarified capture-revision limits. | `graphite_theme.py`, `petrel_ui.py`, screenshot scene registry |
| D14 | t5uic1-reference.md, source-audit.md | Corrected Area-0 splash-region restoration; translated the English audit table that was still Turkish. | `PetrelDisplay._draw_boot_progress`, retained historical commits |
| D15 | TR/EN role/protocol guides | Removed escaped backticks and aligned executable placeholders, command blocks and example image order. | Full Markdown pair review and CI document contracts |

## Validation and limits

`tests/test_markdown_contracts.py` checks local Markdown/HTML links, section anchors, explicit language-pair exceptions, paired command blocks/image order and discovery endpoint coverage. These mechanical checks complement semantic review; matching counts do not prove translation meaning or hardware behavior.

No runtime printer behavior, acceptance JSON, physical test results or PNG/GIF image bytes were changed by this audit. Existing images remain example captures; current text describes later recovery/time changes. External URL availability was not exhaustively network-checked. No local regression suite/emulator or physical printer test was run; the complete suite runs in CI on the signed commit.

English-only exceptions follow the existing index policy: `t5uic1-reference.md`, `source-audit.md`, `mmu-driver-integration.md`. They were reviewed, not mistaken for missing user-guide translations. `docs/assets/screens/README.md` contains both languages in one file.

## Complete baseline file inventory

| File | Review outcome |
|---|---|
| `CONTRIBUTING.md` | Corrected |
| `CONTRIBUTING_TR.md` | Corrected |
| `README.md` | Corrected |
| `README_TR.md` | Corrected |
| `assets/README.md` | Reviewed; retained |
| `assets/README_TR.md` | Reviewed; retained |
| `assets/emulator/README.md` | Reviewed; retained |
| `assets/emulator/README_TR.md` | Reviewed; retained |
| `assets/icons/README.md` | Reviewed; retained |
| `assets/icons/README_TR.md` | Reviewed; retained |
| `assets/shared-artwork/README.md` | Reviewed; retained |
| `assets/shared-artwork/README_TR.md` | Reviewed; retained |
| `assets/stock-dwin/README.md` | Reviewed; retained |
| `assets/stock-dwin/README_TR.md` | Reviewed; retained |
| `docs/README.md` | Corrected |
| `docs/README_TR.md` | Corrected |
| `docs/assets/screens/README.md` | Reviewed; retained |
| `docs/installation.md` | Corrected |
| `docs/installation_TR.md` | Corrected |
| `docs/klipper-recovery.md` | Reviewed; retained |
| `docs/klipper-recovery_TR.md` | Reviewed; retained |
| `docs/lcd-assets.md` | Reviewed; retained |
| `docs/lcd-assets_TR.md` | Reviewed; retained |
| `docs/maintenance-acceptance-2026-10-17.md` | Corrected |
| `docs/maintenance-acceptance-2026-10-17_TR.md` | Corrected |
| `docs/maintenance-assessment.md` | Reviewed; retained |
| `docs/maintenance-assessment_TR.md` | Reviewed; retained |
| `docs/maintenance-audit-fixes.md` | Corrected |
| `docs/maintenance-audit-fixes_TR.md` | Corrected |
| `docs/maintenance-auxiliary.md` | Reviewed; retained |
| `docs/maintenance-auxiliary_TR.md` | Reviewed; retained |
| `docs/maintenance-backend.md` | Corrected |
| `docs/maintenance-backend_TR.md` | Corrected |
| `docs/maintenance-discovery.md` | Corrected |
| `docs/maintenance-discovery_TR.md` | Corrected |
| `docs/maintenance-filament.md` | Reviewed; retained |
| `docs/maintenance-filament_TR.md` | Reviewed; retained |
| `docs/maintenance-guided.md` | Corrected |
| `docs/maintenance-guided_TR.md` | Corrected |
| `docs/maintenance-motion.md` | Reviewed; retained |
| `docs/maintenance-motion_TR.md` | Corrected |
| `docs/maintenance-physical.md` | Corrected |
| `docs/maintenance-physical_TR.md` | Corrected |
| `docs/maintenance-pi-acceptance.md` | Corrected |
| `docs/maintenance-pi-acceptance_TR.md` | Corrected |
| `docs/maintenance-probe.md` | Reviewed; retained |
| `docs/maintenance-probe_TR.md` | Reviewed; retained |
| `docs/maintenance-profiles.md` | Corrected |
| `docs/maintenance-profiles_TR.md` | Corrected |
| `docs/maintenance-pulse.md` | Corrected |
| `docs/maintenance-pulse_TR.md` | Corrected |
| `docs/maintenance-read-executor.md` | Corrected |
| `docs/maintenance-read-executor_TR.md` | Corrected |
| `docs/maintenance-reference-printer-acceptance.md` | Corrected |
| `docs/maintenance-reference-printer-acceptance_TR.md` | Corrected |
| `docs/maintenance-resonance.md` | Corrected |
| `docs/maintenance-resonance_TR.md` | Corrected |
| `docs/maintenance-runtime.md` | Corrected |
| `docs/maintenance-runtime_TR.md` | Corrected |
| `docs/maintenance-safety.md` | Corrected |
| `docs/maintenance-safety_TR.md` | Corrected |
| `docs/maintenance-stage8-acceptance.md` | Corrected |
| `docs/maintenance-stage8-acceptance_TR.md` | Corrected |
| `docs/maintenance-system.md` | Corrected |
| `docs/maintenance-system_TR.md` | Corrected |
| `docs/maintenance-test-catalog.md` | Corrected |
| `docs/maintenance-test-catalog_TR.md` | Corrected |
| `docs/maintenance-test-planner.md` | Corrected |
| `docs/maintenance-test-planner_TR.md` | Corrected |
| `docs/maintenance-test-recording.md` | Corrected |
| `docs/maintenance-test-recording_TR.md` | Corrected |
| `docs/maintenance-thermal.md` | Corrected |
| `docs/maintenance-thermal_TR.md` | Corrected |
| `docs/maintenance-ui.md` | Reviewed; retained |
| `docs/maintenance-ui_TR.md` | Reviewed; retained |
| `docs/mmu-driver-integration.md` | Reviewed; retained |
| `docs/mmu-guide.md` | Reviewed; retained |
| `docs/mmu-guide_TR.md` | Reviewed; retained |
| `docs/print-controls.md` | Corrected |
| `docs/print-controls_TR.md` | Corrected |
| `docs/restore-stock-dwin.md` | Reviewed; retained |
| `docs/restore-stock-dwin_TR.md` | Reviewed; retained |
| `docs/screenshots.md` | Corrected |
| `docs/screenshots_TR.md` | Corrected |
| `docs/source-audit.md` | Corrected |
| `docs/t5uic1-reference.md` | Corrected |
| `docs/ui-emulator.md` | Corrected |
| `docs/ui-emulator_TR.md` | Corrected |
| `docs/user-guide.md` | Corrected |
| `docs/user-guide_TR.md` | Corrected |
| `tests/README.md` | Corrected |
| `tests/README_TR.md` | Corrected |
