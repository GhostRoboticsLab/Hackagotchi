## Hackagotchi probe firmware — v1.1 🛠️🐾👻

The **"a debug probe with a soul"** release. v1.0 shipped the three-roles-on-one-RP2040 core
(probe + black-box recorder + dashboard); v1.1 is the **OLED UI overhaul** that gives it a face —
a cat and **Spectre the ghost**, where *every flicker of personality is a literal readout of a real
probe/recorder signal*. Still R1-clean (0 DAP transfer stalls): the whole character layer renders at
idle priority off snapshot-only reads, never on the DAP hot path.

### What's new since v1.0
- 👻 **Spectre, the ghost** — its state *is* the target board's soul: dozing (quiet) / live (talking) /
  pale (wedged) / glitch (SD fault) / exorcised, driven from real UART liveness. Attested `g:<state>`.
- 🐱 **Cat moods** — sleep / content / hunting / alert from existing signals; flying-data particle
  speed scales with live throughput. Attested `cat:<mood>`.
- 🎨 **A real graphics engine** — `ssd1306_blit()`, a clipped 1-bit sprite blit (OR / ANDNOT / XOR)
  with a pico-free, host-unit-tested core and an ASCII-art sprite pipeline. Sprites are flash-resident (~0 RAM).
- 📊 **Persistent status bar** on every screen (REC / SD glyphs + a ghost pip), attested as a `BAR …` line.
- 💀 **Resurrection tally** — wedge→recover + fault counts, edge-counted in the 50 Hz SD task.
- 🕹️ **Companion interaction over CDC1** (no physical button): `pet`, `summon`/`banish`, `exorcise`
  (a host flasher fires it after a clean reflash), `ghost` (mute → pure-instrument cluster), `theme`
  (motion density).

Footprint over v1.0: text +3.3 KB, bss +164 B. Everything else from v1.0 is unchanged.

### Flash it (no toolchain needed)
1. Download **`hackagotchi_probe.uf2`** below.
2. BOOTSEL the XIAO (or, on a running unit, send `{"q":"bootsel"}` to the control port — hands-free).
3. `picotool load -x hackagotchi_probe.uf2` (or drag the `.uf2` onto the `RPI-RP2` drive).
4. Confirm — send `{"q":"status"}` to the control serial port → `{"fw":"Hackagotchi","ver":"1.1.0",…}`.

### Assets
`hackagotchi_probe.uf2` · `hackagotchi_probe.elf` (to symbolicate crash dumps) · `THIRD-PARTY-NOTICES.md` · `LICENSE`

### Notes
- The firmware reports its own version live (`{"q":"status"}` → `ver` = `1.1.0`).
- **License:** project GPL-3.0-or-later; the `firmware/c/` subtree MIT. All dependencies permissive (MIT / BSD-3 / Apache-2.0).
- ⚠️ Under an *artificial* continuous-max-SD soak, retryable (0-stall) DAP errors can appear — ~0 in real use (the target is halted during a real flash). Run soaks on an idle host.

📓 Full changelog: `CHANGELOG.md` · 🔧 build from source: `docs/c-firmware-build.md` · 🛠️ build a unit: `docs/build-a-hackagotchi.md`
