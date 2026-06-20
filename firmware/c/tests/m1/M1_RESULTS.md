# M1 — Probe + bridge + control core: results

The plan-of-record milestone after the three gates (`docs/engineering-plan.md` §M-table, `docs/TODO.md`).
M1 is the **reliability/control core**, NOT the screen port (screens are M3). Built in provable
increments, each with a falsifiable HIL claim — same discipline as the gates
(`../gates/GATE_RESULTS.md`, `docs/mcu-bringup-playbook.md`).

---

## Increment 1 — Crash box (post-mortem fault diagnosis) — **PASS (live, 2026-06-20)**

**Falsifiable claim.** A fault on the probe (HardFault, or a FreeRTOS-detected stack-overflow /
malloc-failure) is captured to **reset-surviving storage**, the probe **auto-reboots and
re-enumerates**, and the post-mortem (kind, a plausible PC, a count that advances across the reboot)
is **surfaced afterwards** over CDC1 `{"q":"lastfault"}` and the boot stdio log. Matters because the
probe normally runs **probe-less** — nothing is attached to debug IT, so a silent fault otherwise
vanishes without a trace.

**Rig.** XIAO RP2040 = probe (DUT), in the locked Gate-1/2 config; Pico W target on the SWD pins.
Firmware `/tmp/hg-build-m1` (normal product config: DASH below DAP, `stall_cfg=0`), flashed via
`picotool load -x`. Provenance: the running firmware self-attests over CDC1
(`fw=Hackagotchi, prio=0, stall_cfg=0`), and the `crashes` counter + `lastfault` record are new in
this build (an old image has no `crashes` field → the test FAILs fast on the wrong image).

**Implementation** (overlay; `src/crash_box.{c,h}`, wired in `src/main.c` + `src/cdc1_control.c`):
- `isr_hardfault` overrides the pico-sdk weak vector — a naked M0+ trampoline that selects the
  faulting stack pointer (PSP/MSP per EXC_RETURN bit 2) and tail-calls the C handler, which records
  the 8-word exception frame `[r0..r3,r12,lr,pc,xpsr]`.
- Record lives in `.uninitialized_data` (NOLOAD) — **verified** outside `[__bss_start__,__bss_end__]`
  so crt0 never zeroes it and the `copy_to_ram` bootrom load never overwrites it → survives a
  watchdog reboot. Mirrored into the RP2040 watchdog scratch registers as a guaranteed cross-check.
- The two FreeRTOS hooks (`configCHECK_FOR_STACK_OVERFLOW=2`, `configUSE_MALLOC_FAILED_HOOK=1` — both
  already enabled upstream) now route into the same box instead of a bare `panic()` (and the upstream
  `*pcTaskName` `%s` bug is fixed in passing).
- CDC1 control surface: `{"q":"lastfault"}` reads the record; `{"q":"crash"}` forces a real HardFault
  (store to unmapped `0xF0000000`) for the HIL self-test; `status` gains a `crashes` counter.

**Machine assertion** (`tests/m1/crashbox_hil.py`, and it CAN fail): baseline status+lastfault →
force `crash` → wait for re-enumeration → assert `lastfault` reports `hardfault`, PC ≠ 0, and
`crashes` advanced by exactly 1. If `.uninitialized_data` had NOT survived, `lastfault` would read
`none` post-reboot → FAIL.

**Result (live).**
```
[baseline]  status   : {...,"prio":0,"crashes":0}
[baseline]  lastfault: {"fault":none}
[fault]     {"q":"crash"} -> HardFault + auto-reboot
[recovered] status   : {...,"up":3,"n":13,"crashes":1}     # up/n reset => genuinely rebooted
[recovered] lastfault: {"fault":{"kind":"hardfault","count":1,"pc":"0x20000d90",
                                 "lr":"0x2000c6d1","xpsr":"0x81000000","task":""}}
PASS: HardFault captured (PC=0x20000d90), survived reboot, count 0->1, re-enumerated
```
Rank-2 cross-checks: `arm-none-eabi-objdump` confirms `isr_hardfault` is our PSP/MSP trampoline (not
the weak bkpt) and its literal targets `crash_box_from_fault`; `nm` confirms `g_box @ 0x200000c0` is
below `__bss_start__ @ 0x2000ee40` (outside the bss clear); `addr2line 0x20000d90` →
`tud_cdc_rx_cb @ cdc1_control.c` (the deliberate fault store — the captured PC is accurate, not
garbage); `probe-rs list` still binds `Hackagotchi Probe (CMSIS-DAP)` after the fault cycle.

