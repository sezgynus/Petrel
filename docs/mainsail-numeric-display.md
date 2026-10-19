# Mainsail numeric display parity

[Türkçe](mainsail-numeric-display_TR.md)

Reference: Mainsail source `dda4f43f2a2e667af9a0050c0db151daad0c8516`.

## Applied

- MMU remaining filament percentage: ceiling; total weight uses initial_weight, otherwise filament.weight. Missing totals produce an unknown percentage.
- Fan, speed/flow overrides, light, CPU/RAM and MCU load use JavaScript Math.round semantics.
- Live speed uses toFixed(0); flow clamps negative display values to zero and uses toFixed(1) where it fits.
- Move X/Y use two decimals, Z three; wider Z offset fields use three. Dashboard X/Y use two.
- MMU nozzle temperature uses one decimal; wider target fields preserve the raw numeric target. System temperatures use toFixed(0).
- PA/smooth time floor to three decimals, SCV to one, firmware retraction lengths to two. Retraction speeds and Motion velocity/acceleration truncate to integers. Cruise ratio displays as a percentage.
- Elapsed/Remaining include seconds as H:MM:SS; file preview duration uses days/hours/minutes/seconds. Preview weights use integer grams; filament length above 1000 mm uses meters with two decimals, otherwise integer mm.
- Mesh values and min/max use three decimals where they fit.

## Layout exceptions

| Field | Retained format | Reason |
|---|---|---|
| Dashboard nozzle/bed temperature pair | Integer | The decimal pair exceeds its 74 px column with the 8 px font. |
| Dashboard Z | One decimal | Sign, three integer digits and three decimals exceed the right column. |
| Dashboard Z offset | Two decimals | -20.000 exceeds the 48 px field. |
| Dashboard flow >=100 mm³/s | Integer | 100.3mm3/s exceeds the 74 px column. |
| Dense meshes and wider negative values | Previous density-based precision | Point labels must not overlap; 9+ columns retain the old format. |
| Unusually long menu/preview/duration values | Field-specific legacy short format | Fall back to legacy precision when added digits do not fit; menu values use bounded # markers if that also fails. |

Examples: Move Z -100.123 falls back to -100.1; an eight-column mesh shows -0.13 instead of -0.126. Existing pixel budgets remain in force.

Telemetry sampling, estimate algorithms and command increments are unchanged. Maintenance evidence retains its general four-significant-digit format: there is no single equivalent Mainsail field for every evidence value. Formatting parity does not synchronize samples taken at different times.

## Validation

CI regressions compare rounding boundaries against the JavaScript runtime, preserve raw command values and check label pixel bounds. The full suite, Maintenance measurements and all documentation screen renders run in CI. Physical display testing remains separate; this report does not claim hardware validation.
