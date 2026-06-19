# PocketTap — C firmware ("PocketDebugger")

The next-generation C firmware: a fork of the Raspberry Pi
[debugprobe](https://github.com/raspberrypi/debugprobe) that turns the device into a **real
hardware SWD debug probe** (drivable by OpenOCD / probe-rs to halt, erase, and reflash a wedged
target chip regardless of its firmware state) **while also** running the PocketTap OLED
dashboard, UART black-box recorder, and host command protocol — reimplemented in C on the
Pico SDK + TinyUSB + FreeRTOS SMP.

**Read first:**
- [`../../docs/c-firmware-analysis.md`](../../docs/c-firmware-analysis.md) — the build/keep decision.
- [`../../docs/engineering-plan.md`](../../docs/engineering-plan.md) — the execution plan: base
  decision (debugprobe **v2.2.3**, not yapicoprobe), the reliability stack, the WBS, and the
  detailed **3-gate plan**. **This is the source of truth.**

## Status: gates first

**No OLED/dashboard code is written until the 3 hardware gates pass.** The gates de-risk the one
genuinely uncertain thing — SWD ⇄ dashboard concurrency — for hours instead of weeks. The gate
harness lives in [`tests/gates/`](tests/gates) and is ready to run the moment the SWD header is
soldered. See that directory's README and `docs/engineering-plan.md` §6.

```
Gate 0  stock debugprobe.uf2 on the XIAO halts/erases/flashes a SEPARATE target   (0% porting)
Gate 1  fork + SWD remapped off the SD bus + 1 low-prio OLED task survives a       (make-or-break)
        sustained flash loop with zero DAP corruption
Gate 2  add a 2nd CDC: two usbmodem nodes, DAP still binds, JSON round-trip
```

## Fork model

We pin to upstream tag **`debugprobe-v2.2.3`** (before the #189 SMP flash regression). The product
fork will live on the org remote; until then `setup.sh` fetches the pinned upstream into
`upstream/` (gitignored) so we can build **stock** for Gate 0 and use it as the fork base.

```bash
./setup.sh                 # clone debugprobe@v2.2.3 + submodules into upstream/ (also fetches pico-sdk if needed)
./setup.sh --build-stock   # additionally build the stock standalone probe UF2 for Gate 0
```

`setup.sh` does **not** modify upstream — Gate 1 onward applies our overlay (the board config
below + a single low-priority OLED FreeRTOS task) to a fork of it.

## Board config

[`boards/board_pockettap_config.h`](boards/board_pockettap_config.h) is the **draft** XIAO pin map
for the fork. It documents the full current PocketTap pin usage and the SWD-vs-SD-bus collision.
⚠️ **The SWCLK/SWDIO pins are a candidate pending the physical soldering decision** — a wrong pin
fails Gate 1 silently as "no IDCODE." Lock them there, then validate with `probe-rs info` on the
soldered header *before* trusting the Gate-1 soak.

## Toolchain

Pinned via git submodules (pico-sdk, FreeRTOS-Kernel, TinyUSB, carlk3 FatFs) + a pinned
`arm-none-eabi-gcc` — same philosophy as PicoInky's MicroPython UF2 build. Already installed on
this host (verify with `tests/gates/pin_toolchain.sh`): `probe-rs`, `openocd`, `picotool`.
