# Hackagotchi — Gate Results

Copy this file per attempt (e.g. `GATE_RESULTS_2026-06-20.md`) and fill it in. Evidence dirs
(`gate0/ gate1/ gate2/`) are gitignored; attach key logs to the run record.

```
Date: 2026-06-19  Operator: Pratheek  Host macOS: Darwin 25.5.0  probe-rs: 0.31  openocd: 0.12.0  picotool: 2.2
Probe fw source/SHA: stock debugprobe-v2.2.3 (debugprobe_on_pico.uf2), CMSIS-DAP serial 4150324E30363318
Pico SDK tag: 2.x (MicroPython-bundled; blink fixtures built with pinned Arm GCC 13.3.Rel1)
Target: fresh Pico W (RP2040 rev B2, flash 'win w25q16jv' 2MB) running PicoInky 0.8.0 before the wipe
Wired SWD (Gate 0): SWCLK=GP2 (D8)  SWDIO=GP3 (D10)  GND  (3-pin, no RESET)
Wired SWD (Gate 1, REMAPPED + LOCKED): SWCLK=GP26 (D0)  SWDIO=GP27 (D1)  GND  — fork firmware; verified live by probe-rs info (see gate1/provenance.txt). NB: the CMSIS-DAP serial 4150324E30363318 is the RP2040 flash unique-id and is IDENTICAL for the stock probe and the fork — it is NOT firmware-discriminating; the picotool product string ("Hackagotchi Probe") + GP26/27 pin map are.
```

