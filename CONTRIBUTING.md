# Contributing to Hackagotchi

Thanks for wanting to help! Hackagotchi is a debug probe that is *also* a black-box recorder and an
OLED dashboard, all on one single-core RP2040 — so the bar for a change is a little different from a
typical app: **it must not break the one guarantee that makes the whole thing work** (the probe never
stalls). This guide is how to contribute without tripping that wire.

Read this once; it'll save you a confusing review.

---

## TL;DR

- The shipping product is the **C firmware** in [`firmware/c/`](firmware/c). (`firmware/micropython/` is
  the legacy v1 prototype — not where new work goes.)
- **Never edit `upstream/`** — it's a fetched, gitignored copy of `debugprobe`. We *overlay*, we don't fork-in-place.
- **Nothing may block the DAP (probe) hot path.** This is the R1 invariant; most review feedback is about it.
- **Prove hard claims on hardware (a gate) before building on them.** Don't trust a green you didn't watch go red first.
- Build: `./setup.sh && ./build_fork.sh`. Gate: `./analyze.sh` must pass. Then run the relevant HIL tests.
- Commit small, atomic, signed-off (`git commit -s`), conventional-commit style. CI must be green.

---

## 1. Philosophy (why the code looks the way it does)

- **Gates-first.** Before a feature, the risky *architectural* question gets proven on real hardware as a
  falsifiable gate (claim → quantified bar → machine assertion → adversarial variant → verdict). The
  enemy isn't a crash — it's a **silent pass** (a soak that counts nothing, a test that can't fail). See
  [`docs/mcu-bringup-playbook.md`](docs/mcu-bringup-playbook.md) and `firmware/c/tests/gates/GATE_RESULTS.md`.
- **Reuse over reinvent.** We fork `debugprobe`, vendor carlk3 FatFs, jsmn, ssd1306, ws2812 — and stay
  rebasable on upstream. Prefer a well-established library + an upstream contribution to a bespoke wheel.
- **Don't gold-plate.** Document an accepted, understood caveat rather than chase it into a fork of
  pristine upstream code. (The retryable-DAP-fail caveat is the canonical example — see release-readiness.)

## 2. The R1 invariant — the rule that governs most reviews

The RP2040 here is **single-core** (`debugprobe-v2.2.3`, no SMP). Coexistence is bought with **task
priority**, not a second core:

```
high ──────────────────────────────────────────────► low
UART bridge / watchdog  >  USB (TUD)  >  DAP  >  dashboard + SD writer
```

**R1: a flash in progress must never stall.** Concretely, when you touch firmware:

- **Nothing on the DAP/USB hot path may block.** No `sleep`, no busy-wait, no blocking I/O, no taking a
  lock the DAP path also needs — in any task at or above DAP priority (the bridge `cdc_task`, the TUD
  callbacks). Long/blocking work goes in a **lower-priority** task (dashboard, SD).
- **One owner per resource.** FatFs is touched *only* by the SD task; the OLED/I2C1 *only* by the
  dashboard task; uart0 TX *only* by the bridge task. Don't reach across a task boundary into someone
  else's resource.
- **No shared mutable structs across tasks.** Move data by **single-writer published snapshots** (the
  seqlock in `sd_gate.c` / `dash_get_rec_snapshot`) or **lock-free SPSC rings** (`spsc_ring.h`). A reader
  gets a consistent copy; it never locks the writer.
- **Async request → reply-on-a-later-call** for anything that must run on the owning task (e.g. SD
  `ls`/`cat`/config-save are *posted* from CDC1 and serviced by the SD task, never inline).
- **The "0 stalls" bar is non-negotiable.** Retryable (0-stall) DAP transfer errors under an artificial
  max-SD soak are an accepted, documented caveat; an actual **stall** (hang / corruption / transfer
  desync) is a release blocker.

The detailed, codified conventions (error-code/goto-cleanup idiom, stack sizing, the crash box, the
watchdog) live in [`docs/firmware-conventions.md`](docs/firmware-conventions.md) — read it before a
non-trivial firmware PR.

## 3. The fork-overlay model

`firmware/c/` is an **overlay** on upstream `debugprobe`, not a vendored copy:

- `setup.sh` fetches pristine `debugprobe-v2.2.3` (+ carlk3 FatFs, pico-sdk) into `upstream/` (**gitignored**).
- `CMakeLists.txt` compiles **our** files instead of the matching upstream ones (e.g. our `src/main.c`),
  and puts `src/` + `boards/` first on the include path so our headers shadow upstream's. The board pin
  map is injected via a `boards/board_debug_probe_config.h` **shim** — never by editing upstream.
- **So: never modify anything under `upstream/`.** If you need to change upstream behavior, copy the file
  into `src/`, add it to `CMakeLists.txt`, and document what changed in its header (so the next
  upstream-bump diff is obvious). See [`docs/upstream-strategy.md`](docs/upstream-strategy.md).
- **Upstream-worthy fixes should go upstream** (to `raspberrypi/debugprobe` / yapicoprobe) — keeping the
  `firmware/c/` subtree MIT exists precisely to make that easy.

## 4. Dev setup

You need the pinned toolchain (the build refuses anything else):

- **Arm GCC 13.3.Rel1** and **pico-sdk 2.2.0** — see [`docs/c-firmware-build.md`](docs/c-firmware-build.md)
  for paths / `GCC_DIR=` / `PICO_SDK_PATH=` overrides.
- `cmake` ≥ 3.13, `picotool` 2.x, and (for tests) `probe-rs` + `openocd`. Optional `cppcheck`.
- A **bench rig** for HIL: the XIAO probe, a target RP2040 wired SWD (GP26/GP27 + GND), a microSD card,
  and Python `pyserial` for the test harnesses.

```bash
cd firmware/c
./setup.sh                              # fetch pinned upstream into upstream/ (gitignored)
VERSION=$(git describe --tags --always) ./build_fork.sh   # -> build/hackagotchi_probe.uf2 (+ .elf)
./analyze.sh                            # static-analysis gate — must pass
```

Flash: BOOTSEL the XIAO (hold **B**, tap **R**, release **B**) then `picotool load -x build/hackagotchi_probe.uf2`
— or, on a running device, `{"q":"bootsel"}` over CDC1, then load.

## 5. Building blocks — how to add things

- **A CDC1 command:** add a `{"q":"..."}` branch in `src/cdc1_control.c`. Keep reply buffers `static`
  (the TUD task stack is small). If it touches SD/recorder/OLED state, **post a request** to the owning
  task — don't do the work inline. Document it in the README command table.
- **A dashboard screen:** add a `screen_*` fn in `src/hackagotchi_dashboard.c`, register it in `SCREENS[]`,
  and read only the **published snapshot** (never `g_rec`/FatFs directly). Monitor screens auto-cycle;
  tool screens go past `N_MONITOR` and are summoned over CDC1. Emit the text model for self-attestation.
- **A gate / HIL test:** add it under `tests/gates/` or `tests/mN/`. Make the assertion decide on the
  **right signal** (parse the authoritative line, not a progress substring) and **feed it a known-bad
  input once** to watch it fail before you trust the pass. Record the verdict in the matching `*_RESULTS.md`.

## 6. Testing & verification

- **Host unit tests** (no hardware) for portable logic — e.g.
  `cc -I src -pthread tests/m1/ring_test.c -o /tmp/ring && /tmp/ring`,
  `cc -I src tests/m2/recorder_test.c src/recorder.c -o /tmp/rec && /tmp/rec`. Add one when you add
  portable logic; these can run in CI.
- **HIL tests** for anything touching hardware/timing/USB — `tests/{gates,m1,m2,m3,m4}/*.py`, run with the
  project venv python. **They cannot run in CI** (they need the bench); attest them by hand on the image
  you're proposing and note results in [`docs/release-readiness.md`](docs/release-readiness.md).
- **Bench gotchas** (these bite everyone):
  - The `/dev/cu.usbmodem*` suffix isn't stable — find the **control** port by behavior (answers
    `{"q":"status"}` as `Hackagotchi`); the other is the bridge.
  - Open the **bridge (CDC0) first and let it settle ~0.6 s** before driving control/loopback (opening it
    re-inits uart0). Keep connections persistent; churning a CDC port wedges macOS USB-CDC.
  - Run soaks on an **idle host** (host load inflates the retryable-fail rate) and **power-cycle the
    target between long soaks** (some boards re-glitch their QSPI under sustained hammering — still 0 stalls).
  - Run the UART-loopback tests **standalone on a settled device**, not back-to-back after the
    reboot-inducing crashbox/watchdog tests.
