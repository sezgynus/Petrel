# UI native-code candidate analysis

[Türkçe](ui-native-profiling_TR.md)

Analysis branch: `analysis/ui-native-profiling`, based on C broker revision
`80a3641`. No UI algorithm has been moved to C. These tools are diagnostic only;
profiling is off by default and is not an installation dependency.

## Three separate passes

Use the same Pi, screen configuration, remote/emulator settings and files. Restart
after switching revision; do not change the checkout while a capture is running.
Record the current SHA, Python/OS/architecture and whether caches are cold/warm.
Do not print, heat, home or start maintenance tests during these UI measurements.
Use view-only screens. Repeat each workload three times, with the same duration
and approximate action count; compare medians and run-to-run variation.

| Workload | 60-second activity |
|---|---|
| idle | Leave the dashboard untouched |
| menus | Repeat the same navigation route; record turns/clicks |
| thumbnails | Open the same file previews; measure first-load and cached runs separately |
| mesh | View an existing mesh; do not start calibration |
| maintenance | Browse existing usage/reminder/assessment pages; do not run tests |

### 1. Normal process CPU and memory

```bash
cd ~/Petrel
git fetch origin
git switch analysis/ui-native-profiling
git pull --ff-only
sudo systemctl restart Petrel.service
sleep 30
git rev-parse HEAD
sudo ~/petrel-env/bin/python tools/profile_ui_resources.py baseline \
  --label idle-1 --seconds 60 --output-dir "$HOME/petrel-ui-profiles/baseline"
```

Repeat with descriptive labels for the workloads above. This tool reads `/proc`
externally; it does not activate a profiler in Petrel. CPU is a percentage of one
core. Reports include raw RSS/PSS/USS/Swap/SwapPss, PSS+SwapPss, PID/starttime,
platform and tool checkout SHA. Restart/PID reuse invalidates a run. The tool SHA
does not prove which code an already-running service loaded; restart as above.
Report filenames are unique and private. A separate `sudo chown -R "$(id -u):$(id -g)"
"$HOME/petrel-ui-profiles"` can restore ownership after all captures.

Record action count and observed pauses separately. These tools do not claim to
measure encoder-to-panel latency. That needs targeted timestamps or video later.

### 2. Active-stack sampling, all threads

Install py-spy in a separate environment, leaving runtime dependencies untouched:

```bash
python3 -m venv ~/petrel-profile-env
~/petrel-profile-env/bin/python -m pip install py-spy
~/petrel-profile-env/bin/py-spy --version
sudo ~/petrel-env/bin/python tools/profile_ui_resources.py cpu \
  --label menus-1 --seconds 60 \
  --py-spy "$HOME/petrel-profile-env/bin/py-spy" \
  --output-dir "$HOME/petrel-ui-profiles/cpu"
```

Repeat the same workloads. Save the installed py-spy version with the results. If
pip has no wheel for the Pi architecture, stop and report that error rather than
changing the application environment. The tool records at 49 Hz, with thread IDs,
to a local Speedscope JSON plus a metadata JSON. Sampling slightly perturbs the
process; use pass 1 for absolute CPU/RAM. Never add `--locals`.

