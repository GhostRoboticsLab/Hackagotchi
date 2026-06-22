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
- [x] **Gate 1 — deferred robustness** — **CLOSED** *(2026-06-20, GATE_RESULTS Close-out wf_96721d04)*:
  at-DAP-priority genuine contention machine-captured (`prio=1`, `stall_us≈50000`, dashboard `n`
  307→2189, 0 fails); the gate doc is upgraded to unconditional PASS for the contention claim.
- [x] **Gate 2 core** — **PASS** *(2026-06-20)*: 2nd CDC (IAD `0xEF/0x02/0x01`), DAP still binds,
  `gate2_cdc.py` round-trip 100/100, exactly two nodes.
- [~] **Gate 2 deferrals (M5)** — tooling built + (b) firmware-proven: `gate2_cdc.py --live-uart` PASS
  (CDC0 UART loopback 0-drop + CDC1 answered + 0 stalls concurrent with a DAP soak); `--replug-rounds`
  added for (a). Pending the operator bench run: (a) physical 3× replug + 1 reboot, and a (b) re-run on a
  power-cycled target so the flash also completes clean. See `docs/release-readiness.md`.

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
  - [x] **SD-write-during-flash coexistence soak** (heavy R1 proof) — **DONE (recorder PASS; DAP caveat
    documented)** *(2026-06-20)*: device-side load generator (`{"q":"recgen_on"}`, ~33 `f_sync`/s) so the
    host only runs probe-rs (isolates SD-vs-DAP from host USB contention). 300 cycles: recorder FLAWLESS
    (err=0, logging=1, wedge=0, rec_drop=0, 761 KB written, content intact). DAP: 6/600 vs 0/600
    standalone — ~1 % retryable (0-stall) USB-transfer errors from background SD-DMA bus contention, ONLY
    under continuous-max-SD overlap that the real flow avoids (flashing halts the target → its UART/
    recording pauses). M3+ mitigation noted (defer SD flush during DAP flash). See `tests/m2/coexist_soak.py`
    + M2_RESULTS.md.
- [x] **M2 SD + black-box logging — COMPLETE** *(2026-06-20)*: SD gate · recorder core (host 31/31) ·
  HW wiring · RAM-headroom (copy_to_ram→XIP, +139 KB) · PCF8563 RTC wall-clock stamps · coexistence soak.
