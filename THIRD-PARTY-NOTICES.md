# Third-party notices

Copyright © 2026 GhostRoboticsLab and the Hackagotchi authors.

Hackagotchi's own source code is licensed **GPL-3.0-or-later** (see [`LICENSE`](LICENSE)),
**except** the `firmware/c/` subtree, which is **MIT** (see
[`firmware/c/LICENSE`](firmware/c/LICENSE) and the note below). Bundled and build-time
third-party components remain under their own licenses, reproduced or referenced here.

## firmware/micropython — v1 (project code: GPL-3.0-or-later)

Vendored MicroPython drivers, redistributed under their original **MIT** license:

| Component | Path | License | Upstream |
|---|---|---|---|
| `ssd1306.py` | `firmware/micropython/lib/ssd1306.py` | MIT | MicroPython project (`micropython/micropython`) |

MIT is one-way compatible with GPL-3.0, so the combined v1 firmware (GPL-3.0 application
code + MIT drivers) is distributable as a whole under **GPL-3.0-or-later**.

## firmware/c — v2 (subtree license: MIT)

The v2 debug-probe firmware is a fork of Raspberry Pi's **`debugprobe`** (MIT) and is kept
under **MIT** so fixes remain upstream-compatible (see `docs/upstream-strategy.md`). Its full
per-component attribution lives in
[`firmware/c/THIRD-PARTY-NOTICES.md`](firmware/c/THIRD-PARTY-NOTICES.md) and covers, in brief:

| Component | License |
|---|---|
| `raspberrypi/debugprobe` | MIT |
| ARM CMSIS-DAP | Apache-2.0 |
| FreeRTOS-Kernel | MIT |
| Raspberry Pi Pico SDK | BSD-3-Clause |
| TinyUSB | MIT |
| `daschr/pico-ssd1306` | MIT |
| `zserge/jsmn` | MIT |

All permissive, no copyleft. Per release, ship this notice and keep any GPL (sigrok) or
non-commercial (SEGGER SystemView) components **out** of the shipping image, per
`docs/engineering-plan.md`.
