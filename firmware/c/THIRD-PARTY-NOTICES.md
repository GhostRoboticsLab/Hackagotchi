# Third-party notices — Hackagotchi C probe firmware

The built firmware (`hackagotchi_probe.uf2`/`.elf`) links the components below. All are permissive
(MIT / BSD-3-Clause / Apache-2.0) — no copyleft. Most are **fetched at build time** (gitignored
`upstream/` + the Pico SDK), not redistributed in this repo's source tree; only `src/ssd1306/` is
vendored in-tree (with its own `LICENSE`). This file documents what ends up in the binary.

> The Hackagotchi project's OWN license is not yet chosen (org decision — see `docs/TODO.md`). This
> notice covers only the third-party dependencies, independent of that choice.

| Component | Role | License | Source |
|---|---|---|---|
| `raspberrypi/debugprobe` @ `debugprobe-v2.2.3` | fork base: CMSIS-DAP probe, SWD-over-PIO, USB | **MIT** (© Raspberry Pi Ltd) | fetched by `setup.sh` |
| Arm CMSIS-DAP (`CMSIS_DAP/`, within debugprobe) | DAP command processing | **Apache-2.0** | within debugprobe |
| FreeRTOS-Kernel | RTOS (SMP-capable; built single-core here) | **MIT** | debugprobe submodule |
| Raspberry Pi Pico SDK 2.2.0 | HAL, boot, build | **BSD-3-Clause** | runner cache / fetched |
| TinyUSB | USB device stack (DAP vendor + 2× CDC) | **MIT** (© hathach) | pico-sdk submodule |
| `daschr/pico-ssd1306` | OLED driver (vendored) | **MIT** (© 2021 David Schramm) | `src/ssd1306/` (+ `LICENSE`) |
| `zserge/jsmn` | JSON parser for the CDC1 control channel (vendored, header-only) | **MIT** (© 2010 Serge Zaitsev) | `src/jsmn.h` (license header in-file) |

Toolchain (not linked into the binary): Arm GNU Toolchain 13.3.Rel1 (GPL — compiler, not a runtime
dependency); the produced object code is not a derivative of the compiler.

**Before any public/commercial release (M5):** choose the project license, ship this NOTICE alongside
the binary, and confirm no component was swapped for a copyleft alternative. If yapicoprobe code is
ever cherry-picked (RTT/MSC), re-check its per-file licenses (MIT/Apache/SEGGER-BSD) and that an
umbrella license exists — see `docs/upstream-strategy.md`.
