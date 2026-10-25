# Documentation

[English](README.md) · [Türkçe](README_TR.md) · [Project home](../README.md)

## User guides

| Guide | Use it for |
|---|---|
| [Printer connection and recovery](klipper-recovery.md) | Normal startup delay, error details and guarded restart actions |
| [Installation and configuration](installation.md) | Wiring, setup, external settings, updates and troubleshooting |
| [Kconfig configuration menu](configuration.md) | Menu navigation, saving and applying settings, optional components and automated configuration |
| [DWIN auxiliary UART](dwin-uart.md) | Optional Linux serial port installation/removal, application access, baud rates and transport limits |
| [Daily use](user-guide.md) | Printing, movement, heating, calibration, Device, Info, light and power |
| [Using Maintenance](user-guide.md#maintenance) | Care plans, hardware checks, results, diagnostics, recommendations and current screenshots |
| [Maintenance physical acceptance](maintenance-stage8-acceptance.md) | Guarded physical tests, optional output profiles, operator observation and real-Pi acceptance |
| [MMU and filament](mmu-guide.md) | Happy Hare gates, spool assignment, tool map, EndlessSpool and recovery |
| [NFC tags and sharing](user-guide.md#nfc-and-rfid) | Emergency stop, spool tags/gates, phone link sharing; [Kconfig setup](configuration.md#nfc) and LCD Device → NFC Settings |
| [LCD compatibility](lcd-assets.md) | Choosing the supported display and checking panel resources |
| [Restore original DWIN resources](restore-stock-dwin.md) | Persistent Flash warning, supplied Creality DWIN_SET and LCD microSD recovery steps |
| [Print and Tune](print-controls.md) | Print dashboard, quiet runtime edits and optional job policy switches |

[Screenshot gallery](screenshots.md): documented example states and direct image links for forum posts.

## Contributing and tools

| Guide | Use it for |
|---|---|
| [Contributing](../CONTRIBUTING.md) | Issues, pull requests, documentation and development checks |
| [Emulator screenshots](ui-emulator.md) | Enable capture and save images from the running service |
| [Tests](../tests/README.md) | Run automated checks and plan hardware validation |
| [UI native-code candidate profiling](ui-native-profiling.md) | Separate normal resource measurements, CPU sampling and Python allocation ownership |
| [LCD artwork](../assets/README.md) | Prepare custom icons and identify artwork |
| [Emulator assets](../assets/emulator/README.md) | Choose matching host-side fonts and icons |

## Optional technical and historical references

These English references are for panel work or historical context; they are not required for ordinary use. Current behavior is described in the user guides above.

- [T5UIC1 panel configuration and protocol](t5uic1-reference.md): panel firmware/resources and low-level reference.
- [Stock asset inventory](lcd-assets.json): audited resource hashes and dimensions.
- [Historical source audit, 2026-10-05](source-audit.md): findings from an earlier review.
- [Historical MMU driver integration, 2026-10-08](mmu-driver-integration.md): the integration record before the MMU merge.

- [Repository Markdown audit, 2026-10-18](documentation-audit-2026-10-18.md): source consistency, bilingual coverage, corrections and the complete reviewed-file inventory.
