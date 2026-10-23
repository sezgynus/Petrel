# Native C broker installation and recovery

[Auxiliary UART](dwin-uart.md) · [Türkçe](dwin-uart-c_TR.md)

The optional UART installer on `master` builds and installs the native C broker.
The Python reference implementation remains in the source tree; it is not a
selectable runtime on current master. The TTY, alias, kernel module, display
socket handshake and shared-transport limits are unchanged.

## Install or migrate

Close auxiliary UART applications, then:

```bash
cd ~/Petrel
git fetch origin
git switch master
git pull --ff-only
./configure.sh
```

Keep **DWIN auxiliary UART as a Linux serial port** checked, save, exit and apply.
The installer builds the native executable before stopping services, then changes
`Petrel-dwin.service` to the versioned binary. A Python installation manifest is
migrated automatically. No additional Kconfig toggle or manual compiler command is
needed. Apply once to install the startup preflight described in the
[UART update guide](dwin-uart.md). Later Petrel restarts automatically rebuild changed
native sources; the broker still runs an installed binary.

Installation makes the binary directories searchable despite configure's private
`umask 077`, and checks `--help` as the service user before stopping services.
Reapplying also repairs directory permissions from the initial C installer.

```bash
systemctl show Petrel-dwin.service -p ExecStart
systemctl is-active Petrel.service Petrel-dwin.service
```

`ExecStart` must name `/usr/local/libexec/petrel-dwin/broker-…`, not Python. If both
services are active, repeat the same binary TX and PSS/USS/SwapPss measurements used
for Python, with the same screen state and traffic. No measured Pi memory saving
is claimed before that comparison. CI memory figures from another architecture
are not a substitute.

## Disable the auxiliary transport

Close auxiliary applications, then run:

```bash
cd ~/Petrel
./configure.sh
```

Uncheck **DWIN auxiliary UART as a Linux serial port**, save, exit and apply.
Removal restores direct Petrel display communication and removes the auxiliary
TTY. Re-enable the option on master to install the C transport again.

The old `feature/dwin-aux-uart` and `feature/dwin-aux-uart-c` branches are
historical development snapshots. Switching to either changes the entire
application, including newer NFC and Maintenance features; it is not a
transport-only rollback. A failed installer transition instead restores its
previous service unit and executable automatically. Inspect the journal before
retrying; do not change branches merely to enable or repair the current UART.

## Validation boundary

CI builds release and AddressSanitizer/UndefinedBehaviorSanitizer variants. PTY and
packet-socket tests cover binary payloads containing framing bytes, baud commands,
length-aware replies, UI isolation, malformed input and heartbeat recovery. The test
packet backend is compiled only for these contracts; the installed executable uses
the kernel misc device. Linux 6.1/6.12 guests exercise the production C broker and
actual TTY through binary loopback, baud readback, drain and broker-exit hangup.

Physical Pi TX/RX, baud timing, UI responsiveness, disconnect/recovery and sustained
memory/CPU acceptance remain necessary. Existing transport throughput limits apply.
