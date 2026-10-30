#!/usr/bin/env python3
"""External UI baseline / CPU sampling. Does not read service environments."""
import argparse
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.measure_petrel_resources import cpu_ticks, parse_smaps
from petrel.diagnostics.memory_profile import write_report


def process_identity(pid):
    if pid <= 0:
        raise ValueError('Service has no running process (MainPID=0)')
    stat = Path('/proc', str(pid), 'stat').read_text()
    fields = stat[stat.rfind(')') + 1:].split()
    return fields[19]  # /proc/PID/stat field 22: starttime


def service_pid(service):
    pid = int(subprocess.check_output(
        ['systemctl', 'show', service, '-p', 'MainPID', '--value'], text=True).strip())
    process_identity(pid)
    return pid


def read_sample(pid):
    root = Path('/proc', str(pid))
    smaps = (root / 'smaps_rollup').read_text()
    memory = parse_smaps(smaps)
    swap = {}
    for line in smaps.splitlines():
        key, _, value = line.partition(':')
        if key in ('Swap', 'SwapPss'):
            swap[key] = int(value.split()[0])
    if 'SwapPss' not in swap:
        raise ValueError('Kernel did not report SwapPss')
    memory.update(swap)
    memory['Pss_plus_SwapPss'] = memory['Pss'] + memory['SwapPss']
    return {'monotonic_seconds': time.monotonic(), 'memory_kib': memory,
            'cpu_ticks': cpu_ticks((root / 'stat').read_text())}


def assert_same_process(service, pid, identity):
    if service_pid(service) != pid or process_identity(pid) != identity:
        raise RuntimeError('Service restarted during capture; discard this run')


def capture_baseline(pid, identity, seconds, interval=1):
    samples = []
    deadline = time.monotonic() + seconds
    while True:
        if process_identity(pid) != identity:
            raise RuntimeError('PID reused during capture; discard this run')
        samples.append(read_sample(pid))
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(interval, remaining))
    elapsed = samples[-1]['monotonic_seconds'] - samples[0]['monotonic_seconds']
    ticks = samples[-1]['cpu_ticks'] - samples[0]['cpu_ticks']
    return {'samples': samples, 'elapsed_seconds': elapsed,
            'cpu_percent_single_core': 100 * ticks / os.sysconf('SC_CLK_TCK') / elapsed}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('baseline', 'cpu'))
    parser.add_argument('--service', default='Petrel.service')
    parser.add_argument('--seconds', type=float, default=60)
    parser.add_argument('--label', required=True)
    parser.add_argument('--output-dir', required=True)
    parser.add_argument('--py-spy', default='py-spy')
    args = parser.parse_args(argv)
    if not math.isfinite(args.seconds) or not 2 <= args.seconds <= 600:
        parser.error('--seconds must be between 2 and 600')
    pid = service_pid(args.service)
    identity = process_identity(pid)
    directory = Path(args.output_dir)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    report = {'schema': 1, 'mode': args.mode, 'label': args.label,
              'pid': pid, 'process_start_ticks': identity,
              'service': args.service, 'platform': platform.platform(),
              'machine': platform.machine(),
              'clock_ticks_per_second': os.sysconf('SC_CLK_TCK')}
    repo = Path(__file__).resolve().parents[1]
    report['tool_checkout_sha'] = subprocess.check_output(
        ['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip()
    report['service_working_directory'] = str(Path('/proc', str(pid), 'cwd').resolve(strict=True))
    print('Capture started: %s / %s / PID %s / %s seconds' %
          (args.mode, args.label, pid, args.seconds), flush=True)
    if args.mode == 'baseline':
        report.update(capture_baseline(pid, identity, args.seconds))
        report['instrumented'] = False
    else:
        output = directory / ('cpu-%s-%s.speedscope.json' % (pid, time.time_ns()))
        subprocess.run([args.py_spy, 'record', '--pid', str(pid),
                        '--duration', str(math.ceil(args.seconds)), '--rate', '49',
                        '--threads', '--format', 'speedscope', '--output', str(output)],
                       check=True)
        report.update(instrumented=True, profile=str(output),
                      interpretation='Active-stack samples, not exact per-function CPU time; '
                                     'idle detection is approximate, especially on ARM32.')
    assert_same_process(args.service, pid, identity)
    print('Report:', write_report(directory, report))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
