# Optional DWIN auxiliary UART

[Documentation](README.md) · [Türkçe](dwin-uart_TR.md)

The auxiliary port can be exposed as a Linux TTY. It is optional and **off by default**.
The native C broker is included in `master` and installed by the optional UART
installer. CI exercises the real TTY through the native broker in Linux 6.1 and
6.12 virtual machines; validate physical timing and recovery on your own DWIN/Pi.
See the [C broker installation and recovery guide](dwin-uart-c.md).

## Locate the auxiliary port

![DWIN auxiliary UART connection beside the black display connector](assets/hardware/dwin-aux-uart-location.png)

The yellow box and arrow identify the auxiliary UART connection beside the black
display connector on the pictured board. The connection has VCC, RX, TX and GND;
the connector housing obscures part of it in this photo. The marker identifies the
connection area, not the pin order; use the markings on your own board.

## Enable or remove

Run `./configure.sh` from `~/Petrel`. Under **DWIN auxiliary UART**, toggle
**DWIN auxiliary UART as a Linux serial port** with Space; save, exit and confirm
Apply. Checked installs the port; unchecked removes it. First-time `./install.sh` includes this choice.
Existing settings are preserved, and a repeated enable with unchanged configuration
leaves an active port alone. Close programs using the auxiliary port before removing
or changing the installation. Removal restores direct Petrel display communication.

![Auxiliary UART installation selected in Kconfig](assets/configuration/auxiliary-uart.png)

The installer obtains headers for the **running** kernel, builds a DKMS module,
installs udev permissions and enables `Petrel-dwin.service`. It does not change the
Device Tree or install a different kernel. Missing headers/build failures stop the
optional setup before switching the screen transport. Later failures attempt to
restore the previous transport. Shared build dependencies are retained on removal.
DKMS rebuilds the module for later kernels when matching headers are available.
Secure Boot systems may require their existing module-signing/key-enrollment process.

The installer also compiles the C broker for the host architecture before
stopping either service. The service runs a root-owned, versioned executable under
`/usr/local/libexec/petrel-dwin/` as the installed user in `dialout`; the running
broker needs no Python interpreter. Build failures leave the active transport in
place. Failed transitions restore the previous unit and retain its executable;
successful removal or replacement cleans up superseded native executables.


Moonraker manages only `Petrel` in `managed_services`; adding `Petrel-dwin`
to that option is rejected by Moonraker, even when it is in `moonraker.asvc`.
Run `./configure.sh` once after pulling this fix and apply with auxiliary UART
enabled. This removes the invalid entry, reloads Moonraker and installs a root
startup preflight in the Petrel service drop-in. Future Moonraker updates (or
manual Git pulls followed by a Petrel restart) refresh the installed C broker and
kernel sources before starting the UI. Unchanged installations skip rebuilding
and do not restart the broker, including when an auxiliary client is open.
Close auxiliary clients before source updates: an in-use port blocks replacement;
a successful replacement hangs up old descriptors. Build/transition failures
fail the UI start and preserve/restore the previous transport; check the journal,
resolve the error and restart Petrel. The preflight never restarts its own UI or
Moonraker during an update. DKMS still handles kernel version changes.
The privileged preflight uses the installed account's `~/Petrel` checkout, just
like the sudo installer; only trusted code should be installed there.

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

The native broker writes transport errors directly to stderr, captured by the
service journal. It does not load Python logging modules. Compare memory at matching
startup, traffic and fault states, including `SwapPss` alongside PSS.

Before release, verify on the actual panel/Pi: setup/removal/reinstallation;
auxiliary TX/RX loopback with binary bytes including `CC 33 C3 3C`; 19200/115200 baud
on a logic analyzer; pySerial/minicom access and enumeration; simultaneous screen
navigation; Petrel-only restart; panel power loss/recovery; busy-port removal refusal;
and CPU/RAM/latency under sustained traffic. Kernel VM tests do not replace these checks.

The display socket also supports a transport-only drain barrier used by Petrel's `serial.flush()` during Picture Flash uploads: a single NUL request is acknowledged only after preceding display commands have drained from the physical UART. Neither control byte is forwarded as a DWIN command. The optional C broker is refreshed by the installed Petrel service's startup hook after updating the repository.
