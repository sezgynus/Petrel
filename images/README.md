# Wiring illustrations

[English](README.md) · [Türkçe](README_TR.md) · [Installation](../docs/installation.md)

## Current default wiring

![Current Petrel default wiring](petrel-wiring.svg)

The diagram distinguishes BCM identifiers from physical header pin numbers. It shows encoder A/B/button on GPIO21/16/20 (physical 40/36/38), UART TX/RX on GPIO14/15 (physical 8/10), 5 V/GND on physical 2/6, and the GPIO19 hardware PWM buzzer driver input on physical 35. Use a suitable buzzer driver and a common ground.

These are new-install defaults. Existing encoder assignments are preserved by configuration; keep the wiring and saved settings consistent rather than changing an existing installation to match a picture.

## Historical installation examples

The original [GPIO drawing](GPIO.png), [display connector photograph](wire1.png), [second wiring photograph](wire2.png), [third wiring photograph](wire3.png) and [Pi connector photograph](wire4.png) document an older installation with different pin assignments. They are retained as historical references, not the current default pin map. Wire colors alone do not identify a signal.

[Panel photograph](panel.png)
