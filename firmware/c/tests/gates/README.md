# Hackagotchi gate harness

Host-side scripts to run the three go/no-go gates from `docs/engineering-plan.md` §6. They
**de-risk the one uncertain thing** — SWD ⇄ dashboard concurrency — before any UI is ported.

All scripts are **hardware-blind-safe**: with no probe wired they exit cleanly with a clear
message (exit code 2 = "can't run yet", 0 = pass, 1 = fail). So they're ready to run the moment
the SWD header is soldered.

## Order

| Gate | Script | Needs |
|---|---|---|
| pre | `pin_toolchain.sh` | nothing — records tool versions into every gate log |
| pre | `usb_enum_snapshot.sh` | nothing — snapshot USB before/after to diff descriptors |
| 0 | `gate0_check.sh [elf]` | bare XIAO w/ **stock** debugprobe.uf2, wired to a spare Pico target |
| 1 | `gate1_soak.sh [N]` + `gate1_soak_openocd.sh [N]` | the **fork** + remapped SWD + 1 OLED task; soak ≥1000 cycles |
| 1 | `heap_plot.py <log>` | the CDC heap-watermark capture from the soak |
| 2 | `gate2_cdc.py` | the fork + 2nd CDC built |

`fixtures/build_fixtures.sh` builds the two distinct blink ELFs the soak needs (run once the
Pico SDK + Arm GCC are set up — see `../../setup.sh`).

## Hardware

- **Probe** = the Hackagotchi XIAO. Gate 0 uses a **bare** XIAO (stock GP2/GP3 SWD free); Gate 1+
  use the soldered, remapped SWD header (`../../boards/board_hackagotchi_config.h`).
- **Target** = a separate spare **Raspberry Pi Pico** (plain RP2040). Powered by its own USB.
- **Wiring** = Probe SWCLK→Target SWCLK, SWDIO→SWDIO, **GND→GND** (mandatory). Optional RESET→RUN.

## Recording results

Copy `GATE_RESULTS.md` per attempt and fill it in. Evidence lands in `gate0/ gate1/ gate2/`
(gitignored — they're per-run artifacts).

> ⚠️ Before trusting Gate 1, validate the **soldered** SWD pins with
> `probe-rs info --chip RP2040 --protocol swd` — a wrong pin fails silently as "no IDCODE".