- **The static-analysis gate is a hard gate.** `analyze.sh` FAILs on any `-Wanalyzer-*` finding or any
  warning in the genuinely-new files (`hackagotchi_dashboard.c`, `cdc1_control.c`). Keep those pristine.

## 7. Commits & pull requests

- **Small, atomic commits**, each one building + passing the gate on its own.
- **Conventional-commit subjects**: `feat(scope): …`, `fix: …`, `docs: …`, `test: …`, `chore: …`.
- **Sign off every commit** (`git commit -s`) — we use the [DCO](https://developercertificate.org/);
  your sign-off certifies you can contribute the change.
- **Open a PR against `main`** with: what changed and *why*, which R1 rule it touches (if any), and the
  test evidence — host-test output and/or the HIL `*_hil.py` PASS lines (or "needs bench: <which>" if you
  can't run them). CI (build + `analyze.sh`) must be green.
- For firmware changes, say explicitly whether anything runs on or above the DAP path — reviewers will
  look there first.

## 8. Licensing of contributions

- Contributions to **`firmware/c/`** are **MIT** (to stay upstream-rebasable). New first-party source
  files there get an `SPDX-License-Identifier: MIT` header.
- Contributions elsewhere are **GPL-3.0-or-later** (the project license).
- Don't add a dependency under a copyleft (GPL) or non-commercial (e.g. SEGGER SystemView) license to the
  *shipping image*; if you vendor a new permissive dep, add it to `THIRD-PARTY-NOTICES.md` with its license.

## 9. Questions

Open a GitHub issue. For the deep "why," the sources of truth are
[`docs/engineering-plan.md`](docs/engineering-plan.md) (the plan + 3-gate model),
[`docs/firmware-conventions.md`](docs/firmware-conventions.md) (the codified rules), and
[`docs/release-readiness.md`](docs/release-readiness.md) (what's proven, and how). 🐾
