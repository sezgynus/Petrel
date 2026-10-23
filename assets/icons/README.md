# Managed LCD icons

[English](README.md) · [Türkçe](README_TR.md)

The library contains **212 icons, IDs 0–211**. **212–255 are free**; use **212** for the next icon and continue sequentially. Filenames are zero-padded (`212.jpg`, `assets/icon-source/212.svg`). Bind UI and generator code through `lcd_resources.py`. The one-time [ID migration map](id-migration.json) records the old/new directory IDs; do not apply it again at runtime.

The cleanup removed **40 unused icons** (44,535 JPEG bytes). Bed Mesh's former ID 203 was found to be active and is retained as `ICON_BED_MESH` (165). All 212 surviving JPEGs and editable SVGs moved without changing their bytes, dimensions, colors or quality. IDs are dense; physical placement is independent of ID order.

## Sources and packing

Add baseline **4:2:0 JPEGs** under this directory. IDs must be unique and within 0–255. Progressive JPEGs, other color sampling, invalid filenames and payloads above 32767 bytes are rejected. The renderer preserves existing JPEGs unless explicitly invoked to regenerate artwork.

Picture Flash **0** holds boot artwork, **1** shared QR/UI artwork, and **2–15** are reserved for library **2**. The current export uses **13×32 KiB**, slots **2–14**. It has **12,581 usable free bytes** within those blocks and slot **15** remains available; the full reservation has **45,348 usable bytes free**. These figures change with new sources. The 4096-byte directory stays fixed even when IDs are removed.

The runtime and export tool share the deterministic packer: best-fit decreasing followed by bounded subset-sum searches that consolidate earlier gaps. Refinement never adds a block to enlarge a hole. Each block search is exact; sequential searches do not prove a global bin-packing optimum. Every block's last byte is reserved, and no JPEG crosses a block boundary. Packing changes addresses, not JPEG bytes or directory IDs. The cache avoids repacking unchanged resources on every reconnect.

```sh
python tools/pack_icon_library.py assets/icons /tmp/2.ICO --library 2
```

`assets/emulator/2.ICO` is a checked-in reference export. Production builds from JPEG sources automatically; the emulator uses the same sources. Update the export and `docs/lcd-assets.json` after changing assets.

## Automatic update and ID migration

The first LCD connection synchronizes the library. Metadata **PETICO02** distinguishes the compact IDs from the previous directory. PETICO01 metadata cannot start boot frames with the new IDs; the first migrated startup begins animation only after the new directory is committed. All native animations stop before Picture Flash writes. Payload blocks upload first, the directory last; CRC-verified metadata checkpoints allow interrupted uploads to resume. Unchanged subsequent connections do not write Flash. A failed automatic Picture Flash attempt is not retried in the same process.

Slots 0/1, display and buzzer settings, NFC UIDs and Spoolman records do not move. No LCD SD update is required. Old library-base metadata (3/7) is not reused for the managed base 2. Downgrading to older software rebuilds its own resource directory from its own sources.

Stop Petrel before manual diagnostic uploads. `tools/reload_icons.py` forces checkpointed synchronization from current sources. `tools/flash_icon_library.py` uploads current sources by default; `--file` explicitly uploads an ICO. Diagnostic uploads invalidate old metadata so the next normal startup restores managed sources. See [LCD artwork](../README.md).

## Current resources

| Purpose | IDs | Dimensions / behavior |
|---|---|---|
| Dashboard hotend / bed | 9 / 10 | 18×18; old unused 20×20 setting variants were removed |
| MMU normal / selected | 120 / 121 | 110×100 |
| Display normal / selected | 71 / 72 | 110×100 |
| Folder; MCU; machine; host; software; power | 122; 123; 124; 125; 69; 70 | Folder 20×18, others 20×20 |
| Spool flanges / empty spool | 73–86 / 87 | Widths 1–7, height 52 / 42×52 |
| Maintenance check / diagnostics / advice / care | 126–129 | 20×20 |
| Wi-Fi weak / medium / strong | 130–132 | 20×20, filtered dark background |
| NFC settings; interface; port | 133; 118; 119 | 20×20 |
| RFID home normal / selected | 134 / 135 | 110×100 |
| Phone approach | 136–147 | 12 opaque 160×160 frames, channel 2, 200 ms/frame |
| Compact NFC share normal / selected | 148 / 149 | 20×20 control, 16×16 glyph |
| Spool approach | 150–161 | 12 opaque 160×160 frames, channel 3, 200 ms/frame |
| Emergency; spool; assign; remove; next; retry | 35; 47; 48; 49; 50; 51 | Shared 20×20 semantic glyphs |
| Card approach | 57–68 | 12 opaque 160×160 frames, channel 3, 200 ms/frame |
| Bed Mesh menu | 165 | Symbolic `ICON_BED_MESH` |
| Fan; boot | 192–199; 207–211 | Native animation channels 1 / 0 |

Phone sharing loops in 2.4 s without host frame timers. Reader completion, failure, cancellation and window replacement stop its animation. Capability discovery controls the small NFC share control before the Petrel version in Software; no extra QR share row is added. Failed sharing displays a static first frame.

Spool and generic card enrollment share the capture popup. Emergency Assign/Replace uses card frames; spool assignment uses spool frames. Clicking cancels; reading stops animation before explicit UID/save confirmation. A read alone never writes a Spoolman assignment. Power overlays, disconnect/close and screen replacement stop or clear animation; a retained capture resumes or completes when its origin returns. Redraws and encoder movement do not restart capture.

## Artwork generation

- `python tools/render_icon_sources.py --ids 148 149` renders selected SVG IDs; omit `--ids` only for an intentional full regeneration. Baseline 4:2:0 is required by the physical panel; 4:4:4 previously corrupted artwork.
- `python tools/render_button_backings.py` uses the current backing IDs.
- `python assets/icon-source/nfc-settings/render.py` and `python assets/icon-source/rfid/render.py` generate current semantic glyphs and SVGs.
- `python assets/icon-source/nfc-card/render.py`: quality 65, optimized Huffman tables, baseline 4:2:0.
- `python assets/icon-source/nfc-spool/render.py`: original lossless PNGs, quality 84, optimized Huffman tables, baseline 4:2:0.
- `python assets/icon-source/nfc-share/render.py`: approved phone artwork and NFC N-Mark. Every generator now targets the compact IDs.

The shared Graphite stroke, filtered black backgrounds and normal/selected states are preserved. The N-Mark attribution is in [NFC-LICENSE.txt](../icon-source/NFC-LICENSE.txt); Lucide attribution remains in [Lucide-LICENSE.txt](../icon-source/Lucide-LICENSE.txt).

## Print buttons, switches and fan artwork

Print Tune/Pause/Resume/Stop/MMU controls use normal IDs 200–204 and selected IDs 88–92. Wide Tune uses 93/94 and Close uses 95/96. Job switches use 205/206. Labels remain native runtime text on transparent rounded artwork. Fan frames 192–199 retain their dashboard-colored opaque background and native animation; the renderer recognizes the new ranges without changing JPEG quality.
