# Managed LCD icons

[English](README.md) · [Türkçe](README_TR.md)

Add or replace baseline **4:2:0 JPEGs** here. Use the icon ID as the filename prefix: `092.jpg`, `092-about.jpg` or `092_about.jpeg`. IDs are 0–255; each ID must occur once. Existing IDs retain their meaning. Renaming an icon without changing its ID or bytes does not trigger an upload. A new image enters the library; UI code chooses where its ID is displayed.

JPEGs are preserved without resizing or recompression. Progressive JPEGs, other color sampling formats, duplicate IDs and images larger than 32767 bytes are rejected. The whole library must fit Picture Flash slots 3–15; picture 0 holds Petrel boot artwork, picture 1 holds the shared UI artwork page and picture 2 is unused.

After an application update, the first LCD connection builds the library from this directory. The packer places larger icons first and fits smaller icons into remaining holes. Icon IDs do not depend on physical placement. Every block's last byte is reserved and excluded from UART writes. No JPEG crosses a block boundary.

Only changed blocks are uploaded; the directory block is committed last. Panel metadata records successful blocks, so a subsequent start resumes incomplete uploads. Unchanged libraries cause no Flash writes. A failed Picture Flash attempt is not repeated in the same process. Logs describe upload progress and failures.

Preview/export the exact runtime pack:

```bash
python tools/pack_icon_library.py assets/icons /tmp/3.ICO --library 3
```

The emulator uses these same JPEG sources. `assets/emulator/3.ICO` is a reference export, not the source for automatic updates.

Custom UI icons use IDs 100–109 and 124. MMU uses 100/101 and Display uses 108/109 for normal/selected 110×100 home tiles, using the established native tile footprint. The empty spool uses ID 124. Metal spool flanges use IDs 110–123 for widths 1–7, so compact lanes need no separate complete spool artwork. The symbolic mapping is in `lcd_resources.py`. All UI icons render directly through library 3.

After reinstalling panel resources, force a reload because stored metadata may still describe the previous installation:

```bash
sudo systemctl stop Petrel.service
~/petrel-env/bin/python ~/Petrel/tools/reload_icons.py
sudo systemctl start Petrel.service
```

Write acknowledgements and metadata readback are verified; Picture Flash itself is not read back. Confirm the newly packed icon layout on the physical display.

## Graphite

Graphite adds dedicated IDs 210–234 for light, brightness, sound settings, motion parameters, calibration and profiles. Editable SVG sources are in `assets/icon-source`; use `python tools/render_icon_sources.py` to regenerate JPEGs (developer dependency: CairoSVG). Black JPEG backing is filtered with the native transparent/enhanced icon mode; menu and dashboard surfaces remain visible. The icon pack starts at picture slot 3 and may use slots 3–15; its 512-byte metadata record occupies Data Flash `0x0200–0x03FF`.

## Print buttons, switches and fan artwork

Print buttons contain the rounded surface, selection outline and Lucide symbol in one JPEG; labels remain native panel text using font ID **0**. Normal narrow buttons use **243–247** and selected variants **125–129** (78×36); completed-print Tune/Close pairs use **130–133** (119×36). AFTER JOB switches use **248/249** (27×12). Keep normal/selected silhouettes identical: the renderer uses a hard rounded mask with the same neutral opaque perimeter so filtered JPEG edges do not retain the previous state.

Fan frames **235–242** use a neutral fan symbol on the dashboard's **RGB565 `0x18C4`** background. The SVG uses mid-bin RGB `#1c1a24` so JPEG rounding stays inside that RGB565 color. Native animation (`0x28`) has no background-filter option, so these frames are opaque; the stopped fan uses the same opaque rendering. Preserve this backing when regenerating from SVG. Fan and full-button JPEGs use **quality 100**, baseline **4:2:0**. Other generated icons use quality 94. Regenerate from SVG rather than recompressing JPEGs. Lucide source licensing: [Lucide license](../icon-source/Lucide-LICENSE.txt).

