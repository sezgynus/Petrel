# Source audit fixes

[English](source-audit-fixes-2026-10-19.md) · [Türkçe](source-audit-fixes-2026-10-19_TR.md)

Branch: `fix/source-audit-2026-10-19`. Base: `bc5e395`. Hardware acceptance is pending; master is unchanged. Regression checks run in GitHub Actions only.

| ID | Item | Implementation |
| --- | --- | --- |
| K01 | Maintenance progress through overlays and UART loss | Implemented |
| K02 | Observe emergency stop before transport shutdown | Implemented |
| K03 | Usage coverage for optional fans/heaters | Implemented |
| K04 | Flush usage during orderly shutdown | Implemented |
| K05 | Small input/read/buzzer snapshots | Implemented |
| K06 | Prepare large file lists off the UI owner | Implemented |
| K07 | Targeted print metadata invalidation | Implemented |
| K08 | Bound remote connections and read deadlines | Implemented |
| K09 | Cooperative worker shutdown and update isolation | Implemented |
| K10 | Shared remote JPEG cache with animation freshness | Implemented |
| K11 | Incremental recovery rendering | Implemented |
| K12 | Negative thumbnail cache | Implemented |
| K13 | Try alternate thumbnail candidates | Implemented |
| K14 | One source for client version | Implemented |
| K15 | Remote Enter shortcut | Implemented |

## Hardware acceptance

All 15 items are implemented on this branch. Hardware acceptance is still pending; no automatic merge is requested. Each logical change is checked on its signed HEAD by the full branch regression workflow. No local test or development emulator was run.

1. During an idle-printer Maintenance test, open/cancel the hold-and-release power popup. The check must continue and its result must appear after closing the popup. Verify service stop/restart and LCD reconnect behavior under controlled conditions.
2. Confirm observed usage increases and survives a normal Petrel restart. Devices without telemetry must not acquire a fabricated zero counter or an ON-hours reminder basis.
3. Navigate a large nested file tree and change sort preferences. Check thumbnails, back navigation, preview confirmation, deleted files and print-start validation.
4. During a print, upload a different G-code file. Remaining/Finish should retain their current metadata source. Replacing the actual file or reconnecting must still refresh the correct metadata.
5. Keep two remote viewers open: verify encoder controls, keyboard Enter, static frames and fan animation. Focused buttons must retain their normal Enter behavior.
6. In recovery, move between buttons and scroll a long message. Only changed buttons/text should repaint; shortened messages and cleared notices must leave no remnants.
7. Open a file with no thumbnail, one with a broken first thumbnail, and one with a temporary download failure. Missing images should not poll repeatedly; alternatives and transient retries must work.

Client identification now uses the installed checkout's cached `git describe --tags --always --dirty` value. Without readable Git metadata it reports `unknown`; it does not invent a release tag. An already dispatched software update cannot be reversed by closing the UI; closing prevents follow-up requests and releases its private transport when that request returns.

## Second audit

| ID | Item | Implementation |
| --- | --- | --- |
| R01 | Foreground preview identity | Implemented |
| R02 | Worker-based resort | Pending |
| R03 | File cache lifetime | Pending |
| R04 | Single maintenance tick and interval | Pending |
| R05 | Usage counter capacity | Pending |
| R06 | Drain accepted result writes | Pending |
| R07 | Safe thumbnail attempt budget | Implemented |
