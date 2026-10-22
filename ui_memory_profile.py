"""Opt-in, bounded diagnostic capture; never imported during normal startup.

Traced allocations explain Python ownership, not total process RAM. No locals,
printer configuration, API keys or full snapshots are written to the report.
"""
import json
import logging
import math
import os
from pathlib import Path
import tempfile
import threading
import time
import tracemalloc


def _seconds(environ, name, default):
    value = float(environ.get(name, default))
    if not math.isfinite(value) or not 1 <= value <= 600:
        raise ValueError(name + ' must be between 1 and 600 seconds')
    return value


def allocation_rows(statistics, limit=40):
    """Bound report size; store code locations and sizes, never frame locals."""
    rows = []
    for stat in statistics[:limit]:
        row = {'bytes': stat.size, 'count': stat.count,
               'traceback': [{'file': frame.filename, 'line': frame.lineno}
                             for frame in stat.traceback]}
        if hasattr(stat, 'size_diff'):
            row.update(bytes_diff=stat.size_diff, count_diff=stat.count_diff)
        rows.append(row)
    return rows


def write_report(directory, report):
    """Private, atomic report; never overwrite an earlier capture."""
    directory = Path(directory)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.memory-', dir=directory)
    target = directory / ('memory-%s-%s.json' % (os.getpid(), time.time_ns()))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(report, stream, indent=2)
            stream.write('\n')
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return target


def capture(directory, warmup, seconds):
    """Tracing begins before UI imports; snapshots surround only the workload."""
    started = time.monotonic()
    try:
        time.sleep(warmup)
        baseline = tracemalloc.take_snapshot()
        tracemalloc.reset_peak()
        logging.info('UI memory profile: workload window started (%s seconds)', seconds)
        window_started = time.monotonic()
        time.sleep(seconds)
        current, peak = tracemalloc.get_traced_memory()
        tracer_bytes = tracemalloc.get_tracemalloc_memory()
        final = tracemalloc.take_snapshot()
        report = {
            'schema': 1, 'instrumented': True, 'pid': os.getpid(),
            'python': __import__('sys').version,
            'warmup_seconds': warmup,
            'window_seconds': time.monotonic() - window_started,
            'elapsed_seconds': time.monotonic() - started,
            'traced_current_bytes': current, 'traced_peak_bytes': peak,
            'tracer_metadata_bytes': tracer_bytes,
            'limitations': [
                'Instrumented run: do not compare its RAM/CPU with normal operation.',
                'Native allocations and short-lived freed allocations may be absent.',
                'Profiler and snapshot allocations can appear in these statistics.',
                'Positive net growth is retention, not proof of a leak.',
            ],
            'retained_by_traceback': allocation_rows(final.statistics('traceback')),
            'net_change_by_traceback': allocation_rows(final.compare_to(baseline, 'traceback')),
        }
    finally:
        tracemalloc.stop()
    # Release full snapshots before serializing the bounded report.
    del baseline, final
    target = write_report(directory, report)
    logging.info('UI memory profile complete; tracing stopped; report: %s', target)


def start_from_environment(environ=None):
    environ = os.environ if environ is None else environ
    directory = environ.get('PETREL_PROFILE_MEMORY_DIR')
    if not directory:
        return None
    try:
        warmup = _seconds(environ, 'PETREL_PROFILE_WARMUP_SECONDS', '30')
        seconds = _seconds(environ, 'PETREL_PROFILE_SECONDS', '60')
        if tracemalloc.is_tracing():
            raise ValueError('another tracemalloc session is already active')
        # Validate destination before starting an expensive trace.
        Path(directory).mkdir(mode=0o700, parents=True, exist_ok=True)
        tracemalloc.start(5)
        def work():
            try:
                capture(directory, warmup, seconds)
            except Exception:
                logging.exception('UI memory profile failed; normal UI continues')
        try:
            worker = threading.Thread(target=work, name='ui-memory-profile', daemon=True)
            worker.start()
        except Exception:
            tracemalloc.stop()
            raise
        return worker
    except Exception:
        logging.exception('UI memory profile could not start; normal UI continues')
        return None
