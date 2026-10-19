# Maintenance assessment

The assessment backend is independent of presentation; the final UI connects through its API. Immutable measurements, evidence and findings distinguish observation from diagnosis. Baseline comparison requires matching device, method, configuration and explicit test conditions. Legacy results without conditions cannot establish a performance trend. No automatic actuation or configuration saving.

Registered plans are intersected with current capabilities and grouped by topic/device. H01 supplies seven thermal outcomes. Findings preserve user provenance and distinguish incomplete checks from failed criteria. Only an available PID adapter may be suggested; no automatic diagnosis or dispatch.

Explicit baselines and confirmed service records use a bounded atomic versioned store. Device replacement invalidates baselines. Service intervals require a named source; no defaults are invented. Counter resets or identity changes yield unknown. Sampled ON time below an interval cannot prove maintenance is not due.

Petrel ingests completed results into a bounded epoch/config-scoped assessment cache. maintenance_assessment_report() is an on-demand backend API and never dispatches tests. Thermal results retain operation identity, target, duration, initial temperature, verified fan start state and firmware identity. Missing fan evidence prevents a reference. The operator explicitly confirms unchanged hardware and cooling conditions; environment or remaining part life is never assumed. History preserves conditions and restoration separately.

Firmware facts distinguish active throttling from historical flags, Klipper state and supported driver faults. Numeric policies require explicit source/version and finite limits. Trend comparison is indicative and never identifies a failed part. Missing evidence cannot satisfy a rule.

The backend detailed_report API accepts sourced metric policies, capability-bound service tasks and comparable trend evidence. Unsupported subjects are omitted. Current observations expire after a configurable freshness window (not a user-interaction timeout); stale data becomes unknown. Storage requests use the existing worker and an operation allowlist. No test scheduling or physical command is automatic.

Service policies persist separately from confirmed completion events. Calibration completion never implies hardware health. Semantic messages have matching English/Turkish text without prescribing a UI. Export retains operation, conditions and restore provenance. Petrel exposes maintenance_assessment_details for the detailed backend report.

Typed evidence bridges live observations and saved results using an explicit unit registry. Unknown units are omitted. Caller-verified comparison conditions cannot overwrite measured conditions. Missing or unknown conditions prevent baseline comparison. F12 now emits structured PWM bounds without parsing reason strings. Heating-speed reference saving, comparison and removal require separate UI confirmation. A new measurement or changed reference invalidates the old comparison finding.


Sampled printing and component ON time are bound to service records through a durable counter identity. Completion stores its date, counter and identity; missing/reset counters or identity changes stay unknown. A sampled lower bound above the interval can prove due; below it cannot prove not due. Calendar and usage bases use distinct completion records.

Configuration fingerprints use canonical JSON converted recursively from frozen mappings; key insertion order does not change identity. Exact legacy fingerprints remain readable for compatible heating references without implicit rewriting. New width captures migrate an exact legacy key to its canonical identity.
