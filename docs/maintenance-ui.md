# Maintenance user experience

The final UI is developed on feature/maintenance-ui-ux independently of the temporary test UI. The pure experience model groups registered capabilities by purpose and device; it does not discover or actuate hardware. A combined thermal check replaces seven separate entries. Existing Leveling offset, mesh and screw flows are not duplicated. Calibration is separated from functional checks. Summaries distinguish measurement failure, user observation, information and incomplete execution. Numeric evidence and restoration provenance remain available in optional details.

## Encoder interaction

Maintenance opens four Graphite tiles: Check printer, Findings, Service plan and More. Groups and device instances come from registered controller plans. Preparing a check performs no actuation; the controller preflight is followed by a separate Start confirmation. Controller-owned observation, sensor transitions, external measurement, F12 full-stop and workflow steps remain explicit. Back returns to the same device. Information reads are on demand. Active operations continue polling when a recovery view covers Maintenance. Safety stop wording distinguishes heating shutdown from ordinary navigation.

The panel keeps the normal status strip. Root tiles use managed text-free icons 156–163; subpages use bounded partial redraws. Numeric evidence is an optional scrollable Details view. Support recording is under More, not the home page. No local tests/emulator are needed; the Actions regression suite validates the new navigation.

## Service reminders and history

Service records are loaded only after an explicit request and processed on the existing worker. Add a reminder by choosing a supported device, task and basis: calendar days, sampled printing hours, or sampled ON hours for supported components. The operator chooses the interval. The initial editor value is not an installed policy; saving requires review and explicit confirmation. Saving a reminder does not claim the service was performed. Record actual completion separately. An unknown last-service date stays unknown. Removed devices are hidden and cannot receive new completion records. No wear or remaining-life estimate is inferred.

Recent check history is separately loaded and explicitly marked historical. Existing print usage, sampled usage and sanitized report export remain on-demand information reads. Current Findings includes the individual thermal component outcomes even though the user runs only one combined heating check. Maintenance entry invalidates its draw cache so other screens cannot leave stale pixels.

## Final interaction guards

An ENTER captured against changed actions redraws instead of dispatching. Controller phase changes reset focus to the safe first action. Long controller instructions remain reachable on a separate scrollable page. Multiple findings for the same device are grouped, with all explanations retained. Rendering stays above the normal status strip and unchanged pages emit no redraw packets. The existing accepted physical backends remain the authority; CI validates UI integration but is not physical acceptance of the new screen layout.

Cancelled global power overlays also invalidate the Maintenance canvas before restoration; no check is replayed. External measurement preparation explicitly calls for an instrument and a clear travel path.


## Measured heating-speed reference

A complete H01 result exposes Heating speed reference. The operator separately confirms saving the H05 measurement from known-working hardware. Compare requires choosing a percentage review limit and confirming unchanged heater/nozzle hardware and cooling setup. Target, duration, 5 °C start-temperature band, fan start state, firmware or configuration mismatch prevents comparison. Stale or incomplete records cannot become references. Hardware changes require explicit removal of the old reference. The result describes the measured change and conditions to inspect; it does not diagnose a failed heater cartridge or remaining life. Numeric evidence stays optional.

## Current records and usage coverage

Calendar due state is recomputed from current time when rendering. Discovery changes invalidate the record view; Refresh records reloads on the existing worker. Sampled counters accumulate only observed continuous short intervals and are lower bounds. Creating a reminder never marks maintenance performed; explicit completion after actual work records the current counter baseline. Changed counter identity prevents comparison to the old baseline. Being below a sampled interval never proves maintenance is not due. Loaded due reminders also appear in the home summary. Queue/disk write failures are surfaced on screen.

Moonraker history totals are not assumed to be exact lifetime or reset-proof service counters. Travel without verified continuity is not converted into a maintenance criterion. These sources remain available as information; previous physical acceptance does not certify the new UI layout.
