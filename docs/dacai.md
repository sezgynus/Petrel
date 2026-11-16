# DACAI panels

[English](dacai.md) · [Türkçe](dacai_TR.md) · [Documentation](README.md)

Some Creality printers, for example the **Ender 3 Max Neo**, ship a 4.3-inch knob display that looks like the DWIN T5UIC1 panel but is made by **Guangzhou DACAI** (大彩). Its firmware emulates most of the T5UIC1 command set, so Petrel can drive it with a small panel-specific driver.

## Recognize the panel

- The panel's microSD update folder is named **`private`** (with `icon/`, `image/`, `truefont/`, `config.txt`) instead of `DWIN_SET`.
- The board carries an **Allwinner F1C100s** processor and often a 大彩 sticker.

## Panel firmware

The reference panel runs Creality's official Ender 3 Max Neo display firmware: `firmware.zlib`
(build May 18 2022) from the Creality package `SW-V1.4.1_C` (20 Oct 2022), folder
`Display Firmware`. Animations (`0x28`), virtual areas (`0x25`/`0x26`) and the `0x27` bit 7
behavior were also verified with the panel's older factory firmware. **Thumbnails (`0x70`),
picture upload (`0x33`), picture IDs above 15 and therefore the icon sprite sheets were only
verified with the official firmware.** If icons or thumbnails stay empty, update the panel first:
copy `firmware.zlib` and the `private` folder from that package to the root of a FAT32 card
(allocation unit 4096), power the panel with the card inserted and remove the card afterwards.

> **⚠️ Never copy a `DWIN_SET` folder to a DACAI panel.** DWIN and DACAI resource packs are not interchangeable.

## Enable

Run `./configure.sh`, open **Display panel**, choose **Panel type → DACAI** and optionally choose a faster **DACAI host UART speed**. Save, exit and confirm Apply. The settings are stored as `PETREL_DACAI=1` and `PETREL_DACAI_BAUD` in `Petrel.env`.

