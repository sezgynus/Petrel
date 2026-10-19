# Maintenance user experience

Maintenance uses the same Graphite header, bitmap menu font, shared line icons, thin cyan encoder cursor and dashboard as master. It draws only above y=360. The approved entry screen has four fixed destinations: Care schedule, Check printer, Diagnostics and Recommendations (count). Adding plans, devices or recommendations never adds root rows or displaces another destination.

## Care schedule

The fixed summary shows at most two saved reminders, ordered due first, then the nearest known calendar deadline, then unknown coverage. The complete schedule is a separate encoder-scrollable view with three visible rows and a position scrollbar; five or more plans remain reachable. Add reminder and Refresh records stay reachable in that view. Progress means elapsed configured service interval, never wear, component health or remaining lifetime.

Saved policies load on the existing worker when Maintenance opens. Drawing and encoder navigation perform no disk, discovery or network work. The load neither runs a test nor marks service completed. A background result never takes over a screen the user has already opened. Storage failures remain visible, with explicit retry in Care schedule. Cached records are invalidated when the READY/config identity changes.

No reminder, interval or last-service date is invented. Unknown or future calendar timestamps show no filled bar. A sampled counter may prove an interval elapsed, but cannot establish a known remaining interval below the limit. Removed devices are excluded. Create a reminder by choosing a supported device, task, basis and interval; review and save explicitly. Record actual completion in a separate confirmation. Only then is its service date/counter baseline written.

## Predictable destinations

Check printer contains capability-derived functional groups and device instances. Thermal component checks remain combined, and everyday offset, screw and mesh functions remain in Leveling. Diagnostics is directly reachable from the root and groups registered read-only information by purpose. Usage/history and support recording/export live there. Recommendations groups current attention/issue findings by device; new findings update the count and appear inside that destination, never as extra root rows. Calibration remains reachable through the existing additional tools.

Preparing a check does not actuate hardware. Controller preflight and explicit Start consent remain separate. Observations, sensor transitions, external measurement, F12 physical full-stop and workflow choices retain controller authority and have no user-answer timeout. Results distinguish measurements, user observations and unfinished execution. Optional details retain recorded evidence; history is explicitly historical. Calibration settings are not automatically saved.

## Drawing and interaction

The Back row matches master at y=31–83. It returns to the prior selection/device; root Back restores the main-menu Maintenance tile. Root rows stay fixed while only the care subview scrolls. Existing small Graphite icons are reused instead of the former large Maintenance tiles. No large printer illustration occupies the entry screen.

Rendering caches independent text, bar and cursor signatures. Turning between unchanged choices redraws only the old/new thin cursor strips; it does not resend icons or text or clear the full frame. A changed viewport repaints only the content above the dashboard. Progress is quantized to panel pixels before comparing draw signatures. ENTER against changed action identities redraws instead of dispatching the wrong target. Controller phase changes restore safe first focus. Global power/recovery and active operation polling remain unchanged.

## Reference and records

A complete H01 result exposes Heating speed reference. Saving requires known-working hardware and explicit confirmation. Comparison requires a chosen review limit and unchanged hardware/cooling conditions. Target, duration, initial-temperature band, fan state, firmware/config changes and stale evidence prevent invalid comparison. Hardware changes require explicit reference removal. No result diagnoses heater ageing or remaining life.

Regression tests run in GitHub Actions on each signed commit. No local test or development emulator run is required or performed. CI validates UI integration and bounded drawing; it does not replace physical panel acceptance.

The empty-evidence root does not build an assessment report or controller plan. Service targets follow registered plans, including axis names that differ from discovery device names.

## Diagnostic presentation and shared artwork

Successful information reads open their measured facts directly, without another Details selection. Familiar labels and declared units replace internal evidence keys. Pi warning bits are explained as current/history host warnings, never as a 24 V PSU diagnosis. Result/history status and restoration flags use plain language; registered diagnostic fields receive explicit labels and units. Long text wraps and full instructions remain reachable. Retired tile IDs 156–163 are removed from SVG/JPEG sources and the packed library; Maintenance uses master icons 13, 45 and 218. The matching export/manifest is 9 blocks (288 KiB), one block smaller than the former Maintenance UI.

## Incremental updates across all submenus

Encoder rotation reuses the displayed model; ENTER still rebuilds and validates action identities before dispatch. Like master list menus, scrolling uses native move_area, retaining overlapping rows and drawing only the exposed row. Care rows, descriptions, label fields, progress pixels and action viewports keep separate signatures. A value or action-count change does not invalidate the whole frame. Bar growth/shrink paints only the changed span.

## Semantic icons

Small 20x20 Graphite icons 164–167 identify Check printer, Diagnostics, Recommendations and Care schedule. They use master line weight/caps and palette, baseline 4:2:0 JPEG sources, the existing library ID and unchanged 9-block footprint. Submenu icons are selected from action, topic, test feature and service task contracts: heaters, bed, fan, axes/homing, probe, filament, driver, host, buzzer, lights, history and storage use their corresponding existing icons. Info is used only for actual Details; unknown actions and numeric facts do not receive an Info fallback. Care and menu labels remain native LCD text.

## Read-only reports

Diagnostic reads, results, evidence, historical evidence, recommendations and full instructions separate information from actions. Reports use a status heading, muted explanation, two-column labeled measurements and explicit Previous/Next page actions. Numeric facts never become selectable rows. All text remains reachable through bounded pages above the shared dashboard. Focus redraws only action cursor strips; a changed measurement repaints only its value field. CI compares incremental report pixels with clean frames and renders current Maintenance documentation scenes through the production UI. Example screenshots are not physical test evidence.

## Diagnostic field coverage

Every registered information reader now has a named LCD report and explicit field presentation. Driver register replies show readable alerts, standstill, drive mode and current-scale readings; unknown chip layouts retain the register value without inventing a clean status. Motor enable/current, homed axes/commanded coordinates, carriage modes, environmental readings, MCU timing, CAN counters, UART/encoder counters, panel resources, saved history, sampled usage and component-specific update information remain on the LCD. Zero counters and false states are displayed. The former generic support-report redirect is removed.

MCU average/variation values are converted from seconds to microseconds; configured driver currents are amperes. Klipper BME environmental pressure is hPa and gas resistance is ohms. Recorded usage durations are readable time spans, and sampled coverage is explicitly a lower bound. Missing or invalid readings are not replaced by fabricated values. Internal event timestamps and unknown backend bookkeeping do not become measurements. CI covers every registered reader, the actual TMC/MCU/motion parsers and local panel/usage/history output contracts.

Care records refresh asynchronously on every Maintenance entry and at most once per minute while the care view is idle and visible. The existing schedule remains visible during refresh; sampled-hour due states and an open reminder update from the completed worker result.
