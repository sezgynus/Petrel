# Maintenance user experience

The final UI is developed on feature/maintenance-ui-ux independently of the temporary test UI. The pure experience model groups registered capabilities by purpose and device; it does not discover or actuate hardware. A combined thermal check replaces seven separate entries. Existing Leveling offset, mesh and screw flows are not duplicated. Calibration is separated from functional checks. Summaries distinguish measurement failure, user observation, information and incomplete execution. Numeric evidence and restoration provenance remain available in optional details.

## Encoder interaction

Maintenance opens four Graphite tiles: Check printer, Findings, Service plan and More. Groups and device instances come from registered controller plans. Preparing a check performs no actuation; the controller preflight is followed by a separate Start confirmation. Controller-owned observation, sensor transitions, external measurement, F12 full-stop and workflow steps remain explicit. Back returns to the same device. Information reads are on demand. Active operations continue polling when a recovery view covers Maintenance. Safety stop wording distinguishes heating shutdown from ordinary navigation.

The panel keeps the normal status strip. Root tiles use managed text-free icons 156–163; subpages use bounded partial redraws. Numeric evidence is an optional scrollable Details view. Support recording is under More, not the home page. No local tests/emulator are needed; the Actions regression suite validates the new navigation.

## Service reminders and history

Service records are loaded only after an explicit request and processed on the existing worker. Add a reminder by choosing a currently supported device, task and calendar interval. The initial editor value is not an installed policy; saving requires review and explicit confirmation. Saving a reminder does not claim the service was performed. Record actual completion separately. An unknown last-service date stays unknown. Removed devices are hidden and cannot receive new completion records. No wear or remaining-life estimate is inferred.

Recent check history is separately loaded and explicitly marked historical. Existing print usage, sampled usage and sanitized report export remain on-demand information reads. Current Findings includes the individual thermal component outcomes even though the user runs only one combined heating check. Maintenance entry invalidates its draw cache so other screens cannot leave stale pixels.
