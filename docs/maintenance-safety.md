# Maintenance safety session guards (development)

[Türkçe](maintenance-safety_TR.md) · [Planner](maintenance-test-planner.md)

**Status:** This module handles fail-closed admission and session invalidation. Production readers and physical controllers already consume it; the module itself does not dispatch commands or draw UI.

`maintenance_safety.py` introduces `SafetyContext`, `SafetyDecision`, `SafetySession`, `precheck` and `MaintenanceSafetyCoordinator`. Admission requires READY with the identical Klipper epoch and settings-object marker, explicitly READY webhooks, idle print statistics, definitely inactive virtual SD/pause state, no active manual probe or busy MMU, positively checked job queue and positively checked Petrel-operation conflict state. Missing critical status is a refusal, not optimistic permission.

A caller must report fresh job-queue evidence (`queue_checked=True`). `job_queue=None` is only appropriate when verified absent; an existing queue must have a known safe state and be empty. Petrel operation checks are similarly explicit (`operations_checked=True`, `conflicting_operation=False`). These flags must be backed by actual checks in the existing Executor integration; setting them blindly defeats the contract.

One local session is permitted at a time. It carries a monotonic token, epoch and in-process configuration marker; source state, queues, and responses are not retained. Before **every** side-effecting dispatch the Executor must supply a fresh `SafetyContext` and call `guard`. Disconnect, state changes and external print start invalidate the reservation; old callbacks cannot affect the next session. This is **not a global printer lock** and cannot prevent simultaneous commands from external Moonraker clients. No restoration or physical PASS is implied by ending a session.

`tests/test_maintenance_safety.py` covers missing data, queue starting/loading, simultaneous operations, paused/printing state, MMU/probe, epoch/config drift, stale tokens and cancel/restart. GitHub Actions CI is the regression gate. Readers and physical adapters are integrated separately; nothing authorizes unattended physical actuation.
