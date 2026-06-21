# Release readiness — `v1.0`

The single evidence index for the C probe firmware release. It draws the line between what **CI can
automate** and what is **operator-attested on real hardware**, and pins each green to the *tagged
image* (not a per-increment dev build).

> ⚠️ **The HIL gates cannot run in CI.** Every gate/milestone test needs a physical probe + target
> (+ for some, an SD card / SWD fixtures). CI (`.github/workflows/firmware-c.yml`, self-hosted runner)
> runs **only** the build + the `analyze.sh` static-analysis gate. A green CI badge therefore means
> "builds + passes static analysis," **not** "the gates ran." The gates below were run by hand on the
> v1.0 image and recorded here.

## Release identity

| | |
|---|---|
| Tag | `v1.0` |
| Version (compiled in) | `1.0.0` — reported live by `{"q":"status"}` → `"ver"` |
| Base | fork of `raspberrypi/debugprobe` @ `debugprobe-v2.2.3` (single-core FreeRTOS) |
| Local build (attested image) | `text 170604 / bss 84140` · `.uf2` sha256 `7d1a2b50…27047` · `.elf` sha256 `149708ea…f380` |
| Released artifact | **byte-identical local rebuild** — `.uf2` sha256 `7d1a2b50…27047` matches the attested image bit-for-bit. The self-hosted CI runner was offline after a power-cycle, so it was built locally from the tagged source (reproducible) and released directly; CI remains available for future tags. |
| Published | **tag `v1.0` @ `44081d9`** · [Release](https://github.com/GhostRoboticsLab/Hackagotchi/releases/tag/v1.0) (`.uf2` + `.elf` + NOTICE + LICENSE) · 2026-06-22 |
| History note | The firmware version compiled into the binary is `1.0.0` (unchanged — `{"q":"status"}` → `ver=1.0.0`; build with `VERSION=1.0.0` to reproduce the byte-identical `.uf2`). The public git history was scrubbed in two passes (2026-06-21: internal strategy docs purged; 2026-06-22: residual agent co-author/session trailers + strategy detail stripped from commit messages); the cleaned release commit is `44081d9`, byte-identical in tree to the pre-scrub attested image. GitHub immutable-releases permanently reserves a tag name once a release has used it, so the original `v1.0.0` tag could be neither re-pointed nor reused — the release was retired and re-cut under a fresh tag **`v1.0`** at `44081d9`. |

## Section A — CI-automated (`firmware-c.yml`)

| Check | Tool | Result on v1.0 |
|---|---|---|
| Build | CMake + pinned Arm GCC 13.3 + pico-sdk 2.2.0 | **PASS** (clean) |
| Static-analysis gate | `analyze.sh` (GCC `-fanalyzer` + cppcheck) | **PASS** — 0 analyzer / 0 style on the pristine TUs (`cdc1_control.c`, `hackagotchi_dashboard.c`); only report-only upstream-inherited warnings |
| Artifacts + Release | uploads `.uf2`+`.elf`; optional Release ships **+ THIRD-PARTY-NOTICES.md + LICENSE** | wired |

Host unit tests (`ring_test`, `recorder_test`) are pure-host and **CI-able** (no hardware); they pass
locally (below) and a CI job for them is a tracked follow-up.

## Section B — HIL-attested on the v1.0 image (NOT run in CI)

Ports: CDC1/control `/dev/cu.usbmodem21204`, CDC0/bridge `/dev/cu.usbmodem21202`. Runner:
`…/PicoInky/.venv/bin/python`. Device flashed with the v1.0 `.uf2` (`{"q":"status"}` → `ver=1.0.0`).

| Suite | Proves | On v1.0 | Result |
|---|---|---|---|
| Version provenance | device self-reports its release | ✅ re-run | **PASS** — `fw=Hackagotchi, ver=1.0.0` |
| `m1/ring_test` (host) | SPSC ring (FIFO/wrap/drop/fence) | ✅ re-run | **PASS** 35/35 |
| `m2/recorder_test` (host) | recorder core state machine | ✅ re-run | **PASS** 31/31 |
| `m1/jsmn_hil` | JSON dispatch, strstr-trap reject, frag reassembly, nav | ✅ re-run | **PASS** (nav assertion hardened — async read) |
| `m1/uart_bridge_hil` | CDC0↔UART IRQ→ring→drain, 0 drops | ✅ re-run | **PASS** 55 B, 0 drops |
| `m1/crashbox_hil` | HardFault + malloc-fail captured, survive reboot | ✅ re-run | **PASS** |
| `m1/watchdog_hil` | SW watchdog catches a wedged TUD | ✅ re-run | **PASS** |
| `m3/screen_hil` | screen self-attestation (shows==loops) | ✅ re-run | **PASS** |
| `m3/feedback_hil` | buzzer/NeoPixel event transitions | ✅ re-run | **PASS** |
| `m4/hex_hil` | SNIFFER ASCII↔hex render | ✅ re-run | **PASS** (gutter assertion hardened — row-wrap) |
| `m4/macro_hil` | macro sender loops back | ✅ re-run | **PASS** |
| `m4/baud_hil` | runtime baud change + loopback at new rate | ✅ re-run | **PASS** |
| `m4/sd_hil` | SD explorer ls/cat | ✅ re-run | **PASS** |
| `m4/config_hil` | settings persist across reboot | ✅ re-run | **PASS** |
| **Gate 2 deferral (b)** `gate2_cdc.py --live-uart` | CDC0 live UART concurrent with a DAP flash soak | ✅ re-run | **PASS** — loopback 125/125, `urx_drop`/`utx_drop` +0, CDC1 answered 125/125, **0 stalls** ¹ |
| Gate 0 | probe halts/erases/flashes a target | cited | **PASS** 5/5 — `GATE_RESULTS.md` (prior image; needs SWD target + fixtures to re-run) |
| Gate 1 | OLED task survives sustained flash, 0 stalls; at-DAP-prio contention | cited | **PASS** — `GATE_RESULTS.md` (1000/1000 + self-attesting 300; prior image) |
| Gate 2 core | 2 nodes, DAP binds, 100/100 JSON | cited + corroborated | **PASS** — `GATE_RESULTS.md`; on v1.0 the probe enumerates as `Hackagotchi Probe (CMSIS-DAP)` and `--live-uart` exercised both CDCs + DAP live |
| M2 coexistence soak (R1) | 0 stalls under continuous SD-write + DAP flash | cited | **PROBE PASS** — `M4_RESULTS.md`: **0 stalls, flash succeeded every cycle**; the 13/300 (4.3%) are RETRYABLE host/USB hiccups, not flash-fails or probe faults (M4 image; v1.0 differs only by the `ver` string, so not re-run) |

¹ First run: the target re-glitched its QSPI (`fails=300`, still 0 stalls — the documented fragility).
**Clean re-run after a power-cycle (2026-06-21): PASS — `fails=1` (1%), 0 stalls, loopback 64/64,
urx/utx_drop +0, CDC1 answered 64/64** — the DAP flash also completed clean *concurrent with* byte-perfect
UART + USB liveness. Unambiguous close of deferral (b).

## Open operator-gated items

1. **Gate 2 deferral (a)** — node-map stability across replug/reboot. **One cycle effectively passed**:
   the 2026-06-21 power loss + operator replug was a real reboot+replug, and behavioral discovery recovered
   the roles correctly afterward (exactly 2 nodes; control `usbmodem21204` answers as `Hackagotchi`; bridge
   `usbmodem21202` silent). The full interactive 3×-replug + 1-reboot run is available via
   `gate2_cdc.py --replug-rounds 4` (it prompts the operator each round).
2. ~~Gate 2 deferral (b) clean re-run~~ — **DONE** (footnote ¹: clean PASS on the power-cycled target).
3. *(optional rigor)* re-run Gate 0/1 + `coexist_soak.py 300` on the v1.0 image (cited above from the
   functionally-identical M4 image).

## Carried caveats (unchanged from M4)

- Retryable (0-stall) DAP transfer errors rise under the *artificial* continuous-max-SD soak; ~0 in
  real use (the target is halted during a real flash). **Host-load-sensitive** — run soaks on an idle host.
- Some target boards re-glitch their QSPI under sustained flash hammering (still 0 stalls throughout) —
  power-cycle the target between long soak campaigns. Probe firmware unaffected.

## Reproduce

```bash
cd firmware/c && ./setup.sh && VERSION=1.0.0 BUILD_DIR=/tmp/hg-v100 ./build_fork.sh && ./analyze.sh
# flash /tmp/hg-v100/hackagotchi_probe.uf2 (picotool load -x, or {"q":"bootsel"} then load), then:
VENV=…/PicoInky/.venv/bin/python
$VENV tests/m1/jsmn_hil.py; $VENV tests/m1/uart_bridge_hil.py; $VENV tests/m1/crashbox_hil.py; $VENV tests/m1/watchdog_hil.py
$VENV tests/m3/screen_hil.py; $VENV tests/m3/feedback_hil.py
$VENV tests/m4/hex_hil.py; $VENV tests/m4/macro_hil.py; $VENV tests/m4/baud_hil.py; $VENV tests/m4/sd_hil.py; $VENV tests/m4/config_hil.py
$VENV tests/gates/gate2_cdc.py --live-uart --secs 150       # deferral (b)
$VENV tests/gates/gate2_cdc.py --replug-rounds 4            # deferral (a) — operator-driven
cc -I src -pthread tests/m1/ring_test.c -o /tmp/ring && /tmp/ring
cc -I src tests/m2/recorder_test.c src/recorder.c -o /tmp/rec && /tmp/rec
```

> Run HIL suites **standalone on a settled device** (not back-to-back after the reboot-inducing
> crashbox/watchdog tests, and not on a loaded host) — the UART-loopback tests share device state.
> See the `run-hil-gate` skill for the bench runbook.
