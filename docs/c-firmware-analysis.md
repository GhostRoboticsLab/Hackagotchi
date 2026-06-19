# PocketDebugger: Fork debugprobe in C? — Engineering Decision

## 1. Verdict

**Yes, fork `raspberrypi/debugprobe` — but gate it behind a 2-day hardware spike before committing to the full UI port, and treat the dashboard as a from-scratch C subsystem, not a translation.** The probe half is essentially free (debugprobe is production-grade, OpenOCD/probe-rs already drive it); the dashboard half is ~90% of the labor and re-earns reliability you already have in MicroPython. The single most important caveat: **the make-or-break risk is not the USB endpoint budget (that passes comfortably) — it is concurrency.** A blocking OLED `show()`, blocking SD write, blocking buzzer, or per-byte `strstr` on the RX hot path can stall the USB/DAP task mid-flash and time out the probe. If the MVP spike (a live SWD flash loop running *while* the OLED refreshes) shows DAP corruption you can't tame, Option 2 is dead — and you should fall back to the "$4 spare Pico flashed with stock `debugprobe_on_pico.uf2`" two-tool answer instead.

---

## 2. Is it even possible? (USB feasibility — the make-or-break)

**Yes, with comfortable margin.** The target composite is **DAP v2 (vendor bulk) + 2× CDC** (CDC0 = UART telemetry bridge, CDC1 = PocketTap JSON control channel). debugprobe *already ships* DAP v2 + 1 CDC as a working composite; adding a second CDC is strictly additive and templated by TinyUSB's `cdc_dual_ports` example.

### Endpoint math

The load-bearing fact: on the RP2040, **one endpoint number can host both an IN and an OUT endpoint** (separate per-direction registers). The controller has 16 endpoint numbers (EP0–EP15).

| Function | Notif (INT IN) | Bulk OUT | Bulk IN | Directional EPs |
|---|---|---|---|---|
| DAP v2 (vendor) | — | 1 | 1 | 2 |
| CDC0 (UART bridge) | 1 | 1 | 1 | 3 |
| CDC1 (JSON control) | 1 | 1 | 1 | 3 |
| **Total non-control** | | | | **8** |

Minimal packing uses **6 of 16 endpoint numbers** (EP0 control + EP1–EP5). Even debugprobe's loose, one-number-per-direction style stays ≤9. **The budget is not the binding constraint.**

