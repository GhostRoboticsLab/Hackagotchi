## Hackagotchi probe firmware — v1.1 🛠️🐾👻

**The "give it a soul" release.** v1.0 shipped the hard part — a CMSIS-DAP debug probe, a UART-to-microSD
black-box recorder, and a reactive OLED dashboard, **all three on one single-core RP2040 without ever
stalling a flash**. v1.1 gives that machine a *face*: a cat and **Spectre, the ghost**, where every
flicker of personality is a **literal readout of a real probe/recorder signal** — not decoration.

And because we hold ourselves to "prove it on hardware," the heavier graphics exposed a subtle, *zero-stall*
timing regression — so we caught it, root-caused it, and **fixed it before shipping** (the `HG_PIN_DAP`
story below). Still **R1-clean: 0 DAP transfer stalls.**

---

### 🆕 What's new since v1.0

| | Feature | Attested as |
|---|---|---|
| 👻 | **Spectre, the ghost** — its state *is* the target's soul: dozing (quiet) / live (talking) / pale (wedged) / glitch (SD fault) / exorcised, driven from real UART liveness | `g:<state>` |
| 🐱 | **Cat moods** — sleep / content / hunting / alert from live signals; flying-data particle speed scales with throughput | `cat:<mood>` |
| 🎨 | **A real graphics engine** — `ssd1306_blit()`, a clipped 1-bit sprite blit (OR / ANDNOT / XOR), host-unit-tested, fed by an ASCII-art sprite pipeline. Sprites are flash-resident (~0 RAM) | `blit_test.c` |
| 📊 | **Persistent status bar** on every screen (REC / SD glyphs + a ghost pip) | `BAR …` line |
| 💀 | **Resurrection tally** — wedge→recover + fault counts, edge-counted in the 50 Hz SD task (never misses a fast edge) | on UPTIME |
| 🕹️ | **Companion interaction over CDC1** (no button): `pet`, `summon`/`banish`, `exorcise` (auto-fired after a clean reflash), `ghost` (mute → pure instrument), `theme` (motion density) | CDC1 verbs |
| 🛡️ | **`HG_PIN_DAP`** — DAP/USB hot path pinned to SRAM (the XIP-cache fix below). **On by default.** | `dap_xfers` = live |
| 📈 | **DAP health telemetry** — `{"q":"status"}` now reports `dap_xfers` (transfers executed) + `dap_idle_ms` | `status` reply |

The whole character layer renders at the **lowest priority off snapshot-only reads** — it never touches
the DAP hot path. (v1.0's full feature set — probe, recorder, two CDCs, crash box, watchdog, SD explorer —
is all unchanged and carried forward.)

---

### 🛡️ Under the hood: the regression we caught (and fixed)

A debugger you can't trust isn't a debugger. So this is worth a paragraph.

The firmware runs from **flash XIP** through a 16 KB instruction cache (that choice buys +139 KB of SRAM at
identical DAP throughput). The new render loop churns a big enough flash-instruction working set that it
**evicts the CMSIS-DAP framing path from that cache** — and the next probe transaction pays a flash-refill
delay right inside the USB response window. The result was **retryable** DAP desyncs at **~1.4–3.0%**, where
shipped v1.0 sat at **~0.2%**. Crucially it was **still 0-stall** (the RAM-resident USB ISR keeps the bus
acked — it's added *latency*, not a hang), so it slipped past the hard correctness bar while quietly
regressing a softer one. **Task priority doesn't help here: priority schedules the CPU, not the shared
cache.** We proved it was the firmware (not bench noise) with an **interleaved A/B against the actual
shipped v1.0 image** on one bench, candidate last-in-time.

**The fix (`HG_PIN_DAP`, on by default):** a linker variant pins just the 7 DAP/USB transaction objects into
**SRAM**, out of the contended cache — a *residency* change only (no priority change, no upstream edit,
~18.8 KB of the SRAM headroom). The pinned image soaks **0/500**, back at/below the v1.0 floor, 0 stalls
throughout. And to make sure a "clean" soak can never silently pass with a dead probe, the probe now
self-reports a monotonic `dap_xfers` counter you can read before/after.

→ Full write-up: `docs/firmware-conventions.md` §2, `docs/mcu-bringup-playbook.md` §10, `docs/release-readiness.md` §0.

---

### ⬆️ Flash it / upgrade from v1.0 (no toolchain needed)

1. Download **`hackagotchi_probe.uf2`** below.
2. Enter BOOTSEL — on a running v1.0 unit, **hands-free**: send `{"q":"bootsel"}` to the control port
   (there's no button — GP27 is SWDIO). Otherwise BOOTSEL the XIAO at power-up.
3. `picotool load -x hackagotchi_probe.uf2` (or drag the `.uf2` onto the `RPI-RP2` drive).
4. Confirm — send `{"q":"status"}` to the control serial port → `{"fw":"Hackagotchi","ver":"1.1.0",…,"dap_xfers":…}`.

Settings persist across the upgrade. No re-wiring; same pin map as v1.0.

---

### ✅ Verified on this image

- **Build + static-analysis gate** (`analyze.sh`) — PASS; the two pristine TUs stay 0-warning.
- **Artifact provenance** — `strings` → `ver 1.1.0`; `nm` confirms all 7 DAP/USB objects resident in SRAM
  (`0x2000xxxx`), i.e. the fix is actually in the binary, not just the source.
- **DAP under sustained flash** — the pinned image soaks **0/500** (Gate 1, **0 stalls**) — the clean
  reference. A longer 1000-cycle run on a *non-idle* host stayed **0-stall** but logged **2 retryable
  (recoverable) desyncs on a single cycle** — a strict-bar miss at ~0.2% (the v1.0-class idle floor), with
  a live `dap_xfers` witness (~2 M transfers serviced) confirming the probe never went dark. The fix is
  proven by the A/B (the ~7–15× regression is gone) + the 0/500; an idle-host 1000-cycle re-run for a
  clean 0/N is the one open item (`docs/release-readiness.md` §0).
- The v1.0 HIL suite (probe / bridge / recorder / crash box / watchdog / CDC / SD) carries forward —
  unaffected by a `+0` UI layer + a residency change. See `docs/release-readiness.md`.

---

### 📦 Assets

`hackagotchi_probe.uf2` · `hackagotchi_probe.elf` (to symbolicate crash dumps) · `THIRD-PARTY-NOTICES.md` · `LICENSE`

### 📝 Notes

- The firmware reports its own version live (`{"q":"status"}` → `ver` = `1.1.0`).
- **License:** project GPL-3.0-or-later; the `firmware/c/` subtree MIT. All dependencies permissive (MIT / BSD-3 / Apache-2.0).
- ⚠️ Under an *artificial* continuous-max-SD soak, retryable (0-stall) DAP errors can still appear — ~0 in
  real use (the target is halted during a real flash). Run soaks on an idle host. Some target boards
  re-glitch their QSPI under sustained hammering (still 0 stalls) — power-cycle the target between long soaks.

📓 Full changelog: `CHANGELOG.md` · 🔧 build from source: `docs/c-firmware-build.md` · 🛠️ build a unit: `docs/build-a-hackagotchi.md`
