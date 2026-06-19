# Hackagotchi — Gate Results

Copy this file per attempt (e.g. `GATE_RESULTS_2026-06-20.md`) and fill it in. Evidence dirs
(`gate0/ gate1/ gate2/`) are gitignored; attach key logs to the run record.

```
Date: __  Operator: __  Host macOS: __  probe-rs: __  openocd: __  picotool: __
Probe fw source/SHA: __  Pico SDK tag: __  Target: spare Pico (rev __)
Locked SWD: SWCLK=GP__ SWDIO=GP__ RESET=GP__ UART=GP0/GP1 OLED I2C=GP6/GP7
```

## GATE 0 — stock probe halts/erases/flashes a target  ·  [ PASS / FAIL ]
- [ ] `probe-rs list` shows CMSIS-DAP
- [ ] `info` reads IDCODE: ______
- [ ] `erase` 0-error
- [ ] `download --verify` ⇒ "Verification successful"
- [ ] `openocd verify_image` ⇒ verified
- [ ] `reset` ⇒ target LED blinks
- [ ] 5/5 consecutive clean runs
- Evidence: `gate0/`

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