**Disclosed (not blockers).** The two SW hooks share the exact `record_common → reboot_now` path the
HardFault test exercises, but were not *independently* force-triggered (no on-demand stack-overflow /
malloc-fail injector yet). `lastfault` clean-state prints `{"fault":none}` — `none` is unquoted (not
strict JSON); cosmetic, fix to `null` next flash. Crash box is HardFault-only by design on M0+
(single fault vector).

**Verdict: PASS** — crash box captures + survives + surfaces a fault at rank-1, with the probe
recovering and DAP intact.

---

## Increment 2 — SW watchdog + self-reflash (`{"q":"bootsel"}`) — **PASS (live, 2026-06-20)**

> **SUPERSEDED by Increment 5(c):** this increment introduced the watchdog **disarmed by default** (a
> conservative dev-state) and the transcript below was captured against that build. The **as-shipped
> posture is now ARMED BY DEFAULT** — see Increment 5(c) for the armed-by-default code, the re-run
> `watchdog_hil.py` (wd_armed=1 at boot, no manual arm), and the strengthened safety soak. The
> mechanism (monitor TUD, record `kind=watchdog`, reboot) is unchanged.

**Falsifiable claims.** (a) An ARMED software watchdog detects the high-priority TUD task wedged,
records `kind=watchdog, task=TUD` into the crash box, and reboots the re-enumerating probe. (b)
`{"q":"bootsel"}` drops the probe to BOOTSEL so it can be reflashed via `picotool` with **no physical
button** — removing the dev-loop bottleneck (debugprobe has no reset interface).

**Implementation** (`src/watchdog_task.{c,h}`, `src/crash_box.*`, `src/cdc1_control.c`, `src/main.c`):
- SW watchdog at the HIGHEST app priority (`tskIDLE+3`) so it is never starved and can preempt a
  wedged lower task. Monitors the **TUD** task via a heartbeat counter `g_tud_checkin` bumped each
  `usb_thread` loop — deliberately NOT a low-prio task (which legitimately starves under flash load →
  would false-reset mid-flash). Stall window 4 s; HW WDT 8 s backstops the watchdog task itself dying.
- **Disarmed by default**: the HW WDT is not enabled until `{"q":"wd_arm"}` — a fresh flash cannot
  reboot-loop. On a caught stall → `crash_box_record_watchdog()` (new `CRASH_WATCHDOG` kind) → reboot.
- `{"q":"bootsel"}` → `reset_usb_boot(0,0)`. `{"q":"wd_test"}` sets `g_tud_wedge` so `usb_thread`
  self-wedges (HIL hook). `status` gains `wd_armed`; `lastfault` clean state is now valid JSON (`null`).

**Machine assertions** (both can fail): `tests/m1/watchdog_hil.py` (arm → wedge → assert
re-enumeration + `kind=watchdog/task=TUD` + count+1 + disarmed-after); the bootsel autonomy loop
(send `bootsel` → confirm BOOTSEL → `picotool load` with no button → device responds).

**Result (live).**
```
watchdog: [baseline wd_armed=0] arm -> wd_armed=1 -> wd_test (wedge TUD)
          -> reboot (up/n reset) -> lastfault {"kind":"watchdog","count":2,"task":"TUD"}, crashes 1->2,
          wd_armed back to 0 -> PASS
crashbox regression on this image: hardfault captured, count 2->3 -> PASS
bootsel:  {"q":"bootsel"} -> dropped to BOOTSEL (picotool reachable, no serial) -> picotool load -x
          (NO button) -> device boots, status responds, probe-rs binds "Hackagotchi Probe (CMSIS-DAP)"
          -> PASS  (dev loop now hands-free)
```

