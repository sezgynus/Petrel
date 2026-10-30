#!/usr/bin/env python3
"""Synthetic CPU-only comparison; not a Pi RAM or whole-process saving claim."""
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from petrel.moonraker.subscription import MoonrakerSubscription
from petrel.printer.state import PrinterState


def measure(immutable, rounds=150):
    sub = MoonrakerSubscription('http://127.0.0.1:7125', autostart=False)
    sub._state, sub._error = 'ready', None
    sub._settings = {'printer': {'kinematics': 'cartesian'}}
    status = {'device_%d' % i: {'value': i, 'array': list(range(64))}
              for i in range(120)}
    sub._merge(status, 0, replace=True)
    # Both paths start with settings already frozen, as in a stable epoch.
    state = (sub.immutable_state() if immutable
             else PrinterState.from_snapshot(sub.snapshot()))
    started = time.process_time()
    for tick in range(1, rounds + 1):
        sub._merge({'device_0': {'value': tick}}, tick)
        state = (sub.immutable_state() if immutable else PrinterState.from_snapshot(
            sub.snapshot(include_settings=False), reused_settings=state.settings))
    elapsed = time.process_time() - started
    assert state.status['device_0']['value'] == rounds
    assert state.status['device_119']['array'] == tuple(range(64))
    return elapsed


if __name__ == '__main__':
    reference, candidate = measure(False), measure(True)
    print(json.dumps({'scope': 'synthetic: 120 objects, 1 changing object, 150 rounds',
                      'legacy_cpu_seconds': reference, 'incremental_cpu_seconds': candidate,
                      'candidate_over_reference': candidate / reference,
                      'limitation': 'No threshold; hardware workload and RAM must be measured separately.'},
                     indent=2))