First installation, panel selection, test-branch switching and software updates/rollback are covered in the [shared installation guide](installation.md). The [panel feature table](lcd-assets.md#panel-features) summarizes DWIN/DACAI differences. This reference retains firmware, recovery, storage measurements and protocol details.

### DWIN auxiliary UART

The DWIN auxiliary UART protocol is unsupported by Petrel's DACAI driver, so **Panel type → DACAI** and **DWIN auxiliary UART as a Linux serial port** exclude each other:

- Selecting **Panel type → DACAI** hides the auxiliary UART option. Apply turns it off and removes an installed auxiliary-UART broker (kernel driver, service and `/var/lib/Petrel/dwin-uart.json`), so an existing installation can switch to a DACAI panel in one step.
- `configure.sh --apply-config` refuses a file that enables both, and `install.sh` stops before changing anything when `Petrel.env` contains `PETREL_DACAI=1` together with `PETREL_AUX_UART=1`.
- Petrel refuses to start a DACAI panel through the broker socket (`PETREL_DWIN_SOCKET`).

NFC readers connected to the host (USB or the Pi's own UART/I²C/SPI) are unaffected.

| Speed | Use |
|---|---|
| 115200 | Default; the panel's power-on speed |
| 230400, 460800, 921600 | Faster artwork upload and thumbnails; all three were error-free on the reference panel |

The panel keeps a raised speed until it loses power. Petrel switches it back to 115200 when it exits and, while it waits for the panel, tries every host speed (the configured one first), so a crashed service still finds it, even after the speed setting was changed.

## What Petrel uploads

No microSD card is needed. On the first start Petrel uploads over the UART:

| Picture | Content |
|---|---|
| 0 | Boot artwork |
| 1 | Shared UI artwork (Info QR regions) |
| 16 and up | Icon sprite sheets: the complete icon library packed onto 272×480 JPEG sheets (currently 8) |

Each picture occupies 32 KB of panel storage (about 320 KB in total, of which about 260 KB is new compared with the stock pictures; a panel with the stock files has about 630 KB free). The first upload takes about 20 seconds at 460800 baud and about 40 seconds at 115200 (measured on the reference panel). Content fingerprints are stored in the panel's Data Flash, so later starts upload only changed pictures.

DACAI panels only read icons from their own icon files, which cannot be written over the UART. Petrel therefore draws each icon by copying it from a sprite sheet in virtual display area 1, and steps icon animations (boot progress, fan, NFC approach) from the host. Every later frame of the large NFC animations is stored as the most similar earlier frame plus the rectangle that changed, and each of these animations sits on a sheet of its own, which keeps the whole library on 8 sheets. Other Petrel features work unchanged.

If the upload or its verification fails, Petrel does not mark the artwork as synced: it reports the error like a failed DWIN artwork sync, does not draw from stale sheets, and uploads again on the next start.

## After a microSD update

Updating the panel from its microSD card removes the uploaded pictures, but the fingerprints remain, so Petrel would not notice. Upload everything again with:

```bash
sudo systemctl stop Petrel.service
~/petrel-env/bin/python ~/Petrel/tools/dacai_artwork.py --serial-port /dev/ttyS0
sudo systemctl start Petrel.service
```

Use the UART from your configuration instead of `/dev/ttyS0`.

## Icons stay empty after an upload

The panel stores every picture as a file on its 1 MB flash file system and acknowledges `0x33`
even when it cannot store the file. Pictures cannot be read back over the UART, so Petrel cannot
detect this: the log reports a completed upload, but the icons on the missing sheets stay empty.

This happens when the file system is full. A panel with its stock files has plenty of room, but
larger files of your own (for example custom icon files) or an offline edit of the file system
can use it up. Update the panel from its microSD card to reset its files, then upload the
artwork again as described above.

## Limits

- **Font:** text uses the TrueType font installed on the panel (`private/truefont`). Petrel does not upload fonts.
- **No auxiliary UART:** Petrel does not support the DWIN auxiliary UART protocol on this panel, so [DWIN auxiliary UART](dwin-uart.md) and NFC readers attached to the display cannot be used (see [DWIN auxiliary UART](#dwin-auxiliary-uart) above). NFC readers connected to the host work.
- **Diagonal lines:** the panel's `0x03` draws only horizontal and vertical segments; a diagonal segment becomes one L-shaped step. Petrel sends diagonals as one-pixel staircases, which look like normal lines.
- **Black is transparent:** like DWIN icon drawing, transparent icons treat near-black pixels as background, so very thin dark details can disappear.
- **Thumbnails are opaque:** `0x70` cannot filter the black backing like `0x24`, so Petrel composes print previews on the UI background (or the print tile) instead. The panel decodes only 4:2:0 JPEGs, so a thin colour fringe of up to 2 px can remain at model edges.
- **Emulator and remote display:** the driver announces the DACAI dialect, so the emulator interprets `0x70`, the inverted `0x27` bit 7, the extra `0x27` row, `0x09` moves and the resident sprite sheets like the panel.

## For developers

`DacaiDriver` (`petrel/hardware/dwin/dacai.py`) subclasses `T5UIC1Display`; the DWIN path stays
unchanged. Keep these points in mind when changing display code:

- **Draw through the driver methods.** `show_icon`, `configure_animation`, `set_animation_mask`,
  `copy_cache`, `move_area`, `draw_polyline`, `show_sram_jpeg`, `set_backlight` and
  `prepare_picture` are overridden. Code that sends raw opcodes with `_send` bypasses the DACAI
  handling (for example the corrected `0x27` and `0x09` rectangles, see the table below).
- **Icons need no extra work.** Sprite sheets are built from `assets/icons` at runtime
  (`petrel/artwork/sprites.py`); new or changed icons are uploaded on the next start. Frames of
  `sprites.DELTA_SEQUENCES` (the large NFC animations) are stored as a patch over the most
  similar earlier frame. Patches sit on the 16 px JPEG grid of their frame and leave out their
  outer pixel, so 4:2:0 chroma from neighbouring sheet content cannot bleed in. The tests keep
  the library at 8 sheets and each NFC animation on one sheet.
- **Capabilities instead of panel checks.** Feature code asks the driver, not `dacai.enabled()`:
  `OPAQUE_SRAM_JPEG` (thumbnails need a background) and `PANEL_PROTOCOL` (packet dialect for the
  emulator).
- **Lines:** `draw_polyline`/`draw_line` turn diagonal segments into staircases; long staircases
  are split into several `0x03` frames.
- **Animations** of library 2 are stepped by the host (`poll_host_animations`, called from the UI
  tick). The interval keeps the `0x28` unit of 10 ms; the shortest frame time is 40 ms.
- **Reserved resources:** pictures 0 (boot), 1 (shared artwork) and 16 and up (sprite sheets);
  Data Flash `0x0600`–`0x083F` (sprite checkpoints) in addition to the DWIN records.
- **Not available on DACAI:** `0x24` (use `show_sram_jpeg`), `0x39`/`0x3A` (no auxiliary UART;
  the aux methods raise `UnsupportedPanelFeature`), writing icon files. A new opcode may need an
  override in `DacaiDriver`; see the table below.
- **New artwork in pictures:** pass JPEG bytes through `lcd.prepare_picture()` before
  `write_sram` + `store_sram_as_picture` (baseline 4:2:0, at most 32,764 bytes on DACAI).
- **Tests:** `tests/test_dacai_panel.py` covers the protocol differences, sprite packing/sync,
  sync failures, host animations, diagonal lines, `0x27`/`0x09` rectangles, the emulator dialect
  and the auxiliary-UART exclusion.

## Differences from DWIN T5UIC1

Measured on the reference panel (Ender 3 Max Neo, board Rev 1.5). The driver is `petrel/hardware/dwin/dacai.py`.

| Command | DACAI behavior | Driver |
|---|---|---|
| `0x24` SRAM JPEG | Not implemented; DACAI `0x70 x y address` draws opaque | Uses `0x70`; thumbnails composed on the UI background at the centre of its RGB565 step, JPEG quality 100 |
| `0x27` copy area | Bit 7 inverted: set = black transparent; copies rows `y0`…`y1+1` (columns exact) | Inverts bit 7; sends `y1` one lower |
| `0x09` move area | Moving left or up treats `x1`/`y1` as exclusive (one line left per move); right and down are exact | Sends `x1`/`y1` one higher for left/up |
| `0x03` polyline | Draws only horizontal/vertical segments; a diagonal becomes an L-shaped step | Sends diagonals as staircases |
| `0x33` SRAM → picture | Stores all 32 KB as `image/<id>.jpg`; the file must end with `FF D9`; IDs above 15 accepted | Pads JPEGs to 32 KB with a COM segment |
| Icon library | Icon files cannot be written over UART | Sprite sheets + `0x25`/`0x27` |
| `0x28` animation | Only for the panel's own icon files | Animations stepped by the host |
| `0x31`/`0x32` Data Flash | Write acknowledged with a bare `A5 'OK'` | Accepted as acknowledgement |
| `0x30` backlight | Clamped to 0–63 | 0–255 mapped to 4–63 (0 = off) |
| `0x38` | Re-clocks the host UART until power loss | Optional faster link |
| `0x39`/`0x3A` | Not implemented | No auxiliary UART |
