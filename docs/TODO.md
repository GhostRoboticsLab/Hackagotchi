# Hackagotchi — TODO

Working backlog. The plan of record is `docs/engineering-plan.md`; this is the live checklist.

## Now — the 3 gates (gates-first; no OLED port until all pass)
- [x] **Gate 0 (probe half):** bare XIAO flashed with stock `debugprobe_on_pico.uf2` (v2.2.3),
  enumerates as CMSIS-DAP (probe-rs sees it). *(2026-06-19)*
- [x] **Gate 0 (fixtures):** `blink_a.elf` (250ms) + `blink_b.elf` (80ms) built & on disk
  (`fixtures/`, gitignored) via pinned Arm GCC 13.3.Rel1 + existing pico-sdk — NOT system GCC 16.1.
  Full download+verify is ready. *(2026-06-19)*
- [x] **Gate 0 (finish): PASS — 5/5 clean** *(2026-06-19)*. Fresh Pico W target (RP2040 rev B2),
  SWCLK=GP2/SWDIO=GP3/GND. info reads DPIDR 0x0bc12477; full 2MB mass-erase via openocd ~7.7s;
  probe-rs `download --verify` + openocd `verify_image` (6596 B) both confirm. See
  `firmware/c/tests/gates/GATE_RESULTS.md`. **Finding F0-1:** `probe-rs erase` is pathologically slow
  on RP2040 (>150s, doesn't use bootrom block-erase) — gate + our recovery flows use openocd/bootrom.
- [x] **Gate 1 — build half** *(2026-06-19, commit 2158e3d)*: fork built on debugprobe-v2.2.3,
  SWD remapped + **locked** to GP26/GP27 (adjacent), UART0 tap GP0/1, one lowest-prio OLED
  coexistence task on a real SSD1306 (i2c1 GP6/7), **heap_4**. Builds clean (pinned GCC 13.3 +
  pico-sdk 2.2.0); `picotool info` verifies the pin map. Findings F1-1 (v2.2.3 is single-core
  FreeRTOS — no SMP affinity), F1-2 (board injected via boards/ shim, not a probe_config.h overlay).
- [x] **Gate 1 — soak half: PASS (core claim)** *(2026-06-19, commit 07c1a70)*. probe-rs 1000/1000,
  openocd 200/200, adversarial-50ms 1000/1000 (+3000 stretch), all 0 fails/stalls under the corrected
  stdout check; OLED liveness operator-attested; **heap_4 kept**. 5-lens verification = PASS_WITH_BLOCKERS;
  blockers closed (F1-3 verify-guard bug fixed, provenance banner, doc). See GATE_RESULTS.md.
- [ ] **Gate 1 — deferred robustness (on hardware return):** GP0→GP1 loopback to machine-capture the
  OLED counter (monotonic) + heap series + adversarial `stall=` build-id; flash the at-DAP-priority
  variant (`ADVERSARIAL_AT_DAP_PRIO=ON`, compile-verified) for a genuine contention test; then flip
  the gate doc to unconditional PASS.
- [ ] **Gate 2:** add the 2nd CDC (`cdc_dual_ports`, IAD `0xEF/0x02/0x01`); `gate2_cdc.py`
  round-trip 100/100; node mapping stable across 3 replug + 1 reboot.

## After gates pass — build the firmware (engineering-plan M1–M5)
- [x] **M1 probe + bridge + CDC1 control + reliability core** — **COMPLETE / PASS** *(2026-06-20)*,
  HIL-verified end-to-end (`tests/m1/M1_RESULTS.md` OVERALL). Conventions codified in
  `docs/firmware-conventions.md`. Cleared to start M2.
  - [x] **Crash box** (fault handler/crash-box + stack/malloc hooks routed to it) — **PASS, HIL-verified**
    *(2026-06-20)*: `isr_hardfault` overlay captures the M0+ exception frame to `.uninitialized_data`
    (survives the watchdog reboot — verified outside the bss clear), surfaced via CDC1 `{"q":"lastfault"}`;
    `tests/m1/crashbox_hil.py` forces a fault and asserts capture+survival+re-enumeration (0→1).
  - [x] **SW-watchdog task** — **PASS, HIL-verified** *(2026-06-20)*: monitors the high-prio TUD task
    (not a low-prio one — would false-reset mid-flash), records `kind=watchdog/task=TUD` + reboots;
    disarmed by default (HW WDT off until `wd_arm`); `tests/m1/watchdog_hil.py` (arm→wedge→assert).
  - [x] **`{"q":"bootsel"}`** CDC1 command (`reset_usb_boot`) — **PASS, HIL-verified** *(2026-06-20)*:
    dropped to BOOTSEL + reflashed via `picotool` with no button. Dev loop is now hands-free.
    Recovery guarantees documented in `docs/recovery-model.md`.
  - [x] **jsmn parser** (replaces `strstr`) + `next`/`prev`/`dump` — **PASS, HIL-verified** *(2026-06-20)*:
    vendored `src/jsmn.h` (MIT), bounded line buffer, structured `"q"` dispatch; `tests/m1/jsmn_hil.py`
    proves strstr false-positives (`{"q":"statusx"}`, `{"note":"status please"}`) are now rejected +
    fragmented requests reassemble. **Finding F1-4:** a JSON parser's locals overflowed the 1 KB TUD
    task stack (ENXIO on CDC1) — fixed with static buffers + a 512-word TUD stack.
  - [x] **bounded SPSC UART bridge (CDC0) hardening** — **PASS, HIL-verified** *(2026-06-20)*:
    target→host RX is now interrupt-driven into a 4 KB lock-free SPSC ring (`src/spsc_ring.h` +
    `src/uart_bridge.c`), replacing the polling-into-32B that lost bytes between polls. Host unit test
    `tests/m1/ring_test.c` (6/6); HIL `tests/m1/uart_bridge_hil.py` round-trips via PL011 internal
    loopback (no jumper), 0 drops. Telemetry `urx_drop`/`urx_hw`/`utx_drop` in status.
  - [x] per-interface USB string descriptors (already wired in Gate-2; verified) + non-blocking host→target
    TX (replaced uart_write_blocking) + error-code/goto-cleanup idiom codified (`docs/firmware-conventions.md`). *(2026-06-20)*
  - [x] **Watchdog armed-by-default** *(2026-06-20)*: monitors TUD (DAP can't starve it); proven to FIRE on a
    real wedge (`watchdog_hil.py`) and NOT false-fire under 25-flash DAP soak (`watchdog_soak.py`).
- [~] **M2 SD + black-box logging** — IN PROGRESS (`firmware/c/tests/m2/M2_RESULTS.md`).
  - [x] **SD bring-up gate** — **PASS, HIL-verified** *(2026-06-20)*: carlk3 FatFs v3.6.2 (fetched by
    setup.sh) on SPI0 GP2/3/4/CS28, low-prio SD task; `{"q":"sd"}` → mount+write+readback OK on a real
    16 GB FAT32 card; DAP binds, M1 regression green. Heap trimmed 64→44 KB (FreeRTOSConfig overlay) to
    fit FatFs under copy_to_ram. RTC confirmed PCF8563 (not PCF85063A).
  - [x] **recorder core** (`src/recorder.c` + `tests/m2/recorder_test.c`) — **PASS, host-tested** *(2026-06-20)*:
    pure logic behind a `recorder_hw_t` vtable (naming/flush/visible-stop/wedge/triggers/freeze/heartbeat/
    throughput/RTC), 31/31 host checks + verify-the-verifier. Not yet wired to the firmware (increment 3).
  - [x] **wire to HW** — **PASS, HIL-verified** *(2026-06-20)*: 2nd SPSC ring + cdc_task tee + low-prio
    recorder→SD; `{"q":"rec"}`/`{"q":"tail"}`. Clean payload + heartbeat + WEDGE+freeze on the card
    (log_007), session# increments across reboots, DAP intact. Fixed a real bug: probe stdio was on GP0
    (bridge TX) polluting the target line — removed stdio_uart_init + the Gate-1 dashboard printf.
  - [x] **RAM-headroom pass** — **DONE, HIL-verified** *(2026-06-20)*: 98%→87% (−30 KB, free SRAM
    4.5→34 KB). ffconf overlay (exFAT/LBA64/mkfs/expand off → ff.c 46→29 KB) + dropped unused SDIO
    (~11 KB, SPI-only + 2 stubs) + heap 44→34 KB. FatFs/recorder/M1 all verified intact. copy_to_ram kept.
  - [x] **copy_to_ram → XIP (big RAM lever)** — **DONE, HIL-verified** *(2026-06-20)*: dropped
    `copy_to_ram` (one CMake line → `pico_set_binary_type default`); code runs from flash XIP. No
    `__not_in_flash_func` pinning needed (SWCLK is PIO-generated, hot path stays in the 16 KB XIP cache).
    **Free SRAM 35 → 174 KB (+139 KB)** for M3. Full re-gate green: probe-rs 1000/1000 + openocd 200/200
    (0/0), throughput +2.6 % (noise), crash box (PC now in flash 0x10xx) + watchdog HIL pass, M2 SD intact.
    See `tests/m2/M2_RESULTS.md` "copy_to_ram → XIP".
  - [x] **PCF8563 RTC — wall-clock log stamps** — **DONE, HIL-verified** *(2026-06-20)*: PCF8563 @0x51
    on I2C1, new `src/rtc_pcf8563.{c,h}` + `src/i2c1_bus.{c,h}` (shared-bus mutex closing the OLED↔RTC
    race); `hw_rtc_read` wired → recorder stamps wall-clock; CDC1 `{"q":"time"}`/`{"q":"settime"}`.
    `tests/m2/rtc_hil.py`: set→tick→reboot→new session header `start 2026-06-20 21:59:32` (not `+0s`).
  - [~] **SD-write-during-flash coexistence soak** (heavy R1 proof) — IN PROGRESS. First attempt's harness
    was FLAWED: it generated SD load by having the HOST inject via UART loopback, so the host drove BOTH
    probe-rs (DAP) and a heavy CDC0 stream → host-side USB contention (not the SD-vs-DAP thing we want),
    AND `rx=0` showed the injection never reached the recorder. The over-heavy run also brown-out-glitched
    the TARGET's QSPI flash (reads `0x00ffffff`; CPU cores still answer SWD) → needs a physical
    power-cycle. Probe firmware + M2 recorder stayed healthy throughout. REDESIGN: device-side recorder
    load generator (a CDC1 test hook) so the host only runs probe-rs and the SD-write load is internal —
    cleanly isolates "SD writes during flash" from host USB contention.
- [ ] M3 core screens; M4 full UI parity; M5 polish + tagged release (.uf2 + .elf).
- [ ] **Raise the reliability stack further** over time (per user) — more host tests, HIL CI,
  tighter analyzers, RTT observability.

## Upstream (see `docs/upstream-strategy.md`)
- [ ] Track official **debugprobe stable tags**; after Gate 1 is green on v2.2.3, spike `v2.3.1`
  through the soak and rebase the overlay if it passes.
- [ ] Cherry-pick from yapicoprobe (verify license + add tests): **MSC drag-n-drop UF2 flash**,
  **RTT-into-CDC** (both HIGH, post-Gate-2).
- [ ] **Contribute upstream:** fix yapicoprobe **#197** (build broken on modern GCC) as a first
  PR; propose an umbrella LICENSE; pursue the co-maintainer path.

## Housekeeping
- [ ] Add a **LICENSE** (org choice) before any public/commercial release. *(third-party deps documented
  in `firmware/c/THIRD-PARTY-NOTICES.md` — all permissive MIT/BSD-3/Apache; project's own license still TBD.)*
- [ ] Vendor `sdcard.py` into `firmware/micropython/lib/` (currently a noted gap).
- [ ] Add the **org remote** when the URL is provided, then `git push -u origin main`.
- [x] CI/CD: `.github/workflows/firmware-c.yml` — manual-dispatch build (setup.sh + build_fork.sh,
  pinned Arm GCC 13.3 via the self-hosted runner's fw-build cache) + the `analyze.sh` static-analysis
  gate + .uf2/.elf artifacts + optional Release (`engineering-plan.md` §7). *Untested until the org
  remote + a workflow run exist.* TODO: host-test (Ceedling) job after M1 introduces portable logic.
