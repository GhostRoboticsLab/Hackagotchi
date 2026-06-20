#!/usr/bin/env python3
"""
M1 UART-bridge hardening HIL test — IRQ-driven RX capture into the SPSC ring.
SPDX-License-Identifier: MIT

Falsifiable claim:
  With the PL011 in internal loopback (TX->RX in-chip), a payload written to CDC0 round-trips back to
  the host THROUGH the hardened path: bridge reads CDC0 -> UART TX -> (loopback) -> UART RX -> RX IRQ
  -> SPSC ring -> bridge drains ring -> CDC0. The ring's high-watermark advances and 0 bytes are
  dropped.

Why it can FAIL (not a tautology):
  - If the RX IRQ / ring / drain path is broken, nothing comes back on CDC0 -> FAIL. This is the
    per-run rank-1 signal: cdc_task drains target->host EXCLUSIVELY via uart_bridge_read (spsc_pop),
    so any bytes returned this run necessarily traversed the ring this run.
  - If the ring overflowed, urx_drop > 0 -> FAIL.
  (urx_hw is a MONOTONIC peak that persists for the firmware's uptime, so it is corroborating only,
  NOT a per-run pass/fail signal — a stale peak from earlier traffic would mask a broken run.)

Needs NO external jumper (uses the chip's internal loopback). Uses single held connections (no
reconnect churn, which wedges the macOS USB-CDC driver).

Run (pyserial venv): .venv/bin/python firmware/c/tests/m1/uart_bridge_hil.py
"""
import glob
import sys
import time

import serial  # pyserial

BAUD = 115200
PAYLOAD = b"HACKAGOTCHI_UART_BRIDGE_LOOPBACK_0123456789_abcdefghij\n"


def field_int(reply, key):
    tok = f'"{key}":'
    i = reply.find(tok)
    if i < 0:
        return None
    j = i + len(tok)
    k = j
    while k < len(reply) and (reply[k].isdigit() or reply[k] == "-"):
        k += 1
    try:
        return int(reply[j:k])
    except ValueError:
        return None


def find_ports():
    """Return (data_port=CDC0, ctrl_port=CDC1). CDC1 is the one that answers status."""
    cands = sorted(glob.glob("/dev/cu.usbmodem*"))
    ctrl = None
    for p in cands:
        try:
            with serial.Serial(p, BAUD, timeout=0.6) as s:
                s.reset_input_buffer()
                s.write(b'{"q":"status"}\n')
                s.flush()
                time.sleep(0.5)
                if "Hackagotchi" in s.read(400).decode(errors="replace"):
                    ctrl = p
                    break
        except Exception:
            pass
    if not ctrl:
        return None, None
    data = [p for p in cands if p != ctrl]
    return (data[0] if data else None), ctrl


def ctrl_cmd(c, msg, wait=0.4):
    c.reset_input_buffer()
    c.write(msg.encode())
    c.flush()
    time.sleep(wait)
    return c.read(400).decode(errors="replace").strip()


def main():
    data_port, ctrl_port = find_ports()
    if not ctrl_port:
        print("FAIL: no Hackagotchi control node (CDC1) found")
        return 1
    if not data_port:
        print("FAIL: no second CDC node (CDC0/UART bridge) found")
        return 1
    print(f"CDC0 (UART bridge) = {data_port}")
    print(f"CDC1 (control)     = {ctrl_port}")

    # Open CDC0 first (its DTR resumes the bridge task; its line-coding re-inits the UART), then CDC1.
    with serial.Serial(data_port, BAUD, timeout=1.0) as d, serial.Serial(ctrl_port, BAUD, timeout=1.0) as c:
        time.sleep(0.6)  # let CDC0's line-coding re-init + IRQ re-arm settle

        loop_on = ctrl_cmd(c, '{"q":"uloop_on"}\n')
        print(f"[loopback] uloop_on -> {loop_on}")
        if '"uloop":1' not in loop_on:
            print("FAIL: could not enable UART loopback")
            return 1

        base = ctrl_cmd(c, '{"q":"status"}\n')
        hw0, dr0 = field_int(base, "urx_hw"), field_int(base, "urx_drop")
        print(f"[baseline] urx_hw={hw0} urx_drop={dr0}")
        if hw0 is None or dr0 is None:
            print("FAIL: status has no urx_hw/urx_drop fields — wrong/old firmware")
            ctrl_cmd(c, '{"q":"uloop_off"}\n')
            return 1

        # Write the payload to CDC0; it must come back via the full capture path. Retry up to 3x to
        # ride out transient macOS USB-CDC hiccups (a genuinely broken path fails ALL attempts).
        got = bytearray()
        for attempt in range(3):
            d.reset_input_buffer()
            d.write(PAYLOAD)
            d.flush()
            got = bytearray()
            deadline = time.time() + 2.0
            while time.time() < deadline and len(got) < len(PAYLOAD):
                chunk = d.read(len(PAYLOAD))
                if chunk:
                    got.extend(chunk)
            if bytes(got) == PAYLOAD:
                break
            print(f"  [retry {attempt+1}/3] got {len(got)}B (transient CDC hiccup?), retrying")
        print(f"[roundtrip] sent {len(PAYLOAD)}B, got {len(got)}B: {bytes(got)!r}")

        after = ctrl_cmd(c, '{"q":"status"}\n')
        hw1, dr1 = field_int(after, "urx_hw"), field_int(after, "urx_drop")
        print(f"[after] urx_hw={hw1} urx_drop={dr1}")

        ctrl_cmd(c, '{"q":"uloop_off"}\n')  # cleanup

    ok = True
    if bytes(got) != PAYLOAD:  # per-run rank-1 proof: returned bytes must have traversed the ring
        print("FAIL: round-trip payload mismatch (capture path broken or lossy)")
        ok = False
    if dr1 is None or dr1 != 0:
        print(f"FAIL: ring dropped bytes (urx_drop={dr1})")
        ok = False
    print(f"[corroborate] ring high-watermark {hw0}->{hw1} (monotonic peak — informational only)")

    if ok:
        print(f"\nPASS: full {len(PAYLOAD)}B payload round-tripped through IRQ->ring->drain, 0 drops")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
