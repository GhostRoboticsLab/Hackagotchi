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

## GATE 1 — fork + SWD-remap + OLED task survives sustained flash  ·  [ **PASS** — at-DAP-priority contention CLOSED at rank-1 (2026-06-20) ]
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
  - [x] stretch (hardened script + provenance banner, on the adversarial-50ms firmware): **3000/3000**, 0 fails/stalls/mismatch — probe healthy after. Cumulative Gate-1 evidence = **5200 clean flash cycles**.
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
- [x] **CLOSED 2026-06-20 on hardware return** (see the at-DAP-priority close-out section below) — the deferred
      machine-capture + genuine contention test are DONE at rank-1; this verdict is upgraded from PASS_WITH_BLOCKERS
      to unconditional PASS for the at-DAP-priority contention claim.

### Close-out 2026-06-20 — at-DAP-priority GENUINE contention, machine-captured (adversarial workflow wf_96721d04)
The 5200 prior cycles were at IDLE priority (DAP preempts in ~50 µs = a weak/tautological stressor) and the running
image was never machine-bound to the soak. Both are now fixed; a re-run adversarial workflow (4 lenses) had flagged exactly
these as a **silent-pass risk** (a stock-image soak would have produced byte-identical evidence) and returned DO-NOT-PASS
until bound — that binding is now done:
- **Genuine contention build, artifact-verified (rank-2):** `build-gate1-adv` with `ADVERSARIAL_AT_DAP_PRIO=ON`
  (DASH task at DAP priority 1 — objdump: `main` `movs r3,#1` before the 3rd `xTaskCreate`, vs `#0` in stock `build/`)
  + `ADVERSARIAL_STALL_MS=50` (objdump: `dashboard_task` loads literal `0xc350`=50000 into `busy_wait_us`; absent in stock).
  FreeRTOS is `configUSE_PREEMPTION=1` + `configUSE_TIME_SLICING=1` @ 50 µs tick, single-core, so a non-yielding 50 ms
  busy_wait at DAP's own priority genuinely round-robins with DAP — NOT the idle-prio tautology.
- **Soak A (provenance-bound, rank-2): 1000/1000, 0 fails / 0 stalls** at at-DAP-priority. Binding: AFTER the soak,
  `picotool verify /tmp/gate1-adv-a75ff0fa.uf2` against the untouched device flash = **OK** (byte-match to the adversarial
  image, sha `a75ff0fa…`), and the control `picotool verify build/…uf2` (stock `45aba69c…`) = **device contents did not
  match** → the soak provably ran the adversarial image, discriminated from stock.
- **Soak B (self-attesting, rank-1): 300/300, 0 fails / 0 stalls** on a rebuilt image that reports its own identity over
  CDC1 (`{"fw","heap","up","n","stall_cfg","stall_us","prio"}`). Captured every 5 s throughout (`gate1_liveness.py`):
  - `prio=1` for all 95 samples → at-DAP-priority build running (provenance from the firmware itself).
  - `stall_us` = 50000–50049 every sample → the 50 ms busy_wait actually FIRED (the +0..49 µs overage IS DAP
    time-slicing the busy_wait — direct evidence of genuine contention, not a number).
  - **`n` 307 → 2189, 0 N-FROZEN events → the DASHBOARD TASK looped continuously DURING the DAP soak** — closes the
    frozen-but-alive gap that CDC1-only/`up`-only liveness could not (CDC1 is serviced by the higher-prio TUD task).
  - `up` monotonic 76→547 s (no reset), heap flat 51016 B, CDC1 answered every poll (USB never wedged).
- **Verdict signal proven FALSIFIABLE (rank-1):** flash A then `probe-rs verify` B → **"Verification failed: contents do
  not match"** (red path fires); matching image → "Verification successful". So 1300/1300 clean is a real result, not a
  no-op count. (Confirms F1-3 live: `verify` prints failed but the script decides by stdout, not exit code.)
- **DAP healthy after both soaks:** `probe-rs info` reads both target cores' ROM tables; final self-attest `n=2199`.
- **Remaining DISCLOSED caveats (not blockers):** (a) heap-flat is near-vacuous — the harness does zero FreeRTOS alloc and
  the SSD1306 framebuffer is C-lib malloc invisible to `xPortGetFreeHeapSize`; revisit at M1 with newlib instrumentation.
  (b) A non-yielding busy_wait is a CPU-hog proxy; it does NOT exercise shared-bus (SD/SPI) or IRQ-latency contention a real
  blocking peripheral would (plan R1 worst case). (c) The SHIP config runs DASH strictly BELOW DAP (prio 0) — this build is a
  conservative UPPER BOUND, so passing it exceeds the product requirement.
- Evidence: `gate1/fullsoak_*.console` + `soak_*.log` (Soak A), `gate1/resoak_*.console` + `resoak_selfattest_*.csv`
  (Soak B), `gate1/provenance_20260620T110945.txt`. Self-attestation added in `src/cdc1_control.c` + `hackagotchi_dashboard.{c,h}`.

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

