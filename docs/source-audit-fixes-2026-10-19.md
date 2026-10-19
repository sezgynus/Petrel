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
| R02 | Worker-based resort | Implemented |
| R03 | File cache lifetime | Implemented |
| R04 | Single maintenance tick and interval | Implemented |
| R05 | Usage counter capacity | Implemented |
| R06 | Drain accepted result writes | Implemented |
| R07 | Safe thumbnail attempt budget | Implemented |

### Second-audit validation and behavior

- A cold preview beyond the first five preload entries is valid immediately; replacing or deleting its actual file still invalidates it. Unsafe image paths do not consume the four-download attempt budget.
- Sort preference changes prepare a private list and paths on the read worker. Publication requires the same source list, epoch, file revision and sort revision. Disconnect/epoch changes release backend indexes and UI aliases together; an already running job may retain its private inputs until it finishes.
- One UI tick shares one model update. Active Maintenance caps the final interval at 100 ms without slowing a faster render task; input events outside the tick still request fresh state. Hold, popup and UART-loss paths keep advancing checks.
- New usage ledgers admit at most 32 named counters. A full ledger preserves its existing values and identity, continues print-time/existing-counter updates, and reports rejection of new names through record errors and the journal. Legacy oversized batches up to 64 names remain readable and retain all existing counters; they cannot grow further. Counters are not silently removed or reset.
- Orderly shutdown finalizes up to eight accepted local result batches, even when their queued Futures were cancelled during worker close. A started local write is joined through its transaction lock and is never attempted again after success or failure. Disk failure remains an explicit record error/journal warning. No printer command is replayed.

Hardware acceptance remains pending. In addition to the earlier list, check a previously unopened sixth/later file, a sort change while browsing, and normal restart immediately after a check result. These changes have no merge authorization for master.

## Third audit

| ID | Item | Implementation |
| --- | --- | --- |
| A01 | Result history byte retention | Implemented |
| A02 | Non-expiring accepted local writes | Implemented |
| A03 | Idle preview tick cadence | Pending |
| A04 | File snapshot during retry backoff | Pending |

Result history retains at most 64 entries and 64 KiB, evicting oldest entries while keeping the complete newest result group. A group that cannot fit on its own is rejected with a record error; the previous file is preserved. Accepted local result writes use the existing bounded worker queue without an admission expiry. Network reads retain their deadlines, queue-full rejection remains explicit, and orderly shutdown still finalizes cancelled local writes exactly once. No disk work is moved onto normal UI ticks and no printer command is replayed. Regression coverage includes wide results, group preservation, subsequent writes, queue ageing, and unchanged network-read expiry. Hardware acceptance is pending.