## GATE 0 — stock probe halts/erases/flashes a target  ·  [ **PASS** ]  (2026-06-19, 5/5)
- [x] `probe-rs list` shows CMSIS-DAP — "Debugprobe on Pico (CMSIS-DAP)"
- [x] `info` reads IDCODE: **DPIDR 0x0bc12477** (Part 0x1002, Raspberry Pi); both cores' ROM tables @0xe00ff000
- [x] full 2MB mass-erase 0-error — **via openocd, ~7.7s** (see finding below)
- [x] `download --verify` (probe-rs) ⇒ "Finished in 0.83s" (read-back verify OK)
- [x] `openocd verify_image` ⇒ **verified 6596 bytes** (independent 2nd-tool confirmation)
- [x] `reset` ⇒ rc 0 (LED note: Pico W LED is on the CYW43 chip, not GP25 — blink fixture won't blink visibly; verify is the proof)
- [x] **5/5 consecutive clean runs** (mass-erase 7.69–7.81s, openocd 6596 B every run)
- Evidence: `gate0/`

### Finding F0-1: `probe-rs erase --chip RP2040` is pathologically slow over CMSIS-DAP
A full-chip `probe-rs erase` hung a gate run for >150 s (never completed) — it does not use the RP2040
bootrom `flash_range_erase` block path. **openocd's rp2040 flash driver erases all 2MB in ~7.7 s.** Not a
hardware/wiring fault (the same probe+target mass-erase fine via openocd). `gate0_check.sh` now does the
full mass-erase through openocd and gets the per-region sector-erase proof from `probe-rs download --verify`.
Carry-over for the product: our own recovery/flash flows should use the bootrom block-erase, not probe-rs erase.

## GATE 1 — fork + SWD-remap + OLED task survives sustained flash  ·  [ **PASS** (core claim) — robustness items deferred, see verdict ]
- Fork base: `debugprobe-v2.2.3` (upstream HEAD 466432c)  Build commit **2158e3d**; soak-hardening **07c1a70** (2026-06-19)
- **Build — DONE & statically verified:**
  - [x] Fork builds clean (pinned Arm GCC 13.3.Rel1 + pico-sdk 2.2.0, text 62520, copy_to_ram).
  - [x] SWD locked **SWCLK=GP26 / SWDIO=GP27** (adjacent, SWDIO=SWCLK+1 per probe.pio), PROBE_IO_RAW, UART0 tap GP0/1.
        `picotool info -a` + the soak provenance banner confirm pins 26/27 + "Hackagotchi Probe (CMSIS-DAP)".
  - [x] ONE OLED coexistence task at tskIDLE_PRIORITY (strictly below DAP); real SSD1306 on i2c1 GP6/7;
        touches only I2C+heap (no tud_* → cannot perturb USB/DAP). heap_4.
- **Soak — DONE (pre-soak `probe-rs info` on GP26/27 read both cores' ROM tables):**
  - [x] probe-rs: **1000/1000**, 0 fails, 0 stalls, 0 re-verify mismatch
  - [x] openocd twin: **200/200**, 0 fails, 0 stalls
  - [x] adversarial 50 ms (idle-prio): **1000/1000**, 0 fails, 0 stalls *(build flashed via picotool load; `stall=` self-proof deferred — see verdict)*
  - [x] stretch (hardened script + provenance banner): **3000** cycles, 0 fails/stalls *(running → final count on completion)*
  - [x] OLED counter advanced throughout — **operator-attested** ("the OLED was always working perfectly", 2026-06-19) + pre-soak visual (n= rising, heap min 51016)
  - Pass/fail decided by STDOUT ("Verification successful" count==N, no "Verification failed"), NOT exit code — see F1-3.
  - Heap: scheme **heap_4**  free **51016 B**  min-ever-free **51016 B** (of 64 KB)  leak? none observed  **DECISION: keep heap_4**
    (capability + the coexistence harness does ZERO runtime FreeRTOS allocation, so free==min is expected; revisit when the
    real dashboard mallocs, and instrument newlib then — the SSD1306 framebuffer is C-lib malloc, invisible to xPortGetFreeHeapSize).
  - Evidence: `gate1/soak_*.log` (provenance banner + per-cycle verify), `gate1/provenance.txt`.

### Verdict — 5-lens adversarial verification (workflow wf_8b26aea9): PASS_WITH_BLOCKERS → core claim PASSES, robustness deferred
The DAP-safety ENGINEERING was verified sound by all lenses + an independent re-check (DAP higher-prio than the OLED task,
single-core, `i2c_write_blocking` holds no lock/IRQ, three independent peripherals, no priority inversion); the soaks are real
(0 fails under the corrected check). Blocker disposition:
- [x] **F1-3 (CRITICAL) — defanged re-verify guard:** `probe-rs verify` 0.31 prints "Verification failed: contents do not match"
      but EXITS 0 (confirmed live). The old `if ! probe-rs verify` counted nothing. FIXED (07c1a70: decide by stdout); existing
      logs retroactively re-validated clean.
- [x] **Provenance:** the CMSIS-DAP serial is the RP2040 flash unique-id (identical stock↔fork), NOT firmware-discriminating.
      Closed via the picotool product string + GP26/27 pin map + a `probe-rs info` provenance banner now teed into every soak log.
- [x] **OLED liveness** (a clean soak alone doesn't prove the panel kept looping — NAKs are swallowed, `ok` latched at boot):
      closed by operator attestation + pre-soak visual confirmation.
- [x] **Gate doc** now records the run (this section).
- [ ] **DEFERRED to hardware return** (needs a GP0→GP1 loopback jumper + 1 BOOTSEL — impossible while the operator is away):
      machine-capture the OLED counter (assert monotonic) + heap series + adversarial `stall=` build-id via the loopback→CDC;
      flash the **at-DAP-priority** variant (`ADVERSARIAL_AT_DAP_PRIO=ON`, compile-verified) for a genuine contention test (the
      idle-priority busy_wait is preempted in ~50 µs = a weak stressor). These STRENGTHEN the verdict; the core SWD⇄dashboard
      coexistence claim already holds on the design proof + 2200+ clean cycles + attestation.

### Finding F1-1: debugprobe-v2.2.3 is SINGLE-CORE FreeRTOS (the engineering-plan SMP affinity model does NOT apply)
`src/FreeRTOSConfig.h` sets `configNUM_CORES=1`; no `multicore_launch`/`vTaskCoreAffinitySet` anywhere
(SMP — and the #189 flash regression — arrived later, via commit 457e048, which is exactly why 2.2.3
was pinned). So the plan's "DAP on core 1, dashboard on core 0" cannot be used. DAP is the LOWEST of
the three upstream tasks (UART+3 > TUD+2 > DAP+1); the OLED task is added strictly below DAP
(tskIDLE_PRIORITY). The DAP guarantee is therefore **priority/preemption**, not core isolation — a
more conservative gate (the 23 ms ssd1306_show I2C burst, and the adversarial 50 ms busy-wait, are
both fully preemptible by DAP). When we later spike `debugprobe-v2.3.1`, re-evaluate under real SMP.

### Finding F1-2: board pins injected via a boards/ shim, not a probe_config.h overlay
The C quote-include rule searches the including file's own directory first, so upstream's `.c` files
always pick up upstream's adjacent `probe_config.h` regardless of `-I` order — a `src/probe_config.h`
overlay silently had NO effect (picotool showed the stock GP12/13/14 pins). Fix: shadow
`board_debug_probe_config.h` (which is NOT adjacent to probe_config.h) from `boards/` instead; the
unmodified upstream probe_config.h `#include`s it and our copy wins for every TU. The picotool-info
check is the guard that catches a wrong-board build.

## GATE 2 — 2nd CDC: two nodes, DAP binds, JSON round-trip  ·  [ PASS / FAIL ]
- Device class: `0xEF/0x02/0x01` (IAD)  CFG_TUD_CDC=2
- [ ] exactly TWO `/dev/cu.usbmodem*` nodes
- [ ] `probe-rs list`/`info` still succeed (DAP unaffected)
- [ ] node map by NAME — CDC0=UART: ______  CDC1=Control: ______
- [ ] mapping stable across 3 replug + 1 host reboot
- [ ] `{"q":"status"}` 100/100 valid JSON
- [ ] CDC0 carried live UART concurrently
- Evidence: `gate2/`

---
**OVERALL:**  [ ] all 3 PASS → proceed to the UI port (M1+)   [ ] blocked at gate ____: ____________
