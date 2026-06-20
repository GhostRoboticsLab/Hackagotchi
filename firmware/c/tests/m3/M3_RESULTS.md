# M3 — OLED dashboard / UI port: results

M3 turns the device into the **Hackagotchi dashboard**: the Gate-1 OLED coexistence harness
(`src/hackagotchi_dashboard.c`) becomes a multi-screen renderer driven entirely by single-writer
published snapshots — never touching the recorder/RTC state another task owns (the M2 two-ring rule
applied to the read direction). Gates-first, same discipline as M0–M2 (`../m2/M2_RESULTS.md`,
`docs/mcu-bringup-playbook.md`).

**Design of record:** the adversarially-critiqued `m3-design` workflow (3 parallel deep-reads + 1
skeptic). Verdict: CONDITIONAL GO. Screen triage (against the LOCKED static pin map): drop the 3 hard
pin-conflict screens (Oscilloscope = ADC on GP26/SWCLK; PWM Lab = GP28/SD-CS + GP2/SD-SCK; Logic
Analyzer = the whole locked bus) + I2C-scanner + demo; defer the button-menu screens (Macro/Baud/SD-
explorer) to M4; M3-core = Mascot/bridge-home · Sniffer/live-UART · Watchdog/flight-recorder · Throughput
· +Clock · +Recorder-status. Three corrections the critic proved against the source reshaped the plan:
(1) a cross-task race ALREADY shipped in `{"q":"rec"}` (fixed in M3.0); (2) DASH and SD are the SAME
priority (idle+0), not "dash below SD" — a heavy render time-slices the recorder drain, so `rec_drop`
must be gate-proven 0; (3) the probe-active signal needs an edit on the upstream DAP hot path — DEFERRED
out of M3 core, gated on a probe-rs re-soak if ever added.

---

## Increment M3.0 — HW reconciliation + snapshot boundary — **PASS (live, 2026-06-20)**

**Falsifiable claim.** (a) The surviving output HW (status LEDs, buzzer) drives correctly and
NON-BLOCKING, off the DAP hot path; on-device input is gone (no button) and that is reconciled. (b) The
SD/recorder task can publish a CONSISTENT snapshot of recorder state that any other task reads lock-free,
so the dashboard never touches `g_rec` across the task boundary — and routing the existing `{"q":"rec"}`
through it CLOSES a real pre-existing race. (c) None of this regresses the R1 DAP guarantee.

### Part 1 — feedback HAL (`src/feedback.{c,h}` + `src/ws2812.pio`)
Non-blocking NeoPixel + buzzer, serviced from the low-prio SD task (`feedback_service()` each 20 ms tick),
so a beep dwell or pixel write never sits on the DAP/USB path. Buzzer = GP29 PWM tone (clkdiv 64, 50 %
duty). Status LED = the XIAO onboard **WS2812 NeoPixel** (GP12 data + GP11 power-enable), driven via PIO
(pio1 — SWD owns pio0) so the SM clocks the 800 kHz waveform in HARDWARE and the CPU only pushes one word
(never blocks/masks IRQs → R1-safe). Beep + pixel requests each latch as one 32-bit slot (atomic cross-task
hand-off). CDC1 commands added: `{"q":"beep","hz":N,"ms":M}`, `{"q":"led","r":0/1,"g":0/1}`, and
`{"q":"pixel","r":0..255,"g":..,"b":..}` (with a new `get_int` jsmn numeric extractor).

**HIL (operator-observed, the one camera-/ear-in-the-loop step the gate needs):**
- **Buzzer GP29: PASS** — three rising tones (1500/2200/3000 Hz) audible; non-blocking (no DAP effect).
- **NeoPixel GP12/GP11: PASS** — `{"q":"pixel"}` RED→GREEN→BLUE→WHITE→off all rendered correctly (GRB
  order + power-enable + PIO init confirmed). This is the M3 status LED.
- **Finding M3-1 (why NeoPixel, not the onboard RGB):** the first reconcile drove the onboard RGB on
  GP17/GP16; it lit, but the observed colour did NOT match the nominal R=17/G=16 spec and it competes with
  the probe's GP25 blue USB-heartbeat (`usb_thread` free-runs GP25) → unreliable as a status channel. The
  XIAO's onboard WS2812 NeoPixel (GP12/GP11) is bright, fully colour-addressable, and conflict-free, so M3
  uses it instead. No physical button exists (GP27 = SWDIO) → input is auto-cycle + CDC1 (next/prev/screen),
  reconciled. (External buttons/LEDs/sensors are a deferred soldering option per the user.)

