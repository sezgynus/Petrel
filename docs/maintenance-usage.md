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

**Diagnostics → Usage and history → Sampled component usage** shows all retained component counters through continuous encoder scrolling, including counters after the former first-16 limit. Exact object keys remain distinct in storage and evidence; only presentation supplies friendly names. Tracking states and remaining counter slots expose capacity problems. S10 Moonraker recorded print history remains separate from S12 Petrel sampled usage.

## Resource and persistence bounds

- At most **64 live descriptors**. Standard `fan`, `extruder` and `heater_bed` take priority, followed by object-name order. Names exceeding **96 UTF-8 bytes** are excluded and counted.
- At most **64 LEDs per chain** and **256 LED elements in total** across tracking profiles. These bounds also constrain additional status-copy and subscription payload costs. Excluded supported profiles appear as **Tracking capacity excluded** in S12.
- At most **128 durable component counters**, including removed devices. Old entries are preserved; a full ledger rejects a new name and reports **Counter capacity reached**, without presenting zero usage or evicting an existing service reference. There is no automatic lifetime-counter deletion.
- The usage JSON remains version 1 within **64 KiB**. Existing `sampled_on_s`, `sampled_print_s`, `counter_id`, service completions and tracking anchors keep their identities and units. No retrospective use is assigned to newly supported devices. Repeated loading does not migrate/reset existing values.
- Sampling has no file/network I/O. Existing worker flushes run about every **five minutes**, on explicit worker reads and orderly close. An unchanged empty ledger delta avoids a rewrite. Failed atomic writes restore pending amounts for retry. Sudden power loss can lose the unflushed tail.
- New optional field subscriptions are assembled during connection bootstrap. Case-light view and thermal-check leases retain the usage fields; disabling a view cannot stop their counters. No independent thread, socket or HTTP polling loop is added.

Returning to a pre-feature writer is not a reverse migration: older writers have smaller ledger limits (including a 64-entry read ceiling). Preserve the matching usage/assessment files before any such downgrade; do not truncate the newer ledger or regenerate its identity to force compatibility. Object names identify configured sources, not hardware serial numbers: replacing hardware under the same name does not automatically detect a new component lifetime.

## CI validation and cost reporting

Every signed branch HEAD runs the complete regression suite. Coverage includes arbitrary output names, invalid samples, gaps/epochs, shared subscriptions, legacy identity and write recovery, service anchors, 128-counter scrolling, LED payload bounds and capacity reporting. Existing partial-render/framebuffer regressions remain active; the layout and icon assets are unchanged. Hardware acceptance is still separate.

`tools/benchmark_maintenance_usage.py` compares the new collector with `maintenance_records.py` from signed base `a1c01ef13249e2b9b703cd3a97f7b27b8d24600c`. The workflow fetches that exact source. Typical, 64-fan and 256-LED-budget fixtures report uninstrumented tick times; separate tracing reports retained/peak Python allocations. The full source-status JSON and a full long-name ledger are also sized. Existing discovery RSS/PSS/USS reports include descriptor storage.

These are synthetic runner measurements. A one-Hz CPU conversion is an estimate from collector execution time, not measured Pi utilization; subscription decoding/copying, full application memory and physical LCD traffic are outside that microbenchmark. Real Pi CPU/RSS/PSS/USS acceptance remains unmeasured until an authorized hardware comparison.

To remove a saved reminder, open it in **Care schedule**, choose **Remove reminder**, then confirm on the separate **Remove reminder?** screen. **Keep reminder** is selected first. Removal runs on the existing worker and returns to the refreshed schedule. It removes that saved policy and its active tracking anchor, freeing both slots; usage counters and completed-service history are retained. A reminder edited after the confirmation opened cannot be deleted by that stale confirmation.

## Optional Cartesian axis travel

Enable the optional extra through the existing [configure.sh flow](installation.md#optional-axis-travel-counters), default **on** at first configuration and removable there. No raw movement stream is sent to Petrel. The extra reads the existing toolhead trapq every **0.5 seconds**, integrates elapsed acceleration/cruise/deceleration portions and accumulates absolute X/Y/Z distance. Position offsets and coordinate resets are not movement. It adds no per-move Python hook, new thread, motion command or disk write to Klipper. The native pull buffer is **128 records (10,240 bytes)** and reused; one extraction and at most 128 records are considered per tick. A full buffer drops the entire interval instead of unbounded catch-up. Stalls above two seconds and clock regressions are also dropped and counted. Homing/probing moves are deliberately excluded because endstop-triggered queue truncation requires separate treatment. No physical step-loss or encoder measurement is claimed. Cartesian toolhead travel is not CoreXY belt/motor travel, delta tower travel, independent carriage travel, input-shaper oscillation or manual-stepper travel.

Choose **Care schedule → Add reminder → X/Y/Z travel → Lubricate mechanism → Recorded travel (metres)**. The editor uses whole metres (1–87,600); storage uses millimetres. These are user-defined intervals, not recommended part lifetimes. Below-limit recorded travel cannot prove that maintenance is not due. Completion starts a new maintenance cycle and leaves totals intact.

**Sampled component usage (S12)** includes durable axis totals and tracking/paused state. **Recorded axis travel (S13)** shows this Klipper session's raw counters, explicitly labelled as recorded lower bounds. Petrel's `maintenance-travel.json` atomically stores cumulative totals, a ledger identity and at most eight session checkpoints. The existing worker writes it with the existing five-minute flush, explicit reads and orderly shutdown; unchanged totals avoid a rewrite. Petrel reconnect/restart in the same session does not replay distance. Missing sessions, more than eight unflushed restarts, collector overload, homing/probing, and an abrupt shutdown can lose distance. Counters start at extra READY, not printer manufacture. When disabled/unavailable, progress pauses; no fabricated zero or replacement service anchor is used. Runtime discovery requires the actual loaded extra, not just an installation preference.

The full CI suite checks installation rollback, clean Git state, default-on/preserved-off configuration, removal, session continuity, partial-move integration, overload and optional failure isolation. `tools/benchmark_axis_travel.py` builds the **pinned upstream Klipper trapq C implementation** in CI, verifies acceleration/partial intervals/reverse direction/coordinate reset, and reports extra execution times versus an API-like extraction/JSON/parse calculation. This excludes real sockets and complete API wrappers. Runner timings are not Raspberry Pi CPU percentages or proof against `Timer too close`; physical low-end-board scheduling acceptance remains outstanding. The extra uses internal Klipper C/Python contracts and must be revalidated as Klipper evolves. Unsupported runtime collection disables itself without deliberately invoking printer shutdown; loader/config compatibility failures still require fixing/disabling the extra and restarting Klipper.
