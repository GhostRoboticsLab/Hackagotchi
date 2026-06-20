#!/usr/bin/env python3
"""
M1 reliability-core HIL test — the software watchdog.  SPDX-License-Identifier: MIT

Falsifiable claim:
  When ARMED, the SW watchdog detects the high-priority TUD task wedged, records the reason
  (kind=watchdog, task=TUD) into the crash box, and reboots the probe — which re-enumerates.

Why this can FAIL (not a tautology):
  - If the watchdog never fires, the wedged TUD task means USB stays dead -> no re-enumeration -> FAIL.
  - If it reboots but doesn't record kind=watchdog/task=TUD, the crash-box path is wrong -> FAIL.
  - Disarmed-by-default safety: wd_armed must read 0 at boot (no HW WDT until armed).

Run (pyserial venv): .venv/bin/python firmware/c/tests/m1/watchdog_hil.py
"""
import glob
import sys
import time

import serial  # pyserial

BAUD = 115200


def query(port, msg, wait=0.6):
    try:
        with serial.Serial(port, BAUD, timeout=wait) as s:
            s.reset_input_buffer()
            s.write(msg.encode())
            s.flush()
            time.sleep(wait)
            return s.read(512).decode(errors="replace").strip()
    except Exception:
        return ""


def find_control_port(timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        for p in sorted(glob.glob("/dev/cu.usbmodem*")):
            r = query(p, '{"q":"status"}\n', wait=0.5)
            if "Hackagotchi" in r:
                return p, r
        time.sleep(0.5)
    return None, None


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


def main():
    print("== M1 software-watchdog HIL test ==")

    port, status = find_control_port()
    if not port:
        print("FAIL: no Hackagotchi CDC1 control node found")
        return 1
    print(f"[baseline] {port}  {status}")

    if field_int(status, "wd_armed") is None:
        print("FAIL: status has no 'wd_armed' field — wrong/old firmware")
        return 1
    if field_int(status, "wd_armed") != 0:
        print("FAIL: watchdog should be DISARMED at boot (safety) but wd_armed != 0")
        return 1
    crashes0 = field_int(status, "crashes")

    # arm enforcement
    armed = query(port, '{"q":"wd_arm"}\n')
    print(f"[arm] reply: {armed}")
    status_armed = query(port, '{"q":"status"}\n')
    if field_int(status_armed, "wd_armed") != 1:
        print(f"FAIL: watchdog did not report armed after wd_arm ({status_armed})")
        return 1
    print(f"[arm] confirmed wd_armed=1")

    # wedge the TUD task -> the armed watchdog must catch it and reboot
    print('\n[wedge] sending {"q":"wd_test"} -> TUD task wedges; watchdog should reboot in ~4-8s ...')
    query(port, '{"q":"wd_test"}\n', wait=0.3)

    time.sleep(5.0)  # > WD_TUD_STALL_MS (4s)
    print("[wedge] waiting for re-enumeration ...")
    port2, status2 = find_control_port(timeout=30)
    if not port2:
        print("FAIL: probe did not re-enumerate — watchdog did NOT catch the wedged TUD task")
        return 1
    print(f"[recovered] {port2}  {status2}")

    last = query(port2, '{"q":"lastfault"}\n')
    print(f"[recovered] lastfault: {last}")
    crashes1 = field_int(status2, "crashes")

    ok = True
    if '"kind":"watchdog"' not in last:
        print("FAIL: lastfault did not report kind=watchdog")
        ok = False
    if '"task":"TUD"' not in last:
        print("FAIL: lastfault did not name the stalled task (TUD)")
        ok = False
    if crashes0 is None or crashes1 is None or crashes1 != crashes0 + 1:
        print(f"FAIL: crash count did not advance by 1 ({crashes0} -> {crashes1})")
        ok = False
    if field_int(status2, "wd_armed") != 0:
        print("FAIL: watchdog should be disarmed again after the reboot")
        ok = False

    if ok:
        print(f"\nPASS: armed watchdog caught wedged TUD, recorded kind=watchdog/task=TUD, "
              f"count {crashes0}->{crashes1}, probe re-enumerated on {port2}")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
