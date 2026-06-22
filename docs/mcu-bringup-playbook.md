# MCU bring-up playbook — proving firmware on real hardware before you build on it

A repeatable method for bringing up firmware on any microcontroller product, distilled from the
Hackagotchi C debugprobe fork (and applicable to PicoInky, the XIAO bridge, and whatever comes next).
The core idea, the firmware sibling of `case-design-playbook.md`: **never trust a source edit, a green
exit code, or your own eyeballs — prove each claim against the artifact and against a test you have
watched fail.** The expensive bugs here are not crashes; they are *silent passes* — a soak that counts
nothing, an overlay that never compiled in, a verifier that exits 0 on a real mismatch.

This is the workflow that took Hackagotchi through Gate 0 → Gate 1 → Gate 2. Follow it for every new
firmware product. See `docs/engineering-plan.md` for the *why* of this product; this is the portable
*how*.

---

## 0. Gates-first — the central discipline

Before porting a single screen of UI, prove the **hard, falsifiable architectural questions** on real
hardware as a short series of *gates*. A gate is a yes/no claim that, if false, kills or reshapes the
plan — so you want to find out cheaply and early.

Hackagotchi's three gates (the pattern, not the specifics):
- **Gate 0 — can the substrate do the core job at all?** (stock probe halts/erases/flashes a target.)
- **Gate 1 — does the risky coexistence hold?** (the dashboard task survives a sustained flash soak
  without starving the probe.)
- **Gate 2 — does the composite grow cleanly?** (add the 2nd USB CDC; DAP still binds, JSON round-trips.)

Rules:
- **No feature work until the gates pass.** The temptation is always to build the pretty part first;
  resist it. The gate answers the question that, unanswered, makes the pretty part worthless.
- **Each gate is one falsifiable claim** with a quantified bar and a *machine-checked* verdict.
- **Order gates by risk, not by ease.** The thing most likely to be false goes first.
- **A gate that only tests the easy configuration is not passed** — see §3 (the weak-stressor trap).

---

## 1. The hierarchy of truth (firmware edition)

When you assert "the build has pin X / the probe still binds / the OLED is alive," rank your evidence
and always reach for the highest you can get. Trusting a lower rank is how silent passes happen.

| Rank | Evidence | Proves | Notes |
|---|---|---|---|
| 1 | **The running hardware, machine-observed** | the actual behaviour | the gold standard; a script reads a counter / round-trips JSON / reads IDCODE |
| 2 | **The built binary, decoded** (`picotool info`, `nm`, `strings`, descriptor-from-ELF) | what actually compiled in | catches source-edit-didn't-reach-binary (F1-2); cheap, do this every build |
| 3 | **A second independent tool agrees** (openocd *and* probe-rs; cppcheck *and* -fanalyzer) | not a single-tool artifact | each tool lies differently; agreement is strong |
| 4 | **The build log** (text size, "copy_to_ram", 0 warnings) | it compiled & linked | necessary, not sufficient — it links fine and still does the wrong thing |
| 5 | **Operator eyeball** ("the OLED looked fine") | a human saw it once | last resort; a known soft spot — replace with rank-1 capture asap |
| 6 | **The source diff** ("I changed the pin to GP26") | your intent | proves *nothing* about the artifact (F1-2). Never the final word. |

The Hackagotchi findings are all rank-collapse stories: F1-2 trusted rank 6 (the edit had no effect);
the original soak trusted rank 4 (exit code) when rank 1 (stdout) said mismatch; the OLED claim still
rests on rank 5 and is explicitly flagged for rank-1 capture.

---

## 2. Anatomy of a gate

Write every gate down with these six parts (the `firmware-gate` skill scaffolds them; results live in
`tests/gates/GATE_RESULTS.md`):

1. **The falsifiable claim** — one sentence, stated so a failure is unambiguous. *"The OLED coexistence
   task survives ≥1000 consecutive target flashes with 0 probe failures."*
2. **The minimal rig** — exact wiring (pins, which board is probe vs target), firmware under test, and
   its provenance (how do you *know* the DUT is running your build, not the stock one — see §4).
3. **The quantified bar** — N clean cycles, a latency ceiling, "exactly 2 nodes." A number, not "works."
4. **The machine assertion** — a script that decides PASS/FAIL by reading the *right* signal (stdout
   content, a monotonic counter, a JSON field), **never** a human glance and **never** the exit code
   alone (§5). It must be able to emit FAIL.
5. **The adversarial variant** — a build that *should* stress the claim to its breaking point (§3). If
   the stressor can't actually hurt the system, the gate is decorative.
