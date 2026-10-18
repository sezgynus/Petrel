# Maintenance physical acceptance

[English](maintenance-stage8-acceptance.md) · [Türkçe](maintenance-stage8-acceptance_TR.md) · [Profiles](maintenance-profiles.md) · [LCD guide](user-guide.md#maintenance) · [Acceptance ledger](maintenance-reference-printer-acceptance.md)

## Scope and prerequisites

Maintenance is integrated into master. CI validates software contracts, not actual movement, sound, light, heat or restoration. Acceptance is specific to the feature/device/version recorded in the ledger; do not reset accepted records merely because this procedure is revised.

Use a signed, CI-passing revision and verify the running service's checkout. Update/restart only while idle: no print/pause, queued job, MMU/probe/calibration activity or unresolved jog recovery. Clear the physical path and inspect the relevant group's requirements. Physical actuation requires an attending operator. Optional visual/audible/generic-fan/standalone-LED outputs need version-2 role declarations; recognized Happy Hare LEDs use their verified controller mapping. Part-fan candidates need no extra profile.

## On-device manual sequence

1. Open **Maintenance → Check printer**, select the functional group and exact device, then **Prepare check**. Preparation reads state and does not actuate hardware.
2. Read the preparation and separate confirmation. Choose **Start check**, or **Home axes and continue** when offered. Controller-specific actions may say **Run short pulse**, **Run speed steps**, **Run color sequence** or **Run PID**. There is **no operator-answer timeout**. Stale safety evidence requires fresh checks, never a timed-out human response.
3. Observe the requested physical behavior and follow the selected workflow. F02 has three 2-second stages; O04 is red → blue → green → white; F12 requires physical standstill confirmation. Thermal H01 produces seven component metrics in one heater cycle, not seven separate menu trials.
4. Inspect restoration evidence and the result. Only explicit observation with supported readback can produce `PASSED_USER`. S18 and Happy Hare O04 use `OBSERVED_USER`, `restore_verified=False`; do not invent electronic restoration for them. A measured criterion failure is different from a failed procedure.
5. Review **Details**, pages and any recommendations. **Back to checks** returns to the originating device. Active cancellation follows the group's disclosed safety procedure; heating/uncertain motion may request Klipper shutdown. Never replay an ambiguous command blindly.
6. Read independent information under **Maintenance → Diagnostics**. Readings are reports, not hardware PASS. Support recording/export is under **Diagnostics → Support tools**.

## Record and rollback

Record the tested signed SHA, exact target/method, operator answer, controller result and restoration evidence. Update the canonical JSON and both acceptance trackers only after explicit operator approval. CI never grants physical acceptance. For a temporary candidate checkout, restore the original systemd configuration, daemon-reload and restart while idle; verify the actual WorkingDirectory/ExecStart rather than assuming which checkout is running.

## Historical Stage 8 field findings

The following dated failures describe earlier revisions; current acceptance is in the ledger. Their temporary branch paths, legacy profile keys and previous pending states are not deployment instructions. In particular, legacy `buzzer_output` is replaced by version-2 actuator roles, and later reference-printer F01/S18/O04/F02 acceptances remain intact.

## F01 field finding and follow-up verification

During live Remote Display acceptance on 2026-10-16, the F01 part-cooling fan visibly pulsed through the camera, but the controller returned `INCONCLUSIVE / restore_not_verified`. A later independent `/printer/objects/query?fan&webhooks` check showed `fan.speed=0.0`, `fan.rpm=null`, and `webhooks.state=ready`. The initial physical attempt **is not a PASS**, as the immediate restore validation failed; the later read is not proof of the earlier restore timing. The verification-window/retry patch has CI fake coverage and needs a **new** real-Pi acceptance after updating the feature worktree. Confirm the printer is idle and the fan stopped before repeating any physical test.

## S18: field finding and separate pending readback acceptance

On the Pi, `configfile.settings['pwm_cycle_time buzzer']` had pin PB13, value=0, shutdown_value=0, scale=1, but `printer.objects.list` omitted the buzzer and `printer.objects.query` had no status. The updated S18 opt-in path uses configuration-only discovery and **human audible observation**; the result `OBSERVED_USER` does not indicate verified restoration. S18's telemetry-backed restoration acceptance is **not available** with this Klipper object. Enable `buzzer_output='buzzer'` only after checking the actual buzzer and observing it can be safely actuated when the printer is idle. Do not count a CI fake as a real test.

## S18 case-sensitive G-code field observation

On 2026-10-16 the new S18 entry appeared, but its first physical attempt failed with `INCONCLUSIVE / script_failed_or_restore_unknown`: Klipper listed valid mux option `Buzzer`, whereas Petrel generated `PIN=buzzer`. The pin was **not** confirmed actuated. The signed fix resolves the original case-sensitive section name during a read-only preflight. Stage 8 S18 stays **PENDING** until a new idle-printer physical test demonstrates a brief sound **and silence afterward**, recorded as `OBSERVED_USER` without claiming status-based restore verification.
