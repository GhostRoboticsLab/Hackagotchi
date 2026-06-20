#!/usr/bin/env python3
"""
M1 watchdog arm-by-default SAFETY soak.  SPDX-License-Identifier: MIT

Falsifiable claim:
  With the SW watchdog ARMED BY DEFAULT, sustained heavy load (repeated target flashes over DAP +
  the USB traffic they drive) does NOT spuriously reboot the probe — `up` only ever increases and the
  `crashes` counter never increments. (If a flash could starve the monitored TUD task past the 4 s
  stall window, the watchdog would fire: `up` would reset and `crashes` would jump -> FAIL.)

This is the "characterise under flash load" proof behind flipping the watchdog to armed-by-default.

Run (pyserial venv): .venv/bin/python firmware/c/tests/m1/watchdog_soak.py [cycles]
  (run from firmware/c so the blink fixtures resolve)
"""
import glob
import subprocess
import sys
import time

import serial  # pyserial

BAUD = 115200
FIX = ["tests/gates/fixtures/blink_a.elf", "tests/gates/fixtures/blink_b.elf"]


def find_ctrl(timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        for p in sorted(glob.glob("/dev/cu.usbmodem*")):
            try:
                with serial.Serial(p, BAUD, timeout=0.5) as s:
                    s.reset_input_buffer()
                    s.write(b'{"q":"status"}\n')
                    s.flush()
                    time.sleep(0.5)
                    if "Hackagotchi" in s.read(400).decode(errors="replace"):
                        return p
            except Exception:
                pass
        time.sleep(0.5)
    return None


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


def status(s):
    s.reset_input_buffer()
    s.write(b'{"q":"status"}\n')
    s.flush()
    time.sleep(0.5)
    return s.read(400).decode(errors="replace").strip()


def main():
    cycles = int(sys.argv[1]) if len(sys.argv) > 1 else 25
    port = find_ctrl()
    if not port:
        print("FAIL: no control node")
        return 1

    with serial.Serial(port, BAUD, timeout=1.2) as s:
        base = status(s)
        up0, cr0, armed = field_int(base, "up"), field_int(base, "crashes"), field_int(base, "wd_armed")
        print(f"[baseline] {base}")
        if armed != 1:
            print("FAIL: watchdog is not armed by default (wd_armed != 1)")
            return 1
        print(f"[baseline] up={up0} crashes={cr0} armed={armed}; soaking {cycles} flash cycles...")

        last_up = up0
        flashes_ok = 0
        for i in range(cycles):
            elf = FIX[i % 2]
            r = subprocess.run(["probe-rs", "download", "--chip", "RP2040", elf],
                               capture_output=True, text=True, timeout=60)
            if r.returncode == 0:
                flashes_ok += 1
            # check probe health after each flash
            st = status(s)
            up, cr = field_int(st, "up"), field_int(st, "crashes")
            tag = "ok" if r.returncode == 0 else f"flash-rc={r.returncode}"
            print(f"  cycle {i+1:2d}/{cycles} [{tag}] up={up} crashes={cr}")
            if up is None or cr is None:
                print("FAIL: lost the probe (no status) mid-soak")
                return 1
            if cr != cr0:
                print(f"FAIL: crashes incremented {cr0}->{cr} — the armed watchdog (or a fault) FIRED")
                return 1
            if up < last_up:
                print(f"FAIL: up went backwards {last_up}->{up} — the probe REBOOTED (spurious watchdog)")
                return 1
            last_up = up

        final = status(s)
        up1, cr1 = field_int(final, "up"), field_int(final, "crashes")
        print(f"[final] {final}")

    print(f"\nPASS: {flashes_ok}/{cycles} flashes; armed watchdog did NOT false-fire "
          f"(up {up0}->{up1} monotonic, crashes steady at {cr1})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