## GATE 2 — 2nd CDC: two nodes, DAP binds, JSON round-trip  ·  [ **PASS** (core) — 2026-06-20 live hardware ]
- Device class: `0xEF/0x02/0x01` (IAD composite)  CFG_TUD_CDC=2  ·  build commit: see git log
- **Firmware — BUILT & statically verified (no hardware; can't enumerate while operator away):**
  - [x] Builds clean (text 64340); `build/` rebuilt to the Gate-2 image — `nm` shows `tud_cdc_rx_cb`,
        `strings` shows "Hackagotchi UART" + "Hackagotchi Control".
  - [x] Descriptor decoded from the ELF: wTotalLength **164 == sum(bLength) 164**; **5 interfaces**
        (0=DAP-vendor, 1/2=CDC0, 3/4=CDC1); **2 IADs** (firstItf 1 & 3); endpoints
        {0x04,0x85,0x81,0x02,0x83,0x86,0x07,0x88} **no collisions**.
  - [x] DAP integrity: vendor ITF0 + EP 0x04/0x85 byte-identical to upstream, appended-before the
        CDCs, MS-OS-2.0/WinUSB still keyed on ITF0 → probe-rs will still bind. CFG_TUD_VENDOR=1.
  - [x] Fixed a real 2-CDC bug: `cdc_uart.c` line-coding/line-state/send-break callbacks now itf-guard
        to CDC0 (else opening/closing/setting-baud on CDC1 would reprogram/suspend the UART bridge).
  - [x] CAP_BREAK runtime index rewritten to CDC0 (idx 62 = CDC0 ACM bmCapabilities; old relative
        form would land in CDC1).
  - [x] RP2040 DPSRAM budget sufficient (8 EPs ≈ 896 B of 3712 B); +4.2 KB .bss for the 2nd CDC FIFO.
  - 4-lens adversarial workflow (wf_62d07ed1): SOURCE spec-correct; the only NEEDS_FIX was a stale
    `build/` artifact (now rebuilt). Notes deferred to M1: CDC1 uses `strstr("status")` not jsmn
    (fine — gate2_cdc.py sends one clean line); `tud_cdc_n_write` return unchecked (fine for ~50 B).
- **Validation — PASS on LIVE hardware (2026-06-20, attempt 2; `build/hackagotchi_probe.uf2` flashed via `picotool load -x`):**
  - Pre-flash provenance (rank-2, decoded from the staged ELF): pins GP26/27, product "Hackagotchi Probe
    (CMSIS-DAP)", strings "Hackagotchi UART"+"Hackagotchi Control", `tud_cdc_rx_cb` present, reply template
    `{"fw":"Hackagotchi","heap":%u,"up":%u}` — confirmed the 2-CDC image BEFORE flashing.
  - [x] exactly TWO `/dev/cu.usbmodem*` nodes — **usbmodem21202 + usbmodem21204**
  - [x] `probe-rs list` still finds the probe — **"Hackagotchi Probe (CMSIS-DAP)"** — DAP binds WITH both CDCs
        present (re-checked AFTER the 100-cycle round-trip: still bound). [a target-attached `info` IDCODE read
        is the stronger DAP proof — captured on the Gate-1 rig, which wires a real target.]
  - [x] node map by ROLE (behavioral, suffix-independent): **CDC0=UART = usbmodem21202** (silent to `status`),
        **CDC1=Control = usbmodem21204** (answers JSON). macOS does not surface the iInterface strings as BSD
        names (`ioreg` shows both as "usbmodem"), so role is keyed on behavior — more robust than a name string.
  - [x] `{"q":"status"}` → **100/100 valid JSON** (latency avg 0.3 ms / max 0.5 ms). **NEGATIVE CONTROL:** the
        UART node returned 0 replies to the identical request → the round-trip check genuinely discriminates and
        CAN emit FAIL (not a tautology).
  - [x] heap watermark machine-read live: **free=51016 B** in the reply — IDENTICAL to Gate-1's recorded 51016
        (the +4.2 KB 2nd-CDC FIFO is `.bss`/static, NOT on the FreeRTOS heap) → **closes the Gate-1 heap
        re-measure note** at rank-1. (`up=104 s` also confirms the monotonic clock.)
  - [ ] DEFERRED (low-risk; operator opted to skip 2026-06-20): node-map stable across 3 replug + 1 host reboot —
        role is behavioral/suffix-independent so the residual risk is cosmetic; CDC0 carrying live *target* UART —
        no target-UART wire / no loopback jumper this session (the Gate-1 rig is SWD-only).
  - Evidence: `tests/gates/gate2/roundtrip_*.log`

---
**OVERALL (2026-06-20, hardware return):**  Gate 0 ✅ PASS (5/5)  ·  Gate 1 ✅ PASS — at-DAP-priority GENUINE contention closed at rank-1 (1000 cycles provenance-bound by `picotool verify` + 300 self-attesting cycles: dashboard `n` looped 307→2189, `stall_us`≈50000, `prio=1`, 0 fails; heap/representativeness caveats disclosed)  ·  Gate 2 ✅ PASS (core) — 2 nodes + DAP binds + 100/100 JSON live; replug-stability + CDC0-live-UART deferred (low-risk).  **All three gates pass on hardware → cleared to start M1 (UI port).**
