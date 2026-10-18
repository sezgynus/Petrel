# Bounded read-only Maintenance executor (development)

[Türkçe](maintenance-read-executor_TR.md) · [Safety](maintenance-safety.md)

**Status:** The on-demand information executor is integrated into Diagnostics. It does not actuate motors/heaters/fans or award hardware PASS. M07 uses a guarded register-query G-code path; the other readers use bounded GET or explicitly registered local record/panel providers.

`maintenance_executor.read_only_adapters()` joins host/system, thermal, motion/driver, filament and ambient field registries. Registrations are not inferred from arbitrary device names. It uses the existing client and worker, without a new thread, connection or subscription. Every read requires positive idle/session checks; dispatch and result collection reject changed print/lifecycle/config state. Local readers include saved history, sampled usage and panel/encoder counters. Explicit report export is a separate bounded storage operation, not a hardware action.

`start(row)` validates an explicit INFORMATION plan, a trusted fixed adapter, a bound timeout and a fresh positive safety context, returning admission status. `poll()` is nonblocking and returns `None` until a result is available. `cancel()` invalidates the session and suppresses late responses; `close()` does not close Petrel-owned client/worker. Only selected numeric/status fields from a response become a small evidence tuple; raw API mappings and secrets are not retained.

A successful information read has `ReadResult.status=None`, meaning **observed telemetry, not a hardware PASS**. Missing measurements produce `INCONCLUSIVE`, cancellation/unsafe state `ABORTED`, and read errors/timeouts `ERROR`. These are intentionally not persisted as completed physical tests.

**Current integration:** `MaintenanceReadController` supplies live queue/operation evidence and owns this executor; the LCD presents named reports and full paginated measurements. A caller must never fabricate positive safety flags. The initial GET-only stage is historical; M07's direct path below is already implemented.

`tests/test_maintenance_executor.py` covers valid/missing/invalid payloads, method selection, cancellation, queued reads, external printing, epoch drift and shared worker ownership in GitHub Actions CI.

## Current M07 implementation: homing-independent direct register diagnostics

Current M07
Diagnostics issues `DUMP_TMC STEPPER=<verified name> REGISTER=DRV_STATUS` on
explicit request for supported TMC chips. Klipper's `notify_gcode_response`
is correlated using the existing Moonraker connection, a fresh response
cursor and RPC completion. Historical lines, ambiguous/double replies,
missing data and communication errors never become a fault-free result.
No motor enable/homing/movement or register writing occurs. Exact TMC2208
bit masks yield a bounded fault summary; other supported chips show only
the raw register. TMC2660 keeps its passive fallback because selecting its
read register writes RDSEL. M07 remains informational; M10 stays reserved.
GitHub CI covers normal GET and direct register/failure paths; no local tests.
