# Contributing

[English](CONTRIBUTING.md) · [Türkçe](CONTRIBUTING_TR.md) · [Documentation](docs/README.md)

## Report a bug or suggest a feature

Open a GitHub issue describing what you tried, what you expected and what happened. Include the Petrel revision, Pi/OS, display model, relevant Klipper/Happy Hare versions, reproduction steps and a short service-log excerpt. For visual issues, add an original-size screenshot and, when relevant, a photo of the physical display. Remove credentials and private network information.

Feature proposals should describe the user workflow and the required printer capability. Contributions can include code, documentation, translations, icons or hardware test results.

## Prepare a change

Start a branch from current `master`; keep the change focused and open a pull request explaining the problem, resulting behavior and validation. Use a separate development checkout so Moonraker Update Manager can keep the installed checkout clean. Put machine settings in the external environment file.

For user-visible changes, update the relevant guide and screenshots. **English and Turkish documentation must cover the same features and steps**, use the same screenshots/order and keep on-screen labels unchanged. Current usage belongs in the guides; historical audits are references.

## Development tools

| Tool | What it is for | Where to start |
|---|---|---|
| Optional framebuffer emulator | Capture the running LCD UI for visual review, documentation and bug reports | [Emulator guide](docs/ui-emulator.md) |
| Regression suite | Check a change without connecting to or moving a printer | [Test guide](tests/README.md) |
| JPEG icon packer | Add icons and export the managed library | [Icon source guide](assets/icons/README.md) |
| Service logs | Diagnose startup, connection and operation errors | [Troubleshooting](docs/installation.md#troubleshooting) |

## Run and verify

The regression workflow runs on every branch push and master-targeted pull request. Push each logical change, wait for commit signing, then verify CI on that final signed HEAD before continuing. Do not treat checks on the superseded unsigned SHA as the final gate. The commands below document optional local contributor tools; they are not required by the CI-first project workflow.

On an installed Pi, the existing application environment contains the runtime dependencies. Run tests from the development checkout:

```bash
~/petrel-env/bin/python -m unittest discover -s tests -v
~/petrel-env/bin/python -m compileall -q .
```

For manual application testing, stop the installed service first so only one process uses the UART and encoder. Supply your own connection/pin values; running `run.py` directly does not read the service's environment file and its bare UART/button defaults differ from the installer:

```bash
sudo systemctl stop Petrel.service
if systemctl is-active --quiet Petrel-dwin.service; then
  export PETREL_DWIN_SOCKET=/run/petrel-dwin/display.sock
else
  unset PETREL_DWIN_SOCKET
fi
cd ~/Petrel
~/petrel-env/bin/python run.py \
  --serial-port /dev/ttyS0 \
  --encoder-pins 21 16 \
  --button-pin 20 \
  --moonraker-url http://127.0.0.1:7125
```

After exiting the manual process, restart the installed service with `sudo systemctl start Petrel.service`. Use `run.py --help` for available options; CLI values override environment values. Test movement, calibration and MMU changes on appropriate hardware in addition to automated tests.

When the auxiliary UART is installed, keep its broker running and select the display socket explicitly as above; an SSH shell does not inherit the service drop-in. Without a broker, use the physical UART directly. See [manual transport ownership](assets/README.md#manual-transport-ownership).

## Screenshots and documentation

Capture the screen with the [emulator](docs/ui-emulator.md). Store descriptive filenames in `docs/assets/screens/`, replacing the existing image when it represents the same screen/state. Keep the original **272×480 PNG**; do not upscale, crop or convert it to JPEG. Use consistent display widths in Markdown and meaningful alt text in each language.

Check local links, section anchors, image paths, translated guide pairs and user commands before opening the PR. Documentation-only changes do not need printer regression tests unless they also change behavior.

Use `tools/render_docs_screenshots.py` to regenerate all documentation screens without a printer; the [offline rendering guide](docs/ui-emulator.md#render-documentation-screens-offline) explains the commands and example data. Preserve existing image filenames so forum links keep working.

### Production and validation contracts

Run the [PNG and GIF refresh commands](docs/ui-emulator.md#refresh-pngs-frames-and-gifs) together. Preserve 272×480 panel PNGs; framed 528×900 copies are presentation only. Use one checkout, sample data, scene order and matching EN/TR captions. Original PNG gallery links use repository-relative paths to follow the same branch; copy the opened GitHub page's full address for forum posts.

Print/Tune validation: an After Job click must only send `SET_PIN`, never immediately switch off hardware; older replies must not overwrite a newer edit; rejected values/switches/Pause blink red twice and return to subscribed state; an incomplete hold preserves the draft. Source and hardware checks are in the [test guide](tests/README.md).

For JPEG changes preserve the [fan/button contracts](assets/icons/README.md#print-buttons-switches-and-fan-artwork), font ID 0, baseline 4:2:0 and source/export equivalence. Normal/selected button masks must match. Validate relevant states on the physical panel after emulator review.

## PN532 Type 4 target workaround

### Problem and chosen implementation

During PN532 read-only Type 4 NDEF URI emulation, Android sometimes identified the target as **Unknown FeliCa / NfcF**, rather than ISO14443A NDEF. Experiments compared target Mode `0x05` / `0x04`, ATQA `00 04` / `00 08`, and a PN532 mode-detector register intervention.

The production path in `petrel/features/nfc/libnfc.py` retains the distribution's original `libnfc.so.6`, upstream PN532 `TgInitAsTarget` Mode `0x05`, ATQA `00 04` and SAK `0x20`. Immediately before **each** `nfc_target_init()` attempt, PN532 targets queue this masked write through `ctypes`:

```python
pn53x_write_register(device, 0x6301, 0x04, 0x04)
```

Address `0x6301` is `CIU_Mode`; mask `0x04` selects bit 2, `ModeDetOff`, associated with AutoColl mode detection. This is a hardware-specific workaround for the observed misidentification, **not a documented public “disable FeliCa” API**. The masked write preserves unrelated bits. libnfc caches the write and flushes it on subsequent native PN532 communication; return code `0` confirms acceptance, not register readback or successful RF behavior.

The original system library plus this register intervention was chosen because physical trials removed the observed FeliCa misidentification without maintaining custom libnfc builds, replacing system libraries, or exposing experimental A/B/C/D profiles and marker files as product settings. Apply it automatically only when the configured reader model is `PN532` and the exclusive target session is active. Do not send these writes to other readers or add them to ordinary initiator scanning.

### Separate Android URL-dispatch issue

Reading an NDEF URI in NFC Tools did not initially cause Android to offer/open the URL. That was a separate session-lifetime defect: closing immediately after the first complete NDEF read prevented subsequent Android `SELECT`/`READ` APDUs. `NFCTargetSession.serve_uri()` now continues serving APDUs after transfer, uses a 2000 ms post-transfer receive timeout, and emits `share.ndef_transferred` only once. **ModeDetOff addresses technology misidentification; the post-transfer APDU lifetime addresses URL dispatch.** Preserve both mechanisms independently.

### Evidence and maintenance limits

- On the tested PN532/Pi/Android combination, the user reported 20/20 NDEF reads with URL opening, no FeliCa detections, and one separate red activation error. This is limited physical evidence, not a guarantee for all phones or libnfc packages; the rare `nfc_target_init(-1)` error remains unresolved.
- `pn53x_write_register` is exported by the tested upstream/distro libnfc 1.8.x, but is a **private symbol, not a stable public API**. `bind_pn532_register()` binds its exact ABI and reports a clear error if unavailable; do not silently fall back. CI checks the distro symbol and PN532-specific behavior. Recheck symbol/ABI compatibility when changing libnfc versions or platforms.
- Closing the PN532 target session queues a masked clear of bit 2 as **best effort**. A deactivated device or cached write means this is not verified hardware restoration.
- Keep the distribution library intact. Do not restore custom `.so` selection, experiment profiles or activation-marker files. Real NFC reader configuration and optional feature installation remain valid, separate concerns.
- Relevant regressions: `tests/test_nfc_system_modedet.py`, `tests/test_nfc_type4_dispatch.py` and `tests/test_libnfc_api.py`. Automated tests cannot establish RF compatibility; validate technology detection and Android URL opening physically after changing this path.

## Home menu ordering contract

Info is always the final home entry. Insert new features before Info; RFID immediately precedes Info. `tests/test_rfid_emergency.py` preserves this ordering.

## Commit titles and wiring compatibility

Use `type(scope): description`, for example `feat(ui): ...`, `fix(nfc): ...`, `fix(dwin): ...` or `docs(guides): ...`. The signing bot preserves the message; it does not repair its format. `docs(nfc):` is an explicit NFC-only publishing opt-in, so do not use it for general documentation work.

New encoder wiring uses A/B GPIO21/16 and buzzer GPIO19. Existing A/B GPIO21/19 installations remain supported with a different non-conflicting buzzer PWM pin; do not silently rewire an existing installation.

For a full audit, a `docs(audit):` commit on master explicitly opts into generation of all LCD PNGs/GIFs and Kconfig captures before the signing bot amends that same commit. Generated assets, galleries and static bilingual/link checks must succeed first. Normal commits keep the existing signing behavior. Wait for the complete regression result on the final signed SHA. The standalone Documentation Render action remains available for later refreshes.
