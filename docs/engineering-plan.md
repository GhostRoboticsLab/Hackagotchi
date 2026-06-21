# Hackagotchi — Engineering Plan

**Status:** Execution plan. Companion to `docs/c-firmware-analysis.md` (the decision doc). The *whether* is settled — this is the *how*. Folds in three research reports: yapicoprobe verdict (A), reliability stack (B), gate test strategy (C).

**Last verified:** 2026-06-19. Facts re-confirmed this session against live sources are tagged ✅; report-flagged caveats are preserved as ⚠️.

---

## 1. Scope & principles

**Goal.** Evolve the Hackagotchi device (Seeed XIAO RP2040 + expansion: SSD1306 128×64 OLED on I2C GP6/GP7; microSD on SPI0 GP2/3/4/CS28; PCF8563-class RTC @0x51; buzzer GP29; button GP27; LEDs GP25/26/17; target-UART tap on UART0 GP0/GP1) from its current MicroPython firmware into a **single C firmware** that is simultaneously:
- a **real SWD debug probe** (fork of `raspberrypi/debugprobe`, C + Pico SDK + TinyUSB + FreeRTOS SMP + PIO SWD), and
- the full **Hackagotchi OLED dashboard + UART "black-box" recorder**, reimplemented in C.

**Principles (in priority order):**