- **DPRAM** (the other hard limit): only the 64-byte HW buffers live in the 4 KB DPRAM. EP0 (128 B + 8 B) + 8 endpoints (≤128 B each double-buffered ≈ 1 KB) fits in ~3.7 KB usable. Fine.
- **The actual binding resource is main SRAM FIFOs**, not endpoints: debugprobe's `CFG_TUD_VENDOR_RX/TX_BUFSIZE = 8192` + `CFG_TUD_CDC_TX_BUFSIZE = 4096` already cost ~20 KB; the 2nd CDC adds ~4 KB. On a 264 KB-SRAM RP2040 that's tolerable but is the number to watch (and the strongest argument for RP2350's 520 KB later).

### Detection is safe
OpenOCD (`cmsis_dap_usb_bulk.c`) and probe-rs match on **VID/PID + the "CMSIS-DAP" interface string + vendor class 0xFF + a bulk EP pair** — they explicitly filter out CDC interfaces by class and ignore absolute endpoint numbers and interface count. Extra CDCs are invisible to probe detection. **Constraint: keep the substring "CMSIS-DAP" in the DAP interface's string descriptor; don't rename it.**

### The one thing to verify on hardware
**Set the device descriptor to the IAD-composite class `bDeviceClass=0xEF / 0x02 / 0x01`** (TinyUSB `TUSB_CLASS_MISC` / `MISC_SUBCLASS_COMMON` / `MISC_PROTOCOL_IAD`) — what `cdc_dual_ports` uses. debugprobe currently ships `0x00` and works with one CDC, but there is real uncertainty about whether `0x00` reliably enumerates **two** CDCs on every macOS version. Test both; prefer `0xEF`.

---

## 3. Recommended architecture

### Base: **fork `raspberrypi/debugprobe`** (with caveats)
| Candidate | Why / why not |
|---|---|
| **debugprobe** ✅ | Production-grade, RPi-maintained, BSD-3 (permissive — fine for a product). Already ships DAP v2 + CDC composite, PIO SWD, autobaud UART bridge, FreeRTOS scaffolding, and `debugprobe_on_pico` / `_on_pico2` variants (RP2040 + RP2350 upgrade path near-free). **Caveat: pin the fork to the `2.2.3` tag, not `master`** — the SMP commit `457e048` (Issue #189, still open at last check) causes *random* flash hangs / corrupted writes. Validate the SMP race before adopting `master`. |
| Black Magic Debug ❌ | Best ergonomics (on-probe GDB, no OpenOCD), but the **RP2040-as-*host* port is community WIP/untested** (`ambraglow/blackmagic-rp2040`, ~3★, "fix timing entirely", never tested vs a real target) and **GPL-3.0** (heavier if sold). Higher/riskier effort. *Borrow the idea, not the codebase.* |
| free-dap ❌ (as base) | Permissive BSD/MIT, clean RP2040 platform — but you lose debugprobe's UART bridge + RTOS scaffolding and rewrite them. Net effort ≈ debugprobe fork with more to write. Good fallback if the GPL/maturity calculus changes. |
| **yapicoprobe** 🔶 | A debugprobe-family fork that **adds MSC drag-n-drop UF2 flashing + RTT-into-CDC + optional sigrok**. Strongly consider forking *this* instead of stock debugprobe after the MVP — it's a strict superset and would make PocketDebugger genuinely better than a stock probe. (License is mixed — verify before shipping.) `jancumps/picoprobe` is a XIAO-RP2040 adaptation worth mining for board bring-up. |

### OLED library: **`daschr/pico-ssd1306`** (MIT)
Near 1:1 with the MicroPython `framebuf` calls PocketTap already uses (`pixel/line/rect/fill_rect/show` → `draw_pixel/draw_line/draw_empty_square/draw_square/ssd1306_show`), owns an in-RAM 1024-byte framebuffer flushed by `ssd1306_show()`, links `hardware_i2c` directly (no HAL to write), matches GP6/GP7 @ 0x3C. Reject u8g2: **no in-tree Pico SDK I2C port** (you'd write+maintain a two-callback HAL), paradigm mismatch (`ClearBuffer/SendBuffer` + font handles), and its headline feature (huge font catalog) is mooted by PocketTap's hand-tuned custom 5×7 `_F5x7` table.
- **Port note:** keep PocketTap's `text_small` manual pixel-loop and drop the `_F5x7` hex table in as a `const uint8_t[]` (lowest-risk). Carry framebuf's 8×8 font as a custom table to preserve exact layout (daschr's built-in is 8×5). Swap `malloc` buffer → static `uint8_t[1024]` (heap-1 / no-malloc friendly). Watch daschr's float-slope `draw_line` (fine for sparklines/cat; drop in 10-line Bresenham if pixel-perfect diagonals matter). Pin a commit (last push 2024-07-08, quiet not dead).

### USB layout
- **DAP v2** (vendor bulk) — untouched, OpenOCD/probe-rs bind to it.
- **CDC0** — the UART↔target telemetry bridge (debugprobe's existing CDC; the bridge core is **already done better** than PocketTap's `select.poll` loop).
- **CDC1** — PocketTap's JSON host-command channel, so `{"cfg":…}` / `{"screen":N}` / `{"q":…}` traffic **never collides** with target UART bytes on CDC0. This dissolves the Python "don't register stdout for POLLOUT" hazard (independent IN/OUT endpoints) and is cleaner than today's `\n`+`{`-prefix interception heuristic. **Host CLI impact:** `host/pockettap_ctl.py` must move from "one serial port" to selecting CDC1 by interface index (macOS shows both as generic `usbmodem` nodes; set distinct iInterface strings + a stable serial number so port order is predictable).

### Core allocation
debugprobe already uses **both** cores (it is FreeRTOS SMP, `configNUMBER_OF_CORES=2` with `vTaskCoreAffinitySet`):
- **Core 1** — DAP command processor + autobaud. **Leave it alone** (probe latency).
- **Core 0** — TinyUSB device task + CDC-UART bridge (highest prio) + watchdog.
- **Add the OLED/SD/RTC dashboard as a *low-priority task pinned to core 0*.** SWD timing lives in PIO hardware (not CPU spin) and DAP is event-driven, so a preemptible low-prio UI task won't starve it — provided it never busy-loops (yield via `vTaskDelay`) and never blocks the UART task. **Do not pin new work to core 1.**
- **Switch the heap from `heap_1` (no `free()`) to `heap_4`** so the dashboard can `malloc`/`free` normally — or keep heap_1 and statically pre-allocate every buffer at boot. Measure heap headroom in the MVP.
- **Resource rule:** the SWD probe owns **`pio0` SM0** (+ autobaud PIO). Dashboard additions must avoid those — use hardware I2C/SPI blocks, or `pio1` if PIO is needed (e.g. a real logic analyzer).

### Pin plan — resolving the total collision
**Every stock debugprobe line collides with PocketTap.** debugprobe `DEBUG_ON_PICO` puts SWCLK=GP2, SWDIO=GP3, RESET=GP1, UART=GP4/GP5 — and PocketTap has SD-SPI SCK=GP2 / MOSI=GP3 / MISO=GP4, target UART0 on GP0/GP1, OLED I2C GP6/GP7. **You cannot keep the stock pin map.** On the XIAO every GPIO is freely routable for PIO (SWD) and UART, so clone `board_pico_config.h` into a XIAO board config and remap:

| Function | Keep / move | Pin |
|---|---|---|
| SD SPI (SCK/MOSI/MISO/CS) | **keep** | GP2 / GP3 / GP4 / GP28 |
| OLED I2C (SDA/SCL) | keep | GP6 / GP7 (shared bus w/ RTC 0x51, buzzer GP29) |
| **Target tap UART0** | keep | GP0 (TX) / GP1 (RX) |
| **SWCLK / SWDIO** | **MOVE to two free XIAO pads** (NOT GP2/GP3) | TBD free pads — must physically reach target SWD test points |
| RESET (optional) | a free pad | TBD |

The hard constraint is physical, not logical: SWD must reach the target's SWCLK/SWDIO test points and SD-SPI must reach the card on non-overlapping pads. **Critical follow-on:** PocketTap's runtime pin-juggling (`apply_signal_generator`, `ensure_sd_pins` — GP28 is *both* PWM-gen-out and SD CS; GP2/3/4 are *both* SD SPI and logic-probe/PWM-meter inputs) relied on the forgiving Python loop. In C with live SWD + live SD logging you need a **statically-reasoned per-pin ownership model**, not re-init-on-demand, or you risk wedging the SD mid-write (corrupt log).

---

## 4. Pros — what the C rewrite buys

- **Real hardware SWD recovery** — halt/erase/flash a wedged target *regardless of its firmware state* via OpenOCD/probe-rs (`probe-rs erase --chip RP2040`). This is the entire point and the one thing MicroPython PocketTap fundamentally cannot do.
- **Native, standard tooling** — driverless binding (DAP v2 + MS OS 2.0 descriptors) to probe-rs (built-in RP2040/RP2350 target descriptions, no `.cfg` files) and OpenOCD. probe-rs's one-shot recovery UX closes most of Black Magic's GDB-on-probe gap, which is *why you can stay on the permissive-BSD debugprobe base* instead of GPL Black Magic.
- **A better bridge than today's** — debugprobe's TinyUSB CDC + PIO/HW-UART + ring buffers beats PocketTap's `select.poll(0)` superloop; independent IN/OUT endpoints kill the POLLOUT hazard.
- **Performance headroom** — DMA'd ADC scope (replaces today's loop-blocking `sleep_us` burst), PIO logic analyzer, non-blocking PWM buzzer envelope — several screens become *better* than the Python original.
- **Upgrade path** — `debugprobe_on_pico2` already exists; RP2350 (520 KB SRAM, dual M33) is a near-free firmware target if/when you spin custom hardware, relieving the SRAM-FIFO pressure.
- **Free upgrades from siblings** — fork yapicoprobe and you also get **MSC drag-n-drop UF2 flashing + RTT** with little extra work.

---

## 5. Cons / costs / risks (incl. devil's advocate)

- **The rewrite delivers ~zero new capability for ~90% of the effort.** The SWD probe is ~0% of the porting work (debugprobe does it). The bulk is faithfully re-implementing 12 screens, the cat mascot, RTC, SD flight-recorder, buzzer, fonts — purely to *match* what already works in MicroPython. Best case = feature parity.
- **You delete your fastest feedback loop.** `mpremote` hot-push (edit→REPL→seconds) becomes edit→CMake→cross-compile→BOOTSEL→drag UF2→reboot→printf. For UI iteration — which a 12-screen dashboard is *all about* — that's a 10–50× per-iteration slowdown.
- **You lose the `try/except` safety net.** PocketTap's whole loop is wrapped in catch-all recovery + fault-storm reboot, which is *why bad bytes / SD hiccups / I2C glitches don't kill it*. C has no equivalent — every SD/I2C/UART/USB call needs explicit return-code handling + `hardware/watchdog`. Pervasive, low-LOC, and **easy to under-do**, risking a device *less* reliable than the one it replaced.
- **Concurrency is the real hard part** (see §2 verdict): USB-coexistence stalls, and splitting RX *capture* (PIO/IRQ/ring-buffer hot path) from RX *analysis* (`feed_watch`'s per-byte `strstr` + freeze ring). Get the producer/consumer decoupling wrong and you drop bytes under load → **false wedge alerts**, i.e. the black box lying about the exact thing it exists to detect.
- **Maintenance burden / regression cliff** — one self-contained `.py` becomes a fork tracking upstream debugprobe + FreeRTOS-Kernel + TinyUSB + Pico SDK submodules, with heap_1 footguns, stack-overflow/priority bugs, and ISR concurrency. Your own notes say the current firmware "works."
- **The headline benefit is already available off-the-shelf for ~$4.** A spare RP2040/Pico flashed with stock `debugprobe_on_pico.uf2` (BOOTSEL + drag, free) gives full OpenOCD/probe-rs target recovery *today* over 3 wires. Two cheap single-purpose tools beat one fragile dual-purpose rewrite — **this is the strongest card against Option 2.** The rewrite is only justified if "one integrated device in one enclosure" is a genuine product requirement, not just elegance.
- **Known upstream flakiness to plan around:** debugprobe SMP flash regression (#189, open), probe-rs↔OpenOCD `CMD_INFO` state conflict requiring a power-cycle if you interleave them (don't), general OpenOCD version-coupling finickiness (#126/#143/#155), RP2350 needs the Raspberry Pi OpenOCD fork.

---

## 6. Effort estimate

Premised on **forking debugprobe** (USB enumeration, CMSIS-DAP, PIO UART bridge come free), one experienced embedded-C dev:

| Workstream | Days |
|---|---|
| USB/architecture integration (graft onto TinyUSB+FreeRTOS, add 2nd CDC for JSON, keep DAP intact, verify OpenOCD + bridge simultaneously) — **the risky chunk** | 4–6 |
| SSD1306 driver + both fonts + all 12 screen renders + cat/splash/transitions (~1500 LOC, volume-bound) | 5–7 |
| FatFs (carlk3 `no-OS-FatFS-SD-SDIO-SPI`) + session logging/rotation/heartbeat + SD explorer/viewer + ENOSPC→`FR_DENIED` remap | 3–4 |
| Background subsystems: ADC scope (+DMA), PWM gen+meter, logic probe, I2C scan, RTC, throughput, button/LED/buzzer | 3–4 |
| Flight-recorder (decoupled lossless RX analysis, wedge/trigger/freeze, alert engine) + host JSON byte-faithful to keep `pockettap_ctl.py` working | 3–4 |
| Config-in-flash struct, fault/watchdog rethink, demo mode, pin-conflict ownership model, on-hardware bring-up | 4–6 |
| **Total** | **≈ 22–31 eng-days (~4.5–6 weeks)** |

A minimal "probe + bridge + logging + 4 core screens" subset is **~10–12 days**; the long tail is reproducing all 12 screens + alert/recorder fidelity. *Confidence: medium — the USB-coexistence line item is the one most likely to blow up.*

### Hardest features (difficulty table)
| Difficulty | Feature | Why hard |
|---|---|---|
| **Hard** | USB composite coexistence | Any blocking call (OLED `show`, SD write, beep, scope burst) stalls USB → probe times out mid-flash. Structural, not a translation. |
| **Hard** | RX capture vs analysis split | Per-byte `strstr` on the IRQ/PIO hot path drops bytes → false wedge alerts. Subtle producer/consumer correctness. |
| **Hard** | Replacing `try/except` forgiveness | No C equivalent; explicit error handling at every call site or the device gets *less* reliable. |
| Medium | Pin-budget arbitration | GP28 = PWM-out *and* SD CS; GP2/3/4 = SD SPI *and* logic/PWM-meter. Needs static ownership, not runtime re-init. |
| Medium | ADC scope, PWM gen+meter | `time_pulse_us` has **no Pico-SDK equivalent** — reimplement via PWM edge-count / PIO freq counter. DMA scope is an upgrade. |
| Medium | SD logging | FatFs not reentrant by default — serialize SD access; remap ENOSPC. |
| Medium | Host JSON protocol | No `json` in C — use **jsmn** (single-header, MIT) to parse; `snprintf` the fixed-shape responses byte-faithfully (`fw:"PocketTap"` token). |
| Easy | 12 screen renders, cat, fonts, sniffer, I2C scan, RTC, LEDs, buttons | Pure framebuf primitives → daschr 1:1. Volume, not difficulty. |

---

## 7. Phased plan / MVP first slice

**Do the gates before porting a single OLED screen — they isolate the only genuinely uncertain risk (SWD↔dashboard concurrency) for hours, not weeks.**

- **Gate 0 — Prove the hardware can probe at all ($0 of porting).** Flash *stock* `debugprobe_on_pico.uf2` onto the PocketTap XIAO (no fork yet). Confirm it enumerates as CMSIS-DAP and that **probe-rs + OpenOCD can halt/erase/flash a *separate* target** through the wiring. Use `jancumps/picoprobe` (XIAO) as the pin/level-shift reference. **If this fails, Option 2 is dead — found out for free.**
- **Gate 1 — Prove coexistence (THE load-bearing unknown).** Fork debugprobe (pin to `2.2.3`), remap SWD off GP2/GP3, add **one low-priority core-0 FreeRTOS task** that drives the SSD1306 (just a "DAP idle/active" status screen) + blinks an LED. Run a **sustained probe-rs/OpenOCD flash loop against a target *while* the OLED refreshes.** Verify: no DAP corruption, no USB stalls, no I2C/SWD interference; measure FreeRTOS heap headroom (decide heap_1 vs heap_4).
- **Gate 2 — Prove the composite + control channel.** Add the **2nd CDC** (per `cdc_dual_ports`), switch device descriptor to `0xEF/0x02/0x01`, confirm **two `/dev/cu.usbmodem*` nodes on macOS** plus the DAP interface, and round-trip one JSON command (`{"q":"status"}`) over CDC1 from an updated `pockettap_ctl.py` — *while the bridge carries target UART on CDC0 and DAP stays bound.*

**Only after all three gates pass**, schedule the full UI port — and at that point **seriously evaluate forking yapicoprobe instead of stock debugprobe** (free MSC-UF2 flash + RTT) and **targeting `debugprobe_on_pico2` / RP2350** for SRAM headroom.

---

## 8. Open questions — verify on hardware before committing

- **macOS dual-CDC enumeration:** does `bDeviceClass=0x00` reliably enumerate **two** CDCs, or is `0xEF/0x02/0x01` required? (Highest-risk item — test both.)
- **SMP flash regression (#189):** is it still open / does it bite your hardware? Decide base tag (`2.2.3` stable vs `master`) accordingly.
- **The RTC silicon:** code reads it as a **PCF8563**-style register map at I2C 0x51 (VL flag = seconds bit7), but project memory calls it **PCF85063A**. Confirm the actual part when wiring the C driver.
- **XIAO RP2040 board specifics:** does its GPIO/LED (GP25/26/17 active-low) and flash layout match debugprobe's RP2040 assumptions? Which two free pads physically reach the target SWD test points without colliding with SD/I2C/UART?
- **Free FreeRTOS heap size** in stock debugprobe (FreeRTOSConfig.h was not read in any report) — drives the heap_1→heap_4 decision; measure in Gate 1.
- **debugprobe `DEBUG_ON_PICO` UART** defaults to **uart1 GP4/GP5**, while PocketTap taps **uart0 GP0/GP1** — confirm the exact board header you base on and that the bridge can be re-pointed to uart0.
- **yapicoprobe license:** verify the mixed-component licenses before adopting it as the base for a potentially-sold product.
- **probe-rs↔OpenOCD interleave conflict:** reproduce the `CMD_INFO` power-cycle issue on your setup so you document the "don't interleave the two hosts" caveat for users.

---

*Generated by a 5-agent research workflow (debugprobe anatomy · OLED-in-C libraries · feature-port inventory · TinyUSB composite feasibility · alternatives + devil's advocate) → synthesis. Claims about specific upstream commits/issues should be re-verified against current `raspberrypi/debugprobe` before acting.*
