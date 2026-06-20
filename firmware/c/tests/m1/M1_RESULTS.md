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

### Remaining in M1 (next increments)
- **SW-watchdog task** — per-task check-in counters; a low-prio task feeds the lone HW WDT only when
  ALL monitored tasks checked in on time → a wedged task reboots the probe (into the crash box).
  Needs its own HIL test (wedge a task → confirm reset; confirm no spurious resets in normal run).
- **`{"q":"bootsel"}`** CDC1 command (`reset_usb_boot`) — lets the probe be reflashed on demand
  without a manual BOOTSEL, removing the dev-loop bottleneck (one manual BOOTSEL needed to deploy it).
- jsmn line-buffered parser replacing `strstr`; `next`/`prev`/`dump`; bounded SPSC UART bridge;
  per-interface USB string descriptors (stable CDC0=UART / CDC1=Control naming).
- error-code + goto-cleanup idiom adopted for new code.