- [x] **M3 core screens — COMPLETE** *(2026-06-21)* (`firmware/c/tests/m3/M3_RESULTS.md`). Design of record =
  `m3-design` workflow; closed by `m3-closeout-audit` (COMPLETE-WITH-NITS, all silent-passes fixed). The probe
  is a reactive Tamagotchi-style dashboard (cat + 6 screens + buzzer/NeoPixel event feedback) that stays
  R1-clean while flashing targets. Future graphics rewrite plan: `docs/hackagotchiUI_upgrade_v1.1.md`.
  - [x] **M3.0 HW-reconciliation + snapshot boundary** — **PASS, HIL-verified** *(2026-06-20)*:
    `src/feedback.{c,h}` + `src/ws2812.pio` (non-blocking buzzer GP29 + **WS2812 NeoPixel** GP12/GP11
    status LED via PIO/pio1, serviced off the hot path) + `{"q":"beep"}`/`{"q":"led"}`/`{"q":"pixel"}`.
    Buzzer PASS; **NeoPixel PASS** (RED/GREEN/BLUE/WHITE all correct). **Finding M3-1:** the onboard RGB
    GP17/16 is an unreliable status channel (color ≠ nominal + competes w/ the GP25 USB-heartbeat) → use
    the NeoPixel. No button (GP27=SWDIO) → input is auto-cycle + CDC1; external buttons/LEDs later. Published
    `rec_snapshot_t` (single-writer seqlock, SD task) + `dash_get_rec_snapshot()` + `recorder_copy_tail()`
    + cached RTC; **fixed the pre-existing `{"q":"rec"}` cross-task race** (live `g_rec.filename` pointer +
    off-task `hw->sd_mounted()`). Gates: DAP binds, `{"q":"rec"}`×80 0 torn, **coexist soak 0/400 + rec_drop=0**.
  - [x] **M3.1 screen framework + first screen** — **PASS, HIL-verified** *(2026-06-21)*: multi-screen
    renderer (screen table + reader-clamped index, auto-cycle 6s + CDC1 `next`/`prev`/`{"q":"screen","n"}`).
    Screen fns emit a TEXT MODEL drawn to the OLED AND published for **self-attestation** (`{"q":"screen"}`
    returns the exact rendered text + a **show-success counter distinct from the loop counter** so a dark
    panel can't pass). Screens: PROBE/home + RECORDER (snapshot-fed). `screen_hil.py` PASS (nav, auto-cycle,
    OOB clamp no-hardfault, shows==loops climbing); operator confirmed both screens cycling; R1 re-soak 0/0.
  - [x] **M3.2 full feasible screen family + cat** — **PASS, HIL-verified** *(2026-06-21)*: 6 screens —
    HOME/mascot (the **cat** ported pixel-for-pixel: idle/blink/sleep+Z / active eyes+mouth+bubble+particles
    / yawn) · SNIFFER (live UART tail) · RECORDER · THROUGHPUT (sparkline) · WATCHDOG (freeze-frame) · CLOCK
    — all snapshot-fed (no direct g_rec/freeze/RTC from DASH). `screen_hil.py` PASS + live-data run (cat
    active, sniffer streaming, throughput 2.9K/s); operator confirmed render; R1 re-soak 120cyc 0/0 rec_drop=0.
    Dropped (pin conflict): scope/PWM/logic/I2C-scan. Deferred M4: macro/baud/SD-explorer, hex-sniffer.
  - [x] **M3.3 event feedback + closeout** — **PASS, HIL-verified** *(2026-06-21)*: `drive_feedback()` in
    sd_gate.c maps recorder events (wedge→alarm+red, SD-fault→buzz+red, trigger-hit→blip, recovery→chirp+
    green, boot chirp) to the buzzer + NeoPixel, edge-detected, off the hot path. `feedback_hil.py` asserts
    the HAL layer via `{"q":"fb"}` (beep count + colour). **Adversarial closeout audit** (`m3-closeout-audit`)
    = COMPLETE-WITH-NITS; fixed every silent-pass: show-counter now ACK-gated (ssd1306_show returns I2C
    status); `{"q":"time"}`/`{"q":"settime"}` rerouted off the above-DAP TUD task (snapshot read + SD-task
    apply); filename check de-tautologised; auto-cycle test hardened. probe-active DEFERRED with a recipe.
    Final coexist R1 soak 0/0 rec_drop=0.
- [x] **Post-M3: drop RTC, I2C1 → FM+ 1 MHz single-owner, remove the bus mutex** — **PASS, HIL-verified**
    *(2026-06-21)*: per user, the product needs no wall-clock. Deleting the PCF8563 left the OLED the sole
    I2C1 device (dashboard-only), so the mutex + `i2c1_bus_lock/unlock` + `{"q":"time"}`/`{"q":"settime"}`
    are gone; `rtc_read=NULL` → recorder stamps uptime (`+Ns`); screen 5 CLOCK→UPTIME; I2C1 at 1 MHz.
    `screen_hil`/`feedback_hil` PASS (shows==loops at 1 MHz), coexist R1 = 0 stalls/300 ops, OLED visually
    crisp at FM+. Simplifies the OLED path ahead of M4. See M3_RESULTS.md "Post-M3 simplification".