### Part 2 — published recorder snapshot (`rec_snapshot_t` + seqlock)
The SD/recorder task is the SOLE owner of `recorder_t` / the freeze ring / the RTC. It now publishes a POD
`rec_snapshot_t` (logging, wedge, sd_mounted, rx_total, hits, tp_peak, last_err, rec_drop, `file[16]`,
`alert[24]`, `tail[80]`, cached `rtc`) once per loop after `recorder_tick()`, via a single-writer SEQLOCK
(odd/even seq + `__atomic` RELEASE/ACQUIRE fences; reader retries until seq is even + unchanged).
`dash_get_rec_snapshot()` is the lock-free reader for the dashboard (M3.1+) AND for CDC1. The wall-clock
is cached here at ~1 Hz so the dashboard renders time with ZERO i2c1 access (only the OLED show takes the
bus — keeps the i2c1 contenders at two, structurally avoiding the non-recursive-mutex nesting hazard).
`recorder_copy_tail()` exposes the freeze tail (public alias of the static `freeze_read_last`) so ONLY the
owning task fills `snapshot.tail`.

**Race fixed (the critic's H1, confirmed in source).** The old `sd_rec_status_json()` ran in the TUD task
and called `recorder_get_status(&g_rec)` — handing out a LIVE pointer into `g_rec.filename` (rewritten by
`recorder_start` mid-`snprintf` → torn/unterminated read, possible over-read past `REC_FILENAME_CAP`) and
calling `hw->sd_mounted()` off the owning task, violating `recorder.h`'s own "owned SOLELY by the recorder
task" contract. It now reads the published snapshot instead — race closed for both `{"q":"rec"}` and the
future dashboard.

### Gates (falsifiable)
- **DAP binds:** `probe-rs list` → `Hackagotchi Probe (CMSIS-DAP)`. ✓
- **Snapshot robustness / torn-read:** hammered `{"q":"rec"}` ×80 → 80/80 well-formed JSON, filename
  always `log_NNN.txt` (regex-checked), 0 malformed/torn. ✓ (The fix is structural, not timing-dependent:
  the filename is now a bounded copy taken by the owning task under the seqlock.)
- **R1 re-soak (the regression gate):** `tests/m2/coexist_soak.py 200` — recgen continuous SD writes +
  200 concurrent DAP flash cycles (400 ops). **DAP 0 fails / 0 stalls** (better than M2's 6/600 baseline),
  recorder err=0 / logging=1 / wedge=0 / **rec_drop=0** (the extra per-loop publish + feedback service did
  NOT overflow the recorder ring), rx 0→472164 (461 KB written during flashing), on-card RECGEN intact. ✓
- **Health:** `{"q":"status"}` fw=Hackagotchi, crashes=0, wd_armed=1, dashboard looping; RTC valid + ticking.

**Verdict: PASS.** The output HW is reconciled (buzzer reliable, onboard LED best-effort, no button), the
snapshot boundary that all M3 screens depend on is in place and lock-free, a real pre-existing race is
closed, and R1 is intact (0/400 under load, rec_drop=0). Foundation laid for M3.1 (screen framework).

Build: `BUILD_DIR=/tmp/hg-build-m3np ./build_fork.sh` (text 179792). Device resting on `/tmp/hg-build-m3np`
(M3.0 image: snapshot boundary + buzzer + NeoPixel). R1 re-confirmed on this exact build (see soak above).

---

## Increment M3.1 — screen framework + first screen — **PASS (live, 2026-06-21)**

**Falsifiable claim.** The Gate-1 single-frame harness becomes a multi-screen renderer: a screen table
with a reader-clamped index, auto-cycle + CDC1 nav (no button), and **camera-free self-attestation** that
proves the right content renders AND that frames actually flush to the panel — with no DAP regression.

**Design (the verify-the-verifier part).** Each screen fn produces a TEXT MODEL (`dash_screen_t`: title +
≤5 lines); the framework BOTH draws that model to the OLED AND publishes the identical text (seqlock) for
CDC1 `{"q":"screen"}` — so the attestation is faithful *by construction* (it can't drift from what was
drawn). A **show-success counter** `g_dash_shows` ticks ONLY inside the `if (i2c1_bus_lock) { ssd1306_show }`
success branch — DISTINCT from the loop counter `g_dash_counter` — so a dark/skipped panel shows
`shows < loops` and cannot pass as alive (the Gate-1 loop-counter alone couldn't prove a flush). The
dashboard is the SOLE owner of the screen index; CDC1 only posts atomic intents (`dash_nav_step` /
`dash_nav_to`) that the dashboard consumes and wraps `((idx%n)+n)%n` on the READER side (the old unbounded
`s_page++` could have indexed OOB → hardfault). `disp.external_vcc=false` preserved (charge-pump on).

**Screens (M3.1).** (0) PROBE/home — identity, uptime, heap, RTC clock, screen N/M. (1) RECORDER —
logging/file/rx/drop/peak/wedge/hits/clock, entirely from the published snapshot (no `g_rec` access). The
remaining core screens (Mascot · Sniffer/live-UART · Throughput · Clock) are M3.2; all data plumbing is
ready. Trivial primitives ported inline: `fmt_bytes`, header (title + y=9 divider), `sline` text model.

**Input.** Auto-cycle every 5 s + CDC1 `{"q":"next"}` / `{"q":"prev"}` / `{"q":"screen","n":N}`; a manual
nav resets the auto-cycle clock. `{"q":"screen"}` (no n) returns the attestation.

**HIL (`tests/m3/screen_hil.py`, all OK):**
- boots on screen 0 (text contains `HACKAGOTCHI`); `next` → screen 1 (`RECORDER`); `prev` → screen 0.
- screen 1's text carries the LIVE snapshot filename (matched against `{"q":"rec"}`) — content is real.
- `{"q":"screen","n":99}` → CLAMPED to a valid index, `crashes==0` (no OOB hardfault).
- **auto-cycle** advanced 0→1 after ~5 s with zero input.
- **`shows`==`loops`** and climbing (every frame flushed — the panel is genuinely being driven; not a
  skipped/dark path), `dstack` ≈ 884 words free (stack healthy). RTC clock ticks live in the text.
- **Operator glance:** OLED auto-cycling between the PROBE and RECORDER screens (panel confirmed lit —
  anchors that the show-success counter corresponds to real photons; panel known-good since Gate 1).
- **R1 re-soak on this build** (`coexist_soak.py 120`): DAP 0 fails / 0 stalls, recorder err=0/wedge=0/
  rec_drop=0 — the multi-screen renderer (more per-frame draw at the SAME prio as the SD task) did NOT
  starve the recorder drain.

**Verdict: PASS.** The screen framework + self-attestation harness are in place and honest; nav + auto-
cycle + clamp safety proven; R1 intact. M3.2 just adds screen fns to the table.

Build: `BUILD_DIR=/tmp/hg-build-m31 ./build_fork.sh`. Device resting on `/tmp/hg-build-m31`.

---

## Increment M3.2 — full feasible screen family + cat mascot — **PASS (live, 2026-06-21)**

**Falsifiable claim.** The MicroPython screen family ports faithfully onto the M3 framework — the cat
mascot pixel-for-pixel, plus every screen the static pin map allows — all fed by the published snapshot,
with no DAP regression despite the much heavier per-frame draw.

**Ported (6 screens).** 0 HOME/mascot (brand + rx/up/REC/clock + the **cat**), 1 SNIFFER (live UART tail,
wrapped), 2 RECORDER (black-box status), 3 THROUGHPUT (now/peak + auto-scaled **sparkline** from a
dashboard-local 1 Hz bytes/sec ring), 4 WATCHDOG (wedge/hits/alert + freeze-frame tail), 5 CLOCK (big
scale-2 wall-clock + date). Screen fns now draw graphics DIRECTLY (the cat/sparkline aren't text) AND fill
the attestation text model; the show-success counter + an operator glance keep it honest.

**Cat (`draw_cat`).** Ported pixel-for-pixel from main.py via the ssd1306 primitives (rect→empty_square,
fill_rect→square, line, pixel, pixel(0)→clear_pixel, text→draw_string): head/ears/whiskers/nose, wagging
tail (3-stage), and the three states — IDLE (blink / sleeping curved eyes + floating Z's + chest-breath),
ACTIVE (wide eyes + pupils + moving mouth + RX bubble + flying data particles), and the IDLE→ACTIVE YAWN
transition. "active" is derived from the snapshot (`rx_total` climbing within 2.5 s).

**Intentionally absent / deferred** (recorded so it's not mistaken for an omission): Oscilloscope, PWM Lab,
Logic Analyzer, I2C-scanner — hard pin conflicts / bus contention (can't exist). Macro/Baud/SD-explorer —
M4 (need a CDC1-driven redesign; no button). Hex-sniffer sub-mode — needs raw tail bytes + an input
affordance; ASCII sniffer ships now.

**HIL (`tests/m3/screen_hil.py`, all OK).** 6 screens registered; nav (`next`/`prev`/`screen N`) hits each
of HOME/SNIFFER/RECORDER/THROUGHPUT/WATCHDOG/CLOCK; `prev` from 0 wraps to 5; `screen n=99` clamped to 3
(99%6), crashes=0; auto-cycle advances; shows≈loops climbing; dstack ~854 words free. **Live-data run**
(recgen on): HOME cat → `cat:active`, SNIFFER shows the streaming `…quick-brown-fox…` tail, THROUGHPUT
`now 2.9K/s pk 3.1K/s`. **Operator confirmed the cat + all screens render correctly on the panel.**
**R1 re-soak on this build:** coexist 120 cycles, DAP 0 fails / 0 stalls, rec_drop=0 — the heavier draw
did not regress DAP or starve the recorder.

**Verdict: PASS.** The Hackagotchi dashboard is feature-complete for M3-core: a reactive cat + the full
feasible screen set, snapshot-fed, R1-clean. (Future graphics rewrite: see `docs/hackagotchiUI_upgrade_v1.1.md`.)

Build: `BUILD_DIR=/tmp/hg-build-m32 ./build_fork.sh`. Device resting on `/tmp/hg-build-m32`.
