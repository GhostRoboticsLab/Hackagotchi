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

### Remaining in M1 (next increments)
- jsmn line-buffered parser replacing `strstr`; `next`/`prev`/`dump`; bounded SPSC UART bridge;
  per-interface USB string descriptors (stable CDC0=UART / CDC1=Control naming).
- error-code + goto-cleanup idiom adopted for new code.
- Watchdog hardening: characterise DAP/UART/DASH cadence under flash load, then monitor them + flip
  the watchdog to armed-by-default.
