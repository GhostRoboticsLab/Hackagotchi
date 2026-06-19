# Hackagotchi — TODO

Working backlog. The plan of record is `docs/engineering-plan.md`; this is the live checklist.

## Now — the 3 gates (gates-first; no OLED port until all pass)
- [x] **Gate 0 (probe half):** bare XIAO flashed with stock `debugprobe_on_pico.uf2` (v2.2.3),
  enumerates as CMSIS-DAP (probe-rs sees it). *(2026-06-19)*
- [ ] **Gate 0 (finish):** wire SWCLK/SWDIO/GND to the Pico Inky target; run
  `firmware/c/tests/gates/gate0_check.sh` to completion (info/erase/download --verify/reset +
  openocd cross-check); 5/5 clean. *(blocked on soldering the target's 3-pin SWD header)*
- [ ] **Gate 1:** build the fork (debugprobe v2.2.3) + remap SWD off the SD bus + one low-prio
  core-0 OLED task; `gate1_soak.sh` + `gate1_soak_openocd.sh` (≥1000 cycles, 0 fails/stalls +
  adversarial 50 ms variant); record heap watermark → **decide heap_4 vs heap_1**; **lock the SWD
  pins** in `firmware/c/boards/board_hackagotchi_config.h`.
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
