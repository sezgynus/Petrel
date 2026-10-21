# Kconfig configuration menu

[Documentation](README.md) · [Türkçe](configuration_TR.md)

Run `./configure.sh` in `~/Petrel` to open the terminal menu. `install.sh` uses the
same menu on first installation. Kconfiglib 14.1.0 is a configuration-only dependency;
the wrapper installs it into the existing Petrel virtual environment if missing.
Without that environment it creates a separate private configuration virtualenv.
The configurator adds no background work to the running UI.

## Navigate and apply

Use arrows and Enter to navigate/edit, Space to toggle, `?` for help, `S` to save,
and `Q` to exit. The menu contains connections/power, encoder/presets, maintenance
counters, display tools, DWIN auxiliary UART and apply options. Settings that depend
on a disabled feature are hidden; their saved values are retained for re-enabling.

Existing settings are read from `~/.config/Petrel/Petrel.env`. Saving in menuconfig
only stages a selection. After leaving the menu, confirm **Apply saved configuration**
with `y` to perform installation/removal and atomically save the environment file.
Exit without saving, or answer `n` to Apply, to leave runtime settings and optional
installations unchanged. First-install cancellation stops the installer before
service registration. Dependency bootstrap may already have completed.

**Restart running Petrel after applying** is enabled by default. Disable it to skip
the final restart; changing the shared UART transport can still require a restart
inside its installer. Klipper is never restarted automatically. After changing the
counter extra, restart Klipper manually while idle.

## Preservation and failures

Custom keys and private `MOONRAKER_API_KEY` records remain in the environment file;
the API key is not displayed or exported into Kconfig. The preset path and custom
remote address/port are imported. The environment file remains mode `0600`; no
`.config` or installation-specific files are added to the Git checkout.

The apply step validates all fields before invoking installers. If another process
changed the environment while the menu was open, reopen the menu instead of
overwriting those changes. Installer failures leave the environment unchanged and
attempt to undo earlier successful component changes; a failed rollback is reported
explicitly. Each optional component retains its own installation safety checks,
including refusal to remove an auxiliary UART in use.

## Explicit unattended configuration

Piped answers to the former question sequence are no longer accepted. Export the
current settings without applying anything:

```bash
./configure.sh --export-config ~/petrel-settings.config
```

Edit that private file using Kconfig syntax (`CONFIG_PETREL_AUX_UART=y`,
`CONFIG_PETREL_AXIS_TRAVEL=n`, quoted strings), then apply explicitly:

```bash
./configure.sh --apply-config ~/petrel-settings.config --no-restart
```

A supplied file can be a partial overlay: absent symbols retain the imported
settings. Invalid/unknown settings fail before application. `--no-restart` skips only
the final Petrel restart, not transport transitions required by a component installer.
API-key records and other opaque settings are retained from the target machine.