Stack frequency is not exact per-function CPU time. Idle detection is approximate,
especially on ARM32. Python stacks inside native calls do not identify which C
routine is expensive; use a separate native profile if the initial data warrants
it. Do not restrict to `--gil`: Pillow can work outside the GIL. For suspected
UART/network waits, inspect an additional idle-inclusive trace and the transport
code before choosing C. See [py-spy documentation](https://github.com/benfred/py-spy).

### 3. Python allocation ownership

Run this separately from passes 1 and 2. The optional hook starts tracemalloc
before UI imports, waits 30 seconds, then compares snapshots around a 60-second
workload. A journal message marks the workload start. This is instrumentation:
RAM, CPU and startup timing from this run are not a normal-operation baseline.
Five traceback frames and the top 40 entries are retained in the JSON report;
full snapshots and frame locals are never written. Tracing stops automatically
after the window, even on capture failure. A daemon worker does not delay shutdown;
stopping the service early can leave no report.

Use a dedicated runtime drop-in (removed at reboot) and keep the service's existing
user, environment, GPIO and UART ownership:

```bash
sudo mkdir -p /run/systemd/system/Petrel.service.d
sudo tee /run/systemd/system/Petrel.service.d/90-ui-memory-profile.conf >/dev/null <<'EOF'
[Service]
StateDirectory=Petrel-ui-profile
StateDirectoryMode=0700
Environment=PETREL_PROFILE_MEMORY_DIR=/var/lib/Petrel-ui-profile
Environment=PETREL_PROFILE_WARMUP_SECONDS=30
Environment=PETREL_PROFILE_SECONDS=60
EOF
sudo systemctl daemon-reload
sudo systemctl restart Petrel.service
journalctl -u Petrel.service -f --no-pager
```

Start the selected workload at `UI memory profile: workload window started`.
Ctrl+C stops journal viewing, not Petrel. Wait for `UI memory profile complete`.
Repeat with a fresh restart for each workload and record its label/PID separately.
Existing reports are preserved. Invalid options or a profiler error are logged and
do not prevent normal UI startup. Existing tracemalloc sessions are not taken over.
Durations can be adjusted within 1–600 seconds each; the tracer itself can consume
substantial RAM, so do not increase them without reviewing Pi memory headroom.

Remove only this drop-in, then restart to return to an uninstrumented process:

```bash
sudo rm /run/systemd/system/Petrel.service.d/90-ui-memory-profile.conf
sudo systemctl daemon-reload
sudo systemctl restart Petrel.service
sudo tar -czf "$HOME/petrel-ui-memory.tar.gz" -C /var/lib/Petrel-ui-profile .
```

Reports contain code paths, line numbers and byte/count totals, not configuration
contents or keys. Native allocations may not be traced. Net snapshot growth is
retention, not proof of a leak; transient allocations can disappear between
snapshots. The tracer's own overhead is reported separately, but snapshots also
consume memory. Inspect peaks together with retained statistics and pass 1.

## Selecting a candidate

Initial code-inspection candidate: `thumbnail_preview._protect_dark_foreground`
loops over pixels and creates Python tuples. Its importance has not been measured.
Pillow resizing/JPEG encoding already use native code. Rewriting menus or waiting
on UART/network cannot be justified by stack frequency alone.

For each candidate report: workload, absolute process cost, sample share,
retained/peak allocations, likely Python-only improvement, C boundary/copy cost,
and an upper bound on whole-process benefit. A function using 5% of total CPU
cannot save more than that 5% even if made infinitely fast. Prioritize a candidate
only if repeatable whole-process savings or user-visible latency reduction justify
maintenance cost; document the agreed numeric target before implementation.

Keep a Python reference and compare exact packet/image results, boundary inputs,
error handling and cancellation. Any native prototype needs ARM32/ARM64 builds,
sanitizers and CI regression coverage, followed by uninstrumented Pi A/B runs.
Per project policy, do not run local tests/emulator: push each logical commit,
wait for signing, and wait for all CI checks on the final signed SHA.

## First measured candidate change

MMU menu rendering and item eligibility now share one fresh snapshot per build,
including status/settings and the parsed MMU state. The snapshot is not cached
between draws. Input handling takes a new snapshot, and command preparation,
confirmation and dispatch retain their independent current-state validation.
Refresh intervals are unchanged. Measure actual Pi savings before accepting any
CPU or memory improvement claim.

## Incremental immutable UI state

`MoonrakerSubscription.immutable_state()` freezes each changed status object
under the subscription lock and reuses unchanged immutable object trees. A fresh
outer mapping preserves a coherent revision; old published states cannot change.
The latest trees are cached, without retaining revision history. Settings are
frozen once per loaded configuration and reset on disconnect/bootstrap.

`PrinterData.update_variable()` uses this API when explicitly supported. The
existing mutable `snapshot()` API and command validation remain unchanged.
Optional thermal field seeding/pruning and case-light updates invalidate their
object caches. Live update frequency and field coverage are unchanged.

CI checks value equivalence, alias isolation, delta sharing, disconnect/replacement,
optional telemetry and concurrent access. `tools/benchmark_ui_state.py` compares
the legacy path against the incremental path on a synthetic mostly static tree;
its timing is not a claim about whole-process Pi CPU or RAM savings. Repeat
uninstrumented dashboard measurements and the same navigation profile on the Pi.
