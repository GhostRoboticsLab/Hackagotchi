# Changelog

All notable changes to the Hackagotchi C probe firmware (`firmware/c`) are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/); versions are the firmware tags
`v<x.y.z>`. The semver is compiled into the binary and reported by `{"q":"status"}` → `"ver"`.

## [Unreleased]

### OLED UI overhaul — the cat + Spectre the GhostLabs ghost (M-UI-1..5)
A full dashboard glow-up where **every flicker of personality is a literal readout of a real
probe/recorder signal** — all within R1 (idle-priority render, snapshot-only reads) and the
camera-free text-attestation model.

- **Graphics engine:** `ssd1306_blit()` — a clipped 1-bit sprite blit (OR / ANDNOT / XOR) with a
  pico-free, host-unit-tested core (`tests/m_ui/blit_test.c`) and an ASCII-art sprite pipeline
  (`tools/spr_gen.py` → `sprites.gen.h`). Sprites are flash-resident (~0 RAM).
- **Persistent status bar** on every screen (REC / SD glyphs + a ghost pip), attested as a `BAR …`
  line; `DASH_MAX_LINES` 6→8 so a new token can never silently drop a literal fact. New `hud_gauge_h()`.
- **Spectre, the ghost** — its state *is* the target board's soul: absent / live / pale (wedged) /
  glitch (SD fault) / exorcised, bound to the recorder snapshot, attested `g:<state>`.
- **Cat moods** — sleep / content / hunting / alert from existing signals, attested `cat:<mood>`;
  flying-data particle speed scales with live throughput.
- **Resurrection tally** — wedge→recover + fault counts, edge-counted in the 50 Hz SD task (not the
  4 Hz render loop, which could miss a fast edge) and shown on UPTIME.
- **Companion interaction over CDC1** (no physical button): `pet`, `summon`/`banish`, `exorcise`
  (a host flasher fires it after a clean reflash), `ghost` (mute → pure-instrument cluster), `theme`
  (motion density); plus a ghostly dither screen-wipe between screens.

Footprint: text +3.3 KB, bss +164 B total. Static-analysis gate green; the blit host unit test and an
extended `screen_hil.py` attest the new surfaces.

## [1.0.0] - 2026-06-21

First public release. A debug probe that is *also* a black-box flight recorder and a reactive,
Tamagotchi-style dashboard for dev boards that go dark — a fork of Raspberry Pi `debugprobe`
(v2.2.3) that stays **R1-clean (0 transfer stalls)** while doing all three at once.

### Probe / DAP
- CMSIS-DAP v2 probe over SWD-on-PIO (full debug + flash of an RP2040 target), forked from
  `debugprobe-v2.2.3`. SWD remapped + locked to GP26/GP27. The DAP path is guaranteed by FreeRTOS
  task **priority** on the single-core RP2040 (v2.2.3 is single-core — not SMP).
- Runs from flash XIP (not `copy_to_ram`): **+139 KB free SRAM** at identical DAP throughput.

### Bridge + control (two CDC interfaces)
- **CDC0** = transparent target-UART bridge (GP0/GP1), IRQ-driven into a lock-free SPSC ring (0 drops).
- **CDC1** = JSON control channel (`{"q":...}`): status/dump/lastfault, screen nav, hex sniffer,
  macro sender, runtime baud select, SD explorer (ls/cat), settings persistence, beep/led/pixel,
  `bootsel` (hands-free reflash), and test hooks. jsmn-based, bounded, fragmentation-safe.

### Reliability core (M1)
- Post-mortem **crash box** — HardFault + malloc-fail captured to memory that survives the reboot,
  read back over `{"q":"lastfault"}`.
- **Software watchdog**, armed by default, monitoring the USB task (so DAP load can't starve it).
- `{"q":"bootsel"}` software reset-to-bootloader for button-free reflashing.

### SD black-box recorder (M2)
- carlk3 FatFs on SPI0 continuously logs the target's UART (session headers, heartbeats,
  visible-stop + wedge detection, trigger freeze-frames) — the "flight recorder."
- Proven to coexist with DAP flashing: **0 stalls** under a continuous-write soak (the R1 invariant).

### OLED dashboard (M3) + full tool UI (M4)
- 128×64 SSD1306 over I2C1 @ FM+ (1 MHz, single-owner bus): a cat mascot + 6 monitoring screens
  (home / sniffer / recorder / throughput / watchdog / uptime), plus buzzer + WS2812 NeoPixel event
  feedback — all snapshot-fed off the DAP hot path.
- No physical button (GP27 is SWDIO), so navigation + tools are CDC1-driven; the tool screens
  (hex / macro / baud / SD) are excluded from auto-cycle so the panel never parks on a menu.

### Release engineering (M5)
- Firmware **semver compiled in** and reported via `{"q":"status"}` → `"ver"`.
- Manual-dispatch CI (`firmware-c.yml`): build + static-analysis gate (GCC `-fanalyzer` + cppcheck),
  artifacts, and an optional tagged Release that ships the binaries **plus NOTICE + LICENSE**.
- Licensing: project **GPL-3.0-or-later**; the `firmware/c/` subtree **MIT** (upstream-compatible).
  All linked third-party code is permissive (MIT / BSD-3 / Apache-2.0), attributed in
  `THIRD-PARTY-NOTICES.md`.

### Verified
- All gates + milestones HIL-attested on the tagged image — see [`docs/release-readiness.md`](docs/release-readiness.md):
  Gate 0/1/2, the M1–M4 suites, host unit tests, and the R1 0-stall coexistence invariant.

### Known caveats
- Retryable (0-stall) DAP transfer errors rise under an *artificial* continuous-max-SD soak; ~0 in
  real use (the target is halted during a real flash). Host-load-sensitive — run soaks on an idle host.
- Some target boards re-glitch their QSPI under sustained flash hammering (still 0 stalls); power-cycle
  the target between long soak campaigns. Orthogonal to the probe firmware.
