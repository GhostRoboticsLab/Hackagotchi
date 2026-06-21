## Hackagotchi probe firmware — v1.0 🛠️🐾

First public release. A **debug probe that's also a black-box flight recorder and a
Tamagotchi-style dashboard** for dev boards that go dark — a fork of Raspberry Pi
`debugprobe` (v2.2.3) that does all three on one RP2040 **without ever stalling a flash**
(0 DAP transfer stalls under load, proven on hardware).

### What's in it
- 🔌 **SWD debug probe** (CMSIS-DAP) — halt / erase / reflash an RP2040 target with probe-rs or OpenOCD
- 📼 **UART black-box recorder** to microSD — session logs, heartbeats, and a freeze-frame of the target's last words on a wedge
- 🐾 **Reactive OLED dashboard** — a cat mascot + 6 live screens, with buzzer + NeoPixel event feedback
- 🧰 **JSON control over USB** (CDC1) — hex sniffer, macro sender, runtime baud, SD explorer, hands-free reflash
- 🛡️ **Reliability core** — crash box, software watchdog, lossless UART bridge; runs from flash XIP (+139 KB SRAM)

### Flash it (no toolchain needed)
1. Download **`hackagotchi_probe.uf2`** below.
2. BOOTSEL the XIAO: hold **B**, tap **R**, release **B** → an `RPI-RP2` drive mounts.
3. `picotool load -x hackagotchi_probe.uf2` (or drag the `.uf2` onto the drive).
4. Confirm — send `{"q":"status"}` to the control serial port → `{"fw":"Hackagotchi","ver":"1.0.0",…}`.

### Assets
`hackagotchi_probe.uf2` · `hackagotchi_probe.elf` (to symbolicate crash dumps) · `THIRD-PARTY-NOTICES.md` · `LICENSE`

### Notes
- The firmware reports its own version live (`{"q":"status"}` → `ver`).
- Verified on this image: build + static-analysis gate + full HIL suite — see `docs/release-readiness.md`.
- **License:** project GPL-3.0-or-later; the `firmware/c/` subtree MIT. All dependencies permissive (MIT / BSD-3 / Apache-2.0).
- ⚠️ Under an *artificial* continuous-max-SD soak, retryable (0-stall) DAP errors can appear — ~0 in real use (the target is halted during a real flash). Run soaks on an idle host.

📓 Full changelog: `CHANGELOG.md` · 🔧 build from source: `docs/c-firmware-build.md`
