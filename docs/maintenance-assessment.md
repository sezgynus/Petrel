# Maintenance assessment

Backend-only development; the final UI is a separate branch. Immutable measurements, evidence and findings distinguish observation from diagnosis. Baseline comparison requires matching device, method, configuration and explicit test conditions. Legacy results without conditions cannot establish a performance trend. No automatic actuation or configuration saving.

Registered plans are intersected with current capabilities and grouped by topic/device. H01 supplies seven thermal outcomes. Findings preserve user provenance and distinguish incomplete checks from failed criteria. Only an available PID adapter may be suggested; no automatic diagnosis or dispatch.

Explicit baselines and confirmed service records use a bounded atomic versioned store. Device replacement invalidates baselines. Service intervals require a named source; no defaults are invented. Counter resets or identity changes yield unknown. Sampled ON time below an interval cannot prove maintenance is not due.

Petrel ingests completed results into a bounded epoch/config-scoped assessment cache. maintenance_assessment_report() is an on-demand backend API and never dispatches tests. Thermal results retain operation identity, target, duration and initial temperature; unknown fan/environment/hardware conditions are not invented, so these records alone are not a comparable baseline. History preserves conditions and restoration separately.

Firmware facts distinguish active throttling from historical flags, Klipper state and supported driver faults. Numeric policies require explicit source/version and finite limits. Trend comparison is indicative and never identifies a failed part. Missing evidence cannot satisfy a rule.

The backend detailed_report API accepts sourced metric policies, capability-bound service tasks and comparable trend evidence. Unsupported subjects are omitted. Current observations expire after a configurable freshness window (not a user-interaction timeout); stale data becomes unknown. Storage requests use the existing worker and an operation allowlist. No test scheduling or physical command is automatic.

Service policies persist separately from confirmed completion events. Calibration completion never implies hardware health. Semantic messages have matching English/Turkish text without prescribing a UI. Export retains operation, conditions and restore provenance. Petrel exposes maintenance_assessment_details for the detailed backend report.
