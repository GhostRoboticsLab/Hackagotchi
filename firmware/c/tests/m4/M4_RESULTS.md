# M4 — Full UI parity (CDC1-driven) — **COMPLETE, HIL-verified (2026-06-21)**

M4 ports the remaining MicroPython OLED-family features to the C firmware. The original drove them as
**button menus**; the probe has **no button** (GP27 became SWDIO at Gate 1), so the redesign is: **actions
over CDC1, state shown on snapshot-fed screens** — the M3 pattern extended. Triage against the LOCKED pin
map dropped the hardware-bound screens (I2C-scan / Oscilloscope / GPIO-mon / PWM-lab / Demo: their pins are
SWD/SD/UART; the scanner would only find our own OLED now). The feasible, valuable set was built:

| Inc | Feature | Shape |
|-----|---------|-------|
| M4.1 | **Hex sniffer** | snapshot gains raw recent bytes; `{"q":"hex"}` toggles SNIFFER ASCII↔hex (5 B/row + ASCII gutter) |
| M4.2 | **Macro sender** | `{"q":"macro","i":N}` sends `TEXT\r\n` out UART0 via the single TX owner; `{"q":"macros"}` lists; MACRO screen |
| M4.3 | **Baud select** | `{"q":"baud","v":N}` (validated set) applied by the UART owner (uart_set_baudrate + rearm); BAUD screen |
| M4.4 | **SD explorer** | `{"q":"ls"}` / `{"q":"cat","i":N,"off":M}` via the SD-task request/snapshot pattern (cat by INDEX → no path traversal); SD-EXPLORER screen |
| M4.5 | **Settings persist** | baud + macros → `config.txt` (KV) on SD; loaded+applied at boot, saved on change; `{"q":"setmacro","i","s"}` |

**Tool screens (MACRO/BAUD/SD-EXPLORER, idx 6-8) are EXCLUDED from the 6 s auto-cycle** (`N_MONITOR=6`) and
reached only via CDC1 nav, so the panel never parks on a menu. **Persistence is on SD, not flash** — a flash
write pauses XIP and would stall the DAP hot path on this single core (R1); the SD task already does blocking
I/O safely off it.

## Concurrency / R1 (the load-bearing parts)
- **Macro TX** goes through the SINGLE uart0 TX owner (`cdc_task`, +3) via a tiny SPSC inject handshake
  (`cdc_uart_inject` producer / `cdc_uart_drain_inject` consumer, `s_inj_n` gate + RELEASE/ACQUIRE fences),
  drained NON-BLOCKING exactly like the host→target path. No second task writes the TX FIFO.
- **Baud** is applied only by the UART owner (`cdc_task`) via a posted request; SWD is a separate PIO so it
  never touches DAP.
- **SD explorer + config** I/O is SD-task-only (FatFs never crosses a task boundary); `ls`/`cat`/`save` use
  the async request → read-on-a-later-call pattern (like `tail`), off the DAP hot path. `cat` is by numeric
  index → `log_NNN.txt`, so there is no filename string to parse and no path-traversal surface.

## HIL (final image `/tmp/hg-build-m4`, I2C1 @ 1 MHz)
- `m4/hex_hil.py` **PASS** — inject "HEXMODE42" → ASCII shows it; `{"q":"hex"}` → `HEX SNIFFER` + `48 45 58 4D 4F | HEXMO`.
- `m4/macro_hil.py` **PASS** — macros loop back through the recorder (proving real transmission); MACRO screen `>2 STATUS`; tool screen NOT auto-cycled; out-of-range → err.
- `m4/baud_hil.py` **PASS** — set 9600, PING loops back at 9600 (UART functional at the new rate), BAUD screen `>9600 *`, invalid rejected, restored.
- `m4/sd_hil.py` **PASS** — `ls` lists 43 logs; `cat` current → on-disk `BLACK BOX` header; missing index → len 0/eof 1; no-index → err.
- `m4/config_hil.py` **PASS** — baud 9600 + macro M4TEST → reboot → both PERSISTED; new session header logs `baud 9600`; restored.
- `m3/screen_hil.py` + `m3/feedback_hil.py` **PASS** (re-run; updated for the variable screen count + a deterministic feedback baseline).

