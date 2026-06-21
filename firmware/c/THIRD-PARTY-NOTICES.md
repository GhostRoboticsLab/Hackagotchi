# Third-party notices — Hackagotchi C probe firmware

The built firmware (`hackagotchi_probe.uf2`/`.elf`) links the components below. All are permissive
(MIT / BSD-3-Clause / Apache-2.0) — no copyleft. Most are **fetched at build time** (gitignored
`upstream/` + the Pico SDK), not redistributed in this repo's source tree; only `src/ssd1306/` is
vendored in-tree (with its own `LICENSE`). This file documents what ends up in the binary.

> Hackagotchi's own source is dual-licensed: the `firmware/c/` subtree (this fork) is **MIT** (see
> [`firmware/c/LICENSE`](LICENSE)); the rest of the project is **GPL-3.0-or-later** (root `LICENSE`).
> This notice covers the third-party dependencies linked into the C binary, independent of that choice.

| Component | Role | License | Source |
|---|---|---|---|
| `raspberrypi/debugprobe` @ `debugprobe-v2.2.3` | fork base: CMSIS-DAP probe, SWD-over-PIO, USB | **MIT** (© Raspberry Pi Ltd) | fetched by `setup.sh` |
| Arm CMSIS-DAP (`CMSIS_DAP/`, within debugprobe) | DAP command processing | **Apache-2.0** | within debugprobe |
| FreeRTOS-Kernel | RTOS (SMP-capable; built single-core here) | **MIT** | debugprobe submodule |
| Raspberry Pi Pico SDK 2.2.0 | HAL, boot, build | **BSD-3-Clause** | runner cache / fetched |
| TinyUSB | USB device stack (DAP vendor + 2× CDC) | **MIT** (© hathach) | pico-sdk submodule |
| `daschr/pico-ssd1306` | OLED driver (vendored) | **MIT** (© 2021 David Schramm) | `src/ssd1306/` (+ `LICENSE`) |
| `zserge/jsmn` | JSON parser for the CDC1 control channel (vendored, header-only) | **MIT** (© 2010 Serge Zaitsev) | `src/jsmn.h` (license header in-file) |
| `raspberrypi/pico-examples` (ws2812 PIO) | NeoPixel status-LED PIO program (vendored) | **BSD-3-Clause** (© 2020 Raspberry Pi) | `src/ws2812.pio` (SPDX header in-file) |
| `carlk3/no-OS-FatFS-SD-SDIO-SPI-RPi-Pico` @ v3.6.2 | M2 SD/FAT on SPI0 (low-prio black-box writer) | **Apache-2.0** (© Carl Kugler) | fetched by `setup.sh` into `upstream/` |
| ChaN **FatFs** R0.15 (bundled inside carlk3) | FAT core (only `ff.c`/`ffsystem.c`/`ffunicode.c` compiled) | **custom 1-clause BSD** (© ChaN; `ff15/LICENSE.txt` exempts binary redistribution from the notice requirement) | within the carlk3 tree (`ff15/`) |

Toolchain (not linked into the binary): Arm GNU Toolchain 13.3.Rel1 (GPL — compiler, not a runtime
dependency); the produced object code is not a derivative of the compiler.

**Per release:** ship this NOTICE + `firmware/c/LICENSE` (and the bundled `ff15/LICENSE.txt`) alongside
the `.uf2`/`.elf`, and confirm no component was swapped for a copyleft/non-commercial alternative. If
yapicoprobe code is ever cherry-picked (RTT/MSC), re-check its per-file licenses (MIT/Apache/SEGGER-BSD)
— see `docs/upstream-strategy.md`.
