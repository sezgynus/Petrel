# Issue #41 UART trace

Run while the printer is idle. Keep the current panel firmware and kernel.

```sh
git clone --branch debug/issue-41-uart --single-branch https://github.com/sezgynus/Petrel.git "$HOME/Petrel-issue-41"
sudo systemctl stop Petrel.service
systemctl cat Petrel.service
```

Use `sudo systemctl edit --drop-in=90-issue-41.conf Petrel.service` to add a temporary override. Use the installed service's Python interpreter and arguments, but point its working directory and script at the diagnostic checkout. For example:

```ini
[Service]
Environment=PETREL_TRACE_FLASH=1
WorkingDirectory=/home/pi/Petrel-issue-41
ExecStart=
ExecStart=/home/pi/petrel-env/bin/python /home/pi/Petrel-issue-41/run.py
```

If the installed Petrel service uses the broker socket, inspect `systemctl cat Petrel-dwin.service`. Add the same named drop-in to that service, with `Environment=PETREL_TRACE_FLASH=1` and an ExecStart override that preserves the original broker arguments. For the native broker, run `make -C "$HOME/Petrel-issue-41/native"` and use the resulting `native/petrel-dwin-broker` binary from the checkout. For the Python broker, set the diagnostic WorkingDirectory and keep the installed interpreter and module invocation. Restart the broker before starting Petrel. Keep the existing socket settings and use a single owner for the physical UART.

```sh
sudo systemctl start Petrel.service
sudo journalctl -b -u Petrel.service -u Petrel-dwin.service -o short-precise --no-pager | grep 'issue-41'
```

Wait for startup to finish or for the first Flash timeout, then share the trace lines and say whether the broker was enabled. Review logs for private information before posting.

To restore, stop Petrel and remove only the temporary 90-issue-41.conf drop-ins you created under /etc/systemd/system/Petrel.service.d/ and, if applicable, /etc/systemd/system/Petrel-dwin.service.d/. Run `sudo systemctl daemon-reload`, restart the broker if you changed it, and start Petrel.
