# Optional DWIN auxiliary UART

[Documentation](README.md) · [Türkçe](dwin-uart_TR.md)

The auxiliary port can be exposed as a Linux TTY. It is optional and **off by default**.
This feature is under development on `feature/dwin-aux-uart`: CI exercises the real
TTY in Linux 6.1 and 6.12 virtual machines; physical DWIN/Pi acceptance is pending.

## Enable or remove

Run `./configure.sh` from `~/Petrel`. Under **DWIN auxiliary UART**, toggle
**DWIN auxiliary UART as a Linux serial port** with Space; save, exit and confirm
Apply. Checked installs the port; unchecked removes it. First-time `./install.sh` includes this choice.
Existing settings are preserved, and a repeated enable with unchanged configuration
leaves an active port alone. Close programs using the auxiliary port before removing
or changing the installation. Removal restores direct Petrel display communication.

The installer obtains headers for the **running** kernel, builds a DKMS module,
installs udev permissions and enables `Petrel-dwin.service`. It does not change the
Device Tree or install a different kernel. Missing headers/build failures stop the
optional setup before switching the screen transport. Later failures attempt to
restore the previous transport. Shared build dependencies are retained on removal.
DKMS rebuilds the module for later kernels when matching headers are available.
Secure Boot systems may require their existing module-signing/key-enrollment process.


When enabled, the existing Moonraker Petrel update entry also manages the broker.
Close auxiliary-port clients before updating: a broker restart hangs them up.
Rerun `configure.sh` to apply changed kernel-module sources; DKMS handles kernel
version changes, not arbitrary source changes in a Git checkout.

## Use from another program

The port is `/dev/ttyDWIN0`. The enumeration alias `/dev/ttyS_DWIN0` points to the
same device for tools such as pySerial 3.5 whose Linux scanner uses fixed name
patterns. Applications do not need a Petrel API. Automatic enumeration behavior
still depends on the application's scanner; either path can be entered explicitly.
Access uses the normal `dialout` group, like the display's physical UART.

Moonraker/Mainsail lists it as **HARDWARE UART**, with driver **petrel_uart**.
The endpoint is bound on the `dwin` bus; read-only TTY sysfs attributes expose
`uartclk=15667200` (the panel's baud-generator clock) and `port=0x0` (no host I/O
address). This classification does not imply a direct host MMIO UART or remove the
shared-transport limits below. Updating an existing installation requires rerunning
`./configure.sh` and applying with the auxiliary UART enabled to rebuild/reload the
module; then refresh Mainsail's device list.

```python
import serial

with serial.Serial('/dev/ttyDWIN0', baudrate=115200, timeout=1) as port:
    port.write(b'hello\r\n')
    reply = port.read(64)
```

Standard `open`, `read`, `write`, `poll` and `termios` are implemented. Baud settings
apply to the **auxiliary** UART only. The host-to-display UART stays at 115200 baud.
The broker runs independently: stopping `Petrel.service` leaves the auxiliary port
available; stopping the broker or losing panel communication hangs up open clients.
A disconnected port must be reopened after recovery.

## Limits

- 8 data bits, no parity, 1 stop bit. No modem control or hardware flow control.
- Default 115200 baud. The documented divisor range is `1..1023`, with
  `divisor = round(15667200 / baud)`. Requests below **15300 baud**, including
  9600, are unsupported. Divisor rounding determines the actual rate. Unsupported
  hardware settings preserve the preceding termios hardware configuration; read
  back the settings when an application needs a specific rate.
- The display and auxiliary traffic share one 115200-baud physical connection.
  An auxiliary baud setting is not a guaranteed end-to-end throughput. Packet
  overhead, display rendering, kernel scheduling and the panel affect latency.
- The broker splits TX into at most 248-byte commands, avoiding an embedded DWIN
  terminator, and alternates complete display/auxiliary packets. Buffers are bounded;
  outbound writes apply backpressure and inbound overflow logs an error and hangs up.
  There is no hardware flow control to prevent upstream data loss under overload.
- DWIN provides no physical TX-complete acknowledgement. `tcdrain` uses a conservative
  serialization interval and is not a measurement of the final auxiliary stop bit.

## Diagnosis and physical acceptance

Use `journalctl -u Petrel-dwin.service` for broker errors and
`systemctl status Petrel.service Petrel-dwin.service` for service state.
A port node can exist while the screen is powered off; opening it requires a
connected broker and a successful panel handshake.

Before release, verify on the actual panel/Pi: setup/removal/reinstallation;
auxiliary TX/RX loopback with binary bytes including `CC 33 C3 3C`; 19200/115200 baud
on a logic analyzer; pySerial/minicom access and enumeration; simultaneous screen
navigation; Petrel-only restart; panel power loss/recovery; busy-port removal refusal;
and CPU/RAM/latency under sustained traffic. Kernel VM tests do not replace these checks.