**Disclosed (not blockers).** Watchdog ships disarmed (a dev/test state until proven non-false-positive
under real flash load → then flip default-on). Only TUD is monitored so far (DAP/UART/DASH check-ins
deferred — DAP needs an upstream-task overlay; DASH would false-positive on priority starvation). The
`bootsel` command only helps when firmware is alive enough to service CDC1; a pre-USB-enum fault still
needs the physical button (see `docs/recovery-model.md`).

**Verdict: PASS** — watchdog catches a wedged task at rank-1; the probe is now self-reflashable.

---

## Increment 3 — jsmn control parser (replaces strstr) — **PASS (live, 2026-06-20)**

**Falsifiable claim.** CDC1 commands are matched on the STRUCTURED value of the `"q"` key via a real
JSON parse (jsmn) over a bounded line buffer — so an input the strstr prototype would have
FALSE-matched (e.g. `{"q":"statusx"}`, `{"note":"status please"}`) is now correctly rejected, and a
request split across two USB packets is reassembled.

**Implementation** (`src/jsmn.h` vendored MIT, `src/cdc1_control.c`, `src/main.c`):
- jsmn (`zserge/jsmn`, header-only, `JSMN_STATIC`) parses each line; `get_q()` extracts `"q"` and
  dispatches by exact `strcmp`. Bounded `LINE_MAX=128` line buffer accumulates CDC1 bytes until `\n`
  (reassembles fragmented requests; over-long lines drop with `{"err":"toolong"}`).
- Commands: `status`/`dump`/`lastfault`/`wd_arm`/`next`/`prev` (reply) + `crash`/`wd_test`/`bootsel`
  (reboot, no reply). Errors: `badjson`/`noq`/`unknown`. `lastfault` clean state now valid JSON (`null`).
  `status` gains `page`; `next`/`prev` move a page-nav index (M3 dashboard will consume it).

**Finding F1-4 (the bug this increment hit + fixed): a JSON parser on the small USB-task stack
overflows it.** First cut put jsmn's `jsmntok_t[16]` (256 B) + nested 200 B reply buffers (~0.5 KB of
leaf locals) on the `configMINIMAL_STACK_SIZE` (1 KB) TUD task stack, on top of TinyUSB's own call
depth → overflow → corrupted USB endpoint state → the host saw `[Errno 6] Device not configured`
(ENXIO) on CDC1 reads. Tell-tale: the **shallow** `bootsel` path worked while the **deeper** `status`
path (extra reply buffer) failed — same parse, different stack peak. Fix: move the token + reply
buffers to `static` (the rx callback runs only in the single, non-reentrant TUD task) and bump the TUD
stack to 512 words. **Debug note:** isolated firmware-vs-host by reflashing the known-good prior image
(its CDC1 read fine) and by observing the bug survived a physical replug — ruling out the macOS
USB-CDC host wedge it first looked like.

**Machine assertion** (`tests/m1/jsmn_hil.py`, can fail): asserts valid commands dispatch, the two
strstr-trap inputs return an error (NOT a status reply), malformed JSON → `badjson`, and a fragmented
request is reassembled.

**Result (live, m1d image).** All checks PASS: `status`/`dump`/`lastfault`/`next`+`prev` work;
`{"q":"statusx"}`→`{"err":"unknown"}`, `{"note":"status please"}`→`{"err":"noq"}` (strstr would have
matched both); `badjson`/`unknown` errors correct; fragmented `{"q":"sta`+`tus"}` reassembled.
Regression: crash box (count→2) + watchdog (kind=watchdog/TUD, count→3) still pass; DAP still binds.

**Disclosed (not blockers).** `next`/`prev` move a page index nothing consumes yet (M3). The UART
bridge (CDC0) is still upstream's; the bounded-SPSC-ring hardening + per-interface USB string
descriptors are not done.

**Verdict: PASS** — structured JSON control dispatch verified at rank-1, including the strstr
false-positive rejection that is the point of the increment.

---

## Increment 4 — SPSC UART-bridge hardening (IRQ-driven RX) — **PASS (live, 2026-06-20)**

**Falsifiable claim.** Target→host UART capture is interrupt-driven into a bounded SPSC ring (not
polled into a 32-byte buffer that drops bytes between polls), and a payload round-trips through the
full path — CDC0 → UART TX → (PL011 internal loopback) → UART RX → RX IRQ → ring → bridge drains →
CDC0 — with the ring high-watermark advancing and 0 drops.

