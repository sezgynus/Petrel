# Managed LCD icons

[English](README.md) · [Türkçe](README_TR.md)

Add or replace baseline **4:2:0 JPEGs** here. Use the icon ID as the filename prefix: `092.jpg`, `092-about.jpg` or `092_about.jpeg`. IDs are 0–255; each ID must occur once. Existing IDs retain their meaning. Renaming an icon without changing its ID or bytes does not trigger an upload. A new image enters the library; UI code chooses where its ID is displayed.

JPEGs are preserved without resizing or recompression. Progressive JPEGs, other color sampling formats, duplicate IDs and images larger than 32767 bytes are rejected. The whole library must fit Picture Flash slots 2–15; picture 0 holds Petrel boot artwork, picture 1 holds the shared UI artwork page and the icon library starts at picture 2.

After an application update, the first LCD connection builds the library from this directory. The packer first builds a best-fit decreasing layout, then tries to consolidate gaps using byte-exact bitset subset-sum searches to fill earlier blocks. An improved layout is selected only when it uses no more blocks and offers a larger contiguous hole; otherwise the valid baseline is retained. Icon IDs do not depend on physical placement. Every block's last byte is reserved and excluded from UART writes. No JPEG crosses a block boundary.

Only changed blocks are uploaded; the directory block is committed last. Panel metadata records successful blocks, so a subsequent start resumes incomplete uploads. Unchanged libraries cause no Flash writes. A failed Picture Flash attempt is not repeated in the same process. Logs describe upload progress and failures.

Preview/export the exact runtime pack:

```bash
python tools/pack_icon_library.py assets/icons /tmp/2.ICO --library 2
```

The emulator uses these same JPEG sources. `assets/emulator/2.ICO` is a reference export, not the source for automatic updates.

Custom UI icons use IDs 100–109 and 124. MMU uses 100/101 and Display uses 108/109 for normal/selected 110×100 home tiles, using the established native tile footprint. The empty spool uses ID 124. Metal spool flanges use IDs 110–123 for widths 1–7, so compact lanes need no separate complete spool artwork. The symbolic mapping is in `lcd_resources.py`. All UI icons render directly through library 2.

After reinstalling panel resources, force a reload because stored metadata may still describe the previous installation:

```bash
sudo systemctl stop Petrel.service
~/petrel-env/bin/python ~/Petrel/tools/reload_icons.py
sudo systemctl start Petrel.service
```

Write acknowledgements and metadata readback are verified; Picture Flash itself is not read back. Confirm the newly packed icon layout on the physical display.

## Graphite

Graphite adds dedicated IDs 210–234 for light, brightness, sound settings, motion parameters, calibration and profiles. Editable SVG sources are in `assets/icon-source`; use `python tools/render_icon_sources.py` to regenerate JPEGs (developer dependency: CairoSVG). Black JPEG backing is filtered with the native transparent/enhanced icon mode; menu and dashboard surfaces remain visible. The icon pack starts at picture slot 2 and may use slots 2–15; its 512-byte metadata record occupies Data Flash `0x0200–0x03FF`.

## Print buttons, switches and fan artwork

Print buttons contain the rounded surface, selection outline and Lucide symbol in one JPEG; labels remain native panel text using font ID **0**. Normal narrow buttons use **243–247** and selected variants **125–129** (78×36); completed-print Tune/Close pairs use **130–133** (119×36). AFTER JOB switches use **248/249** (27×12). Keep normal/selected silhouettes identical: the renderer uses a hard rounded mask with the same neutral opaque perimeter so filtered JPEG edges do not retain the previous state.

Fan frames **235–242** use a neutral fan symbol on the dashboard's **RGB565 `0x18C4`** background. The SVG uses mid-bin RGB `#1c1a24` so JPEG rounding stays inside that RGB565 color. Native animation (`0x28`) has no background-filter option, so these frames are opaque; the stopped fan uses the same opaque rendering. Preserve this backing when regenerating from SVG. Fan and full-button JPEGs use **quality 100**, baseline **4:2:0**. Other generated icons use quality 94. Regenerate from SVG rather than recompressing JPEGs. Lucide source licensing: [Lucide license](../icon-source/Lucide-LICENSE.txt).

## Package size and reserved space

The current reference pack occupies **13×32 KiB = 416 KiB**, slots **2–14**. The reserved maximum is **14×32 KiB = 448 KiB**, slots **2–15**; slot **15** is available for growth. With the current sources, usable free space is **35,049 bytes**: 2,282 bytes inside the current pack plus 32,767 bytes in the extra slot. This is allocated block space, not an exact JPEG payload budget: the directory, placement gaps and reserved final bytes also consume space. Picture Flash is separate from the **512-byte Data Flash metadata record at 0x0200–0x03FF**. The export tool now defaults to the managed library; explicit exports use `--library 2`.

## JPEG compatibility rule

All managed icons must be baseline RGB/YCbCr JPEG with 4:2:0 sampling (`Pillow: subsampling=2`). Render directly from SVG using `tools/render_icon_sources.py`; do not repeatedly recompress JPEGs. Physical T5UIC1 tests reproduced damaged selected home tiles and homing artwork with 4:4:4 from both Flash and byte-verified SRAM; 4:2:0 rendered correctly. A clean emulator preview cannot validate the panel JPEG decoder. The source loader rejects other sampling formats before any panel access, and CI checks every shipped icon and the exported ICO against its sources. Check selected/unselected home tiles, homing, small menu/status icons and animation on hardware after artwork updates.

Maintenance reuses the existing small Graphite menu icons. Its former large tile IDs 157–163 are retired; they are not shipped or referenced by the UI.

