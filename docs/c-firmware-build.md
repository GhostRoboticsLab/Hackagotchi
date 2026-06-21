# Hackagotchi C probe firmware — build, flash, analyze

The C firmware (`firmware/c/`) is a **fork of `raspberrypi/debugprobe` @ `debugprobe-v2.2.3`** for the
Seeed XIAO RP2040: one image that is both an SWD debug probe (CMSIS-DAP) and the Hackagotchi OLED
dashboard / UART black-box recorder. See `docs/engineering-plan.md` for the *why*; this is the *how*.

## Fork model (overlay, not a vendored copy)

`upstream/debugprobe/` is **fetched on demand** by `setup.sh` and is gitignored — it is never committed.
Our changes live in `firmware/c/` and are compiled *instead of* the matching upstream files:

| Our file | Replaces / shadows | Why |
|---|---|---|
| `boards/board_hackagotchi_config.h` | (the real pin map) | SWD/UART/LED pins for the XIAO |
| `boards/board_debug_probe_config.h` | upstream `include/board_debug_probe_config.h` | **shim** → includes the Hackagotchi config; the only no-edit way to inject the board (the C quote-include adjacency rule defeats a `probe_config.h` overlay — see the shim's header comment) |
| `src/main.c` | upstream `src/main.c` | + the low-priority OLED coexistence task |
| `src/hackagotchi_dashboard.c` | (new) | the OLED task (Gate 1) |
| `src/usb_descriptors.c` | upstream `src/usb_descriptors.c` | 2nd CDC + IAD composite (Gate 2) |
| `src/cdc_uart.c` | upstream `src/cdc_uart.c` | `itf`-guard the CDC class callbacks (Gate 2) |
| `src/cdc1_control.c` | (new) | CDC1 JSON control handler (Gate 2) |
| `src/tusb_config.h` | upstream `src/tusb_config.h` | `CFG_TUD_CDC` 1 → 2 |
| `src/ssd1306/` | (vendored, MIT) | `daschr/pico-ssd1306` OLED driver |

`CMakeLists.txt` lists our files first and puts `src/` + `boards/` first on the include path. When
bumping the upstream base, diff each overlay file against the new upstream version.

## Pin map (XIAO RP2040 + Seeed expansion)

| Function | Pins |
|---|---|
| SWD (locked) | **SWCLK=GP26 (D0), SWDIO=GP27 (D1)** — adjacent, SWDIO=SWCLK+1 (PIO requirement); reclaims D0 LED/ADC + D1 button |
| UART tap (bridge) | GP0 TX / GP1 RX (uart0) |
| OLED | I2C1 SDA=GP6 / SCL=GP7 (OLED @0x3C, FM+ 1 MHz, single-owner — the PCF8563 RTC was dropped) |
| microSD — SPI0 (black box) | SCK=GP2 / MOSI=GP3 / MISO=GP4 / CS=GP28 |
| Buzzer (PWM) | GP29 |
| WS2812 NeoPixel (status) | data=GP12 / power=GP11 |
| USB heartbeat LED | GP25 (onboard blue) |

## Prerequisites (already on the build machine / self-hosted runner)

- **Pinned Arm GCC 13.3.Rel1** at `…/fw-build/arm-gnu-toolchain-13.3.rel1-darwin-arm64-arm-none-eabi`
  (NOT the host's system GCC). Override with `GCC_DIR=`.
- **pico-sdk 2.2.0** at `…/fw-build/micropython/lib/pico-sdk` (override with `PICO_SDK_PATH=`).
  `build_fork.sh` auto-inits its `lib/tinyusb` submodule (MicroPython leaves it empty).
- `cmake` ≥ 3.13, `picotool` 2.x. Optional: `cppcheck` (`brew install cppcheck`) for the 2nd analyzer.

## Build

```bash
cd firmware/c
./setup.sh                      # clone debugprobe-v2.2.3 (+ FreeRTOS) into upstream/ (gitignored)
VERSION=1.0.0 ./build_fork.sh   # -> build/hackagotchi_probe.uf2 (+ .elf); VERSION is compiled in + reported by {"q":"status"} "ver"
```

Gate-test variants (separate images; don't overwrite the product `build/` — use `BUILD_DIR=`):

```bash
ADVERSARIAL_STALL_MS=50 BUILD_DIR=/tmp/adv ./build_fork.sh                       # 50ms stall in the OLED task
ADVERSARIAL_STALL_MS=50 ADVERSARIAL_AT_DAP_PRIO=ON BUILD_DIR=/tmp/adv2 ./build_fork.sh  # + at DAP priority (contention)
```

Confirm the build is the intended image before flashing:

```bash
picotool info -a build/hackagotchi_probe.uf2          # SWCLK=GP26/SWDIO=GP27, "Hackagotchi Probe"
nm build/hackagotchi_probe.elf | grep tud_cdc_rx_cb   # present => Gate-2 (2-CDC) image
strings build/hackagotchi_probe.elf | grep 'Hackagotchi Control'
```

## Flash

The XIAO is the probe; reflashing it needs **USB BOOTSEL** — either the button gesture below, or
`{"q":"bootsel"}` over CDC1 (a software reset-to-bootloader, `reset_usb_boot`) for a hands-free reflash:

```bash
# Put the XIAO in BOOTSEL: hold B, tap R, release B  ->  RPI-RP2 mounts
picotool load -x build/hackagotchi_probe.uf2          # -x = run after load
```

Device-local files (none required for the probe itself yet).

## Static-analysis gate (reliability)

```bash
./build_fork.sh && ./analyze.sh    # GCC -fanalyzer + strict warnings (+ cppcheck) on OUR code only
```

FAILs on any `-Wanalyzer-*` finding, or any warning in the genuinely-new files
(`hackagotchi_dashboard.c`, `cdc1_control.c`); upstream-inherited style warnings in the overlay copies
are report-only. CI runs this as a gate (`.github/workflows/firmware-c.yml`).

## Gates

Hardware-in-the-loop validation lives in `firmware/c/tests/gates/` with results in
`tests/gates/GATE_RESULTS.md`. **Gate 0** (probe flashes a target), **Gate 1** (OLED task survives a
sustained flash soak, 0 stalls — at-DAP-priority contention closed), and **Gate 2** (2nd CDC: 2 nodes,
DAP binds, 100/100 JSON round-trip) all **PASS**. Milestones M1–M4 (reliability core, SD black box,
dashboard, full tool UI) are HIL-verified; per-milestone results are under `tests/m1`…`tests/m4`, and
the release-image attestation (CI-automated vs HIL-attested) is consolidated in
[`release-readiness.md`](release-readiness.md). The HIL gates cannot run in CI — only the build +
`analyze.sh` static-analysis gate do.