| # | Principle | What it means in practice |
|---|-----------|---------------------------|
| 1 | **Reliability by construction** | The probe path must NEVER stall/corrupt. The architecture (task priorities, no blocking on the DAP path), not tooling, is the lever. Tooling only *enforces and regression-tests* it. |
| 2 | **Gates-first** | No UI-porting code is written until **Gate 1** proves SWD ⇄ dashboard coexistence. Each gate is cheap to abandon; a failed gate kills/reshapes the plan before sunk cost. |
| 3 | **Reuse over reinvent** | Established libs for SWD/USB/SD/OLED/JSON/tests. Hand-roll only the ~40-line SPSC ring and the few glue macros. |
| 4 | **PicoInky stays a frozen test mule** | The MicroPython PicoInky repo/firmware is unchanged by this work — it is the *target* board against which the probe is validated, and a behavior reference for the ported screens. Hackagotchi is a **new C codebase** (this repo's `firmware/c/` subtree), not a mutation of the MicroPython tree. |

---

## 2. Base decision — debugprobe 2.2.3 NOW, yapicoprobe re-evaluated LATER

**Decision: fork `raspberrypi/debugprobe` pinned to tag `debugprobe-v2.2.3`. Do NOT fork yapicoprobe now.**

### Verified ground-truth (this session)
- ✅ **`debugprobe-v2.2.3` is a real tag** (Jul 7 2025, "Debugprobe re-release v2.2.3"). Latest upstream is `debugprobe-v2.3.1` (May 27 2026); `v2.3.0` was Feb 11 2026.
- ✅ **Issue #189 is real and as described:** FreeRTOS-SMP flash-programming regression introduced by commit `457e048`, intermittent flash hangs / "cannot read IDR" / corrupted target binary, **GDB+OpenOCD halt unaffected — flash-path only**. Absent from 2.2.3; reappears when 457e048 is cherry-picked. This is exactly why the Gate-1 bar is "1000 cycles, 0 fails," not a happy-path flash. ⚠️ It *may* be fixed in 2.3.x — see trigger below.
- ✅ **yapicoprobe `master` does not currently build on current `arm-none-eabi-gcc`** (issue #197, opened May 11 2026, still **open**, "high prio / in progress": `cannot read spec file 'nosys.specs'`). This directly substantiates Report A's reliability concern.

### Why debugprobe 2.2.3 now
- It is the **Raspberry Pi-maintained reference** every host tool (OpenOCD, pyOCD, probe-rs) is tested against → best fit for "reliability first / well-established."
- The gates were **defined against it**; changing base mid-plan invalidates Gate 0.
- 2.2.3 sits **before** the #189 SMP regression → safest known-good flash path.

### Why NOT yapicoprobe now (reinforced this session)
- **Bus-factor ≈ 1** + a visibly bumpy tracker (#197 build-broken-on-current-GCC, #198/#183 RTT regressions, RP2350 experimental). A sellable, reliability-critical product on a single-maintainer hobby fork is the exact exposure we're avoiding.
- **No umbrella `LICENSE` file** (GitHub license API returns `null`) — a real legal-hygiene problem for a sold product, even though per-file headers are clean (MIT + Apache-2.0 + SEGGER-BSD-1clause + FreeRTOS-MIT, no GPL).
- **Much larger surface** (NCM networking, sigrok, MSC, SystemView) we don't need — more to audit/break, opposite of lean gates-first.
- **No XIAO support either way** → no head start from adopting it.

### What we DO take from yapicoprobe — as a *design reference*, not a base
- Its **FreeRTOS SMP task-priority table** is a free, battle-tested template for our own (LED 30, **TinyUSB 28**, debug-CDC 26, sigrok 9, MSC-writer 8, SystemView 6, **UART-bridge 5**, **DAPv2 exec 3**, RTT-console 1, with the heavy RTT task pinned to core 1 via `vTaskCoreAffinitySet(…, 1<<1)`).
- Its `src/daplink-pico` MSC and RTT-to-CDC plumbing are **drop-in candidates later** (MIT/Apache).
- Cross-check role: run it **at Gate 0 only** as an A/B second-opinion probe firmware. If stock 2.2.3 ever shows a link issue our fork can't explain, yapicoprobe isolates "our fork" vs "RP2040-SWD-in-general."

### Trigger condition to revisit yapicoprobe (or move base to 2.3.x)
Re-evaluate **only after Gate 1 passes**, and adopt only *features* (RTT-into-CDC, MSC UF2 drag-drop, the proven SMP model) — never wholesale — and only if **all** hold:
1. We actually want one of those features in the product, AND
2. yapicoprobe's tracker is green on our toolchain (#197-class build breaks resolved on a pinned tag), AND
3. The license posture is settled (umbrella license confirmed with rgrr, or we've shed SEGGER/sigrok so the residual is plain MIT/Apache).
- **Separately:** once Gate 1 is green on 2.2.3, spike whether `debugprobe-v2.3.1` (post-#189-fix) is a viable newer base; if its flash path passes our Gate-1 soak, prefer it over 2.2.3 to ride upstream maintenance. ⚠️ Do not assume — prove it with the soak.

---

## 3. Adopted toolchain & libraries — "the reliability stack"

Versions are **flagged, not blindly pinned** — confirm against the live tree at adoption time, then pin by commit/tag in CI.

### MUST-HAVE — adopt in full

| Concern | Tool / library | Version (verify→pin) | License | Notes |
|---|---|---|---|---|
| Probe base | `raspberrypi/debugprobe` | tag `debugprobe-v2.2.3` ✅ | BSD-3 | Fork base. SWD-over-PIO, CMSIS-DAP v1/v2. |
| RTOS | FreeRTOS-Kernel (SMP) | submodule, pin SHA | MIT | `configNUMBER_OF_CORES=2`, `configUSE_CORE_AFFINITY`. |
| SDK / USB | Pico SDK + TinyUSB | SDK pin (debugprobe uses 2.x); TinyUSB per-SDK | BSD-3 / MIT | `cdc_dual_ports` is the 2×CDC reference. |
| SD / FAT | `carlk3/no-OS-FatFS-SD-SDIO-SPI-RPi-Pico` (wraps ChaN FatFs) | ~v3.6.2 | BSD-style | SPI0 microSD. **Writes block → low-prio task off the DAP core, never on hot path.** |
| OLED | `daschr/pico-ssd1306` | pin SHA | MIT | Near 1:1 with existing framebuf calls. Render to RAM FB in dashboard task; `ssd1306_show()` I2C flush at low prio/low rate, off hot path. |
| JSON (CDC1 control) | `zserge/jsmn` | single-header, pin SHA | MIT | **Zero-allocation tokenizer** (offset/length into the RX buffer). NOT cJSON (malloc-per-node → heap frag on 264 KB RP2040). Wrap iterate-kv boilerplate once + host-unit-test it. |
| Ring buffer | Pico SDK `queue_t` + hand-rolled SPSC ring (~40 lines) | SDK | BSD-3 | Single-producer/consumer UART path. Unit-tested. **No library** — a dep here is over-engineering. |
| Fault dump | Pico SDK `panic`/`hard_assert`/`assert`/`invalid_params_if` + custom `isr_hardfault`/`HardFault_Handler` override | SDK | BSD-3 | M0+ has **no stack-limit register** → silent stack overflow is real. Capture stacked frame (R0–R3, R12, LR, PC, xPSR) to a reserved-RAM "crash box" surviving reset; dump over CDC; reboot via WDT. Critical because the device often runs **probe-less**. (pico-sdk #228 pattern.) |
| Task health | FreeRTOS software-watchdog task feeding the **one** RP2040 HW WDT | SDK + FreeRTOS | — | Each monitored task checks in; low-prio watchdog task verifies all checked in within deadline, then `watchdog_update()`. Plus `configCHECK_FOR_STACK_OVERFLOW=2` + `vApplicationStackOverflowHook`, `configUSE_MALLOC_FAILED_HOOK=1`. **Primary defense against a blocking call stalling DAP.** |
| Host unit tests | Unity + CMock via **Ceedling 1.0** (ThrowTheSwitch) | 1.0 | MIT | x86 host tests for portable logic; mock HW edges (SD/OLED/USB) at the seam. |
| Static analysis | GCC `-Wall -Wextra -Wshadow -Wconversion -Wundef -Wdouble-promotion`, **`-Werror` in CI**, **`-fanalyzer`** | GCC pin | — | Tier-zero, free, highest bugs/minute. |
| Static analysis | `cppcheck` + `clang-tidy` (curated: `bugprone-*`, `cert-*`, `clang-analyzer-*`, selective `readability-*`) | cppcheck ~2.21 | — | Run **both** (disjoint bug classes). Our code only — exclude vendored SDK/FreeRTOS/TinyUSB. `clang-tidy` needs `compile_commands.json` via `-DCMAKE_EXPORT_COMPILE_COMMANDS=ON`. Curate-then-grow. |
| Heap | FreeRTOS `heap_4` (default), instrumented | — | — | **Gate-1 data decision**: keep `heap_4` (supports `vPortFree`, `xPortGetFreeHeapSize`/`…MinimumEverFreeHeapSize`) unless Gate 1 shows fragmentation alloc failures → only then retreat to `heap_1`. |

### NICE-TO-HAVE — adopt when a real need appears

| Tool | When | Caveat |
|---|---|---|
| **SEGGER RTT** (target-side `SEGGER_RTT.c/.h`) | Near-zero-overhead firmware-diagnostic logging that doesn't block on UART; our probe can *be* the RTT host. | BSD; commercial-OK with attribution. Promote to MUST-HAVE only if we later adopt yapicoprobe's RTT plumbing. Keep separate from the recorded target-UART telemetry. |
| **SEGGER SystemView** (visualizer) | **Bring-up / Gate-1 validation only** — visually prove the dashboard task never preempts DAP. | ⚠️ **Free tier is non-commercial only; commercial use needs a paid license.** **Keep it OUT of the shipping image** — bring-up tool, not a product dependency. |
| **HIL test in CI** (self-hosted mac-mini runner: pyOCD/OpenOCD + pytest, real probe + target) | After Gates 0–2 pass manually. Start with a smoke test (flash target, read IDCODE, assert), not a matrix. | Real maintenance cost (physical rig, flaky USB). |
| **CodeChecker** (Ericsson) | When analyzer output volume grows; aggregates clang-tidy/cppcheck with suppression mgmt. | Premature day one. |
| **ETL** (`ETLCPP/etl`, fixed-capacity no-heap containers) | Only if the dashboard/parser layer is written in **C++**. | MIT, but it's C++ — not worth a language mix just for a fixed vector. |

### EXPLICITLY SKIP — over-engineering for a small product

| Skip | Why |
|---|---|
| **Full MISRA C compliance** | Safety-cert friction (thousands of documented deviations) for little gain over `-Wall -Wextra -Werror -fanalyzer` + cppcheck + clang-tidy. At most run cppcheck's MISRA addon occasionally as a *suggestion source*, never a gate. |
| **Coverity / PVS-Studio / paid Infer** | The free trio covers the vast majority. Justified only at scale / under compliance mandate. |
| **cJSON / full JSON DOM** | malloc-per-node heap fragmentation on RP2040. Messages are tiny/fixed-shape → jsmn. |
| **Bespoke logging/trace framework** | RTT or plain CDC `printf` suffices. |
| **Custom ring-buffer / data-structure libs** | `queue_t` + hand-rolled SPSC ring, unit-tested. |
| **Fancy WDT (external chip / challenge-response)** | SW-watchdog-task-feeds-one-HW-WDT is the standard, sufficient pattern. |

---

## 4. Reliability methodology — how the C firmware beats the MicroPython original

The MicroPython firmware was *resilient by reboot* (the boot contract: never sit blank, re-probe, fall into a minimal loop on exception). The C firmware must be **resilient by construction** — caught earlier, observable when probe-less, and provably non-blocking on the DAP path.

### 4.1 Concurrency discipline (the #1 lever)
- **Core 1 = DAP + autobaud, untouched.** **Core 0 = TinyUSB + UART bridge + a LOW-priority dashboard task.**
- **Priority hierarchy** (modeled on yapicoprobe's): TinyUSB > UART-bridge > DAP-exec-glue **≫ dashboard task** (lowest, e.g. idle+2). The dashboard (OLED/SD/beep) must be *preemptible* by everything on the USB/probe path.
- **Pin the dashboard task to core 0 explicitly** (`vTaskCoreAffinitySet`) — `tskNO_AFFINITY` is **wrong** here; it must never land on core 1 beside DAP.
- **No blocking on the DAP/USB hot path, ever:** no `ssd1306_show()` I2C burst, no FatFs/SD write, no buzzer dwell, **no per-byte `strstr`** on the RX hot path. The bridge does a bounded SPSC enqueue; the dashboard/recorder drains and does the slow work at low priority.
- Gate 1 includes an **adversarial `busy_wait_ms(50)`** variant in the dashboard task to prove even a long core-0 stall (a slow SD write proxy) doesn't corrupt DAP.

### 4.2 Error handling in C (replaces try/except)
- **Error-code enum + single-exit `goto cleanup`** — the canonical idiom (Linux kernel, SQLite, libgit2). One `typedef enum { OK=0, ERR_… } pd_err_t;` per subsystem; resources released in reverse order at a bottom label. **Do not emulate C++ exceptions.**
- **Two boring macros:** `PD_TRY(expr)` (assign + `goto cleanup` on error) and `PD_CHECK(cond, code)`. Keep them few.
- **Pico SDK assert/panic is the foundation:** `assert`, `hard_assert` (→ `panic()` in release), `invalid_params_if`. `panic()` for unrecoverable invariants; error codes for anything a caller can handle.

### 4.3 Fault handler + crash box (because the device runs probe-less)
- Override the weak `isr_hardfault`/`HardFault_Handler`: capture the stacked exception frame → write to a **reserved-RAM crash box** that survives a warm reset → reboot via WDT → on next boot, dump the decoded fault over CDC (and/or RTT).
- Keep the **`.elf`** as a CI artifact to symbolicate these dumps and RTT.

### 4.4 Task health → single HW watchdog
- SW-watchdog pattern (§3): per-task check-in counters; a low-prio watchdog task feeds the lone RP2040 HW WDT only when **all** monitored tasks checked in on time. A wedged DAP/bridge/dashboard task → WDT not fed → chip resets.
- `configCHECK_FOR_STACK_OVERFLOW=2` + `vApplicationStackOverflowHook` compensate for the missing M0+ stack-limit register; `configUSE_MALLOC_FAILED_HOOK=1`.

### 4.5 Testable-logic structure (so logic ships verified, not hardware-hoped)
- **If it touches a register, it lives behind an interface and gets mocked; if it's algorithmic, it gets a host test.** High-value testable units (the project's actual risk areas):
  - UART **line/ring buffer** + framing,
  - the **wedge detector** state machine,
  - the **JSON control parser** (CDC1),
  - **log-rotation / session-index** logic ported from the MicroPython firmware (session-based auto-incrementing log files).
- These get Unity/CMock host tests *as they're extracted from the MicroPython port*, gated in CI.

---

## 5. Work breakdown structure

Phased, gates-first. Estimate reconciled to the prior **~22–31 eng-day** total. Ranges reflect report-flagged uncertainty (hardware bring-up, dual-CDC-on-macOS, soak duration).

| Milestone | Tasks | Reliability-stack mapping | Est (eng-days) |
|---|---|---|---|
| **M0 — Gates** (no UI port) | Build/flash stock 2.2.3 (bare XIAO); **Gate 0** (probe halts/erases/flashes a spare Pico). Lock SWD pin map → `board_hackagotchi_config.h`. Fork + remap SWD + one core-0 OLED coexistence task; **Gate 1** soak (≥1000 cycles, +adversarial 50 ms variant); record heap watermark → heap_4/heap_1 decision. Add CDC1 + jsmn status handler; **Gate 2** (two nodes, DAP binds, JSON round-trip). | Pico SDK base; `daschr/pico-ssd1306`; `heap_4` instrumented; jsmn; SPSC ring; the gate harness scripts (§9). | **6–9** |
| **M1 — Probe + bridge + control core** | Productionize the fork on the locked pin map. Robust UART bridge (CDC0) with bounded SPSC ring; CDC1 JSON control (jsmn) — `status`, `next`/`prev`/`dump` equivalents. **Fault handler + crash box; SW-watchdog task; stack-overflow/malloc hooks.** Per-interface USB string descriptors for stable node mapping. | §4.1 concurrency, §4.2 error idiom, §4.3 fault box, §4.4 watchdog; jsmn; SPSC ring (host-tested). | **4–6** |
| **M2 — SD + black-box logging** | `carlk3` FatFs on SPI0 (off-hot-path low-prio writer task). Port **session-based auto-incrementing log files** + UART telemetry recorder from MicroPython. RTC (PCF8563 @0x51) read for timestamps. | FatFs (low-prio task); log-rotation/session-index logic **host-unit-tested**; wedge detector state machine host-tested. | **3–5** |
| **M3 — Core screens** | OLED dashboard task (RAM framebuffer; low-rate flush). Port the *highest-value* mono screens first: live UART/telemetry view, recorder status, probe status, clock. Button (GP27) + LEDs (GP25/26/17) + buzzer (GP29, non-blocking, off hot path). | `daschr/pico-ssd1306`; dashboard task at lowest prio pinned core 0; buzzer never on hot path. | **3–4** |
| **M4 — Full UI parity** | Remaining Hackagotchi screens to parity with the MicroPython OLED family. Settings/config persisted to SD or flash. JSON control surface for host-side `dashboard_host.py`-style streaming if retained. | Reuse mono-page data conventions from PicoInky as a *behavior reference* (no code reuse — different language). cppcheck/clang-tidy curated set tightened. | **3–4** |
| **M5 — Polish / release** | CI green on the AUTOMATED checks it can run (build + `analyze.sh` static analysis + host unit tests); the HIL gates are **operator-attested on the release image** (CI cannot run hardware — see `docs/release-readiness.md`). Version compiled into the firmware (`{"q":"status"}` `ver`). Tagged GitHub Release with `.uf2`+`.elf` **+ NOTICE/LICENSE**. Docs: pin map, license/NOTICE bundle, flashing guide, README/CONTRIBUTING. License hygiene pass (BSD-3/MIT/Apache NOTICEs shipped; SystemView/sigrok confirmed absent from the shipping image). | CI/CD §7; HIL attested on-image; license posture (§2). | **3–4** |
| | | **Total** | **22–32** |

**Gating rule:** M1+ do not start until **Gate 1 passes**. M0 is abandon-cheap.

---

## 6. The 3-gate plan

**Locked SWD pin map (decide before any soldering).** Stock 2.2.3 defaults ✅ (`board_pico_config.h` @ v2.2.3): `SWCLK=GP2, SWDIO=GP3, RESET=GP1, UART_TX=GP4, UART_RX=GP5, uart1, LED=GP25, PROBE_SM=0`. **Collision:** GP2/3/4/28 are the Hackagotchi SD bus; GP4/5 aren't even broken out on the XIAO; the jancumps XIAO fork already moves the UART bridge to **GP0/GP1** ✅. **Recommended remap:** SWCLK/SWDIO onto two broken-out, uncommitted XIAO pins that avoid GP2/3/4/28 (SD), GP6/7 (OLED), and ideally GP0/1 (UART tap) — candidate **SWCLK=GP26, SWDIO=GP27** *if the button (GP27) is reclaimed*. ⚠️ **A wrong SWD pin fails Gate 1 silently as "no IDCODE."** Lock it in `board_hackagotchi_config.h` and record it in the gate doc; validate by Gate-0-style `probe-rs info` on the actual soldered header **before** trusting Gate 1.

✅ `probe-rs` subcommands confirmed present: `list`, `info`, `erase`, `download` (`--verify`, `--chip` in flattened `ProbeOptions`/`BinaryDownloadOptions`), `verify`, `reset`, `read`, `write`, `benchmark`.

### GATE 0 — stock probe firmware halts/erases/flashes a separate target
**Objective:** prove the *unmodified upstream* firmware turns the XIAO into a working SWD probe against a separate target, on THIS host (macOS) + toolchain. 0% porting. If this fails, nothing downstream matters.

**Setup:** Probe = **bare XIAO, no expansion board** (so stock GP2/GP3 SWD pins are legitimately free — isolates "does the probe work at all" from "on our pin map"; remap is a Gate-1 concern). Target = a **separate spare Raspberry Pi Pico** (plain RP2040 — not the XIAO, not a Pico W). Wiring: Probe SWCLK→Target SWCLK, SWDIO→SWDIO, **GND→GND (mandatory)**, optional RESET→RUN (only for `--connect-under-reset`). Power target via its own USB (don't backpower).

**Procedure / commands (macOS):**
```bash
# Build stock base
git clone --branch debugprobe-v2.2.3 --recurse-submodules \
  https://github.com/raspberrypi/debugprobe.git
cd debugprobe && mkdir build && cd build
cmake .. -DDEBUG_ON_PICO=OFF        # standalone probe
make -j                              # -> debugprobe.uf2
# Flash XIAO via BOOTSEL: copy debugprobe.uf2 to RPI-RP2, or: picotool load -x debugprobe.uf2

# Enumeration / DAP-present
system_profiler SPUSBDataType | grep -iA8 -E 'CMSIS|debugprobe|Picoprobe'
ioreg -p IOUSB -l -w0 | grep -iE 'CMSIS|debugprobe|IOCalloutDevice'
ls /dev/cu.usbmodem*

# probe-rs path (preferred: scriptable, --verify built in)
probe-rs list
probe-rs info --chip RP2040 --protocol swd
probe-rs erase --chip RP2040
probe-rs download --chip RP2040 --verify blink.elf
probe-rs reset --chip RP2040

# openocd cross-check (independent second opinion)
openocd -f interface/cmsis-dap.cfg -f target/rp2040.cfg \
  -c "init; reset halt; flash write_image erase blink.elf; verify_image blink.elf; reset run; exit"
```
Use a known `blink.elf` from `pico-examples` so the blinking LED corroborates `verify`.

**Pass/fail (quantitative):** PASS = `list` shows CMSIS-DAP; `info` reads a valid RP2040 IDCODE; `erase` 0-error; `download --verify` → `Verification successful` (exit 0); LED blinks after `reset`; openocd `verify_image` → verified; **5/5 consecutive clean runs**. FAIL = any non-zero exit, `Verification failed`, no probe in `list`, or no IDCODE.

**Optional A/B:** run yapicoprobe once here as a second-opinion probe firmware (do not adopt). If 2.2.3 shows a link issue our fork can't explain, this isolates "our fork" vs "RP2040-SWD-in-general."

**Evidence:** `gate0/` stdouts (`probe-rs_info.txt`, `download_verify.txt`, `openocd.txt`, `usb_enum.txt`) + blink video + versions (`probe-rs --version`, openocd, fw SHA/tag, macOS).

### GATE 1 — fork + SWD-remapped + ONE low-prio OLED task survives a sustained flash loop
**Make-or-break.** Prove that with SWD remapped off the SD bus AND a continuous core-0 OLED task, the probe flashes the target thousands of times with **zero** corruption/stall/timeout, and quantify heap headroom.

**Built:** fork 2.2.3; add `board_hackagotchi_config.h` (remapped SWCLK/SWDIO, UART GP0/GP1, LED GP25); add **one** low-prio FreeRTOS task **pinned to core 0** that only drives the OLED (`daschr/pico-ssd1306` on GP6/GP7): increment a counter, render a few lines, `ssd1306_show()` in a loop with a small delay. DAP stays on core 1, untouched. This is a **coexistence harness, not the dashboard.** Build **`heap_4`** first.

**Setup:** Gate-0 wiring **plus the Hackagotchi expansion board attached** (real OLED live; SD/buzzer pins physically present to prove remapped SWD truly avoids them). SWD on the **remapped** pins. Optional: logic analyzer or the spare XIAO-UART bridge on GP0 telemetry for an independent stall trace.

**Procedure:** (1) flash fork; confirm `probe-rs info` reads the target on the **remapped** pins *before* stressing (proves the remap). (2) confirm OLED counter ticking + probe enumerated simultaneously. (3) run the soak ≥1000 cycles (~2–4 h). (4) periodically emit `xPortGetFreeHeapSize()` + `xPortGetMinimumEverFreeHeapSize()` over CDC. (5) tally + inspect min-ever-free watermark.

**Stress harness** (`gate1_soak.sh`): alternate **two distinct images** (so `--verify` is a real read-back diff), wrap every call in `timeout` (a DAP hang → detected stall, not infinite hang), run an **independent second `probe-rs verify`** (guards a lying download-verify), dump probe+USB state on first failure. Twin `gate1_soak_openocd.sh` runs the same loop with the openocd client (different DAP pipelining; #189 only showed under flash → vary the client).
```bash
#!/usr/bin/env bash
# gate1_soak.sh
set -uo pipefail
CHIP=RP2040; ELF_A=fixtures/blink_a.elf; ELF_B=fixtures/blink_b.elf
N=${1:-1000}; log=gate1/soak_$(date +%Y%m%dT%H%M%S).log; fails=0; stalls=0
for i in $(seq 1 "$N"); do
  elf=$([ $((i % 2)) -eq 0 ] && echo "$ELF_A" || echo "$ELF_B")
  if ! timeout 30 probe-rs download --chip "$CHIP" --verify "$elf" >>"$log" 2>&1; then
    rc=$?
    [ $rc -eq 124 ] && { echo "STALL/TIMEOUT cycle $i"|tee -a "$log"; stalls=$((stalls+1)); } \
                    || { echo "FAIL(rc=$rc) cycle $i"|tee -a "$log"; fails=$((fails+1)); }
    probe-rs list >>"$log" 2>&1
    system_profiler SPUSBDataType | grep -iA6 CMSIS >>"$log" 2>&1
  fi
  timeout 30 probe-rs verify --chip "$CHIP" "$elf" >>"$log" 2>&1 || \
    { echo "REVERIFY-MISMATCH cycle $i"|tee -a "$log"; fails=$((fails+1)); }
done
echo "DONE N=$N fails=$fails stalls=$stalls"|tee -a "$log"; exit $(( fails + stalls ))
```
**Adversarial variant:** add a `busy_wait_ms(50)` to the OLED task (slow-SD-write proxy) to prove a long core-0 stall still doesn't corrupt DAP. Do NOT yet add real SD writes or the buzzer.

**Pass/fail:** PASS = **1000 consecutive download+verify, 0 fails, 0 stalls** (`exit 0`), independent re-verify passes every cycle, OLED counter advanced throughout. Stretch: 5000 overnight. **Heap decision:** if min-ever-free stays comfortably positive (≳4 KB headroom, no monotonic decline) → keep `heap_4` (preferred; dashboard will malloc framebuffers/JSON). Retreat to `heap_1` only on fragmentation alloc failures (but `heap_1` forbids `vPortFree`, which the OLED lib / future tasks may need). FAIL = any corruption, stall, OLED freeze, downward-trending free heap (leak), or the adversarial variant failing.

**Evidence:** soak log w/ per-cycle timings + tally; heap watermark series (plot via `heap_plot.py`); OLED-counter timelapse; fork SHA; `board_hackagotchi_config.h`; chosen heap scheme + measured headroom. **This log IS the gate verdict.**

### GATE 2 — add 2nd CDC: two usbmodem nodes, DAP still binds, JSON round-trip
**Objective:** composite grows {DAP v2 + CDC0} → {DAP v2 + CDC0 + CDC1} cleanly: macOS enumerates **two** `/dev/cu.usbmodem*`, CMSIS-DAP still binds (probe-rs still works), `{"q":"status"}` round-trips on CDC1 while CDC0 carries the UART telemetry stream and DAP stays bound.

**Built:** merge the `cdc_dual_ports` pattern into the fork's `usb_descriptors.c` — add a 2nd CDC (3rd+4th interface pair + 2 endpoints), keep device descriptor IAD composite `0xEF/0x02/0x01` ✅ with an IAD per CDC, bump `CFG_TUD_CDC=2` + `ITF_NUM_TOTAL`/`EPNUM_*`. Tiny CDC1 line handler parses `{"q":"status"}` (jsmn) → one-line JSON reply `{"fw":"…","heap":NNN,"up":SS}`. CDC0 keeps bridging the target UART. Set **distinct USB interface-name strings** per CDC (`"Hackagotchi UART"` / `"Hackagotchi Control"`).

**Setup:** Gate-1 (probe + target + OLED live) + a known UART stream into GP0/GP1 RX so CDC0 has real traffic.

**Commands (the macOS node-identity problem is the crux):**
```bash
ls /dev/cu.usbmodem*            # expect TWO nodes
probe-rs list                   # CMSIS-DAP still present
probe-rs info --chip RP2040 --protocol swd
# Map name -> node ROBUSTLY (don't trust numeric suffix sort order):
ioreg -p IOUSB -l -w0 -r -c IOUSBHostDevice | \
  grep -iE 'IOCalloutDevice|bInterfaceNumber|USB Interface Name|kUSBString'
system_profiler SPUSBDataType   # shows IAD + each named CDC interface
# JSON round-trip on CDC1 while CDC0 carries UART and DAP is live (run concurrently):
cat /dev/cu.usbmodemCDC0 > gate2/uart_capture.txt &
( probe-rs info --chip RP2040 --protocol swd ) &
python3 - <<'PY'
import serial, json, time
p = serial.Serial('/dev/cu.usbmodemCDC1', 115200, timeout=2)
p.write(b'{"q":"status"}\n'); time.sleep(0.2)
line = p.readline().decode().strip(); print("REPLY:", line)
assert json.loads(line).get("fw"), "no valid JSON status reply"; print("PASS")
PY
wait
```
**Robust node ID:** map **interface NAME → `IOCalloutDevice` path** via `ioreg`/`system_profiler`, NOT the numeric `usbmodemXXXXn` suffix sort order (⚠️ not guaranteed stable across reboots/replugs). Document the mapping recipe in the gate doc.

**Pass/fail:** PASS = exactly **2** nodes; `list`+`info` still succeed (DAP unaffected); CDC1 returns valid JSON with expected keys in timeout; CDC0 simultaneously shows live UART bytes; **round-trip 100/100** with no DAP error during the burst; mapping stable across **3 replug + 1 host reboot**. FAIL = only 1 node, DAP disappears, malformed/no JSON, CDC0 stops carrying UART when CDC1 active, or node identity unresolvable without trial-and-error.

**Evidence:** `gate2/` — `system_profiler` IAD + 2 named CDCs, `ls` listing, 100-request round-trip log (count + latencies), concurrent UART capture, documented name→node mapping recipe.

### Gate-results checklist template (copy into the gate doc)
```
HACKAGOTCHI GATE RESULTS
Date: __  Operator: __  Host macOS: __  probe-rs: __  openocd: __  picotool: __
Probe fw source/SHA: __  Pico SDK tag: __  Target: spare Pico (rev __)
Locked SWD: SWCLK=GP__ SWDIO=GP__ RESET=GP__ UART=GP0/GP1 OLED I2C=GP6/GP7

GATE 0 — stock probe halts/erases/flashes a target            [ PASS / FAIL ]
  [ ] probe-rs list shows CMSIS-DAP   [ ] info reads IDCODE: __
  [ ] erase 0-error  [ ] download --verify => "Verification successful"
  [ ] openocd verify_image => verified  [ ] reset => LED blinks  [ ] 5/5 clean
  Evidence: gate0/

GATE 1 — fork+SWD-remap+OLED task survives sustained flash      [ PASS / FAIL ]
  Fork base: debugprobe-v2.2.3  Fork SHA: __
  [ ] remapped SWD verified by probe-rs info BEFORE soak
  [ ] OLED task pinned core0, DAP on core1
  [ ] N cycles: __ (bar >=1000)  fails: __  stalls: __  re-verify mismatch: __ (must be 0)
  [ ] OLED counter advanced  [ ] adversarial 50ms-stall fails: __ (must be 0)
  Heap: scheme=heap__ free=__B min-ever-free=__B leak?__ DECISION: heap__
  Evidence: gate1/soak_*.log, heap plot, timelapse

GATE 2 — 2nd CDC: two nodes, DAP binds, JSON round-trip         [ PASS / FAIL ]
  Device class: 0xEF/0x02/0x01 (IAD)  CFG_TUD_CDC=2
  [ ] exactly TWO nodes  [ ] probe-rs list/info still succeed
  [ ] node map by NAME (CDC0=UART, CDC1=Control): __ / __  [ ] stable 3 replug + 1 reboot
  [ ] {"q":"status"} 100/100 valid JSON  [ ] CDC0 carried live UART concurrently
  Evidence: gate2/

OVERALL: [ ] all 3 PASS -> proceed to UI port   [ ] blocked at gate __: __
```

---

## 7. CI/CD (GitHub Actions)

Mirror the existing self-hosted-runner pattern (the MicroPython UF2 flow in PicoInky's `.github/workflows/firmware.yml`).

**One firmware workflow + parallel quality jobs:**
- **`build`** — checkout `submodules: recursive` (pico-sdk, FreeRTOS-Kernel, TinyUSB, `carlk3` FatFs all **pinned git submodules** — that IS the toolchain pin). **Pin Arm GCC** to a specific `arm-none-eabi-gcc` release (same philosophy as the existing MicroPython v1.28.0 + Arm GCC 13.3.Rel1 pin). `cmake -DCMAKE_EXPORT_COMPILE_COMMANDS=ON` → build → upload **`.uf2`** and **`.elf`** as artifacts. ⚠️ Pin the GCC version explicitly — the live yapicoprobe #197 ("cannot read `nosys.specs`" on current Debian GCC) is a concrete example of an *unpinned* GCC breaking an Arm embedded build; pinning is the mitigation.
- **`host-tests`** — Ceedling (Unity/CMock) for parser, ring buffer, wedge detector, log-rotation.
- **`cppcheck`** — our code only (exclude vendored).
- **`clang-tidy`** — curated checks, consumes `compile_commands.json`.
- **`werror-build`** — `-Wall -Wextra -Wshadow -Wconversion -Wundef -Wdouble-promotion -Werror -fanalyzer`.
- **Gate:** merges blocked on all of the above.
- **Release:** on tag → GitHub Release with `.uf2` **and `.elf`** attached (the `.elf` is required to symbolicate fault dumps + RTT). Dispatch-only manual trigger, like the existing firmware workflow.
- **(Later) HIL smoke** on the self-hosted mac-mini: real probe flashes a target, asserts IDCODE — added only after Gates 0–2 pass.

**Delivery status (reconciled with reality as of M1, 2026-06-20):** `build` ✅ and a static-analysis gate
(`analyze.sh`: `-Wall -Wextra -Wshadow -Wundef -Wdouble-promotion -fanalyzer -fsyntax-only` + optional
cppcheck) ✅ are in `.github/workflows/firmware-c.yml`. **Deferred to M2** (CI plumbing, not a missing M1
deliverable): the **`host-tests`** Ceedling job (M1 ships the host test `firmware/c/tests/m1/ring_test.c`
run via `cc` — Ceedling wrapping lands when M2 adds log-rotation/wedge-detector logic), a dedicated
**`clang-tidy`** job, and the full **`werror-build`** (`-Werror -Wconversion`) gate. Tracked in
`docs/TODO.md`; M1's own code builds `-Wall -Wextra`-clean.

---

## 8. Risk register

| # | Risk | Severity | Mitigation | Retired by |
|---|---|---|---|---|
| R1 | **Blocking call on the DAP/USB hot path** (OLED `show()`, SD write, beep, per-byte `strstr`) stalls/corrupts flash | **Critical** | §4.1 priority hierarchy; dashboard task lowest-prio + core-0-pinned; bounded SPSC enqueue on bridge; no slow work on hot path | **Gate 1** (incl. adversarial 50 ms variant) |
| R2 | **Heap fragmentation / exhaustion** under FreeRTOS on 264 KB RP2040 | High | `heap_4` instrumented; jsmn zero-alloc (no JSON DOM); watermark logged | **Gate 1** heap decision (data-driven heap_4 vs heap_1) |
| R3 | **Dual-CDC node identity unstable on macOS** (numeric suffix not stable across reboot/replug) | High | Distinct per-interface USB string descriptors; map name→`IOCalloutDevice` via `ioreg`/`system_profiler` | **Gate 2** (3 replug + 1 reboot stability check) |
| R4 | **SMP flash regression (#189)** ✅ — intermittent, flash-path-only, GDB/halt looks fine | High | Pin **2.2.3** (before commit `457e048`); soak with checksum-per-cycle, not happy-path | **Gate 1** soak (1000 cycles, 0 fails) |
| R5 | **Wrong SWD pin remap** ⚠️ — fails silently as "no IDCODE" | High | Lock `board_hackagotchi_config.h`; validate via `probe-rs info` on the **soldered** header *before* soak | **Gate 1** pre-soak `info` check |
| R6 | **SWD pins physically don't reach / not broken out** on the XIAO expansion header (limited free GPIO; GP2/3/4/28=SD, 6/7=OLED, 0/1=UART) | Med | Lock pin map before soldering; candidate SWCLK=GP26/SWDIO=GP27 (reclaim button); verify broken-out on the expansion header | **Gate 0/1** wiring validation |
| R7 | **yapicoprobe adopted prematurely** → bus-factor-1, unpinned breaking edge (#197 build break live), no umbrella license | Med | Stay on debugprobe 2.2.3; yapicoprobe = Gate-0 A/B reference + design template only; strict §2 trigger to revisit | §2 trigger gating |
| R8 | **License hygiene for a sold product** — SystemView non-commercial; yapicoprobe no umbrella license | Med | Keep SystemView a bring-up tool, OUT of shipping image; if any yapicoprobe code is later vendored, confirm umbrella license + ship NOTICEs; residual stack is BSD-3/MIT/Apache | M5 license pass |
| R9 | **Silent stack overflow** (M0+ has no stack-limit register) | Med | `configCHECK_FOR_STACK_OVERFLOW=2` + hook; fault handler + crash box; SW-watchdog | M1 fault-handling work |
| R10 | **Base drift** — 2.3.x may already fix #189, making 2.2.3 needlessly old | Low | After Gate 1 green on 2.2.3, spike 2.3.1 through the same soak; adopt if it passes | Post-Gate-1 base spike |

---

## 9. Test scripts to write NOW (before hardware exists)

All host-side, hardware-blind (fail cleanly with "no probe found" until wired). Authored so they're ready the instant the SWD header is soldered. Location: `firmware/c/tests/gates/`.

| Script | Purpose |
|---|---|
| `gate0_check.sh` | Runs `probe-rs list/info/erase/download --verify/reset` + `openocd verify_image` against `--chip RP2040`; asserts exit codes; writes `gate0/*.txt`. |
| `gate1_soak.sh` | The probe-rs soak loop above — alternating images, `timeout` wrap, independent re-verify, forensic dump on first fail. |
| `gate1_soak_openocd.sh` | Twin of the soak with the openocd client (different DAP pipelining — varies the client per #189). |
| `heap_plot.py` | Ingests the CDC heap-watermark log; plots free vs min-ever-free (leak/fragmentation visual); degrades to a text summary without matplotlib. |
| `gate2_cdc.py` | Two-node enumeration + JSON round-trip harness; parameterized node paths; `ioreg`/`system_profiler` **name→node** mapping helper. |
| `usb_enum_snapshot.sh` | Wraps `system_profiler SPUSBDataType` + `ioreg -p IOUSB -l` + `ls /dev/cu.usbmodem*` into a timestamped snapshot; run before/after each gate to diff descriptor changes. |
| `fixtures/build_fixtures.sh` | Builds two **distinct** `pico-examples` blink ELFs so `--verify` is a real read-back diff (not a same-image pass that masks a stuck write). Run once toolchain is set up. |
| `pin_toolchain.sh` | Install + record versions of `probe-rs` (`--version`), `openocd`, `picotool`, Arm GCC, Pico SDK tag — embedded in every gate log for reproducibility. |

Also write the **host unit tests** (Ceedling) for the portable logic that has no hardware dependency yet — UART ring buffer, wedge-detector state machine, jsmn JSON-control adapter, log-rotation/session-index — porting the algorithms from the MicroPython firmware behind mockable hardware seams. These run in CI from day one and need no probe.

---

*Generated by a 4-agent research workflow (yapicoprobe verdict · robust-embedded-C reliability stack · gate test strategy → synthesis), with live source re-verification. Re-confirm version/issue facts against the upstream repos at adoption time.*