6. **The verdict** — PASS / FAIL / PASS-WITH-BLOCKERS, with evidence paths and every deferred item
   named. "PASS (core claim; X deferred)" is honest; a bare "PASS" that hides a deferred hard test is not.

---

## 3. The weak-stressor trap (volume ≠ strength)

The most seductive failure of a soak is **a huge clean number from a test that could never fail.**

Hackagotchi Gate 1: the OLED task ran at `tskIDLE_PRIORITY`, so DAP preempts it in ~50 µs — it is
*provably incapable* of starving the probe. 5200 clean cycles of that is 5200 cycles of a tautology
("a task that can't interfere doesn't interfere"). The informative test is the **at-DAP-priority**
variant under genuine contention — that one was built and compile-verified but deferred, so the thesis
is *not yet proven under load* despite the impressive cycle count.

Discipline:
- **Identify the worst case the real product will hit** (here: a dashboard doing blocking 23 ms I2C and
  later SD writes, on one core, at or near DAP's priority) and make the adversarial build reproduce it.
- **A stressor you can't make fail is not a stressor.** Before trusting a soak, ask: *what configuration
  would make this gate fail, and have I run it?* If the answer is "I haven't run the one that could
  fail," the gate is open.
- **Report the stressor's strength, not just the count.** "5200 cycles, idle-priority (weak) stressor"
  is honest; "5200 cycles, 0 fails" oversells.

---

## 4. Provenance — prove the DUT runs *your* build

A gate is meaningless if you're testing the stock firmware by accident. Establish provenance every run:
- **Don't rely on serial numbers.** The CMSIS-DAP serial on RP2040 is the flash unique-id — *identical*
  for the stock probe and your fork. It does not discriminate firmware.
- **Use a discriminating artifact:** a product string you set (`picotool info` → "Hackagotchi Probe"),
  your remapped pin map (GP26/27, not stock GP12/13/14), a symbol only your build has
  (`nm … | grep tud_cdc_rx_cb`), a string only your build has (`strings … | grep 'Hackagotchi Control'`).
- **Tee the provenance into the log.** The soak scripts run `probe-rs info` (reads the remapped pins) as
  a banner at the top of every log, so the evidence is inseparable from the result.
- **The byte-identical-builds trap (learned 2026-06-20).** When two builds differ ONLY in behaviour that
  nothing captured records — e.g. a stock build vs an adversarial variant that just changes a task priority
  and adds a `busy_wait` — the product string + pins are *identical*, so a soak of the wrong build produces
  byte-for-byte identical evidence. A re-run `embedded-verifier` workflow caught exactly this here and
  returned DO-NOT-PASS: nothing bound the adversarial image to the 1000-cycle soak. Two fixes, best first:
  - **Firmware self-attestation (best).** Have the firmware report *its own build-id* plus a measurement
    proving the stressor fired, over a channel you already poll. Here the CDC1 status reply gained
    `prio` (1 ⇒ task at DAP priority), a *measured* `stall_us` (≈50000 ⇒ the 50 ms `busy_wait` actually ran;
    the +0..49 µs overage was DAP time-slicing it — contention you can *see*), and a monotonic loop counter
    `n`. Now the run self-proves which image ran AND that the dashboard task kept looping — rank-1, no extra
    wiring. This is strictly better than the loopback jumper it replaced.
  - **`picotool verify` retroactively.** When you can't rebuild: `picotool verify <the-exact-uf2>` against
    the untouched post-soak flash binds the image at rank-2 — and run a CONTROL verify against the *wrong*
    image (it must report "contents did not match") to prove the check discriminates, not a vacuous always-OK.

---

## 5. Verify the verifier (your tools lie, each differently)

Embedded toolchains routinely report success on failure. Before a test's verdict means anything,
confirm the test *fails when it should* — feed it a known-bad input once and watch it go red.

Hard-won instances:
- **`probe-rs verify` (0.31) prints "Verification failed: contents do not match" but EXITS 0** on a real
  mismatch (F1-3). A guard written as `if ! probe-rs verify; then fail; fi` counted *nothing*. Fix:
  decide by **stdout content**, not exit code. This silently invalidated an entire soak until an
  adversarial review caught it.
- **`probe-rs erase --chip RP2040` hangs >150 s** — it skips the bootrom block-erase (F0-1). A "hang" was
  read as a dead board; it was a slow tool. Use openocd's rp2040 driver (~7.7 s) for erase.
- **C quote-include adjacency silently defeats an overlay** (F1-2) — `#include "probe_config.h"` from an
  upstream `.c` picks up upstream's *adjacent* header regardless of `-I` order, so a `src/` overlay of it
  has zero effect. picotool showed the stock pins. See `embedded-fork-overlay`.

Operational rule: **for every test tool, know its failure-reporting quirk before you trust its green.**
Confirm by an independent second tool (rank 3) when the claim matters.

---

## 6. The fork-overlay model (reuse > reinvent, without vendoring)

When the core capability already exists upstream (a CMSIS-DAP probe = `raspberrypi/debugprobe`), fork it
*minimally* rather than rewriting:
- **Pin to a deliberately chosen stable tag**, not HEAD. Hackagotchi pinned `debugprobe-v2.2.3` —
  the last tag *before* the #189 SMP-flash regression (commit 457e048). Know *why* your pin is where it is.
- **Overlay, don't vendor.** Upstream is fetched on demand (gitignored); your files compile *instead of*
  the matching upstream files via include-path ordering. You own a small diff, not a copy that rots.
- **Diff each overlay against upstream on every version bump.** The overlay is a liability that must be
  re-justified when the base moves.
- **Beware the quote-include adjacency rule** (§5 / F1-2): inject a board/config via a *shim* of a header
  that is **not adjacent** to the upstream file that includes it.

The full mechanism — shim, include ordering, toolchain pinning, submodule init — is its own skill:
`embedded-fork-overlay`.

---

## 7. Toolchain pinning (the build is part of the product)

A "works on my machine" embedded build is a non-result. Pin and document:
- **The exact compiler.** Hackagotchi builds with **Arm GCC 13.3.Rel1** (on disk, downloaded), NOT the
  host's system GCC 16.1 (too new — breaks the pico-sdk build). Wrong compiler = subtle miscompiles or
  hard build failures.
- **The exact SDK.** pico-sdk 2.2.0 at a known path; cmake honours the SDK's version range.
- **Submodule gotchas.** MicroPython's bundled pico-sdk leaves `lib/tinyusb` uninitialised (it vendors
  its own), so `bsp/board_api.h` is missing for anything that needs TinyUSB. `git submodule update
  --init lib/tinyusb` once; the build script does it idempotently.
