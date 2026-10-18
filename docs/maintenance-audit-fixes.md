# Maintenance source audit resolution — 18 October 2026

> Dated trace/audit notes below describe their recorded revision. They are not current run instructions or acceptance totals. Use the [current usage guide](user-guide.md#maintenance) and [acceptance ledger](maintenance-reference-printer-acceptance.md). Later changes supersede earlier test availability, safety-threshold and pending-acceptance statements.

Audit base: e324a6684c439e34ec745a614c1f508a5ff3cdbb. Work stays on feature/maintenance-ui-ux. No local tests or emulator were run. Each change was signed and checked by Actions on that exact signed commit before the next development change. One calendar regression required a follow-up test-clock fix before work continued.

| Finding | Resolution | Signed implementation commit |
|---|---|---|
| A01 | Positive dryer safety violations bypass transport retry grace | 7e0c0998 |
| A02 | Workflow emergency stop is guarded by original epoch | b09987a6 |
| A03 | Filament transaction state resets; busy start preserves ownership | 3b957aa8 |
| A04 | Fan restore converts scaled PWM back to request ratio | 282d288e |
| A05 | Recording proxy preserves JSON keyword pulse calls | 96590dfe |
| A06 | Final guided-service step renders its observation screen safely | f6a8a29b |
| A07 | Terminal F12 results reach history and Assessment exactly once | bcadd89a |
| A08 | Rejected F12 continuation displays BLOCKED | 498f8565 |
| A09 | Calendar dates refresh; discovery invalidates record cache | 2ffcec33 |
| A10 | Bounded history Futures expose queue and disk failures | b9df1411 |
| A11 | Independent metric policies retain independent findings | d6897192 |
| A12 | Loaded config-only calibrations are discovered without status objects | bd5d1dac |
| A13 | Overridden pulse and DUMP_TMC commands fail closed | de213739 |
| K01 | Confirmed heating-speed reference, compatible comparison, removal and current Findings | a90b6065, b7d967a0, 032eafe8 |
| K02 | Durable sampled printing/ON counters, explicit usage reminders and coverage | 362b0c56, fa4b05f1, 032eafe8 |

References compare a measured heating response, not part wear or guaranteed lifetime. The operator selects the limit and confirms unchanged hardware/cooling; measured setup conditions must match. Lower-bound usage can prove a reminder due, but cannot prove not due. Exact lifetime, reset-proof Moonraker totals and unverified travel continuity are not invented. Manufacturer service intervals remain explicit policies rather than defaults. New reference/usage functionality requires physical panel acceptance; backend regression success alone is not that acceptance.
