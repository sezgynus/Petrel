# Installation and configuration

[English](installation.md) · [Türkçe](installation_TR.md) · [Documentation](README.md)

## Before installation

> **⚠️ Persistent LCD resource overwrite:** On first connection or when resources change, Petrel automatically writes its own boot JPEG, shared slot-1 JPEG page and icon library to the DWIN LCD's non-volatile Picture Flash. These replace stock visual data and remain after shutdown or Pi software removal. This is required for Petrel's current interface symbols, animations and efficient native rendering. The [original Creality DWIN_SET](../assets/stock-dwin/DWIN_SET) and a [step-by-step stock restoration guide](restore-stock-dwin.md) are included. **Review this before installing or updating.**

Use a compatible DWIN T5UIC1 panel, a Linux SBC with UART/GPIO, Python 3.11+ and a working Klipper/Moonraker setup. Check [LCD compatibility](lcd-assets.md). The installer does not flash LCD kernel firmware or fonts; the application synchronizes Petrel icons automatically at its first LCD connection.

## Wiring and serial setup

| Display connection | Raspberry Pi connection |
|---|---|
| RX | GPIO14 / UART TX |
| TX | GPIO15 / UART RX |
| Encoder A | GPIO21 |
| Encoder B | GPIO19 |
| Encoder button | GPIO20 |
| VCC | 5 V |
| GND | GND |

GPIO numbers are **BCM numbers**. Encoder pins can be changed during configuration. See [wiring illustrations](../images/) for the physical connections.

In `sudo raspi-config`, enable serial hardware and disable the serial login console, then reboot. Confirm which UART device uses GPIO14/15 on your Pi and OS. The installer suggests `/dev/ttyS0`; choose the device appropriate for your installation.

## Install

Run as the user who will own the service. The checkout must be clean and located at `~/Petrel`:

```bash
cd ~
git clone https://github.com/sezgynus/Petrel.git
cd ~/Petrel
./install.sh
```

Press Enter to accept a prompt's default, or enter your own value:

| Setting | Installer default |
|---|---|
| Moonraker URL | `http://127.0.0.1:7125` |
| UART | `/dev/ttyS0` |
| Encoder A/B | `21 19` |
| Encoder button | `20` |
| Moonraker power device | `Printer` |
| Power-on hold | `2000` ms (2 seconds) |
| Axis travel counters | `1` enabled; enter `0` to decline |
| Klipper repository (when enabled) | `~/klipper` |
| Main Klipper config (when enabled) | `~/printer_data/config/printer.cfg` |
| Emulator / screenshot capture | `0` disabled |
| Remote display | `0` disabled |

Installation prepares `~/petrel-env`, installs dependencies and enables `Petrel.service`. It keeps settings in `~/.config/Petrel/Petrel.env`, adds a `Petrel.conf` include beside `moonraker.conf` and registers the service for Moonraker updates. Existing settings are preserved when installation is repeated.

For a nonstandard Moonraker configuration location:

```bash
MOONRAKER_CONFIG=/path/to/moonraker.conf ./install.sh
```

## Optional axis travel counters

The existing `configure.sh` offers **Enable axis travel counters? (1=yes, 0=no)**. First configuration defaults to **1**; Enter accepts installation, `0` declines it. Later runs preserve your saved choice. Existing installations are not silently modified on update: run `./configure.sh` to select this feature.

Enabling creates `klippy/extras/petrel_axis_travel.py` as a symlink to the extra in the Petrel repository, creates `petrel-axis-travel.cfg` beside your main Klipper config, and inserts a marked include block at the beginning of that main config, unless an existing wildcard include already covers the fragment. It does not change tracked Klipper source or `.gitignore`: only that exact symlink path is added to the repository-local Git exclude file. Existing user exclusions are retained. Foreign conflicting files are not overwritten. **Each `configure.sh` prompt above is editable:** URL selects the Moonraker instance, UART selects the LCD port, GPIO entries select encoder wiring, power device selects the relay, hold time controls power-on, and the last three entries control this optional integration and its paths.

**Restart Klipper while idle after enabling or disabling**, then restart Petrel to refresh discovery. The configurator never restarts Klipper automatically. Petrel offers X/Y/Z travel devices and **Recorded travel (metres)** reminders only when the extra is actually loaded. See [usage tracking](maintenance-usage.md) for measurement limits and resource bounds.

Run `./configure.sh` again and choose **0** to disable. This removes only Petrel's managed config fragment/include, symlink and its own added Git exclusion. Counters and maintenance history remain; saved distance reminders pause. Apply the same idle Klipper restart. The extra follows Petrel updates through the symlink; running Klipper loads the updated module on its next restart. A Klipper reinstall/hard recovery may remove the link: rerun `configure.sh` to repair it.

## LCD resources and first start

**LCD font installation is optional.** Petrel works with the stock DWIN font. For the typography shown in Petrel's screenshots, you may optionally [install the bundled LCD font](lcd-assets.md#lcd-font) from the display's SD slot. Icons and boot artwork synchronize automatically over UART.

1. Wait for Petrel startup progress to finish and **Home** to appear.
2. Rotate the encoder and open a menu; check temperatures against the web interface.
3. For wrong text/icons, follow the [LCD resource guide](lcd-assets.md); for connection failures, use the troubleshooting table below.