- **A clean build script** that sets `PATH`/`PICO_SDK_PATH`, inits submodules, does a `rm -rf` clean
  build, and forwards adversarial flags. CI runs the *same* script + a static-analysis gate.

---

## 8. Reliability scaffolding (build it alongside, not after)

What earned its keep on Hackagotchi and transfers to any firmware:
- **A static-analysis gate** (`analyze.sh`): GCC `-fanalyzer` + strict warnings + cppcheck on *your* code
  (overlay-inherited upstream warnings report-only; new files must be clean). `-fanalyzer` is a free
  tier-zero analyzer — use it. CI runs it as a gate.
- **Third-party notices** (`THIRD-PARTY-NOTICES.md`): every linked component, role, license, source.
  Check licenses are permissive *before* you depend; re-check on cherry-picks. The project's own license
  is a separate, deliberate decision.
- **Build docs** that state the overlay/shim model, pin map, and the build/flash/analyze commands, so the
  next person (or you in three months) reproduces the artifact exactly.

---

## 9. Operating without a recovery path (remote / unattended)

When you can't physically touch the hardware (operator away, no BOOTSEL/replug possible):
- **Classify every operation by blast radius.** *Target*-flashing ops (soaks that flash the DUT) are
  safe — a wedged target is recoverable by the probe. *Probe*-reflashing ops are not — the probe has no
  software self-reset path, so a wedge needs a physical replug you can't do.
- **Only run the safe class.** Hackagotchi ran more soak cycles + did no-hardware work (analyze gate, CI,
  docs, NOTICE) while the operator was away, and never touched anything that could wedge the probe.
- **Front-load the staged builds.** Build the variants you'll *want* on return (the at-DAP-priority
  image) now and compile-verify them, so the return visit is flash-and-measure, not build-and-debug.

---

## 10. Gotchas (learned the hard way)

- **Single-core reality can undercut a multicore plan.** v2.2.3 is `configNUM_CORES=1`; the SMP
  core-affinity isolation the plan assumed does not exist (F1-1). Coexistence became pure
  priority/preemption on one core — which makes the contention test (§3) *more* load-bearing, not less.
  Re-verify the assumption against the actual base.