- [x] **M4 full UI parity** — **COMPLETE, HIL-verified** *(2026-06-21, commits 792b84f..00dcaa4)*: hex
    sniffer · macro sender · baud select · SD explorer · settings persistence — all CDC1-driven + snapshot-
    fed (no button), tool screens excluded from auto-cycle, config persisted to config.txt on SD. Adversarial
    closeout (SPSC inject/baud/open-log read confirmed safe; fixed a do_ls_read OOB on a long filename,
    restored the soak's hard 8% ceiling, disclosed a benign hg_config torn-read). R1: 0 stalls every soak;
    retryable DAP-fail rate ~1%->~4% idle-host (XIP-layout, accepted "don't gold-plate"). See M4_RESULTS.md.
    Confirmatory clean soak (both boards power-cycled): PROBE PASS — 0 stalls, flash succeeded every cycle;
    the 13/300 (4.3%) are retryable host/USB hiccups, not flash-fails or probe faults. Recorder flawless.
    Finding: this target board re-glitches its QSPI under sustained hammering (power-cycle between long runs);
    orthogonal to the probe firmware (0 stalls every run).
- [~] **M5 polish + tagged release** (.uf2 + .elf) — IN PROGRESS *(2026-06-21)*: version compiled in
  (`{"q":"status"}` `ver`), licensing/NOTICE bundle + SPDX, CHANGELOG, `docs/release-readiness.md`
  evidence index, CI ships NOTICE/LICENSE. "CI green" = the AUTOMATED checks CI can run (build +
  `analyze.sh` static analysis); the HIL gates are operator-attested on the release image (CI cannot run
  hardware). Remaining: README/CONTRIBUTING upgrade, the operator Gate-2 bench run, then `git push` + dispatch.
- [ ] **Raise the reliability stack further** over time (per user) — more host tests, HIL CI,
  tighter analyzers, RTT observability.

## Next — post-v1.0 backlog (ranked, 2026-06-22)

Prioritised from a survey→propose→rank pass over the current tree (value / effort / R1-risk / fit). Item
**#1 (host-tests CI) is DONE** — see Housekeeping above. The rest, best-first:

- [~] **(2) DAP transfer/health telemetry in `{"q":"status"}`** — value HIGH / effort S / risk MED *(touches the DAP path → re-gate before shipping)*.
  A monotonic `dap_xfers` + a coarse last-active stamp, giving the headline "0 stalls" invariant a
  firmware-side witness so every soak is self-cross-checkable (xfers advanced by the expected count).
  - [x] **Implemented on branch `feat/dap-health-telemetry`** *(2026-06-22, commit 5183048)*, **desk-verified
    only**. NOTE — the TODO's "++ in our overlay `main.c`" premise was wrong: with `THREADED=1` the active
    DAP path is upstream `tusb_edpt_handler.c::dap_thread` calling `DAP_ExecuteCommand`, not the dead
    `while(!THREADED)` loop. Wired instead via `-Wl,--wrap=DAP_ExecuteCommand` → `__wrap_DAP_ExecuteCommand`
    in a new owned `src/dap_health.{c,h}` (counters single-writer/lock-free; non-blocking `++` + `time_us_32`).
    This keeps the upstream re-diff surface at **zero** (no `tusb_edpt_handler.c` shadow → clean for the #8
    v2.3.1 spike). Surfaced in `write_status()` (`dap_xfers`/`dap_idle_ms`; buffer 256→320) + host CLI.
    Builds clean, `analyze.sh` PASS (`dap_health.c`+`cdc1_control.c` 0/0), disasm confirms `dap_thread→__wrap→real`.
  - [ ] **GATE before merge to main (needs the bench):** `gate1_soak.sh 1000` (0 fails + 0 stalls) +
    `coexist_soak.py 300` (0 stalls AND unchanged retryable rate), cross-checking that `dap_xfers` advanced
    by ~the soak's transfer count. Runs AT DAP priority — do not merge until green.
  - [ ] Follow-up (nobody proposed it): a companion `dap_retries` counter + a soak that ASSERTS the retryable
    rate stays under the documented ceiling — turns the central carried caveat into a guarded bound.
- [ ] **(3) BOM + narrative build/flash guide** — value HIGH / effort M / risk low *(pure docs)*.
  `docs/build-a-hackagotchi.md`: a real Bill of Materials (XIAO RP2040, expansion board, SSD1306 OLED,
  microSD, passive buzzer, WS2812, SWD/UART jumpers, filament — with qty/links/approx cost), a step-by-step
  assembly procedure, the consolidated pin map, and an **as-shipped vs case-docs reconciliation** callout:
  the case docs (`case/HACKAGOTCHI_CASE.md`, `CAT_ENCLOSURE_SPEC.md`) still enclose the *dropped* PCF8563 RTC
  + CR1220 coin cell + user button, GP27 became SWDIO, and the `.scad` models no cutout for the NeoPixel the
  firmware drives. This is the single biggest *physical*-reproducibility blocker today.
- [ ] **(4) Close Gate 2 deferral (a) — node-map stability** — value MED / effort S / risk low *(needs bench)*.
  The only genuinely-incomplete gate item in the tree (every other verdict is PASS; this one has had just one
  incidental cycle effectively pass). Tooling already exists: run `tests/gates/gate2_cdc.py --replug-rounds 4`
  (3× operator replug + 1 reboot, re-discover the control port by behaviour each time), record the verdict in
  `GATE_RESULTS.md` + `release-readiness.md`. Cheapest un-attested→attested conversion available.
- [~] **(5) Cut a tagged v1.1** for the shipped-but-unreleased M-UI overhaul — value HIGH / effort M / risk low.
  The Spectre ghost + sprite engine is the README's headline ("a debug probe with a soul"), but the only
  downloadable release (v1.0) predates ALL of it — anyone flashing the latest release gets a product that
  doesn't match the README.
  - [x] **Desk half DONE** *(2026-06-22)*: CHANGELOG `[Unreleased]` → `[1.1] - 2026-06-22` (marked
    candidate, pending HIL+publish), `docs/RELEASE_NOTES_v1.1.md` written, README doc fixes folded in
    (`{"q":"fb"}` added; `{"q":"ghost"}` no-arg auto-reset documented). **Candidate built + gated:**
    `VERSION=1.1.0 BUILD_DIR=/tmp/hg-v110 ./build_fork.sh` → text 173876 / bss 84304; `analyze.sh` PASS
    (pristine `hackagotchi_dashboard.c`/`cdc1_control.c` 0/0); `.elf` self-reports `1.1.0`.
  - [ ] **Bench half (operator)**: flash the candidate, re-attest the relevant HIL (the M-UI surfaces —
    `m3/screen_hil`, `m3/feedback_hil`, `m4/*`, plus `{"q":"fb"}`/`{"q":"ghost"}` behaviour) + a Gate-1
    0-stall re-soak, record in `release-readiness.md`, then tag **`v1.1`** at the release commit and
    publish (build with `VERSION=1.1.0` for the byte-identical `.uf2`). Plan the tag deliberately — GitHub
    immutable-releases permanently burns a tag name once a release uses it (it already forced v1.0.0 → v1.0);
    drop the "candidate" line from the CHANGELOG v1.1 entry on publish.
  - [ ] *Optional hardening:* a `verify-release.sh` that rebuilds from the tag and diffs the `.uf2` sha256
    against the published artifact (the "byte-identical rebuild" claim is currently unscripted).
- [ ] **(6) Host-CLI convenience wrappers + packaging** — value MED / effort M / risk low *(host-only, can't touch R1)*.
  `host/hackagotchi_ctl.py` wraps only ~6 of ~30 CDC1 verbs. Add thin subcommands for the high-value ones that
  today require hand-echoing JSON: `bootsel` (THE documented hands-free reflash path — handle the no-reply
  re-enumeration), `baud`, `sd ls/cat`, `lastfault`/`dump`, `macro`. Ship a pinned `requirements.txt`
  (pyserial, Pillow) + a venv bootstrap + `host/README.md` — every doc says `.venv/bin/python` but nothing
  creates it (guaranteed first-command stumble for a new contributor).
- [ ] **(7) Recorder lifecycle + SD housekeeping over CDC1** — value MED / effort M / risk low.
  `rec_start`/`rec_stop`/`rec_rotate`, `rm` by index, `rec_reset` (zero `rec_drop`/`faults`/`revived`), all via
  the established async-post-to-single-owner-SD-task pattern (structurally off the DAP path), reflected through
  `rec_snapshot_t` so the recorder screen updates live. "SD full" is a reachable, already-surfaced state with
  no way to act on it today (you must pull the card). Also adds the missing `{"q":"fb"}` to the README table.
- [ ] **(8) Spike debugprobe-v2.3.1 (post-#189 fix) through Gate 1** — value MED / effort L / risk MED *(needs bench)*.
  The project's own documented next upstream step (Risk R10 / `upstream-strategy.md` §1) and biggest
  anti-fossilisation lever; Gate 1 passing was the precondition, now met. Re-diff only the 3 shadowed overlay
  files (`main.c`/`cdc_uart.c`/`usb_descriptors.c`) against the new base, build to a separate `BUILD_DIR`, run
  `gate1_soak.sh >=1000` reading the authoritative 0-stall verdict line, write a falsifiable rebase-or-stay
  verdict. Don't rebase the product unless 0 stalls. Fold in the 5-minute fix: an `engineering-plan §4.1`
  "SUPERSEDED — single-core, see Finding F1-1" banner so the stale SMP/dual-core text stops misleading the
  future rebaser.

Minor doc-debt, worth a line when working nearby: (a) document WHY `main.c:243 tud_hid_get_report_cb` is
intentionally a no-op (the only genuine code TODO in the tree — the active DAP path is vendor/bulk and
`set_report` IS wired), so it stops reading as unfinished work; (b) a one-paragraph "where the plan of record
lives" pointer (engineering-plan = plan of record, this file = live checklist, CHANGELOG = shipped) to ease
onboarding given there's no single `ROADMAP.md`.

## Upstream (see `docs/upstream-strategy.md`)
- [ ] Track official **debugprobe stable tags**; after Gate 1 is green on v2.2.3, spike `v2.3.1`
  through the soak and rebase the overlay if it passes.
- [ ] Cherry-pick from yapicoprobe (verify license + add tests): **MSC drag-n-drop UF2 flash**,
  **RTT-into-CDC** (both HIGH, post-Gate-2).
- [ ] **Contribute upstream:** fix yapicoprobe **#197** (build broken on modern GCC) as a first
  PR; propose an umbrella LICENSE; pursue the co-maintainer path.

## Housekeeping
- [x] **LICENSE chosen** *(2026-06-20)*: project GPL-3.0-or-later (root `LICENSE`); the `firmware/c/`
  subtree MIT (`firmware/c/LICENSE`). Third-party deps (all permissive MIT/BSD-3/Apache) attributed in
  both `THIRD-PARTY-NOTICES.md`; SPDX tags on first-party sources.
- [ ] Vendor `sdcard.py` into `firmware/micropython/lib/` (currently a noted gap).
- [x] **Org remote** set: `git@github.com:GhostRoboticsLab/Hackagotchi.git`.
- [x] CI/CD: `.github/workflows/firmware-c.yml` — manual-dispatch build (setup.sh + build_fork.sh,
  pinned Arm GCC 13.3 via the self-hosted runner's fw-build cache) + the `analyze.sh` static-analysis
  gate + .uf2/.elf artifacts + optional Release (`engineering-plan.md` §7). *Untested until the org
  remote + a workflow run exist.*
- [x] **Host-tests CI job** *(2026-06-22)*: `.github/workflows/host-tests.yml` — GitHub-HOSTED
  (ubuntu-latest), push/PR, compiles + runs the three portable unit tests (`ring_test`, `recorder_test`,
  `blit_test`) with plain `cc`, and each test's verify-the-verifier break build (asserts the harness can
  FAIL). The repo's first community-runnable green check; the badge now means "portable logic verified per
  PR", not just "it builds". Done as plain `cc` rather than the originally-planned Ceedling — same coverage,
  no extra dep. (This is item #1 of the post-v1.0 backlog below.)
