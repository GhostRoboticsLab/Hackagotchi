# Release readiness — `v1.1`

The single evidence index for the C probe firmware release. It draws the line between what **CI can
automate** and what is **operator-attested on real hardware**, and pins each green to the *tagged
image* (not a per-increment dev build).

> ⚠️ **The HIL gates cannot run in CI.** Every gate/milestone test needs a physical probe + target
> (+ for some, an SD card / SWD fixtures). CI (`.github/workflows/firmware-c.yml`, self-hosted runner)
> runs **only** the build + the `analyze.sh` static-analysis gate. A green CI badge therefore means
> "builds + passes static analysis," **not** "the gates ran." The gates below were run by hand on the
> image and recorded here.

## Release identity (v1.1)

| | |
|---|---|
| Tag | `v1.1` |
| Version (compiled in) | `1.1.0` — reported live by `{"q":"status"}` → `"ver"` (verified on the artifact: `strings` → `1.1.0`) |
| Base | fork of `raspberrypi/debugprobe` @ `debugprobe-v2.2.3` (single-core FreeRTOS) |
| Headline | OLED UI overhaul (cat + Spectre) **+ the `HG_PIN_DAP` XIP-cache-contention fix it needed** (§0 below) + DAP health telemetry |
| Build | `VERSION=1.1.0 ./build_fork.sh` (Arm GCC 13.3.Rel1 + pico-sdk 2.2.0; **`HG_PIN_DAP=ON` by default**) |
| Footprint | `.text` 110516 B (flash XIP) · `.data` 18832 B copied to **SRAM** at boot (incl. the ~18.8 KB pinned DAP/USB hot path) · `.bss` 82068 B |
| Attested artifact | `.uf2` sha256 `b0826090…d683` · `.elf` sha256 `56c5c975…5bec` |
| Gate | `analyze.sh` **PASS** (exit 0); the 7 DAP/USB transaction objects verified resident in SRAM (`nm`: `0x2000xxxx`), i.e. the pin took effect in the binary |
| Published | **tag `v1.1` @ `29fddde`** · [Release](https://github.com/GhostRoboticsLab/Hackagotchi/releases/tag/v1.1) — **immutable**, latest (`.uf2` + `.elf` + `THIRD-PARTY-NOTICES.md` + MIT `LICENSE`) · 2026-06-22. The published `.uf2` downloads back to sha256 `b0826090…d683`, byte-identical to the attested artifact and a clean reproducible rebuild from `29fddde`. |
| Tag scheme | per v1.0: GitHub immutable-releases reserve a tag name permanently, so semver `1.1.0` ships under the short tag **`v1.1`** (the `1.1.x` tag space stays open for patch re-cuts). |

## Section 0 — v1.1 delta: the XIP-cache-contention finding + `HG_PIN_DAP` fix

The v1.1 UI overhaul is a `+0` (lowest-priority), snapshot-only render layer that never touches the DAP
hot path — yet it introduced a **0-stall DAP regression** via a path priority cannot see. This section is
the proof it was found, root-caused, and fixed before shipping.

**Falsifiable claim (the regression):** *the v1.1 UI does not regress the DAP retryable-desync rate the
shipped v1.0 met.* — **FALSIFIED**, then fixed.

| Step | Evidence | Result |
|---|---|---|
| Reproduce | Gate-1 soaks of the v1.1 candidate on a clean bench | **1.4–3.0% retryable**, **0 stalls**, 0 target-glitch |
| Is it the firmware (not bench drift)? | **Interleaved A/B vs the shipped v1.0 `.uf2`** on one bench/host/cable, candidate **last-in-time**, power-cycle each | v1.0 **~0.2%**; v1.1 **1.4–3.0%** with the v1.1 run last → real **~7–15× regression**, not drift. (Tell: a power-cycle made it *worse*, not better → not dirty-bench.) |
| Root cause | ELF artifact diff + reasoning: the +0 render loop churns the 16 KB XIP I-cache and evicts the flash-resident CMSIS-DAP framing path; only the USB device ISR (`dcd_rp2040_irq`) was SRAM-resident → QSPI refill in the USB-IN window → retryable desyncs, **0-stall** (RAM ISR keeps acking). **The XIP cache is priority-blind.** | confirmed |
| Fix | `HG_PIN_DAP` → `memmap_hackagotchi_pin.ld` drops the 7 DAP/USB transaction objects from flash `.text` so they run from SRAM (residency only; no priority change; no upstream edit). `nm` on the v1.1 artifact: all 7 at `0x2000xxxx`. | in the shipped binary |
| Pure-pin soak | `gate1_soak 500` on the pinned image (run `b7dsm5jry`) | **0/500 fails, 0 stalls** — cleaner than v1.0's own ~0.2% |
| Combined image soak | `gate1_soak 1000` on the combined candidate (`ver 1.1.0-pin-dh` — identical to the released `1.1.0` but for the compiled version string), **non-idle host** (concurrent git/doc work mid-run) | authoritative line **verbatim**: `DONE N=1000 fails=2 stalls=0 target_glitch=0` → **`PROBE VERDICT: FAIL` (strict 0-fail Gate-1 bar)**. **999/1000 clean cycles**; the `fails=2` are both from **one** bad cycle (#994: a `TARGET_OK` retryable download fail + its re-verify mismatch). **0 stalls, 0 target-glitch.** |
| Liveness cross-check | a live `{"q":"status"}` read **immediately after the soak** (companion read — the soak harness logs cycle tallies, not the status reply) | `dap_xfers=1,993,328`, `crashes=0`, `urx_drop=utx_drop=0` — the monotonic `--wrap=DAP_ExecuteCommand` witness shows the probe serviced ~2.0 M transfers, so the clean cycles are real, not a dark/silent pass. |

**Verdict — honest, not flattering.** The R1 hard bar (**0 stalls**) held in every soak, and the fix's
*correctness* is established: the interleaved A/B eliminated the ~7–15× regression and the **pure-pin image
soaked `0/500` (PASS)** — that 0/500 is the clean reference. **But the combined 1000-cycle run's own strict
Gate-1 verdict was `FAIL`** — `fails=2` (0.2%), both from a single non-stall `TARGET_OK` retryable cycle on
an **admitted non-idle host** (the methodology's #1 rate inflator). 0.2% is the *same order* as v1.0's ~0.2%
floor — **not below it**. So the combined run corroborates 0-stall + witness-live but did **not** itself
clear the strict retryable bar; we ship on the strength of the A/B + the 0/500, not this run. **Carried
forward (open):** re-run the combined image `gate1_soak 1000` + `coexist_soak 300` on a strictly idle host
for a clean 0/N headline.

> Methodology now codified in `docs/firmware-conventions.md` §2, `docs/mcu-bringup-playbook.md` §10, and
> the `run-hil-gate` / `firmware-gate` skills: **0 stalls is necessary, not sufficient** — also gate the
> retryable rate against the *shipped* image, interleaved + candidate-last, with the `dap_xfers` witness.

## Section A — CI-automated (`firmware-c.yml`)

| Check | Tool | Result on v1.0 |
|---|---|---|
| Build | CMake + pinned Arm GCC 13.3 + pico-sdk 2.2.0 | **PASS** (clean) |
| Static-analysis gate | `analyze.sh` (GCC `-fanalyzer` + cppcheck) | **PASS** — 0 analyzer / 0 style on the pristine TUs (`cdc1_control.c`, `hackagotchi_dashboard.c`); only report-only upstream-inherited warnings |
| Artifacts + Release | uploads `.uf2`+`.elf`; optional Release ships **+ THIRD-PARTY-NOTICES.md + LICENSE** | wired |

Host unit tests (`ring_test`, `recorder_test`) are pure-host and **CI-able** (no hardware); they pass
locally (below) and a CI job for them is a tracked follow-up.

## Section B — HIL-attested baseline (NOT run in CI) — carried forward to v1.1

> **Carry-forward rationale.** The v1.1 delta is (a) the OLED UI overhaul, which runs entirely at the
> lowest priority off snapshot-only reads — it adds new *screens/attestation*, not new probe/bridge/SD
> paths — (b) the `HG_PIN_DAP` **residency** change (no logic/priority change), (c) the additive
> `dap_xfers`/`dap_idle_ms` status fields, and (d) the `ver` string. The portable + integration suites
> below are unaffected by those, so they carry forward as the v1.1 baseline; the v1.1-specific evidence
> (UI surfaces via `screen_hil`, and the DAP regression + fix) is in **§0** and the M-UI results.

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
