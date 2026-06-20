# M2 — SD + black-box logging: results

The milestone after M1. M2 reuses M1's spine — the SD recorder is a low-priority task that drains the
same `spsc_ring` the IRQ-driven UART bridge fills (M1 built the producer; M2 builds the consumer +
persistence). Gates-first, same discipline as M0/M1 (`../m1/M1_RESULTS.md`, `docs/mcu-bringup-playbook.md`).

Architecture decision (from the `m2-design` research): the SPSC ring allows ONE consumer and `cdc_task`
(high-prio) is it; the SD writer must be low-prio (blocking `f_write`). One task can't be both → **two
rings**: `cdc_task` drains ring1 (lossless, high-prio) → CDC0 + pushes to ring2; the low-prio recorder
drains ring2 → SD. `last_rx` stamped by the high-prio drain (a lagging SD task can't fake a wedge).
Under load, only the lowest sink (SD) drops, counted — capture + host bridge unaffected.

---

## Increment 1 — SD bring-up gate (carlk3 FatFs mount/write/read-back) — **PASS (live, 2026-06-20)**

**Falsifiable claim.** A real microSD on SPI0 (SCK=GP2, MOSI=GP3, MISO=GP4, CS=GP28) mounts via carlk3
FatFs, a written file reads back byte-identical, and free space is reported — all from a LOW-priority
task off the DAP/USB hot path, with DAP and the M1 reliability core unaffected.

**Rig.** XIAO RP2040 probe + a microSD card in the expansion-board slot (user-confirmed). carlk3
`no-OS-FatFS-SD-SDIO-SPI-RPi-Pico` @ v3.6.2 (Apache-2.0; wraps ChaN FatFs R0.15), fetched by `setup.sh`
into gitignored `upstream/` (debugprobe pattern), `add_subdirectory`'d, our `src/sd/hw_config.c` owns
the pin map (12 MHz, mode 0). Flashed hands-free via `{"q":"bootsel"}`.

**Implementation.**
- `src/sd/hw_config.c` — the SD pin lock (SPI0, GP2/3/4/CS28), static ownership (no MicroPython-style
  runtime re-mux). `src/sd_gate.c/.h` — a LOW-priority (idle+0, below DAP) task that runs the bring-up
  self-test once at boot (`f_mount` → write → read-back+compare → `f_getfree`) and stashes the result;
  CDC1 `{"q":"sd"}` reports it. All FatFs/SPI I/O happens HERE, never on the hot path (R1).
- CMake: `add_subdirectory` the lib, then `list(FILTER ... EXCLUDE crash.c)` on its `INTERFACE_SOURCES`
  — carlk3's `crash.c` defines its OWN `isr_hardfault` (collides with M1's `src/crash_box.c`) and parks
  a buffer in `.uninitialized_data`; we keep OUR crash box. The SDIO sources stay compiled (sd_card.c
  hard-references `sd_sdio_ctor`) but are unused (SPI path).
- `src/FreeRTOSConfig.h` — a minimal `#include_next` overlay shrinking the over-provisioned heap
  64 KB → 44 KB (actual task-stack use ~23 KB). FatFs adds ~99 KB of text (mostly LFN unicode tables)
  to the `copy_to_ram` image; the heap trim reclaims the SRAM. Final RAM 245/264 KB (93%).

**Result (live, m2 image).**
```
{"q":"sd"} -> {"sd":1,"done":1,"write":1,"readback":1,"bytes":25,"free_kb":15539848,"fr":0}
```
Mounted ✓, wrote 25 B ✓, read back byte-identical ✓, ~15.5 GB free (16 GB FAT32 card) ✓, FR_OK.
DAP still binds (`Hackagotchi Probe (CMSIS-DAP)`); M1 regression all green on this image (jsmn control,
crash box hardfault+mallocfail on the 44 KB heap, watchdog wedge); SD re-mounts cleanly after reboots.

**Disclosed (not blockers).**
- The SD↔DAP **coexistence soak** (continuous `f_write` *during* a target-flash loop — the real R1
  proof) is increment-3 work (the recorder); this gate's write is one-shot at boot. DAP binding with
  the SD task present is basic coexistence only.
- **RAM is at 93%** under `copy_to_ram`. The M2 recorder (ring2 + buffers) needs headroom →
  `FF_USE_LFN=0` (our names are 8.3: `log_NNN.txt`) drops the unicode tables and is the lever.
