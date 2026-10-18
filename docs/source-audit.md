# Historical source audit — 2026-10-05

This document records an earlier source review and its closed findings. It is
**not the current feature list or a claim of complete hardware validation**.
For current functionality and usage, see [README](../README.md) and
[README_TR](../README_TR.md). For current software checks, see
[test guide](../tests/README.md).

## Scope at the time

The review covered display framing/rendering, input ownership, command/error
handling, movement recovery, state epochs, configuration and asset coordinates.
It used source inspection and fake serial/HTTP/GPIO I/O; no physical printer,
LCD or Pi service was exercised by that audit. Its isolated suite contained
187 passing tests at that time; that number is historical, not today's total.

## Closed findings

The original finding IDs and commit references are retained below.

| ID | Resolution and validation | Commit |
|---|---|---|
| A01 | Real GPIO Enter can confirm error-state actions; waiting input is blocked. Producer-to-owner regression. | eddca211 |
| A02 | Z-offset Enter sends the editor target initialized from the runtime value, with finite/range checks. | fc2f5d5 |
| A03 | Editor draft is separate from subscription state; ticks cannot overwrite edits. Prepare/Tune share input ownership. | 3bcfb8b |
| A04 | Info text is normalized/truncated before centering; long versions cannot produce negative coordinates. | 0e3ceb8 |
| A05 | SAVE is verified separately. Failed motion attempts only RESTORE MOVE=0; uncertainty blocks new movement/printing and offers recovery. Motion is not replayed. | 96cd675 |
| A06 | Every encoder step checks state/capability epoch; changed menus discard stale input. Backend rejects commands from an old connection state. | c0b6a03 |
| A07 | Epoch changes invalidate file lists and UI file views even when the revision matches. | 600399e |
| A08 | UART packets are built atomically after field validation; QR byte length and panel bounds are checked. | 7ef391c |
| A09 | Numeric overflow draws # within the field instead of raising; the actual target stays unchanged. Sign changes clear the field; Motion can use scientific notation. | 2026-10-05 audit commit |


The audit also corrected the three-digit 100% field, completed-minute duration
formatting, negative-zero rendering and immediate screen flushing after input
or reconnect. Moves and edit targets use `gcode_move.position` consistently.

## Limits and later changes

- Jog recovery protects this LCD client; it does not lock other Moonraker clients.
  Its recovery state lives in process memory. An unsuccessful state restore does
  not clear the movement guard.
- Asset hashes describe the audited files, not every installed panel. Real UART
  timing, fonts, filtering and visual placement require physical checks.
- The audit predates the current calibration, paged Home, folder browser,
  metadata preview and SRAM/JPEG cache features. Its earlier absence of image
  transfer APIs is no longer a current limitation.
- Later user panel tests exercised preview display, caching and metadata layout;
  they do not establish compatibility across every printer/display configuration.

Git history retains the full earlier report and implementation details.
