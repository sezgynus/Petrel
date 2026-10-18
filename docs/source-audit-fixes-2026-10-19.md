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
| K08 | Bound remote connections and read deadlines | Pending |
| K09 | Cooperative worker shutdown and update isolation | Implemented |
| K10 | Shared remote JPEG cache with animation freshness | Pending |
| K11 | Incremental recovery rendering | Pending |
| K12 | Negative thumbnail cache | Pending |
| K13 | Try alternate thumbnail candidates | Pending |
| K14 | One source for client version | Pending |
| K15 | Remote Enter shortcut | Pending |