Small Maintenance purpose icons use IDs 164–167 (20×20): check-circle, activity, lightbulb and calendar. Wi-Fi strength uses IDs **168 (poor), 169 (medium), 170 (strong)**, all 20×20, with black JPEG backgrounds erased by the existing native enhanced transparency filter. The source SVGs are in `assets/icon-source`. All follow the shared Graphite stroke and baseline 4:2:0 JPEG encoding. The reference pack now occupies 13×32 KiB.

The NFC settings entry uses ID **171** (`ICON_NFC`), the familiar NFC N silhouette in the shared 20×20 Graphite cyan style. The read-only NFC feature status follows the Info layout and does not use an action icon. The icon's editable source is `assets/icon-source/171.svg`.

The NFC silhouette is adapted from [Pictogrammers Material Design Icons — nfc](https://github.com/Templarian/MaterialDesign/blob/master/svg/nfc.svg); its proportions are preserved, with only uniform scaling and Graphite coloring. Source attribution and license are in [NFC-LICENSE.txt](../icon-source/NFC-LICENSE.txt).

The RFID home entry uses dedicated **172/173** normal/selected NFC N icons (110×100). Graphite tile surfaces, selection outlines and native label space match the other home icons; RFID does not reuse Info artwork.

## NFC phone approach animation

Share via NFC uses twelve opaque 160×160 frames, IDs **174–185**, on popup RGB565 `0x2967`. DWIN native `0x28`, animation channel **2**, interval **20×10 ms**, loops in **2.4 seconds** without host frame timers. Channels 0/1 remain boot/fan. Closing, completion, failure and window replacement stop channel 2 before repainting. Failed sharing shows the first frame without animation. Regenerate with `python assets/icon-source/nfc-share/render.py`; the included NFC N-Mark bitmap preserves the approved preview symbol. The N-Mark identifies NFC (NFC Forum).

## Compact NFC share control

IDs **186/187** (`ICON_NFC_SHARE_NORMAL` / `ICON_NFC_SHARE_SELECTED`) provide normal/selected **20×20** controls with a **16×16** phone, NFC N silhouette and sharing arrow. They fit existing 24-pixel rows without increasing row height. Normal has no focus border; selected adds a cyan border and tinted surface within the same bounds. Editable sources: `assets/icon-source/186.svg` and `187.svg`; regenerate with `python tools/render_icon_sources.py --ids 186 187`. The NFC silhouette reuses the attributed source in [NFC-LICENSE.txt](../icon-source/NFC-LICENSE.txt). Info uses this control immediately before the Petrel version in the Software section, gated by confirmed reader sharing capability; there is no separate share row beneath the QR.

## NFC spool scan animation (reserved artwork)

IDs **188–199** (`ICON_NFC_SPOOL_FIRST` / `ICON_NFC_SPOOL_LAST`) contain the approved preview's twelve opaque **160×160** frames. The spool approaches the panel, NFC waves light up, and the spool retreats. No screen uses these resources yet; no animation channel or timer is started. The suggested interval for future use is 200 ms/frame (2.4 seconds/loop).

Lossless PNG sources are in `assets/icon-source/nfc-spool`. Regenerate with `python assets/icon-source/nfc-spool/render.py`, then update the reference ICO using the packing command above. The new JPEGs use quality **84**, optimized Huffman tables and baseline **4:2:0** to fit Flash capacity; existing icons remain unchanged. The pack occupies **13×32 KiB = 416 KiB**, using slots 2–14 within reserved slots 2–15.

## NFC settings action icons

NFC Settings and its choice submenus use purpose-specific icons instead of Info: RFID module **171**, interface **155** (bidirectional data arrows), port/device **156** (plug), link speed **220**, Save **228**, and connection test **165**. Empty/loading/error device-list rows also use the port icon. New icons 155/156 use the shared 20×20 Graphite stroke on a filterable black background, baseline 4:2:0, quality 94 and optimized Huffman tables. SVG sources: `assets/icon-source/155.svg` and `156.svg`; regenerate with Pillow using `python assets/icon-source/nfc-settings/render.py`. To make room for these icons, spool frames are re-encoded from lossless PNG sources at quality 84; dimensions and animation content remain unchanged. The pack stays within 416 KiB.

## Automatic gap consolidation

The optimizer is shared by runtime `build_library` and ICO export/repacking; JPEG bytes, dimensions and icon IDs remain unchanged. Deterministic placement independent of input order gives identical ICO bytes and fingerprints for identical sources. Each block's subset search is exact; sequential block selection does not guarantee the global bin-packing optimum for every future icon set. A valid baseline is retained if refinement fails, and the reserved slot limit is enforced before producing a file. For the current 234 icons and 13 blocks, **all 2,282 available bytes are consolidated in the final block**. The directory occupies 4096 bytes and each block's last byte remains reserved. Future source changes naturally change available space. The existing pack cache avoids repeating searches in UI frames or unchanged reconnects. On the first update, blocks affected by the new layout upload through normal synchronization.

## Migration from library 3 or 7

The first LCD connection after this update reads CRC-verified metadata. A committed old directory may provide the boot animation until uploading begins. Before any icon block is replaced, every native animation is stopped. Old-library hashes are never reused at the new base: all required blocks are uploaded to slots 2 onward, with the new directory in slot 2 written last. Verified per-block checkpoints resume interrupted transfers; a zero directory hash prevents boot animation from a partial library. Slots 0/1, display settings and buzzer records are preserved. No SD-card resource update is required. Unchanged later connections do not rewrite Flash. Reference exports, emulator and manual reload tools use `2.ICO` and the shared `lcd_resources.py` identity. The 14 block hashes still fit the existing 512-byte metadata record.

Manual diagnostic uploads invalidate and verify the old metadata before overwriting Picture Flash; the next normal startup restores the managed sources automatically. Use `tools/reload_icons.py` for a checkpointed forced source reload.
