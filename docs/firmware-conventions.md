# Hackagotchi firmware — C conventions (the reliability stack, codified)

The conventions the M1 reliability core established, written down so M2+ follow them. These are the
"raise the reliability stack" rules in concrete form. The methodology behind them (gates-first,
evidence ranks, verify-the-verifier) lives in `docs/mcu-bringup-playbook.md`; this file is the
day-to-day coding contract.

## 1. Error handling: error-code + goto-cleanup

New code that acquires **more than one** releasable resource unwinds via a single cleanup label, in
reverse order of acquisition — no nested `if` pyramids, no leaked handle on an early error:

```c
int do_thing(...) {
    int rc = -1;
    FIL *f = NULL;
    if (f_mount(&fs, "", 1) != FR_OK) goto out;          // resource 1
    if (f_open(&file, path, FA_WRITE) != FR_OK) goto unmount;  // resource 2
    if (f_write(&file, buf, n, &bw) != FR_OK || bw != n) goto close;
    rc = 0;
close:   f_close(&file);
unmount: f_unmount("");
out:     return rc;
}
```

- Return an **error code**, not a bool, when the caller can act differently per failure.
- A function that takes **one** resource uses plain early-return (the degenerate case) — that is what
  the M1 modules (`crash_box`, `watchdog_task`, `uart_bridge`, `cdc1_control`) do, since none acquire
  multiple resources. The full goto-cleanup idiom first earns its keep in **M2** (FatFs: mount → open
  → write → close).
- Never `goto` forward over a variable's initialization, and never `goto` backward (no loops).

## 2. Never block on the hot path (anything at or above DAP priority)

Priority order (single-core FreeRTOS, F1-1): UART-bridge +3 > TUD +2 > DAP +1 > dashboard +0, plus the
SW-watchdog at +3. A task at or above DAP must not busy-wait or do slow I/O, or it delays the probe:

- **No `uart_write_blocking` / `f_write` / `ssd1306_show` / `busy_wait` on a +1..+3 task.** The CDC0
  TX path was switched from `uart_write_blocking` to push-only-what-the-FIFO-takes (M1 increment 5)
  for exactly this reason.
- Slow work (SD writes, OLED flush, buzzer) belongs on the **dashboard task (+0)**, which is designed
  to be preemptible and may be starved for seconds under load — that starvation is a *feature*, not a
  wedge (so do **not** watchdog the dashboard task; watchdog TUD instead — it is never legitimately
  starved because DAP is below it).

## 3. Bounded buffers, counted overflow — never silent loss

Every queue/ring/buffer has a fixed cap and a **counter** for what it had to drop, surfaced in the
CDC1 `status` telemetry (`urx_drop`, `utx_drop`, `crashes`, …). A silent drop is a silent pass. The
target-UART RX path is interrupt-driven into a bounded SPSC ring (`spsc_ring.h`) so capture never
depends on poll timing; overflow is counted, not lost-and-forgotten.

## 4. ISR / callback-context buffers go static, not stack (Finding F1-4)

A USB/IRQ callback runs on a small task stack (the TUD task is 512 words) on top of the USB stack's
own call depth. Large locals there overflow it and corrupt adjacent state — the symptom is *not* a
clean crash but, e.g., a corrupted USB endpoint (host `ENXIO`). Put parser token arrays, reply
buffers, DMA scratch, etc. in `static` storage (the callback is single-task, non-reentrant) or in a
dedicated larger stack. See `cdc1_control.c` (jsmn tokens + reply buffers are `static`).

## 5. Firmware self-attestation + machine-checkable telemetry

The running firmware reports its own identity and proof-of-behaviour over CDC1 `status` (build prio,
measured stall, loop counters, fault count, ring drops). This closes provenance gaps (which build is
actually running?) and powers the HIL gates. Prefer a **machine-readable** signal a test can assert on
over an operator eyeball. Every reply is one line of valid JSON.

## 6. Overlay discipline

The probe is an overlay of upstream debugprobe (stable tag). Keep per-file diffs minimal and tagged
`// [HACKAGOTCHI]`; new functionality goes in **new** files (`crash_box`, `watchdog_task`,
`uart_bridge`, `spsc_ring`, `cdc1_control`) wherever possible, so an upstream bump is a small re-diff.
Vendored third-party code is single-header where possible and listed in `THIRD-PARTY-NOTICES.md`.

## 7. Prove it on hardware (gates-first)

No architectural claim is "done" until a falsifiable HIL test asserts it from the right signal and can
emit FAIL. Host-test pure logic off-target (`tests/m1/ring_test.c`); HIL-test integration on the
device (`tests/m1/*_hil.py`). Decode the built artifact (`nm`/`strings`/`addr2line`/descriptor), don't
trust the source diff. Disclose every deferred item in the verdict.
