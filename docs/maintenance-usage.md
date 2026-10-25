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

New reminders start with **editable suggested inspection intervals**, selected from the Klipper object family, maintenance task and chosen metric. These are not manufacturer-certified lifetimes and cannot certify a part's health. Values in the editor's native units (calendar days / printing hours / powered hours / travel metres / events) are:

| Hardware or maintenance task | Days | Print h | ON h | Travel m / events |
|---|---:|---:|---:|---:|
| X/Y mechanical axis | 90 | 200 | — | 30,000 m |
| Z mechanical axis | 180 | 500 | — | 10 m |
| Other mechanical stepper | 180 | 300 | — | — |
| Physical endstop | 180 | 500 | — | 500 events |
| Contact probe | 90 | 200 | — | 2,000 events |
| Filament switch / MMU gate | 90 | 300 | — | 2,000 events |
| Filament motion encoder | 90 | 300 | — | 50,000 edges (uncalibrated) |
| G-code button | 180 | 500 | — | 1,000 events |
| Extruder filament feed / nozzle / heating | 90 / 30 / 180 | 200 / 100 / 500 | — / 100 / 300 | — |
| Heater / fan / lighting | 180 / 90 / 365 | 500 / 200 / 500 | 300 / 200 / 1,000 | — |
| `output_pin`, PWM or unknown connected output | 180 | 500 | 500 | — |
| Temperature sensor / MCU / driver | 365 | 700 | — | — |
| General equipment | 180 | 500 | 500 | — |

For `output_pin` specifically, the **only offered metrics** remain calendar days, global sampled printing hours and device sampled powered hours (when supported). The attached hardware is never inferred from its arbitrary name. Uncalibrated encoder edge thresholds are convenience prompts, not filament distance or wear estimates. All existing saved policies, counters and baselines remain unchanged. The rules are pure constant-time lookups: no extra discovery, Moonraker traffic, Klipper extras or polling. The interval editor keeps 1-unit precision on slow turns; accelerated encoder batches scale the step to 10, 100 or 1,000 units for larger values without changing the stored unit.

For printers with exactly one Klipper extruder, filament-feed, nozzle and hotend-heating reminders also offer **Extruded filament (metres)**. Their editable inspection defaults are 1,000 m for feed, 500 m for nozzle inspection and 1,000 m for heating-system inspection. Petrel reads Moonraker's native `GET /server/history/totals` → `job_totals.total_filament_used` in mm, on demand on the existing maintenance worker, with no new periodic queries. The Moonraker total counts recorded print jobs, not manual extrusions, and it may update only after a job ends. Multi-extruder setups do not offer printer-wide totals as per-nozzle metrics. A detected Moonraker job-total reset rotates a small local identity so old reminder baselines pause rather than silently rebase. As unobserved history changes cannot always be detected, this is not a lifetime odometer.

A new reminder obtains its durable anchor at the first valid counter read. Saving it does not record maintenance. **I completed this service** starts a new service cycle without resetting the total counter. Missing live readings pause progress and cannot replace an existing anchor or become a fabricated zero. Care schedule and reminder detail use recorded progress / Tracking starting / Tracking paused consistently.

**Diagnostics → Usage and history → Sampled component usage** shows all retained component counters through continuous encoder scrolling, including counters after the former first-16 limit. Exact object keys remain distinct in storage and evidence; only presentation supplies friendly names. Only usage quantities are shown: event classifications, tracking state and recorder capacity remain internal evidence rather than extra LCD rows. S10 Moonraker recorded print history remains separate from S12 Petrel sampled usage.

## Resource and persistence bounds

- At most **64 live descriptors**. Standard `fan`, `extruder` and `heater_bed` take priority, followed by object-name order. Names exceeding **96 UTF-8 bytes** are excluded and counted.
- At most **64 LEDs per chain** and **256 LED elements in total** across tracking profiles. These bounds also constrain additional status-copy and subscription payload costs. Excluded supported profiles are retained as **Tracking capacity excluded** in raw diagnostic/support evidence, not as LCD S12 rows.
- At most **128 durable component counters**, including removed devices. Old entries are preserved; a full ledger rejects a new name and records **Counter capacity reached** in support evidence, without inventing a zero reading or evicting an existing service reference. S12 hides capacity/tracking bookkeeping rows. There is no automatic lifetime-counter deletion.
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