- SD task stack is 1024 words; if the recorder workload needs more, bump it (the M1 stack-overflow
  hook → crash box catches an overflow). Baud is a conservative 12 MHz (raise after signal-integrity
  validation per carlk3's HF-radio warning).

**Verdict: PASS** — the SD hardware works as the plan claimed, FatFs integrates into the overlay build,
and the foundational persistence layer is proven at rank-1.

---

## Increment 2 — recorder core (host-tested) — **PASS (host, 2026-06-20)**

**Falsifiable claim.** The black-box recorder state machine — ported from `firmware/micropython/main.py`
— is correct: session-numbered filenames, buffered flush, the **visible-stop-on-fault** invariant, the
strict-boundary wedge detector + 96-byte freeze ring, the trigger-term scan, heartbeat, throughput —
all proven on the HOST with mocked hardware (no Pico, no SD, no RTC), time injected so every boundary
is exercised deterministically.

**Implementation** (`src/recorder.{c,h}`): pure logic behind an injected `recorder_hw_t` vtable
(`sd_mounted`/`sd_max_log_index`/`sd_open_append`/`sd_write`/`sd_close`/`sd_last_fault_full`/`rtc_read`/
`alert`). Producer/consumer split (the research's key deviation from the `.py`): `recorder_note_rx()` is
the cheap hot-path liveness stamp; `recorder_feed()` does the per-byte scan + freeze + buffering off the
hot path; `recorder_tick()` is the periodic driver. So a backlogged low-prio consumer can't manufacture
a false wedge (`last_rx` is stamped by the producer). NOT yet wired into the firmware build — that's
increment 3 (it's pure C + host-verified; adding it unused would only cost `copy_to_ram` RAM).

**Machine assertion** (`tests/m2/recorder_test.c`, can fail): in-memory mocks for the vtable, NDEBUG-proof
`CHECK` macro, a `REC_SELFTEST_BREAK` verify-the-verifier build, and the A–J cases.

**Result (host).** `cc -I src ... recorder_test.c recorder.c` → **31 checks, 0 failed**; broken build
exits 1. Cases proven: empty→`log_001.txt`, idx 7→`log_008.txt`, unmounted→start returns false; header
content + immediate flush + uptime stamp; <64 buffered / 500 ms idle-flush / 64-threshold flush; SD-full
vs write-error classification with logging stopping VISIBLY (never silently) + alert; wedge fires at
8001 ms not 8000 (strict `>`), exactly once while silent, clears + RECOVERED on resume; trigger
first-match-break (two terms one line → one hit) + 300 B flood guard; the WEDGE line carries the last 80
freeze bytes; heartbeat at >60 s with rx count; throughput peak; RTC-trusted wall-clock stamp.

**Verdict: PASS** — the recorder logic is rank-1 host-verified; only the hardware wiring remains.

---

## Increment 3 — recorder wired to hardware — **PASS (live, 2026-06-20)**

**Falsifiable claim.** The recorder core, wired to the live UART bridge + carlk3 FatFs, captures target
UART RX to session log files on the SD card, off the DAP hot path, with DAP and the M1 core unaffected —
and the headline black-box behaviours (clean capture, heartbeat, wedge + freeze frame) happen on real
hardware.

**Wiring.**
- **Two rings, race-free.** `cdc_task` (high-prio) drains the M1 primary ring → CDC0 AND tees every
  captured byte into a SECOND SPSC ring (`uart_bridge_tee`), stamping producer-sourced RX liveness
  (`s_rx_last_ms`/`s_rx_ever`). The low-prio SD task is the SOLE consumer of ring2 and SOLE owner of the
  `recorder_t` — no shared-state race, and a backlogged recorder can't fake a wedge (liveness is the
  producer's, passed into `recorder_tick`). The recorder API was refactored to this boundary (folded the
  old `recorder_note_rx` into `recorder_feed`; `recorder_tick(r, now, rx_last_ms, rx_ever)`); host test
  still 31/31.
- **`recorder_hw_t` → carlk3 FatFs** (`src/sd_gate.c`, the single FatFs caller): `sd_max_log_index` via
  `f_findfirst("log_*.txt")`, `sd_open_append` via `FA_OPEN_APPEND`, close-syncs per flush (durable),
  `FR_DENIED` → SD-full. RTC stub returns false (uptime stamp) until M2.4. Auto-starts logging at boot.
- **CDC1**: `{"q":"rec"}` (logging/file/rx/wedge/hits/err/tp_peak/rec_drop/alert) + `{"q":"tail"}` (async:
  the SD task reads the current log tail off the hot path; CDC1 returns it) for on-card content proof.

**A real bug this surfaced + fixed.** The probe routed its OWN stdout to uart0 = GP0 (the bridge TX) via
`stdio_uart_init()` + a Gate-1 `printf("HEAP n=...")` in the dashboard task — injecting the probe's
telemetry onto the **target's RX line** (visible because internal loopback reflects GP0→GP1). Removed
both: the probe must never transmit on the target lines; its telemetry is on CDC1, faults in the crash
box. uart0 stays fully initialised by `cdc_uart_init` (proven: the host→target round-trip still echoes).

**Result (live, m2c image).** Loopback-injected `HELLO-RECORDER-M2-CLEAN-0123456789` →
`{"q":"rec"}` = `rx:35, tp_peak:35, err:0, rec_drop:0`; `{"q":"tail"}` of the on-card file:
```
=== BLACK BOX log_007.txt | start +0s | baud 115200 ===
--- BB +60s rx=0 ---  /  +120s  /  +180s       (heartbeat firing on schedule)
HELLO-RECORDER-M2-CLEAN-0123456789             (clean — no probe chatter)
--- WEDGE +217s last=[HELLO-RECORDER-M2-CLEAN-012345678]   (wedge + freeze frame on >8s silence)
```
Session numbering increments across reboots (007→010 through the M1 crash/watchdog reboots). DAP binds;
M1 regression green (jsmn, crash box hardfault+mallocfail on the 44 KB heap, watchdog). RAM 265.7/270 KB
(98%) under copy_to_ram.

**Verdict: PASS** — the black box records to SD on real hardware: clean capture, heartbeat, wedge +
freeze frame, robust session numbering, DAP coexistence. The probe no longer pollutes the target line.

### Remaining in M2
- The sustained **SD-write-during-flash coexistence soak** (the heavy R1 proof — recorder writing
  continuously while a target is flashed) is the next step; basic coexistence (DAP binds with the
  recorder running + logging) holds.
- RTC timestamps: PCF8563 driver (i2c1, mutex'd with the OLED), `log_stamp`; HIL-confirm 0x51 reg 0x02
  (currently uptime `+Ns`).

---

## RAM-headroom pass — **DONE, HIL-verified (2026-06-20)**

The wired image was 98% of SRAM (265.7/270 KB) — fine at runtime (~24 KB free heap) but no room for M3.
Measured the consumers and trimmed the cheap, low-risk ones (kept `copy_to_ram`; `ff.c` is NOT removed,
only shrunk). NOTE: my earlier `FF_USE_LFN=0` claim was wrong — `ffunicode.c` is only 1.3 KB; the real
weight was inside `ff.c` (exFAT/64-bit-LBA) + the unused SDIO sources.
- **`src/sd/ffconf.h`** (`#include_next` overlay): `FF_FS_EXFAT=0` + `FF_LBA64=0` + `FF_USE_MKFS=0` +
  `FF_USE_EXPAND=0` — we only ever mount existing FAT32 (≤32 GB) cards. **`ff.c` 46.4 → 29.4 KB (−17 KB)**.
- **Dropped the unused SDIO sources** (SPI-only) via a CMake `FILTER /SDIO/` + 2 trivial stubs in
  `src/sd/sdio_stubs.c` (`sd_card.c` hard-references them). **−~11 KB text**.
- **FreeRTOS heap 44 → 34 KB** (`src/FreeRTOSConfig.h`). Runtime free heap 24 → 14 KB (still ample).
- **Result: 265.7 → 235.5 KB = 87% (−30 KB; free SRAM ~4.5 → ~34 KB).** HIL on the trimmed build:
  `{"q":"sd"}` FAT32 mount/write/readback OK (no exFAT), recorder logs cleanly (log_011, rx=32), heap
  13.9 KB free, crash box (hardfault+mallocfail on the 34 KB heap) + watchdog + recorder host test
  (31/31) all green, DAP binds. The `copy_to_ram`-drop (~140 KB, needs SWD re-verification) was the big
  lever held in reserve — **now done, see below**.

---

## copy_to_ram → XIP (the big RAM lever) — **DONE, HIL-verified (2026-06-20)**

Upstream debugprobe defaults to `pico_set_binary_type(... copy_to_ram)` — the whole image is copied into
SRAM at boot, ostensibly for "deterministic SWD timing". But SWCLK is generated by **PIO hardware**
(`probe.pio`), and the SWD servicing hot path (`probe.c`: `probe_write_bits`/`probe_hiz_clocks`/
`probe_wait_idle`) is tiny — it stays warm in the RP2040's 16 KB XIP cache. Hypothesis: XIP matches RAM
throughput, so dropping copy_to_ram is free SRAM. **Confirmed by measurement, not assumed.**

**Change:** `pico_set_binary_type(hackagotchi_probe default)` (one line). No `__not_in_flash_func` pinning
needed (the soak proved it's unnecessary), no upstream files forked — `probe.c`/`sw_dp_pio.c` stay pristine.

**RAM win (measured from section VMAs, both built from the same tree):**

| binary type | SRAM resident | free of 264 KB |
| --- | --- | --- |
| `copy_to_ram` | 229.3 KB | **35 KB** |
| `default` (XIP) | 90.4 KB | **174 KB** |

`.text` (103 KB) + read-only data (39 KB) move to flash; only true `.data` (8 KB) keeps a RAM copy.
**+139 KB free SRAM** for M3. Flash image grows ~1 KB (irrelevant on 2 MB).

**Re-gate under XIP (full matrix, all green):**
- SWD info: target answers (RP2040 DP + ROM table).
- Throughput: 40-cycle soak **56.0 s vs 54.6 s** baseline = **+2.6 %** (within run-to-run noise; most of
  each cycle is host-side probe-rs USB overhead, not SWD transfer).
- **probe-rs soak 1000/1000**, 0 fail / 0 stall (matches the original Gate-1 bar).
- **openocd soak 200/200**, 0 fail / 0 stall (independent host client).
- M2: `{"q":"sd"}` mount/write/readback OK, recorder logging (log_015→019 across reboots), no boot fault.
- Recorder host test **31/31**.
- **Crashbox HIL PASS** — hardfault captured at PC `0x100017dc` (now in **flash** 0x10xx_xxxx, was SRAM
  0x20xx_xxxx — independent proof code genuinely runs from flash) + mallocfail; both survived reboot.
  `crashbox_hil.py` PC-range assertion widened to accept flash OR SRAM (valid for both binary types).
- **Watchdog HIL PASS** — wedged TUD caught, `kind=watchdog/task=TUD`, rebooted + re-enumerated.
- `.uninitialized_data` crash-box survival still works without the copy_to_ram bootrom load (verified).

**Verdict: PASS.** XIP is reliability- and throughput-equivalent to copy_to_ram and frees 139 KB. The
canonical committed build (`pico_set_binary_type default`) was reproduced (90.4 KB resident), reflashed,
and smoke-tested on hardware. M3 starts with ~174 KB free SRAM. The FreeRTOS heap stays 34 KB (measured
~20 KB use) but can now be raised in M3 since SRAM is no longer the constraint.

---

## PCF8563 RTC — wall-clock log stamps — **DONE, HIL-verified (2026-06-20)**

The recorder stamped log entries with the uptime fallback (`+Ns`) because `hw_rtc_read` was a stub.
Implemented the PCF8563 (the Seeed XIAO-expansion RTC at I2C1 0x51) so stamps become real wall-clock
when the clock is trusted.

**Shared-bus discipline (the load-bearing part):** the OLED (0x3C, DASH task) and the RTC (0x51, SD/
recorder task) sit on the SAME I2C1 (GP6/7) but are driven from DIFFERENT FreeRTOS tasks — a data race
on the peripheral. New `src/i2c1_bus.{c,h}` owns the bus: idempotent bring-up + a FreeRTOS mutex, init'd
once in `main()` before the scheduler so the mutex exists before any task locks. Every OLED burst
(`ssd1306_show`/`_init`) and every RTC transaction now holds `i2c1_bus_lock()`.

- **`src/rtc_pcf8563.{c,h}`** — BCD read/set of regs 0x02–0x08, VL (low-voltage) flag handling, per-
  transfer I2C timeouts (a missing/stuck RTC can never hang the SD task), bus-mutexed. `read()` returns
  false (→ uptime fallback) when absent / I2C error / VL set; `set()` writes the clock and clears VL.
- **`hw_rtc_read`** (sd_gate.c) now calls the driver → the recorder's `stamp()` emits wall-clock.
- **CDC1**: `{"q":"time"}` (read), `{"q":"settime","t":"YYYY-MM-DD HH:MM:SS"}` (set) — a generic
  `get_str` jsmn key extractor was added alongside `get_q`.

**HIL (`tests/m2/rtc_hil.py`, on the RTC build):**
- `{"q":"time"}` → `{"rtc":1,"valid":0}` at boot (present at 0x51; VL set on a never-set clock).
- `settime 2026-06-20 21:59:24` → `set:1`; readback `21:59:26` (valid=1, VL cleared, within 2 s).
- after a 3 s wait → `21:59:30` (advanced ~4 s — actually ticking, not a static echo).
- reboot (`{"q":"crash"}`) → the NEW session header reads
  `=== BLACK BOX log_022.txt | start 2026-06-20 21:59:32 | baud 115200 ===` — **wall-clock, not `+0s`**.
- RTC persisted across the reboot (kept ticking); dashboard self-attest `n` keeps advancing (140→152)
  → the OLED task is NOT deadlocked by the shared-bus mutex.

**Verdict: PASS** — real wall-clock timestamps in the black box, with the OLED↔RTC bus race closed.

---

## SD-write-during-flash coexistence soak (heavy R1) — **DONE (recorder PASS; DAP caveat documented), 2026-06-20**

R1 asks: does the low-prio SD task doing continuous `f_write`/`f_sync` corrupt a concurrent DAP flash,
or vice versa? Tested with a DEVICE-SIDE load generator (`{"q":"recgen_on"}` → the SD task synthesizes
~107 B every loop → ~33 `f_sync`/s, continuous SD writes) so the HOST only runs probe-rs — no host CDC0
stream competing with probe-rs on the same USB device.

> **Methodology note / first-attempt failure (recorded so it isn't repeated):** the first harness
> generated SD load by having the HOST inject UART via PL011 loopback. That made the host drive BOTH
> probe-rs (DAP) AND a heavy CDC0 stream → host-side USB contention (528/600 DAP fails) that has nothing
> to do with SD-vs-DAP, and `rx=0` showed the injection never even reached the recorder. It also
> brown-out-glitched the TARGET's QSPI flash (`ID 0x00ffffff`; CPU cores still answered SWD) → needed a
> physical power-cycle to recover. The device-side generator is the correct isolation.

**Recorder side — PASS (flawless).** During the 300-cycle flash soak: `err=0`, `logging=1` (no
VISIBLE-STOP), `wedge=0` (no false wedge), `rec_drop=0`, `rx` 4 410 → 765 380 (**761 KB written to the
card during flashing**), on-card tail shows intact in-order `RECGEN` lines. The low-prio SD-task design
holds: SD writes are completely unaffected by concurrent DAP flashing.

**DAP side — ~1 % retryable, under a synthetic worst-case only.**

| run (300 cycles = 600 ops) | DAP fails | stalls |
| --- | --- | --- |
| standalone (recgen off) | **0** | 0 |
| concurrent (recgen on, ~33 `f_sync`/s) | **6** (cycles 24/106/142/217) | **0** |

So continuous max-rate SD writes *do* add ~1 % DAP failures — but all are **0-stall**: clean, detectable
USB-transfer errors ("Timeout in USB communication", "Transfer count larger than requested",
"Only 1/3 transfers executed") that probe-rs/openocd retry, never a hang. Mechanism: NOT IRQ-blocking
(the carlk3 SPI busy-waits with `tight_loop_contents()`, IRQs on) and NOT high-priority DMA (the driver
sets no DMA bus priority) — it's subtle bus-fabric contention from background SD DMA occasionally adding
latency to the CPU's USB/PIO servicing, tripping probe-rs's tight USB timeout.

**Why this is negligible in practice:** probe-rs/openocd **halt the target core to flash it**, so while a
flash is in progress the target executes nothing and emits no UART → the recorder has no new data →
SD writes quiesce. The real flow therefore never sustains max-SD-writes *during* a flash; the test forces
that overlap artificially (the device-side generator ignores the target's halt state). Even under that
artificial worst-case the failures are rare and auto-retried, and the recorder is untouched.

**Verdict: PASS with a documented caveat.** R1 core proven (recorder flawless under concurrent flash).
The ~1 % retryable DAP effect occurs only under a synthetic continuous-max-SD load that the natural
target-halt prevents. **M3+ mitigation candidate (not implemented — gold-plating given the halt):** have
the probe detect DAP-active and defer recorder SD flushes during a flash (bounded by `REC_LOGBUF_CAP` so
no data loss), which would fully quiesce SD writes during flashing → expected 0/600.

Test: `tests/m2/coexist_soak.py` (device-side recgen + concurrent `gate1_soak.sh`); device-side hook
`{"q":"recgen_on"}`/`{"q":"recgen_off"}` in `src/sd_gate.c`.

---

## M2 — COMPLETE (2026-06-20)
SD bring-up gate ✓ · recorder core (host 31/31) ✓ · wired to HW ✓ · RAM-headroom (copy_to_ram→XIP,
+139 KB) ✓ · PCF8563 RTC wall-clock stamps ✓ · SD-during-flash coexistence soak ✓ (recorder PASS; DAP
caveat documented). Device resting on the full M2 image (XIP + RTC + recgen hook).
