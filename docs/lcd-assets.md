# LCD compatibility

[English](lcd-assets.md) · [Türkçe](lcd-assets_TR.md) · [Documentation](README.md)

## Supported display

Petrel provides the same 272×480 portrait interface on DWIN T5UIC1 and compatible Creality DACAI panels. The enclosure or printer name alone does not identify the controller. TJC and unrelated DWIN models are outside this support claim. DWIN, DACAI and TJC firmware/resource packs are not interchangeable.

- **DWIN T5UIC1:** Compatible 4.3-inch Ender 3 V2 panel; uses T5UIC1 commands and display direction **1**. The stock font is supported; Petrel's HZK font is optional.
- **DACAI:** The validated reference hardware is Ender 3 Max Neo revision 1.5. Look for an Allwinner F1C100s and often a 大彩 sticker; its update folder is `private` rather than `DWIN_SET`. The detailed [firmware/testing scope](dacai.md) does not automatically validate other revisions or firmware.

[Choose your panel](installation.md#choose-your-panel) during installation. The controller is not detected automatically: select **DWIN T5UIC1** or **DACAI** under **Display panel → Panel type**.

## Panel features

| Feature | DWIN T5UIC1 | DACAI |
|---|---|---|
| Printing, Tune, movement, calibration, MMU, Spoolman and Maintenance | Depends on installed Klipper/integration features | Same shared UI and conditions |
| Boot, menu icons and NFC/fan animations | Native icon library and panel animations | Automatically uploaded icon sheets; host advances frames |
| Print previews | Black-background filtering | Opaque preview composed on the UI background |
| Brightness/dimming | Through the panel driver | Same controls mapped to the panel's 0–63 range |
| Buzzer and event sounds | Pi hardware PWM | Same; independent of panel protocol |
| Host-connected NFC reader | Supported | Supported; USB/UART/I²C/SPI depends on reader capabilities |
| Extra display serial port / attached NFC | Optional DWIN auxiliary UART | Unsupported; selecting DACAI removes an installed broker |
| Screenshot / remote display | Supported | DACAI commands interpreted; physical font/rendering may differ |
| Font | Stock DWIN or optional HZK | Installed `private/truefont` TrueType; Petrel does not upload fonts |
| Host–display speed | 115200 | 115200; optional 230400, 460800 or 921600 |
| Stock resource recovery | Original DWIN_SET, DWIN only | Model-matched DACAI firmware/`private` package; never DWIN_SET |

## Persistent LCD assets and stock recovery

Artwork persists on both panels; removing the Pi software does not restore stock appearance. Boot and shared artwork use pictures 0/1. **DACAI** uploads the complete icon library as currently eight 272×480 JPEG sheets into pictures **16 and up**, using about 320 KB total storage. On the reference panel first upload takes about 40 s at 115200 or 20 s at 460800. Later starts upload only changed pictures. A failed sync is not marked successful; the next start retries. See [DACAI recovery](dacai.md) for SD updates, empty icons and storage limits.

### DWIN resource layout and recovery

The following Picture Flash block/ICO layout and DWIN_SET recovery are for **DWIN only**.

> **⚠️ Stock artwork is replaced automatically.** The original Ender-3 V2 resource set did not provide the complete icon states, animations and artwork needed by Petrel's modern UI. To preserve predictable visuals and responsive native icon drawing, Petrel now manages its own images in non-volatile **Picture Flash**. This is **not temporary** and is not undone by uninstalling Petrel.

- **Boot JPEG:** Petrel synchronizes its `assets/petrel_bootsplash.jpg` to Picture Flash **slot 0**.
- **Shared UI JPEG:** Petrel synchronizes `assets/petrel_shared.jpg` to Picture Flash **slot 1**. Info copies QR regions from its decoded Area 1 cache.
- **Icon library 2:** Petrel packs the baseline JPEGs under `assets/icons/` into 32 KiB blocks starting at **slot 2**, within slots **2–15**, and uploads only changed blocks. This provides menu icons, selected states, print controls and animation frames without redrawing all artwork as primitives.
- **Write reduction:** Content fingerprints are kept in a separate persistent Data Flash area, so matching resources are normally skipped. These fingerprints are **not a backup** of the original OEM images.
- **Not overwritten automatically:** The LCD kernel and font resources. Print thumbnails are transferred to volatile SRAM. The bundled ASCII font is **optional** and is installed manually by SD card only if the user chooses it.

**To restore the stock Creality boot image and icon resources, flash the [original DWIN_SET](../assets/stock-dwin/DWIN_SET) from the LCD microSD slot** after stopping Petrel. Follow the [original DWIN restoration guide](restore-stock-dwin.md). Merely uninstalling the host service cannot restore Picture Flash. This package is for **DWIN T5UIC1 only**; it is not interchangeable with DACAI/TJC. The original LCD files also do not restore the printer mainboard firmware.

## Before installing or replacing a panel

Check the controller family and installed resource pack, not just the screen size. The application installer does not flash LCD kernel firmware or install the LCD font. For DWIN firmware work use the [T5UIC1 reference](t5uic1-reference.md); for DACAI use the [DACAI reference](dacai.md).

After setup, inspect menu labels/icons, colors, preview images and encoder navigation on the physical display. A working emulator screenshot does not guarantee that a different panel/resource pack renders the same way.

## Print previews

Previews come from Moonraker and do not need a new panel asset pack. Missing thumbnails do not prevent starting a print. Images are prepared again after restarting or reconnecting; they do not replace installed icons. **DWIN:** Thumbnails use baseline 4:2:0 JPEG at quality 94 with black backing and native enhanced background filtering. Dark model pixels are lifted to a minimum luminance of 48 before alpha compositing, so pure black becomes dark gray; fully transparent pixels and letterboxing remain black and reveal the UI surface. Partial-alpha edges may be clipped by the panel filter; inspect them on hardware.

**DACAI:** Previews are opaque and composed on the UI background. The panel only decodes 4:2:0 JPEG; a thin colour fringe up to 2 px can remain at model edges. Black filtering is not the DWIN path.

## Resource identification

**The ICO packing and manual upload commands below are DWIN-only.** DACAI converts the same JPEG sources to icon sheets; for forced reload use [DACAI post-SD-update instructions](dacai.md#after-a-microsd-update).

The application now builds library 2 from [`assets/icons`](../assets/icons/README.md) and automatically uploads changed blocks at the first LCD connection after an update. Unchanged resources are skipped. Follow that guide to add JPEGs, export a pack or force a reload after reinstalling panel resources.

Automatic synchronization is the normal path. For developer diagnostics, the following command rebuilds the pack from current `assets/icons` JPEG sources and uploads it over UART; it does not read the reference ICO file:

```sh
sudo systemctl stop Petrel.service
if systemctl is-active --quiet Petrel-dwin.service; then
  export PETREL_DWIN_SOCKET=/run/petrel-dwin/display.sock
else
  unset PETREL_DWIN_SOCKET
fi
~/petrel-env/bin/python ~/Petrel/tools/flash_icon_library.py && sudo systemctl start Petrel.service
```

The tool uses the configured serial port and writes slots starting at 2 (one slot per 32 KiB block). Failed writes leave the service stopped. It checks write acknowledgements, without Flash readback. Inspect the icons on the physical panel after upload.

To inspect the reference export itself, pass `--file` explicitly with the service stopped. This uploads the specified file's bytes rather than rebuilding from JPEG sources; the reference export may differ or be older if sources have changed:

```sh
sudo systemctl stop Petrel.service
if systemctl is-active --quiet Petrel-dwin.service; then
  export PETREL_DWIN_SOCKET=/run/petrel-dwin/display.sock
else
  unset PETREL_DWIN_SOCKET
fi
~/petrel-env/bin/python ~/Petrel/tools/flash_icon_library.py --file ~/Petrel/assets/emulator/2.ICO && sudo systemctl start Petrel.service
```

For contributor artwork, `tools/pack_icon_library.py source.ICO destination.ICO --library 2` preserves JPEG images while keeping each icon within one 32 KiB block. This layout avoids splitting icons at the boundaries associated with the observed rendering faults.

The [stock inventory](lcd-assets.json) records the resources previously audited for this project. It does not identify the files installed on your own panel. Contributor artwork and emulator font-selection instructions are linked from the [documentation index](README.md).

## LCD font

**DACAI:** Uses the installed `private/truefont` TrueType font. Do not apply the DWIN HZK/font-SD procedure below. Petrel does not upload fonts; consult the DACAI firmware package for your model if typography differs.

**For DWIN:**

**Optional — Petrel works with the stock DWIN LCD font.** Changing the font is a visual preference, not a requirement for Petrel's features or performance. The bundled ASCII font can make physical text resemble Petrel's documentation screenshots. If you choose to use it, copy the font-only `assets/fonts/DWIN_SET` directory (containing `0T5UIC1.HZK`) to a compatible LCD update SD card, power off the printer, insert the card in the LCD's card reader and power on. Wait for the resource update to finish, power off, remove the card and start normally. **Do not use the separate stock-recovery `assets/stock-dwin/DWIN_SET` for this optional font change.** Petrel's boot artwork and icon library update automatically over UART, but the Pi service never uploads font Flash. The emulator uses the bundled font, so screenshots can have different typography from a physical panel retaining its stock font. The font's DejaVu license is in `assets/emulator/Petrel-font-license.txt`.


## Compact managed IDs

The current library has 186 icons at IDs 0–185; 186–255 are free. The DWIN PETICO06 metadata version rejects older resident directories, including PETICO05, before new boot frames can start. The DWIN export occupies 12 blocks; DACAI carries the same icon IDs on separate sheets. See the [current icon inventory](../assets/icons/README.md).

### Manual transport ownership

Run these commands as the Petrel service user, while the printer is idle. With the auxiliary UART installed, leave `Petrel-dwin.service` running and explicitly use its display socket as above: an SSH shell does not inherit the UI service drop-in. This retains one physical UART owner and avoids hanging up auxiliary/NFC clients. Without a broker, unset the socket variable and use the configured physical UART directly. Never open that UART directly while the broker owns it. Do not stop the broker as an upload shortcut; it disconnects auxiliary clients. Failure leaves Petrel stopped for inspection; restart only after resolving the error. `reload_icons.py --boot` explicitly restores slots 0 and 1 plus library 2; without `--boot`, its existing icon/shared-page behavior is retained. Panel settings and fonts are preserved.