Normal cold-start MCU connection delays keep the splash for up to 30 seconds; explicit errors/shutdowns open recovery immediately. See [connection and recovery](user-guide.md#printer-connection-and-recovery) for refresh/restart actions.

Moonraker must authorize the Petrel connection. Set `MOONRAKER_API_KEY` if authentication is required. Check the service user's serial/GPIO permissions; the installer configures the `dialout` and `gpio` groups.

## Change settings

```bash
cd ~/Petrel
./configure.sh
```

Current values become the prompt defaults. The emulator and remote-display prompts default to **0 (off)** on new configurations; saved values are preserved on subsequent runs. Emulator enables screen capture; remote display enables browser viewing and encoder control and also starts the emulator, even if the separate capture preference is off. Existing remote host/port settings are preserved; the default listener is `0.0.0.0:8088`. Your custom `PETREL_SETTINGS_FILE` path and other environment settings, including unprompted font/socket/screenshot-directory options, are preserved without duplicating keys. The file is replaced atomically with private permissions. After saving, accept the offered service restart to apply them. Display brightness/dimming are adjusted on the LCD under **Home → Display**, rather than here.

For settings not prompted by the configurator, edit the external environment file. Use plain `KEY=value` lines, without `export`:

| Setting | Purpose / default |
|---|---|
| `MOONRAKER_URL` | Moonraker address / `http://127.0.0.1:7125` |
| `MOONRAKER_API_KEY` | Authentication key if required / empty |
| `PETREL_REQUEST_TIMEOUT` | Request timeout in seconds / `5` |
| `PETREL_SERIAL_PORT` | Configured UART / installer suggests `/dev/ttyS0` |
| `PETREL_ENCODER_PINS` | Encoder A/B in BCM numbering / `21 19` |
| `PETREL_BUTTON_PIN` | Encoder button in BCM numbering / `20` |
| `PETREL_SETTINGS_FILE` | Local preset fallback / `~/.config/Petrel/presets.json` |
| `PETREL_POWER_DEVICE` | Name of your Moonraker power device / `Printer` |
| `PETREL_POWER_ON_HOLD_MS` | Power-on hold in milliseconds / `2000`; `0` means immediate |
| `PETREL_EMULATOR` | Screenshot capture / `0` disabled, `1` enabled; prompted by `configure.sh` |
| `PETREL_REMOTE` | Browser display and encoder control / `0` disabled, `1` enabled; also starts emulator |
| `PETREL_REMOTE_HOST` | Remote listener / `0.0.0.0`; preserved by configurator |
| `PETREL_REMOTE_PORT` | Remote port / `8088`; preserved by configurator |
| `PETREL_AXIS_TRAVEL` | Optional extra installation preference / `1` on first configuration; change using `configure.sh`, not by editing this key alone |
| `PETREL_KLIPPER_DIR` | Klipper repository containing `klippy/extras` / `~/klipper` |
| `PETREL_PRINTER_CONFIG` | Main config to receive the managed include / `~/printer_data/config/printer.cfg` |

Restart after editing: `sudo systemctl restart Petrel.service`. Keep private keys and machine settings outside tracked repository files. See the [emulator guide](ui-emulator.md) for screenshot-specific options.

## Update

### Updates and migration from older installations

Existing installations migrate automatically after their next Moonraker update: the old updater downloads this version, and the first service start schedules a separate migration job. It preserves settings, moves the checkout to `~/Petrel`, prepares `~/petrel-env`, installs `Petrel.service` and reloads Moonraker with the new updater. Allow a few minutes for Python dependencies. Automatic migration requires the same passwordless sudo access normally available on the Pi; otherwise run `sudo python3 ~/KlipperDWIN/petrel_migration.py --user "$USER"` once. Migration refuses to overwrite an existing Petrel installation. A failed service switch restores the previous installation; details are in `journalctl -u Petrel-migration.service`.

After Moonraker reloads its configuration, use **Mainsail → Machine → Update Manager → Petrel**. Refresh and update; dependencies and the service restart are handled automatically. Update Manager follows `master`.

You can also check and install Petrel updates from **Info** on the LCD while the printer is idle. See [Info and updates](user-guide.md#info-and-updates). Local edits to tracked repository files may block updating; inspect or back them up before recovery discards them.

## Troubleshooting

```bash
sudo systemctl status Petrel.service --no-pager
journalctl -u Petrel.service --since "10 minutes ago" --no-pager
sudo systemctl restart Petrel.service
```

| Symptom | What to check |
|---|---|
| Blank screen or repeated reconnects | Panel power, crossed TX/RX, selected UART, serial login console and permissions |
| Encoder does not respond | BCM pin settings and wiring |
| Startup stays on one stage | Klipper/Moonraker readiness, panel resources and service logs |
| Optional menu missing or locked | Required Klipper/Happy Hare configuration, connection and current printer state |
| Preview image or metadata missing | Slicer thumbnails and metadata available in Moonraker |
| Wi-Fi information unavailable | Wireless connection and availability of Linux `iw` |
| Update blocked | Local repository edits and Moonraker Update Manager status |
| Action failed or timed out | Check the actual printer state in Mainsail before repeating |

For a bug report, include the software revision, Pi/OS, configuration relevant to the problem and the log excerpt. Add a photo or [emulator screenshot](ui-emulator.md) for visual problems; remove credentials before sharing.

### Sensor event counters in an extra update

The existing optional axis-travel extra now also supplies event-based sensor counters. The shared `configure.sh` option preserves its existing `PETREL_AXIS_TRAVEL` key. No additional extra file/include is needed. An installed symlink follows the updated file; restart Klipper while idle to load it, then restart Petrel. Klipper is not restarted automatically. An old/disabled/missing extra pauses event-based reminders and preserves histories. See the [usage counter guide](maintenance-usage.md#event-based-sensor-counters) for supported sources and counting coverage.
