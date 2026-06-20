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

### Remaining in M2
- Recorder core (`recorder.c` behind a `recorder_hw_t` vtable) + host unit tests (session naming,
  flush, visible-stop, wedge state machine, freeze ring, heartbeat) — pure logic, like `ring_test.c`.
- Wire to hardware: ring2 + `cdc_task` fan-out + the low-prio recorder draining ring2 → SD; CDC1 status
  (`logging`/`log_file`/`wedge`/`hits`). HIL: a real session log appears; SD-write-during-flash soak.
- RTC timestamps: PCF8563 driver (i2c1, mutex'd with the OLED), `log_stamp`; HIL-confirm 0x51 reg 0x02.
