# PocketTap — C firmware (planned)

This is where the **next-generation C firmware** will live: a fork of the Raspberry Pi
[debugprobe](https://github.com/raspberrypi/debugprobe) that turns the device into a *real*
hardware **SWD debug probe** (drivable by OpenOCD / probe-rs to halt, erase, and reflash a
wedged target chip regardless of its firmware state) **while also** running the PocketTap
OLED dashboard, UART black-box recorder, and host command protocol — all reimplemented in C
on the Pico SDK + TinyUSB.

The motivation: SWD talks to the chip's debug logic directly, so it recovers a board even
when its core is hung or its USB-CDC is wedged — the deterministic fix for the "dark board
needs a physical replug" problem. Folding that into PocketTap upgrades it from a *passive*
UART tap into an *active* debugger that can resurrect the boards it watches.

**Status:** design phase. The build/keep decision, recommended architecture (base firmware,
OLED-in-C library, TinyUSB composite USB layout, RP2040 core allocation, pin plan), pros/cons,
effort estimate, and a phased MVP plan are captured in:

- [`docs/c-firmware-analysis.md`](../../docs/c-firmware-analysis.md) — the engineering decision document

The working [`../micropython/`](../micropython) firmware remains the reference (v1) and the
field-deployable build until the C firmware reaches parity.