## Package size and reserved space

The current reference pack occupies **12×32 KiB = 384 KiB**, slots **3–14**. The reserved maximum is **13×32 KiB = 416 KiB**, slots **3–15**, leaving slots **15** available for growth. This is allocated block space, not an exact JPEG payload budget: the directory, placement gaps and reserved final bytes also consume space. Picture Flash is separate from the **512-byte Data Flash metadata record at 0x0200–0x03FF**. Pass `--library 3` to export; the export tool's legacy default is 7, with a different available slot count.

## JPEG compatibility rule

All managed icons must be baseline RGB/YCbCr JPEG with 4:2:0 sampling (`Pillow: subsampling=2`). Render directly from SVG using `tools/render_icon_sources.py`; do not repeatedly recompress JPEGs. Physical T5UIC1 tests reproduced damaged selected home tiles and homing artwork with 4:4:4 from both Flash and byte-verified SRAM; 4:2:0 rendered correctly. A clean emulator preview cannot validate the panel JPEG decoder. The source loader rejects other sampling formats before any panel access, and CI checks every shipped icon and the exported ICO against its sources. Check selected/unselected home tiles, homing, small menu/status icons and animation on hardware after artwork updates.

Maintenance reuses the existing small Graphite menu icons. Its former large tile IDs 156–163 are retired; they are not shipped or referenced by the UI.

Small Maintenance purpose icons use IDs 164–167 (20×20): check-circle, activity, lightbulb and calendar. Wi-Fi strength uses IDs **168 (poor), 169 (medium), 170 (strong)**, all 20×20, with black JPEG backgrounds erased by the existing native enhanced transparency filter. The source SVGs are in `assets/icon-source`. All follow the shared Graphite stroke and baseline 4:2:0 JPEG encoding. The reference pack now occupies 12×32 KiB.

The NFC settings entry uses ID **171** (`ICON_NFC`), the familiar NFC N silhouette in the shared 20×20 Graphite cyan style. The read-only NFC feature status follows the Info layout and does not use an action icon. The icon's editable source is `assets/icon-source/171.svg`.

The NFC silhouette is adapted from [Pictogrammers Material Design Icons — nfc](https://github.com/Templarian/MaterialDesign/blob/master/svg/nfc.svg); its proportions are preserved, with only uniform scaling and Graphite coloring. Source attribution and license are in [NFC-LICENSE.txt](../icon-source/NFC-LICENSE.txt).

The RFID home entry uses dedicated **172/173** normal/selected NFC N icons (110×100). Graphite tile surfaces, selection outlines and native label space match the other home icons; RFID does not reuse Info artwork.

## NFC phone approach animation

Share via NFC uses twelve opaque 160×160 frames, IDs **174–185**, on popup RGB565 `0x2967`. DWIN native `0x28`, animation channel **2**, interval **20×10 ms**, loops in **2.4 seconds** without host frame timers. Channels 0/1 remain boot/fan. Closing, completion, failure and window replacement stop channel 2 before repainting. Failed sharing shows the first frame without animation. Regenerate with `python assets/icon-source/nfc-share/render.py`; the included NFC N-Mark bitmap preserves the approved preview symbol. The N-Mark identifies NFC (NFC Forum).

## Compact NFC share control

IDs **186/187** (`ICON_NFC_SHARE_NORMAL` / `ICON_NFC_SHARE_SELECTED`) provide normal/selected **20×20** controls with a **16×16** phone, NFC N silhouette and sharing arrow. They fit existing 24-pixel rows without increasing row height. Normal has no focus border; selected adds a cyan border and tinted surface within the same bounds. Editable sources: `assets/icon-source/186.svg` and `187.svg`; regenerate with `python tools/render_icon_sources.py --ids 186 187`. The NFC silhouette reuses the attributed source in [NFC-LICENSE.txt](../icon-source/NFC-LICENSE.txt). Info uses this control immediately before the Petrel version in the Software section, gated by confirmed reader sharing capability; there is no separate share row beneath the QR.
