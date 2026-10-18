# Maintenance Stage 8 — guided hardware observation contracts

[Türkçe](maintenance-guided_TR.md)

This is the **trusted-target and consent layer**, not an actuator. Production pulse compilation and physical execution are implemented in the separate [pulse](maintenance-pulse.md) and [controller](maintenance-physical.md) layers.

`maintenance_guided.guided_plan(snapshot)` joins the existing immutable discovery/catalog/planner and publishes only exact USER-method candidates: `F01` stock part fan (without RPM), `F02` speed steps, `F12` adaptive startup threshold, `F04` actual fan_generic instances, `O04` named LED devices, `O03` each expressly declared `visual` output_pin with `maintenance.visual:<object>` evidence, and `S18` each declared `audible` pwm_cycle_time with `maintenance.audible:<object>` evidence. No arbitrary `output_pin`, heater fan, controller fan, servo, macro, unknown fan or fake tachometer may enter this set. Absence of service evidence means a candidate is not shown, even if the device is physically installed.

`GuidedConsentGate` checks a registered exact target, current READY epoch/config and the existing fail-closed `MaintenanceSafetyCoordinator` with *positively verified* job queue and Petrel operation checks. It records explicit user intent but cannot run or queue a command. Its only positive terminal record is `CONSENTED / no_hardware_command_dispatched`. Consent is not proof of motor rotation, light emission, buzzer audibility or hardware PASS.

The separate physical controller uses a small allowlisted dispatch adapter and must check queue and operation provenance immediately before each write, capture original target state where meaningful, guarantee bounded execution and cleanup on failure/disconnect, and only then ask for user-observed evidence. Always distinguish commanded PWM from measured RPM. Any unsupported cleanup or unsafe hardware profile must remain blocked.

This pure layer performs no UI, endpoint polling, worker creation, physical command or print hot-path work; production UI/controller integration exists separately. Regression suite: `tests/test_maintenance_guided.py`.
