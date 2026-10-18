# Maintenance read-only backend integration

[English](maintenance-backend.md) · [Türkçe](maintenance-backend_TR.md) · [Safety](maintenance-runtime.md)

`PrinterData` owns an on-demand `MaintenanceReadController` connected to **Maintenance → Diagnostics**. The original six-reader Stage 6 is no longer the complete implementation. Registrations in `maintenance_executor.read_only_adapters()` cover host/system, thermal, motion/driver, filament and ambient information; the exact current list is defined there and in the imported field registries.

`maintenance_read_plan()` intersects registered readers with the current discovery snapshot. `start_maintenance_read(feature_id, device=...)` starts a bounded read-only preflight on the existing Maintenance worker. `poll_maintenance_read()` returns no result while pending, then a `ReadResult`; `cancel_maintenance_read()` invalidates late results. Disconnect/epoch changes cancel the owner. Closing it does not create or replace a worker/client.

Preflight positively identifies the job queue through `/server/info` and, if installed, `/server/job_queue/status`. A failed endpoint is not an absent queue. Printer lifecycle, print/pause/manual-probe/MMU and competing Petrel operations are checked before dispatch and result collection. Information readers do not award hardware PASS. M07 is a separately guarded, on-demand register query; see the [executor](maintenance-read-executor.md).

Opening ordinary menus does not run diagnostic readers. Passive READY discovery has its own bounded service probe, and sampled usage has its own recording path; neither should be confused with diagnostic execution. Results open as [read-only LCD reports](maintenance-ui.md), with explicit labels/units and paging. External clients are not locked by Petrel's local reservation. Controller, executor and diagnostic-presentation regressions run in GitHub Actions.
