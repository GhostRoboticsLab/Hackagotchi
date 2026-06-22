# M-UI / v1.2 "Companion" — test results

## Host unit tests (no hardware — run in CI)

| Test | Command | Result |
|---|---|---|
| Sprite blit | `cc -I src -I src/ssd1306 tests/m_ui/blit_test.c -o /tmp/blit && /tmp/blit` | (M-UI baseline) |
| NeoPixel mood renderer | `cc -I src tests/m_ui/neopixel_anim_test.c src/neopixel_anim.c -o /tmp/npa && /tmp/npa` | **PASS** (2026-06-22) |
| Button + joystick logic | `cc -I src tests/m_ui/input_logic_test.c src/input_logic.c -o /tmp/inp && /tmp/inp` | **PASS** (2026-06-22) |

`neopixel_anim_test` asserts off==dark, intensity caps, per-mood channels, the breathing wave, and a
rainbow that actually differs across the chain. `input_logic_test` asserts debounce, short-vs-long
classification, bounce rejection, joystick deadzone/dominant-axis decode, and one-event-per-flick edges.

## Build + static-analysis gate (2026-06-22)

| Build | Result |
|---|---|
| Default (`HG_NEOPIXEL_COUNT=1`, button/joystick OFF) | builds clean; `analyze.sh` **PASS**; DAP/USB hot path still SRAM-pinned (HG_PIN_DAP intact) |
| Companion (`HG_NEOPIXEL_COUNT=5 HG_BUTTON=ON HG_JOYSTICK=ON`) | builds clean; `analyze.sh` **PASS**; new symbols present; `ver=1.2.0-companion` |

Pre-existing `-Wformat-truncation` notes in `hackagotchi_dashboard.c` / `sd_gate.c` are unchanged from
v1.1 and are not gate failures (`analyze.sh` gates `-Wanalyzer-*` + the two pristine files only).

## HIL (hardware-in-the-loop) — PENDING the soldered build

`tests/m_ui/companion_hil.py` — REQUIRED checks (status carries px/btn/joy; mood/fill/btn/joy commands
answer) + interactive button/joystick liveness. Hardware-blind-safe (exit 2 with no probe).

- **2026-06-22, against the bench unit running `1.1.0-pin-dh` (v1.1):** correctly **FAIL** — the v1.1
  image returns `"err":"unknown"` for the new commands and has no px/btn/joy status fields. This is the
  intended "feed it a known-bad input, watch it go red" check; it confirms the test is not a silent pass.
- **Against `1.2.0-companion`:** not yet run — flash the companion image (`HG_NEOPIXEL_COUNT=N
  HG_BUTTON=ON HG_JOYSTICK=ON ./build_fork.sh`, then `picotool load -x`) and re-run. Bar:
  `COMPANION SURFACE: PASS`.
- **Gate 1 coexist soak on the companion image:** not yet run — re-prove **0 stalls** with the strip
  driving + the ADS1115 on the 400 kHz bus before shipping any feature ON.