**Problem fixed.** Stock debugprobe `cdc_task()` polls `uart_is_readable()` into a 32-byte buffer once
per interval; the 32-byte HW FIFO overflows between polls at speed (its own comment: "reading from a
firehose"), silently losing target bytes — fatal for a black-box recorder.

**Implementation** (`src/spsc_ring.h`, `src/uart_bridge.{c,h}`, `src/cdc_uart.c`):
- `spsc_ring.h`: header-only lock-free SPSC byte ring (release/acquire fences order data vs head/tail;
  drop-on-full counted, never silent). Hardware-independent so the firmware + the host unit test
  compile the SAME code.
- `uart_bridge.c`: the UART RX IRQ (producer) drains the HW FIFO into a 4 KB ring the instant bytes
  arrive; `cdc_task()` (consumer) drains the ring → CDC0. Re-armed after a baud-change UART re-init.
- Telemetry surfaced in `status`: `urx_drop` (ring overflow), `urx_hw` (ring high-watermark), and
  `utx_drop` (host→target overflow — upstream counted it but never exposed it; that dead-variable
  `-Wall` warning is now fixed by surfacing it).
- `uloop_on`/`uloop_off` toggle the PL011 internal loopback (LBE) — a jumper-free HIL self-test.

**Machine assertions (two, both can fail).**
- Host: `tests/m1/ring_test.c` — `cc -I src ... ring_test.c` — 6/6 (FIFO order, full+drops,
  wraparound, partial pop, high-watermark). Off-target proof of the ring logic.
- HIL: `tests/m1/uart_bridge_hil.py` — enable loopback, write a 55 B payload to CDC0, assert it
  returns byte-identical, `urx_hw>0`, `urx_drop==0`.

**Result (live, m1e).** Host ring test 6/6 PASS. HIL: payload round-tripped byte-identical
(`urx_hw 16→16`, 0 drops). Regression: jsmn control, crash box (count→4), watchdog (kind=watchdog/TUD,
count→5) all PASS; DAP still binds.

**Disclosed (not blockers).** The loopback test proves the capture path is functional + lossless at
its rate; a high-baud *burst*-loss A/B (the original firehose scenario) wasn't run — no fast external
UART source on the bench — but the architecture prevents it by construction (the IRQ empties the HW
FIFO immediately rather than once per poll). The host→target (TX) path still uses
`uart_write_blocking` for ≤16 B batches (bounded; not the documented loss path). On host disconnect
the ring fills then drops-newest (counted); an M2 recorder draining to SD changes that.

**Verdict: PASS** — target-UART capture is now interrupt-driven + bounded, proven end-to-end at
rank-1 with a host-tested ring underneath.

---

## Increment 5 — closeout: USB strings, non-blocking TX, watchdog arm-by-default — **PASS (live, 2026-06-20)**

**(a) Per-interface USB string descriptors — already in place (Gate-2), verified.** CDC0 `iInterface`=6
"Hackagotchi UART", CDC1 `iInterface`=7 "Hackagotchi Control" (`usb_descriptors.c:134,136,169-170`),
confirmed in the artifact. Caveat: macOS derives the `/dev/cu.usbmodem` suffix from serial+interface
number, NOT `iInterface`, so the node name is unchanged on macOS (Linux/Windows surface the names);
role is still reliably determined by behaviour (CDC1 answers `status`).

**(b) Non-blocking host→target TX.** Replaced `uart_write_blocking` (busy-waited the +3 bridge task up
to ~133 ms at 1200 baud, above DAP) with push-only-what-the-TX-FIFO-takes; the rest stays in the CDC
FIFO (USB back-pressures the host). Artifact: **0 `uart_write_blocking` refs in `cdc_task`**. The
loopback HIL (which drives host→CDC0→TX) still round-trips byte-identical.

**(c) Watchdog armed by default — priority-argued + soak-corroborated.** `s_armed` defaults true. The
safety guarantee is the PRIORITY argument: it monitors TUD (prio +2); DAP (prio +1) is below it, so
flash load can never starve TUD, and TUD goes silent only on a true wedge. (A soak can't *prove* the
absence of a false-fire margin — it corroborates.) Verified **both directions**, re-run against the
armed-by-default build:
- FIRES on a real wedge — `watchdog_hil.py` (wd_armed=1 at boot, no manual arm; wd_test wedges TUD →
  `kind=watchdog/task=TUD` → reboot → wd_armed=1 again).
- Does NOT false-fire under load — `watchdog_soak.py` (strengthened to load the MONITORED task: a
  background DAP flash thread **and** a concurrent CDC0 loopback firehose hammering TUD; no-op runs are
  rejected by requiring real flashes): **120 flashes [0 failed] + 44 KB CDC firehose, `up` 41→122
  monotonic, `crashes` steady at 9, `wd_armed` held 1.** (Also a heavy DAP↔CDC coexistence pass.)

**(d) Error-code + goto-cleanup idiom** — codified as the project convention in
`docs/firmware-conventions.md` (M1 modules are single-resource/early-return; the full idiom earns its
keep at M2's FatFs). The same doc captures the other M1 reliability rules (no-blocking-above-DAP,
bounded+counted buffers, static-not-stack-in-callbacks per F1-4, self-attestation, overlay discipline).

**Verdict: PASS.**

---

## OVERALL — M1 (Probe + bridge + control core): **COMPLETE / PASS** (2026-06-20)

All M1 deliverables done and HIL-verified on hardware:

| Deliverable | Increment | Proof |
|---|---|---|
| Fault handler + crash box; stack/malloc hooks | 1 | `crashbox_hil.py` (capture survives reboot) |
| SW-watchdog (+ armed-by-default) | 2, 5 | `watchdog_hil.py` (fires) + `watchdog_soak.py` (no false-fire) |
| jsmn CDC1 control (status/next/prev/dump) | 3 | `jsmn_hil.py` (structured dispatch, strstr-traps rejected) |
| Bounded SPSC UART bridge + non-blocking TX | 4, 5 | `ring_test.c` (host) + `uart_bridge_hil.py` (loopback) |
| Per-interface USB string descriptors | 5 (Gate-2) | artifact-decoded |
| error-code + goto-cleanup idiom | 5 | `docs/firmware-conventions.md` |

**Findings recorded:** F1-1..F1-3 (gates), **F1-4** (JSON parser locals overflow the small TUD task
stack → ENXIO; fix = static buffers + bigger stack).

**Plan reconciliations (intentional deviations from `docs/engineering-plan.md`):**
- **Priority order:** the plan §4.1 sketches TinyUSB > UART-bridge; the fork keeps upstream debugprobe's
  **UART-bridge (+3) > TUD (+2) > DAP (+1) > dashboard (+0)** (UART must preempt USB or bytes are lost).
  The watchdog being above this whole stack and monitoring TUD is unchanged. (Noted in
  `docs/firmware-conventions.md` §2.)
- **Ceedling/Unity host-test CI:** the plan wants a host-test CI job; M1 ships a host test
  (`ring_test.c`, run via `cc`) but not yet a Ceedling CI job — it lands with **M2**, when the
  log-rotation / wedge-detector logic gives it more to cover.

**Disclosed deferrals (carried to M2+, not blockers):** high-baud burst-loss A/B not run (no fast UART
source on the bench; the IRQ architecture prevents it by construction); DAP/UART/DASH not individually
watchdog-monitored (TUD-keystone is the correct signal — DASH is starvable by design, UART is
suspendable, DAP is upstream; per-DAP-progress monitoring is a possible M2 refinement); the soak left
the target Pico W holding `blink_a.elf` (it's the test mule / M2 SWD target — restore PicoInky if a
dashboard mule is wanted).

**Audit:** an adversarial 3-lens audit (`audit-m1-complete`) flagged the above as test-rigor/doc
issues (no missing deliverables); all were addressed — soak strengthened (concurrent TUD+DAP load,
no-op rejected), `urx_hw` demoted to corroborating (round-trip is the per-run rank-1 signal), crash-box
PC range-checked, "soak-proven" → "priority-argued + soak-corroborated", disarmed→armed docs reconciled.

**Cleared to start M2** (SD + black-box logging — the recorder drains the same `spsc_ring`).
