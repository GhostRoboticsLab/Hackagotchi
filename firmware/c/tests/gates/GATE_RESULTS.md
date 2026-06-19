# Hackagotchi — Gate Results

Copy this file per attempt (e.g. `GATE_RESULTS_2026-06-20.md`) and fill it in. Evidence dirs
(`gate0/ gate1/ gate2/`) are gitignored; attach key logs to the run record.

```
Date: 2026-06-19  Operator: Pratheek  Host macOS: Darwin 25.5.0  probe-rs: 0.31  openocd: 0.12.0  picotool: 2.2
Probe fw source/SHA: stock debugprobe-v2.2.3 (debugprobe_on_pico.uf2), CMSIS-DAP serial 4150324E30363318
Pico SDK tag: 2.x (MicroPython-bundled; blink fixtures built with pinned Arm GCC 13.3.Rel1)
Target: fresh Pico W (RP2040 rev B2, flash 'win w25q16jv' 2MB) running PicoInky 0.8.0 before the wipe
Wired SWD: SWCLK=GP2 (XIAO pad D8)  SWDIO=GP3 (XIAO pad D10)  GND  (3-pin header, no RESET pin)
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

## GATE 1 — fork + SWD-remap + OLED task survives sustained flash  ·  [ PASS / FAIL ]
- Fork base: `debugprobe-v2.2.3`  Fork SHA: ______
- [ ] remapped SWD verified by `probe-rs info` **before** the soak
- [ ] OLED task pinned core0, DAP on core1
- [ ] N cycles: ____ (bar ≥ 1000)  fails: ____  stalls: ____  re-verify mismatch: ____ (must be 0)
- [ ] OLED counter advanced throughout
- [ ] adversarial 50 ms-stall variant fails: ____ (must be 0)
- [ ] openocd-client twin soak also clean
- Heap: scheme = heap__  free = ____ B  min-ever-free = ____ B  leak? ____  **DECISION: heap__**
- Evidence: `gate1/soak_*.log`, heap plot, OLED timelapse

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