## Closeout — adversarial audit (general-purpose reviewer over `afa3557..HEAD`)
Headline: the riskiest primitives (SPSC macro inject, baud handshake, reading the open-for-append log via a
2nd `f_open`) were **confirmed race-free / safe**. Three findings, all addressed:
- 🔴 **`do_ls_read` OOB** — `o += snprintf()` added the *would-be* length; with `FF_USE_LFN` a card-supplied
  long name matching `log_*.txt` could overrun `s_ls_buf[400]` then write the NUL OOB. **FIXED**: advance `o`
  only when the entry actually fit; stop listing (keep counting) otherwise. `sd_hil` re-verified post-fix.
- 🟠 **`coexist_soak` bar too loose** — my interim change gated on 0-stalls only (retryable WARN-not-FAIL), so
  a real 5-8% regression would pass silently. **FIXED**: restored a HARD ceiling (0 stalls AND fails ≤ 8%);
  the rate is still printed every run with the "run on an idle host" note.
- 🟠 **`hg_config` shared-struct torn read** — writer (TUD) vs readers (dashboard/SD). `baud` is an atomic
  aligned uint32; only macro STRINGS can briefly tear → cosmetic (OLED self-heals; config re-validated on
  load); config edits are infrequent. **DISCLOSED** in the header (kept out of the snapshot deliberately — see
  the contention caveat below). Also fixed two brittle test crash-checks (absolute `crashes==0` → delta-based)
  and a feedback_hil baseline that assumed a fresh boot.

## R1 result + the DAP-contention caveat (user-accepted: "don't gold-plate")
**The 0-STALL invariant held in EVERY soak run today** (3 → 300 retryable fails across builds, ALL 0 stalls,
rec_drop=0, recorder flawless) — the hard correctness gate (no hang/corruption/transfer-desync) is solid.

The **retryable** 0-stall DAP-fail rate (probe-rs USB transfer errors it recovers from; the flash still
succeeds) is dominated by HOST/USB conditions + background SD-DMA bus contention under the *artificial* max-SD
soak load. Bisected: pre-M4 ~1% (3/300) → M4.1 ~5% on an idle host; M4's larger published snapshot + extra
code shifted the XIP layout. A `recorder_copy_raw_tail`-only-when-hex-shown optimization trimmed it (≈16→11).
The rate is **highly host-sensitive** (a concurrent host process pushed one run to 90/300) and **nil in the
real world** (the target is HALTED during a real flash → the recorder is idle then → no SD load). Per the
standing "don't gold-plate" directive on this exact M2 caveat, this is **accepted + documented**, not chased
(the only "real fix" — RAM-pinning the DAP hot path — would fork the pristine upstream `probe.c` and re-spend
the XIP RAM win, which the v1.1 plan rejected).

**Confirmatory clean soak (2026-06-21, both boards power-cycled, host idle): PASS — 13/300 (4.3%), 0 stalls**,
recorder flawless (err=0, logging=1, wedge=0, rec_drop=0, rx 0→317k, on-card tail intact). This is the
final hard-ceiling number; it confirms the ~4% idle-host floor (the earlier 90/300 was a concurrent host
process; 300/300 was a glitched target). The power-cycle restored the target's AHB access port
(`0 MemoryAP (AmbaAhb3)` under both cores — absent while glitched), which is what flash program/verify needs.

**Target-hardware finding (orthogonal to firmware):** this particular target Pico W **re-glitches its QSPI
under SUSTAINED flash hammering** — a fresh power-cycle gives one clean 150-cycle soak, then a back-to-back
second soak brown-out-glitches it again (program/verify fails 100%, **still 0 stalls**). The probe firmware
is provably unaffected: 0 stalls in EVERY run all session, DAP enumerates, `{"q":"status"}` clean + the
dashboard `n` keeps incrementing. For future soak campaigns, power-cycle the target between long runs (or use
a fresh target board); it's a target-board fragility, not a probe defect. The 0-stall correctness invariant
held across every single run regardless.

**Verdict: M4 = COMPLETE.** Hex sniffer · macro sender · baud select · SD explorer · settings persistence,
all CDC1-driven + snapshot-fed, audit-hardened, R1 0-stall-clean. Device on `/tmp/hg-build-m4`.
