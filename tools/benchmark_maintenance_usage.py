#!/usr/bin/env python3
"""CI-only synthetic usage collector comparison; never a real-Pi CPU claim.

The optional baseline module is the exact recorder from a pinned signed commit.
Timing is uninstrumented. Allocation runs are separate from timing; source
status/config objects already exist before tracing, as in normal state updates.
"""
import argparse
import gc
import importlib.util
import json
from pathlib import Path
import statistics
import sys
import time
import tracemalloc
from types import SimpleNamespace as NS

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from maintenance_records import MaintenanceBook, MAX_RECORD_BYTES


def fixtures():
    typical = ('fan', 'extruder', 'heater_bed', 'output_pin lamp', 'neopixel strip')
    return (('typical', typical, 4),
            ('64 fans', tuple('fan_generic f%02d'%i for i in range(64)), 0),
            ('LED budget', tuple('output_pin p%02d'%i for i in range(60)) +
             tuple('neopixel strip%d'%i for i in range(4)), 64))


def state_for(names, chain):
    settings, status = {}, {}
    for name in names:
        if name.startswith('neopixel '):
            settings[name] = {'chain_count': chain}
            status[name] = {'color_data': [[0.,0.,1.,0.] for _ in range(chain)]}
        elif name == 'fan' or name.startswith('fan_generic '):
            settings[name] = {}
            status[name] = {'speed': .5}
        elif name in ('extruder','heater_bed'):
            settings[name] = {'heater_pin': 'test'}
            status[name] = {'power': .5}
        else:
            settings[name] = {}
            status[name] = {'value': 1.}
    return NS(ready=True, epoch=1, objects=names, settings=settings, status=status)


def book_for(cls):
    def reject(*args, **kwargs):
        raise AssertionError('Benchmark must not perform worker I/O')
    book = cls(NS(submit=reject))
    book._flush_at = float('inf')
    return book


def measure(cls, state, samples):
    times = []
    for _ in range(5):
        book = book_for(cls)
        book.note(state, 0.)
        start = time.perf_counter()
        for i in range(1, samples+1):
            book.note(state, i*.25)
        times.append((time.perf_counter()-start)/samples)
    # A distinct allocation pass; never report traced timing as CPU cost.
    gc.collect()
    tracemalloc.start()
    book = book_for(cls)
    for i in range(5): book.note(state, i*.25)
    gc.collect()
    retained, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    tracked = len(book._usage)
    result = dict(tick_us=statistics.median(times)*1e6, retained_KiB=retained/1024,
                  peak_KiB=peak/1024, counters=tracked)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-file', type=Path)
    parser.add_argument('--samples', type=int, default=2000)
    args = parser.parse_args()
    if args.samples < 1: parser.error('samples must be positive')
    baseline = None
    if args.baseline_file:
        spec = importlib.util.spec_from_file_location('petrel_usage_baseline', args.baseline_file)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        baseline = module.MaintenanceBook
    for label, names, chain in fixtures():
        state = state_for(names, chain)
        current = measure(MaintenanceBook, state, args.samples)
        old = measure(baseline, state, args.samples) if baseline is not None else None
        print(label+': '+json.dumps({'current': current, 'baseline': old}, sort_keys=True))
        if old:
            print('  collector delta at 1 Hz: %+.6f percentage points of one runner core' %
                  ((current['tick_us']-old['tick_us'])/10000))
        print('  full source-status JSON: %d bytes (not periodic delta traffic)' %
              len(json.dumps(state.status, separators=(',',':')).encode()))
    # Long permitted ASCII names, full 128-entry ledger, representative floats.
    ledger = {'version': 1, 'counter_id': 'a'*32, 'sampled_print_s': 1234567.89,
              'sampled_on_s': {('output_pin %03d_'%i).ljust(96,'x'):1234567.89 for i in range(128)},
              'coverage': 'sampled_lower_bound_not_lifetime', 'saved_at': 1780000000.}
    size = len(json.dumps(ledger, separators=(',',':')).encode())
    if size > MAX_RECORD_BYTES: raise AssertionError('Ledger exceeds storage budget')
    print('128-counter long-name JSON: %d / %d bytes' % (size, MAX_RECORD_BYTES))
    print('Synthetic collector only: excludes full application, subscription copies, network and LCD. '
          'Real Pi CPU/RSS/PSS/USS still require hardware measurement.')


if __name__ == '__main__':
    main()
