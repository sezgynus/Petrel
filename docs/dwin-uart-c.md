# Native C broker trial

[Auxiliary UART](dwin-uart.md) · [Türkçe](dwin-uart-c_TR.md)

`feature/dwin-aux-uart-c` starts at Python commit `4edee47`. The original
`feature/dwin-aux-uart` branch is preserved. Only the broker runtime changes:
`/dev/ttyDWIN0`, its alias, the kernel module, display socket handshake and UART
limits remain compatible. The Python reference implementation stays in the tree.

## Install or migrate

Close auxiliary UART applications, then:

```bash
cd ~/Petrel
git fetch origin
git switch feature/dwin-aux-uart-c
git pull --ff-only
./configure.sh
```

Keep **DWIN auxiliary UART as a Linux serial port** checked, save, exit and apply.
The installer builds the native executable before stopping services, then changes
`Petrel-dwin.service` to the versioned binary. A Python installation manifest is
migrated automatically. No additional Kconfig toggle or manual compiler command is
needed. Reapply configuration after native source updates; the service intentionally
runs an installed binary rather than source files from the checkout.

```bash
systemctl show Petrel-dwin.service -p ExecStart
systemctl is-active Petrel.service Petrel-dwin.service
```

`ExecStart` must name `/usr/local/libexec/petrel-dwin/broker-…`, not Python. If both
services are active, repeat the same binary TX and PSS/USS/SwapPss measurements used
for Python, with the same screen state and traffic. No measured Pi memory saving
is claimed before that comparison. CI memory figures from another architecture
are not a substitute.

## Return to Python

```bash
cd ~/Petrel
git switch feature/dwin-aux-uart
./configure.sh
```

Keep auxiliary UART enabled and apply. The Python branch's installer restores its
Python service command because the installation manifest differs. Switching Git
branches or restarting alone does not change the installed service command. The
older Python installer may retain the unused C binary on disk; it is not executed.

## Validation boundary

CI builds release and AddressSanitizer/UndefinedBehaviorSanitizer variants. PTY and
packet-socket tests cover binary payloads containing framing bytes, baud commands,
length-aware replies, UI isolation, malformed input and heartbeat recovery. The test
packet backend is compiled only for these contracts; the installed executable uses
the kernel misc device. Linux 6.1/6.12 guests exercise the production C broker and
actual TTY through binary loopback, baud readback, drain and broker-exit hangup.

Physical Pi TX/RX, baud timing, UI responsiveness, disconnect/recovery and sustained
memory/CPU acceptance remain necessary. Existing transport throughput limits apply.