Enable the optional extra through the existing [configure.sh flow](installation.md#optional-axis-travel-counters), default **on** at first configuration and removable there. No raw movement stream is sent to Petrel. The extra reads the existing toolhead trapq every **0.1 seconds**, integrates elapsed acceleration/cruise/deceleration portions and accumulates absolute X/Y/Z distance. Position offsets and coordinate resets are not movement. It adds no per-move Python hook, new thread, motion command or disk write to Klipper. The native pull buffer is **128 records (10,240 bytes)** and reused; one extraction and at most 128 records are considered per tick. A full buffer drops the entire interval instead of unbounded catch-up. Stalls above two seconds and clock regressions are also dropped and counted. Homing/probing moves are deliberately excluded because endstop-triggered queue truncation requires separate treatment. No physical step-loss or encoder measurement is claimed. Cartesian toolhead travel is not CoreXY belt/motor travel, delta tower travel, independent carriage travel, input-shaper oscillation or manual-stepper travel.

Choose **Care schedule → Add reminder → X/Y/Z axis → Recorded travel (metres)**. Distance is offered on the existing axis entries; a separate X/Y/Z travel entry appears only when its corresponding axis entry is absent. Both resolve to the same Cartesian counter. Previously saved travel-entry reminders keep their device identity and service anchor; numbered motors and manual steppers do not inherit an XYZ distance counter. The editor uses whole metres (1–87,600); storage uses millimetres. These are user-defined intervals, not recommended part lifetimes. Below-limit recorded travel cannot prove that maintenance is not due. Completion starts a new maintenance cycle and leaves totals intact.

**Sampled component usage (S12)** displays durable axis totals only; tracking/paused state remains available internally for maintenance availability and diagnostics. **Recorded axis travel (S13)** shows this Klipper session's raw counters, explicitly labelled as recorded lower bounds. Petrel's `maintenance-travel.json` atomically stores cumulative totals, a ledger identity and at most eight session checkpoints. The existing worker writes it with the existing five-minute flush, explicit reads and orderly shutdown; unchanged totals avoid a rewrite. Petrel reconnect/restart in the same session does not replay distance. Missing sessions, more than eight unflushed restarts, collector overload, homing/probing, and an abrupt shutdown can lose distance. Counters start at extra READY, not printer manufacture. When disabled/unavailable, progress pauses; no fabricated zero or replacement service anchor is used. Runtime discovery requires the actual loaded extra, not just an installation preference.

The full CI suite checks installation rollback, clean Git state, default-on/preserved-off configuration, removal, session continuity, partial-move integration, overload and optional failure isolation. `tools/benchmark_axis_travel.py` builds the **pinned upstream Klipper trapq C implementation** in CI, verifies acceleration/partial intervals/reverse direction/coordinate reset, and reports extra execution times versus an API-like extraction/JSON/parse calculation. This excludes real sockets and complete API wrappers. Runner timings are not Raspberry Pi CPU percentages or proof against `Timer too close`; physical low-end-board scheduling acceptance remains outstanding. The extra uses internal Klipper C/Python contracts and must be revalidated as Klipper evolves. Unsupported runtime collection disables itself without deliberately invoking printer shutdown; loader/config compatibility failures still require fixing/disabling the extra and restarting Klipper.

## Maintenance classes and passive device inventory

Care inventory is independent of executable test permission. At Klipper READY, Petrel retains at most 256 configured/discovered component names, including config-only probes, servos and sensors. Physical endstops get distinct `endstop stepper_*` identities; sensorless/virtual endstops are not invented as physical switches. BLTouch/smart-effector config and their shared `probe` status object are presented once. The device chooser reports excluded devices if the bounded inventory is full; no menu-entry discovery or new periodic subscription is added.

| Component | Maintenance class |
|---|---|
| Axis / mechanism / manual stepper | Mechanical maintenance |
| Extruder | Filament feed maintenance; Nozzle maintenance; Heating system maintenance |
| Bed / generic heater | Heating system maintenance |
| Fan | Fan maintenance |
| LEDs / lighting | Lighting maintenance |
| Generic digital / PWM output | Connected device maintenance |
| Servo | Actuator maintenance |
| Probe / endstop / filament / temperature / other recognized sensor | Sensor maintenance |
| MCU / driver | Electronics maintenance |
| Other discovered hardware | General hardware maintenance |

A single class is selected automatically; choosing an axis or sensor goes directly to **Choose reminder basis**. Extruders show a class chooser because they have three distinct maintenance subjects. Classes follow the declared Klipper object type, not a custom object name: `output_pin fan` still has connected-device maintenance. Calendar reminders are available for configured sensors even without a live reading or runnable test; global sampled printing time is labelled separately. No trigger-count or sensor-active-time metric is fabricated. Completing a reminder records operator maintenance, not a passed sensor test.

Legacy `inspect_clean`, `lubricate` and `nozzle_inspect` task IDs are displayed with the appropriate new class labels. Saved policies, completion dates, counter identities and tracking anchors are not rewritten, merged or reset. Two old policies that now share a class label remain two independent reminders; remove an unwanted duplicate explicitly.


## Event-based sensor counters

**Usage history / Recorded component usage (S12)** receives cumulative counters from the existing optional `petrel_axis_travel` Klipper extra. The LCD lists each source once with its recorded count, without a second row for event kinds such as homing/probing contacts or switch activations. Sensor states are no longer sampled to infer counts. Reading a total less frequently does not lose events already captured by Klipper.

| Source | Event counted |
|---|---|
| Filament switch sensor / digital or ADC `gcode_button` | Inactive → active transition through its existing callback (existing debounce is preserved) |
| Filament motion sensor | Rising edge of its existing encoder input callback; not the derived filament-present flag |
| Physical endstop / supported contact probe | Positive homing trigger result with confirmed stepper movement |

A two-pass homing can therefore count two contacts; each actual probing contact is separate. A G28 command or a homing-complete notification alone is not counted. Timeout, release-seeking move, unchanged stepper position and duplicate completion do not add an event. Endstops pressed while idle are outside homing capture. Sensorless/virtual endstops and non-contact scans are not presented as physical switch activations. Unsupported internal callback/probe layouts do not get a fabricated counter. An unknown startup level is a baseline, not a new activation; counting begins after a known inactive level.

Choose **Care schedule → Add reminder → sensor → Recorded sensor events**. **Sensor maintenance** is selected automatically. Enter a whole event count, review and save. Saving establishes an anchor without recording completed maintenance. Completion advances the anchor and keeps the total. Missing/old/disabled extra or unavailable source pauses tracking. Counters cover enabled capture, not the hardware's entire lifetime; below-limit totals cannot prove service is not due.

The extra attaches to existing callback delivery once at READY, preserves the original callback's result and exceptions, and adds no sensor polling timer, MCU query, pin registration, G-code, thread or disk write. Its existing distance collector remains unchanged. Sensor capture and distance collector state are independent. Up to 64 sources and bounded temporary homing observations are retained. The status object exposes `sensor_schema`, `sensor_state`, `sensor_counts`, `sensor_kinds`, `sensor_disabled` and `sensor_excluded`.

Petrel's separate atomic `maintenance-sensor-events.json` ledger retains up to 128 historical devices subject to a 32 KiB name budget, eight session checkpoints and the existing 64 KiB record bound. Totals and checkpoints commit together. Same-session reconnect/Petrel restart does not replay a total; a new Klipper session contributes its own counts. Worker write failure retains pending snapshots for retry. Unflushed Klipper session tails, more than eight queued session changes, or abrupt shutdown can lose coverage. Reading frequency does not affect capture within the current running session.

Old `maintenance-sensor-usage.json` sampled totals, identities and reminder anchors remain unchanged and available in the exported diagnostic report. They are omitted from the current usage screen; their tracking is paused. They are never added to event totals, particularly because an old motion-sensor presence count is not an encoder-edge count. Select the new event basis explicitly for a new maintenance cycle. ON-time/travel ledgers and their identities are unchanged. S20 export distinguishes legacy sampled counts and new event totals.

Enable/update through the existing **configure.sh** extra option, which now covers both axis travel and sensor event counters; the existing `PETREL_AXIS_TRAVEL` setting and symlink/include stay compatible. An already installed symlink picks up the updated extra file, but **restart Klipper while idle** to load it, then restart Petrel. Without this Klipper restart an old extra cannot supply the new fields. Disabling the shared option pauses both features and preserves all recorded histories.

## Sensor diagnostics

Open **Maintenance → Diagnostics → Sensors** (the Sensors row uses the existing endstop/switch icon), choose a configured sensor and read its report. The list uses the READY inventory, independent of executable test permissions. Config-only devices remain visible. Each report distinguishes effective configuration, exposed status object, supported readings and source availability. Filament detection/enabled state, button state, last endstop/probe query, temperature/minimum/maximum and supported environmental, width or load-cell fields are presented only when the source supplies a valid value. Missing or invalid readings are not converted to zero.

**Refresh reading** makes one read-only object-status request through the existing worker. There is no new permanent subscription, per-sensor timer, G-code, movement, probing or configuration change. Endstop/probe Refresh reads the stored last-query result; it does not trigger a new physical query. Other values are snapshots at read time. A connection/configuration change rejects an older response; leaving before completion does not redirect the screen. Reports use the existing scrollable Graphite layout and partial redraw cache.

Current S12 usage reports show recorded quantities, not tracking/capacity state rows. Care reminders separately show Tracking starting/paused when appropriate; internal tracking state remains in support/export evidence. Migration history, measurement-scope explanations and encoder-navigation instructions stay in documentation rather than occupying LCD report space.