- **0 stalls ≠ no regression — the shared XIP cache is priority-blind (learned v1.1, 2026-06-22).** On a
  flash-XIP image the DAP/USB response-framing path is flash-resident; a heavy *lowest-priority* task
  (the OLED render loop) churns the 16 KB XIP cache and evicts that path, so the next transaction pays a
  QSPI refill inside the USB-IN response window → **retryable** CMSIS-DAP framing desyncs. They are
  **0-stall** (the RAM-resident USB ISR keeps acking — latency, not a hang), so the R1 hard bar still
  passes while the *retryable rate* silently regresses (v1.1 ~1.4–3.0% vs shipped v1.0 ~0.2%). Priority
  does not protect you — it schedules CPU, not the shared cache/QSPI bus. Lessons: (1) **gate the
  retryable rate against the shipped baseline, not just stalls**; (2) the fix is to pin the hot path into
  SRAM (linker `EXCLUDE_FILE` of the DAP/USB objects, residency-only — no priority change), which took
  the rate to **0/500**.
- **Distinguish a real regression from bench drift with an interleaved A/B against the SHIPPED image.**
  When a candidate's retryable rate looks high you cannot tell "firmware regression" from "noisy host /
  target-QSPI fragility" by one number. Soak the *gold shipped* image and the candidate on the SAME
  bench/host/cable back-to-back, **candidate last in time** (kills the time/order confound), power-cycling
  before each. Here it was decisive: power-cycling the target made the v1.1 rate *worse*, not better —
  falsifying the dirty-bench hypothesis — while the shipped image ran clean on the identical bench, so the
  only variable left was the firmware. Download the released `.uf2` and **sha-match it** so the baseline is
  the exact shipped artifact, not a maybe-different rebuild. A counter like the firmware's own `dap_xfers`
  (transfers executed) read before/after the soak cross-checks that the probe was live throughout — a
  soak whose transfer counter never moved is a silent pass.
- **A counter latched at boot proves nothing.** "The soak ran 1000 times" doesn't prove the OLED task
  kept looping — NAKs are swallowed, an `ok` flag set once stays set. Capture a *monotonic* counter from
  the device (loopback → CDC, or the firmware's own status reply) to prove liveness; eyeball is rank 5.
- **System-alive ≠ task-alive (frozen-but-alive).** A free-running uptime, or a status reply serviced by a
  *higher-priority* task, keeps answering even if your task-under-test froze in a loop. On 2026-06-20 the
  CDC1 `up`/`heap` liveness was serviced by the TUD task (above the dashboard) — so it could not have caught
  a hung dashboard. The fix: report a counter incremented BY the task under test (the dashboard's loop `n`)
  and assert *it* advanced (307→2189, 0 frozen) — that is the rank-1 task-liveness signal, not "device answers."
- **Heap free == min from a no-alloc harness is not headroom.** If the test does zero runtime allocation,
  `free == min` is expected and tells you nothing about the real workload. Re-measure when the actual
  feature mallocs; instrument the right allocator (the SSD1306 framebuffer is C-lib malloc, invisible to
  `xPortGetFreeHeapSize`).
- **Static descriptor decode ≠ enumeration.** USB composite is exactly where static analysis is least
  predictive (host driver quirks). "Flash-ready" from an ELF decode is honest labelling; keep confidence
  low until it enumerates on the actual host.
- **Scope compounds on a small substrate.** Each concurrent subsystem (probe + bridge + control + SD +
  UI) adds memory and scheduling pressure on one small MCU. Gate the *additions*, and re-measure headroom
  as they land — current headroom is not final headroom.

---

## 11. New-firmware checklist

1. [ ] List the **falsifiable architectural risks**; order them by likelihood-of-being-false → gates.
2. [ ] For each gate: claim, minimal rig, quantified bar, **machine** assertion, adversarial variant,
       verdict doc (use the `firmware-gate` skill).
3. [ ] **Pin the toolchain** (compiler + SDK + submodules); write a clean reproducible build script.
4. [ ] If forking upstream: pin a deliberate **stable tag**, overlay-not-vendor, shim the config, diff on
       bump (use `embedded-fork-overlay`).
5. [ ] **Verify the artifact** every build (rank 2): `picotool info` / `nm` / `strings` / descriptor decode.
6. [ ] **Verify the verifier** for every test tool (feed it a known-bad; know its exit-code/stdout quirk).
7. [ ] Establish **provenance** (your build, not stock) and tee it into every log.
8. [ ] Run the gate; if the only stressor that could fail is unrun, the gate is **open** — say so.
9. [ ] Stand up reliability scaffolding **in parallel**: static gate, NOTICE, build docs, CI.
10. [ ] Record the verdict honestly — name every deferred item; "PASS-with-blockers" beats a hollow PASS.

> Many MCU products are coming. The constant across all of them is §0 + §1: **prove the hard claims on
> real hardware, and trust only the highest rank of evidence you can reach.** Everything else is wiring.
