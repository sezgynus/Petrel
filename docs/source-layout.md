# Source layout

[English](source-layout.md) · [Türkçe](source-layout_TR.md) · [Documentation](README.md)

The source tree groups existing code by feature and responsibility. The organization refactor preserves runtime behavior: the same display and printer objects, worker ownership, command guards, event flow, settings, screen coordinates and protocol payloads remain in use. Method bodies and class state are moved without rewriting their logic. A filename or line count alone is not a reason to split a cohesive module.

## Repository map

```text
run.py
petrel/
  application/           display.py, startup.py, input.py, tick.py
  printer/               interface.py, models.py, state.py, capabilities.py
  moonraker/             client.py, subscription.py
  hardware/              encoder.py, dwin/
  ui/                    dashboard.py, header.py, home.py, list_menu.py, selection.py
  features/
    files/               printer.py, browser_view.py, preview.py, metadata.py, ...
    printing/            printer.py, view.py, tuning.py, estimates.py
    motion/              printer.py, view.py, settings.py
    temperature/         printer.py, view.py, preset_store.py
    info/                printer.py, view.py, system.py, qr.py
    nfc/                 printer.py, core.py, backend.py, reader.py, *_view.py, ...
    maintenance/         printer.py, discovery/, execution/, domains/, ...
    mmu/                 state.py, view.py, filament_view.py
    power/               printer.py, view.py, lifecycle.py
    buzzer/              control.py, pwm.py, ipc.py, view.py, ...
    leveling/            bed_mesh.py, probe_wizard.py, *_view.py, ...
    case_light/          printer.py, view.py
    display_settings/    settings.py, view.py
    spoolman/            printer.py, spool_view.py, tags.py
    recovery/            klipper.py, view.py
    software_update/     updater.py
  artwork/               resources.py, boot.py, shared.py, icon_library.py, ...
  emulator/              framebuffer.py, assets.py, runtime.py, remote.py, ...
  diagnostics/           memory_profile.py
  configuration_identity.py
  migration.py
  version.py
tools/
tests/
klipper_extras/
native/
kernel/
assets/
docs/
```

The map highlights ownership; `...` omits supporting files, not a proposed future layer. Python application code lives under `petrel/`. Root files remain deployment/configuration entry points. Tests, developer tools, native/kernel code, Klipper extras and artwork retain their separate purposes.

## Where a change belongs

| Location | Responsibility |
|---|---|
| `application/display.py` | Compose the display object, initialize resources and menus, coordinate actions and cleanup |
| `application/startup.py` | Existing UART reconnection, panel power lifecycle and boot/flash progress methods |
| `application/input.py` | Existing encoder/button event handling, batching and screen dispatch |
| `application/tick.py` | Existing UI tick, telemetry presentation and periodic update methods |
| `printer/interface.py` | Compose `PrinterData`, own existing workers/sessions and coordinate telemetry and command transport |
| `printer/models.py` | Existing position, editor/flag and material preset records; `interface.py` keeps their import bindings |
| `ui/` | Shared display elements and menu/selection primitives used across features |
| `features/<feature>/printer.py` | That feature's existing methods on `PrinterData`; no separate client, worker or state owner is introduced |
| `features/<feature>/view.py`, `*_view.py` | That feature's existing display methods, composed using the existing mixin approach |
| Other feature modules | Existing feature state, protocol integration, settings and calculations |
| `moonraker/`, `hardware/` | Transport, subscription and physical display/encoder integration |
| `artwork/`, `emulator/`, `diagnostics/` | Managed artwork, host display emulation and profiling |

A feature may have several explicitly named views when its screens have distinct responsibilities. Keep a small, coherent set of related functions together. Preserve descriptive existing module names; do not introduce generic `utils` modules or move unrelated helpers into a feature just to reduce file length.

## Maintenance groups

| Directory | Existing responsibility |
|---|---|
| `discovery/` | Capability discovery, device inventory and discovery session |
| `execution/` | Plans, runtime/dispatch guards, controllers, executors and guided workflow |
| `domains/` | Physical domain implementations such as thermal, motion, filament, probe and auxiliary outputs |
| `assessment/` | Assessment model, rules, persistence and service |
| `records/` | Records, usage collectors, device presentation and service references |
| `diagnostics/` | Reports, test tracing and resource probes |
| `ui/` | Maintenance menus, views, navigation and assessment presentation |

`features/maintenance/printer.py` holds the existing bridge methods on `PrinterData`; it does not take ownership from the current controllers or workers.

## Editing and checking the layout

Use explicit package imports and update test patch targets, tool imports, installation paths and documentation when moving code. Attribute names such as `bed_mesh`, `screws_tilt` and `probe_wizard`, persistent keys and native filenames are runtime contracts; they are not Python module paths. Do not apply an unrestricted text replacement to them.

Keep dependency direction intact: feature methods use the display/printer instance supplied through `self`; they must not import the composed display/printer class back from the application entry point. Move methods into existing feature mixins where that responsibility already exists. Keep new grouping mixins free of independent initialization or state ownership.

For an organization-only change, compare method ASTs and class attributes before/after relocation, retain decorators/signatures, then run the [regression checks](../tests/README.md). Existing tests use isolated import-time hardware stubs: patch the owning module captured by `tests/test_regressions.py`, rather than a new copy imported after its `patch.dict` context ends. Run the existing UI-state and maintenance benchmarks as well. The signing bot changes commit SHAs; validate the signed branch HEAD, not its unsigned predecessor. A queued or failed workflow is not a passing check.

Screen behavior still needs the normal physical validation after installation. This layout change does not require settings migration, new services or regenerated panel assets. The documentation screenshot workflow remains a separate manually requested operation.
