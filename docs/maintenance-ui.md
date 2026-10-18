# Maintenance user experience

The final UI is developed on feature/maintenance-ui-ux independently of the temporary test UI. The pure experience model groups registered capabilities by purpose and device; it does not discover or actuate hardware. A combined thermal check replaces seven separate entries. Existing Leveling offset, mesh and screw flows are not duplicated. Calibration is separated from functional checks. Summaries distinguish measurement failure, user observation, information and incomplete execution. Numeric evidence and restoration provenance remain available in optional details.

## Encoder interaction

Maintenance opens four Graphite tiles: Check printer, Findings, Service plan and More. Groups and device instances come from registered controller plans. Preparing a check performs no actuation; the controller preflight is followed by a separate Start confirmation. Controller-owned observation, sensor transitions, external measurement, F12 full-stop and workflow steps remain explicit. Back returns to the same device. Information reads are on demand. Active operations continue polling when a recovery view covers Maintenance. Safety stop wording distinguishes heating shutdown from ordinary navigation.

The panel keeps the normal status strip. Root tiles use managed text-free icons 156–163; subpages use bounded partial redraws. Numeric evidence is an optional scrollable Details view. Support recording is under More, not the home page. No local tests/emulator are needed; the Actions regression suite validates the new navigation.
