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
- [ ] M1 probe + bridge + CDC1 control + **reliability core** (fault handler/crash-box,
  SW-watchdog, stack/malloc hooks, error-code+goto-cleanup idiom).
- [ ] M2 SD + black-box logging (carlk3 FatFs, low-prio writer); RTC timestamps.
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
- [ ] Add a **LICENSE** (org choice) before any public/commercial release.
- [ ] Vendor `sdcard.py` into `firmware/micropython/lib/` (currently a noted gap).
- [ ] Add the **org remote** when the URL is provided, then `git push -u origin main`.
- [ ] CI/CD: GitHub Actions firmware build (pinned Arm GCC — note host has GCC 16.1, very new) +
  host-test/analyzer jobs (`engineering-plan.md` §7).
