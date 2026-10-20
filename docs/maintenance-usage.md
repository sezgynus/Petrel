# Component usage tracking

[Türkçe](maintenance-usage_TR.md) · [Maintenance](user-guide.md#maintenance)

Maintenance derives passive usage descriptors at Klipper READY from the actual object inventory. The same registry supplies the existing WebSocket subscription, collector and discovery snapshot. A physical-test permission is not a prerequisite for reading an output. No output is driven to collect usage, and opening a menu never performs discovery. `printer_capabilities.py` remains independent.

## Supported measurements

| Klipper object | Subscribed field | Recorded meaning |
|---|---|---|
| `fan`, `fan_generic`, `heater_fan`, `controller_fan`, `temperature_fan` | `speed` | Time with reported commanded speed above zero; not verified shaft rotation |
| `extruder`, numbered extruders, `heater_bed`, `heater_generic` | `power` | Time with reported heater PWM above zero; not energy or time above temperature |
| `output_pin`, `pwm_cycle_time`, `pwm_tool` | `value` | Time with reported output value above zero; names are arbitrary |
| `led`, `neopixel`, `dotstar`, `pca9533`, `pca9632` | `color_data` | Time with any reported RGBW channel above zero; not an optical measurement |

Each sample validates the documented field. Missing values, booleans as numbers, non-finite/negative numbers, invalid fan/heater ranges and malformed LED arrays are unavailable readings. LED arrays must match the configured chain length and contain four channels per element, each between zero and one. An effect/enable flag alone does not establish illumination. Servo movement, axis travel, sensor transitions and trigger counts are not inferred from these ON-time profiles. Those require a separate reliable metric contract; calendar and global sampled-print reminders remain available for other discovered devices.

Only intervals greater than zero and at most two seconds with valid ON samples at both ends count. Epoch/config changes and disconnections break continuity. Short activations between observations can be missed. Counts describe recorded lower bounds, never exact lifetime, power consumption, physical motion or remaining useful life. Sampling-gap improvements are a separate task.

## Reminders and diagnostics

Use **Maintenance → Care schedule → Add reminder**, choose a device/task, then **Sampled powered hours** when that device has a usage descriptor. The option represents capability and does not disappear merely because its first reading has not arrived. **Sampled printing hours** is the global printer counter and differs from that component's own ON time.

A new reminder obtains its durable anchor at the first valid counter read. Saving it does not record maintenance. **I completed this service** starts a new service cycle without resetting the total counter. Missing live readings pause progress and cannot replace an existing anchor or become a fabricated zero. Care schedule and reminder detail use recorded progress / Tracking starting / Tracking paused consistently.

**Diagnostics → Usage and history → Sampled component usage** shows all retained component counters through the existing report pagination, including counters after the former first-16 limit. Exact object keys remain distinct in storage and evidence; only presentation supplies friendly names. Tracking states and remaining counter slots expose capacity problems. S10 Moonraker recorded print history remains separate from S12 Petrel sampled usage.

## Resource and persistence bounds

- At most **64 live descriptors**. Standard `fan`, `extruder` and `heater_bed` take priority, followed by object-name order. Names exceeding **96 UTF-8 bytes** are excluded and counted.
- At most **64 LEDs per chain** and **256 LED elements in total** across tracking profiles. These bounds also constrain additional status-copy and subscription payload costs. Excluded supported profiles appear as **Tracking capacity excluded** in S12.
- At most **128 durable component counters**, including removed devices. Old entries are preserved; a full ledger rejects a new name and reports **Counter capacity reached**, without presenting zero usage or evicting an existing service reference. There is no automatic lifetime-counter deletion.
- The usage JSON remains version 1 within **64 KiB**. Existing `sampled_on_s`, `sampled_print_s`, `counter_id`, service completions and tracking anchors keep their identities and units. No retrospective use is assigned to newly supported devices. Repeated loading does not migrate/reset existing values.
- Sampling has no file/network I/O. Existing worker flushes run about every **five minutes**, on explicit worker reads and orderly close. An unchanged empty ledger delta avoids a rewrite. Failed atomic writes restore pending amounts for retry. Sudden power loss can lose the unflushed tail.
- New optional field subscriptions are assembled during connection bootstrap. Case-light view and thermal-check leases retain the usage fields; disabling a view cannot stop their counters. No independent thread, socket or HTTP polling loop is added.

Returning to a pre-feature writer is not a reverse migration: older writers have smaller ledger limits (including a 64-entry read ceiling). Preserve the matching usage/assessment files before any such downgrade; do not truncate the newer ledger or regenerate its identity to force compatibility. Object names identify configured sources, not hardware serial numbers: replacing hardware under the same name does not automatically detect a new component lifetime.

## CI validation and cost reporting

Every signed branch HEAD runs the complete regression suite. Coverage includes arbitrary output names, invalid samples, gaps/epochs, shared subscriptions, legacy identity and write recovery, service anchors, 128-counter pagination, LED payload bounds and capacity reporting. Existing partial-render/framebuffer regressions remain active; the layout and icon assets are unchanged. Hardware acceptance is still separate.

`tools/benchmark_maintenance_usage.py` compares the new collector with `maintenance_records.py` from signed base `a1c01ef13249e2b9b703cd3a97f7b27b8d24600c`. The workflow fetches that exact source. Typical, 64-fan and 256-LED-budget fixtures report uninstrumented tick times; separate tracing reports retained/peak Python allocations. The full source-status JSON and a full long-name ledger are also sized. Existing discovery RSS/PSS/USS reports include descriptor storage.

These are synthetic runner measurements. A one-Hz CPU conversion is an estimate from collector execution time, not measured Pi utilization; subscription decoding/copying, full application memory and physical LCD traffic are outside that microbenchmark. Real Pi CPU/RSS/PSS/USS acceptance remains unmeasured until an authorized hardware comparison.
