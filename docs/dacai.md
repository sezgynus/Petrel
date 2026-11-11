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

Run `./configure.sh`, open **Display panel**, check **DACAI panel** and optionally choose a faster **DACAI host UART speed**. Save, exit and confirm Apply. The settings are stored as `PETREL_DACAI=1` and `PETREL_DACAI_BAUD` in `Petrel.env`.

| Speed | Use |
|---|---|
| 115200 | Default; the panel's power-on speed |
| 230400, 460800, 921600 | Faster artwork upload and thumbnails; all three were error-free on the reference panel |

The panel keeps a raised speed until it loses power. Petrel switches it back to 115200 when it exits and tries both speeds while it waits for the panel, so a crashed or restarted service still finds it.

## What Petrel uploads

No microSD card is needed. On the first start Petrel uploads over the UART:

| Picture | Content |
|---|---|
| 0 | Boot artwork |
| 1 | Shared UI artwork (Info QR regions) |
| 16 and up | Icon sprite sheets: the icon library packed onto 272×480 JPEG sheets |

The first upload takes about 15 seconds at 460800 baud. Content fingerprints are stored in the panel's Data Flash, so later starts upload only changed pictures.

DACAI panels only read icons from their own icon files, which cannot be written over the UART. Petrel therefore draws each icon by copying it from a sprite sheet in virtual display area 1, and steps icon animations (boot progress, fan) from the host. Other Petrel features work unchanged.

## After a microSD update

Updating the panel from its microSD card removes the uploaded pictures, but the fingerprints remain, so Petrel would not notice. Upload everything again with:

```bash
sudo systemctl stop Petrel.service
~/petrel-env/bin/python ~/Petrel/tools/dacai_artwork.py --serial-port /dev/ttyS0
sudo systemctl start Petrel.service
```

Use the UART from your configuration instead of `/dev/ttyS0`.

## Limits

- **Font:** text uses the TrueType font installed on the panel (`private/truefont`). Petrel does not upload fonts.
- **No auxiliary UART:** the panel has no second UART, so [DWIN auxiliary UART](dwin-uart.md) and NFC readers attached to the display cannot be used. The large NFC approach animations are not uploaded.
- **Black is transparent:** like DWIN icon drawing, transparent icons treat near-black pixels as background, so very thin dark details can disappear.
- **Emulator:** screenshots show the DWIN rendering path.

## For developers

`DacaiDriver` (`petrel/hardware/dwin/dacai.py`) subclasses `T5UIC1Display`; the DWIN path stays
unchanged. Keep these points in mind when changing display code:

- **Draw through the driver methods.** `show_icon`, `configure_animation`, `set_animation_mask`,
  `copy_cache`, `show_sram_jpeg`, `set_backlight` and `prepare_picture` are overridden. Code that
  sends raw opcodes with `_send` bypasses the DACAI handling.
- **Icons need no extra work.** Sprite sheets are built from `assets/icons` at runtime
  (`petrel/artwork/sprites.py`); new or changed icons are uploaded on the next start. Icon IDs
  in `sprites.SKIPPED_IDS` (the large NFC frames) are not uploaded.
- **Animations** of library 2 are stepped by the host (`poll_host_animations`, called from the UI
  tick). The interval keeps the `0x28` unit of 10 ms; the shortest frame time is 40 ms.
- **Reserved resources:** pictures 0 (boot), 1 (shared artwork) and 16 and up (sprite sheets);
  Data Flash `0x0600`–`0x083F` (sprite checkpoints) in addition to the DWIN records.
- **Not available on DACAI:** `0x24` (use `show_sram_jpeg`), `0x39`/`0x3A` (no auxiliary UART),
  writing icon files. A new opcode may need an override in `DacaiDriver`; see the table below.
- **New artwork in pictures:** pass JPEG bytes through `lcd.prepare_picture()` before
  `write_sram` + `store_sram_as_picture` (baseline 4:2:0, at most 32,764 bytes on DACAI).
- **Tests:** `tests/test_dacai_panel.py` covers the protocol differences, sprite packing/sync and
  host animations.

## Differences from DWIN T5UIC1

Measured on the reference panel (Ender 3 Max Neo, board Rev 1.5). The driver is `petrel/hardware/dwin/dacai.py`.

| Command | DACAI behavior | Driver |
|---|---|---|
| `0x24` SRAM JPEG | Not implemented | Uses DACAI `0x70 x y address` |
| `0x27` copy area | Bit 7 inverted: set = black transparent | Inverts bit 7 |
| `0x33` SRAM → picture | Stores all 32 KB as `image/<id>.jpg`; the file must end with `FF D9`; IDs above 15 accepted | Pads JPEGs to 32 KB with a COM segment |
| Icon library | Icon files cannot be written over UART | Sprite sheets + `0x25`/`0x27` |
| `0x28` animation | Only for the panel's own icon files | Animations stepped by the host |
| `0x31`/`0x32` Data Flash | Write acknowledged with a bare `A5 'OK'` | Accepted as acknowledgement |
| `0x30` backlight | Clamped to 0–63 | 0–255 mapped to 4–63 (0 = off) |
| `0x38` | Re-clocks the host UART until power loss | Optional faster link |
| `0x39`/`0x3A` | Not implemented | No auxiliary UART |
