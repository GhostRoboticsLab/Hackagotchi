# Hackagotchi — C probe firmware

A fork of the Raspberry Pi [debugprobe](https://github.com/raspberrypi/debugprobe) that turns a
XIAO RP2040 into a **real SWD debug probe** (drive it with OpenOCD / probe-rs to halt, erase, and
reflash a wedged target regardless of its firmware state) **while also** running a UART black-box
recorder to SD, a reactive OLED dashboard, and a JSON control channel — all on the Pico SDK +
TinyUSB + FreeRTOS (**single-core**), staying R1-clean (0 DAP transfer stalls) throughout.

> This is the released product (**M1–M5 complete**; the 3 hardware gates passed). For the product
> overview and flashing a release build, see the [repo-root README](../../README.md). Full
> build/flash/analyze guide: [`../../docs/c-firmware-build.md`](../../docs/c-firmware-build.md).
> Engineering history + evidence: [`../../docs/engineering-plan.md`](../../docs/engineering-plan.md),
> [`../../docs/release-readiness.md`](../../docs/release-readiness.md), and the gate/milestone
> results under [`tests/`](tests).

## Build & flash (from source)

```bash
./setup.sh                        # fetch pinned upstream (debugprobe v2.2.3, carlk3 FatFs, pico-sdk 2.2.0)
VERSION=1.0.0 ./build_fork.sh     # -> build/hackagotchi_probe.uf2 (+ .elf); VERSION is reported by {"q":"status"}
./analyze.sh                      # GCC -fanalyzer + cppcheck static-analysis gate
```

Flash: BOOTSEL the XIAO (hold **B**, tap **R**, release **B** → `RPI-RP2` mounts), then
`picotool load -x build/hackagotchi_probe.uf2`. With the firmware already running, `{"q":"bootsel"}`
over CDC1 drops it to BOOTSEL with no button (remote reflash).

## Layout

- `src/` — our overlay: `main.c` (probe + FreeRTOS tasks), `cdc1_control.c` (JSON control),
  `cdc_uart.c` + `uart_bridge.c` (CDC0 bridge), `sd_gate.c` + `recorder.c` (SD black box),
  `hackagotchi_dashboard.c` (OLED), `crash_box.c` / `watchdog_task.c` (reliability), `feedback.c`
  (buzzer/NeoPixel), `hg_config.c` (settings), vendored `ssd1306/`, `jsmn.h`, `ws2812.pio`.
- `boards/board_hackagotchi_config.h` — the **locked** pin map (below).
- `upstream/` (gitignored) — pristine debugprobe + carlk3 FatFs, fetched by `setup.sh`.
- `tests/` — `gates/` (Gate 0/1/2 + `GATE_RESULTS.md`), `m1/`…`m4/` (HIL + host unit tests).

## Pin map (locked; verified with `picotool info`)

| Function | Pins |
|---|---|
| SWD (probe → target) | SWCLK **GP26**, SWDIO **GP27** |
| Target UART bridge (CDC0) | TX **GP0**, RX **GP1** |
| SD card — SPI0 (black box) | SCK **GP2**, MOSI **GP3**, MISO **GP4**, CS **GP28** |
| OLED — I2C1 @ 1 MHz (addr 0x3C) | SDA **GP6**, SCL **GP7** |
| Buzzer (PWM) | **GP29** |
| WS2812 NeoPixel | data **GP12**, power **GP11** |

There is **no physical button** (GP27 became SWDIO) — navigation + tools are driven over the CDC1
JSON channel. Two USB-CDC nodes enumerate: **CDC0** = UART bridge, **CDC1** = JSON control.

## Fork model

Pinned to upstream **`debugprobe-v2.2.3`** (single-core FreeRTOS — before the #189 SMP flash
regression). `setup.sh` fetches the pristine upstream into `upstream/` (gitignored); our build is an
**overlay** (we compile our `main.c` instead of upstream's and add our tasks) without modifying
upstream, so fixes stay rebasable. See [`../../docs/upstream-strategy.md`](../../docs/upstream-strategy.md).

## License

`firmware/c/` is **MIT** ([`LICENSE`](LICENSE)) to stay upstream-compatible; the rest of the repo is
GPL-3.0-or-later. Third-party components (all permissive MIT/BSD-3/Apache) are attributed in
[`THIRD-PARTY-NOTICES.md`](THIRD-PARTY-NOTICES.md).
