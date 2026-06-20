#!/usr/bin/env python3
"""
M1 reliability-core HIL test — the crash box.  SPDX-License-Identifier: MIT

Falsifiable claim:
  A forced HardFault on the probe is captured to RESET-SURVIVING storage, the probe auto-reboots and
  re-enumerates, and the captured post-mortem (kind=hardfault, a plausible PC, an incremented count)
  is surfaced afterwards over CDC1 `{"q":"lastfault"}`.

Why this can FAIL (it is not a tautology):
  - If `.uninitialized_data` did NOT actually survive the watchdog reboot, `lastfault` comes back
    "none" after the reboot  -> FAIL.
  - If the fault wedged the probe instead of rebooting it, it never re-enumerates -> FAIL.
  - If the crash counter doesn't advance, nothing was recorded -> FAIL.

Run (pyserial venv): .venv/bin/python firmware/c/tests/m1/crashbox_hil.py
"""
import glob
import sys
import time

import serial  # pyserial

BAUD = 115200


def query(port, msg, wait=0.6):
    """Open port, send one line, return the reply text (or '' on any error)."""
    try:
        with serial.Serial(port, BAUD, timeout=wait) as s:
            s.reset_input_buffer()
            s.write(msg.encode())
            s.flush()
            time.sleep(wait)
            return s.read(512).decode(errors="replace").strip()
    except Exception:
        return ""


def find_control_port(timeout=25):
    """Return (port, status_reply) for the node that answers status as Hackagotchi (= CDC1)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        for p in sorted(glob.glob("/dev/cu.usbmodem*")):
            r = query(p, '{"q":"status"}\n', wait=0.5)
            if "Hackagotchi" in r:
                return p, r
        time.sleep(0.5)
    return None, None


def field_int(reply, key):
    """Cheap int extractor for "key":N (no full JSON parse — replies are flat)."""
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
    print("== M1 crash-box HIL test ==")

    port, status = find_control_port()
    if not port:
        print("FAIL: no Hackagotchi CDC1 control node found")
        return 1
    print(f"[baseline] control port {port}")
    print(f"[baseline] status   : {status}")

    crashes0 = field_int(status, "crashes")
    last0 = query(port, '{"q":"lastfault"}\n')
    print(f"[baseline] lastfault: {last0}")
    print(f"[baseline] crashes  : {crashes0}")
    if crashes0 is None:
        print("FAIL: status has no 'crashes' field — wrong/old firmware")
        return 1

    # --- force a real HardFault on the probe ---
    print("\n[fault] sending {\"q\":\"crash\"} -> probe should HardFault + auto-reboot ...")
    query(port, '{"q":"crash"}\n', wait=0.4)  # no meaningful reply; the device faults

    # Let the port drop, then wait for re-enumeration.
    time.sleep(2.0)
    print("[fault] waiting for re-enumeration ...")
    port2, status2 = find_control_port(timeout=30)
    if not port2:
        print("FAIL: probe did not re-enumerate after the fault (wedged, not rebooted)")
        return 1
    print(f"[recovered] control port {port2}")
    print(f"[recovered] status   : {status2}")

    last1 = query(port2, '{"q":"lastfault"}\n')
    print(f"[recovered] lastfault: {last1}")
    crashes1 = field_int(status2, "crashes")
    print(f"[recovered] crashes  : {crashes1}")

    # --- assertions ---
    ok = True
    if '"kind":"hardfault"' not in last1:
        print("FAIL: lastfault kind != hardfault (crash box did NOT survive the reboot)")
        ok = False
    pc = None
    i = last1.find('"pc":"')
    if i >= 0:
        pc = last1[i + 6 : last1.find('"', i + 6)]
    pcval = int(pc, 16) if pc else 0
    # The copy_to_ram image runs from SRAM (0x20000000-0x20042000); a sane captured PC lands there,
    # not at 0 or some wild address — turns the PC check from 'nonzero' into 'plausible code address'.
    if not (0x20000000 <= pcval < 0x20042000):
        print(f"FAIL: captured PC {pc} is not a plausible SRAM code address (garbage capture?)")
        ok = False
    if crashes1 is None or crashes0 is None or crashes1 != crashes0 + 1:
        print(f"FAIL: crash count did not advance by 1 ({crashes0} -> {crashes1})")
        ok = False

    if not ok:
        return 1
    print(f"[hardfault] PASS: PC={pc}, survived reboot, count {crashes0}->{crashes1}")

    # --- second fault path: force a malloc failure (proves the FreeRTOS malloc hook -> crash box) ---
    print("\n[oom] sending {\"q\":\"oom_test\"} -> exhaust FreeRTOS heap -> mallocfail hook + reboot ...")
    query(port2, '{"q":"oom_test"}\n', wait=0.4)
    time.sleep(2.0)
    port3, status3 = find_control_port(timeout=30)
    if not port3:
        print("FAIL: probe did not re-enumerate after the OOM fault")
        return 1
    last_oom = query(port3, '{"q":"lastfault"}\n')
    crashes2 = field_int(status3, "crashes")
    print(f"[oom] lastfault: {last_oom}")
    if '"kind":"mallocfail"' not in last_oom:
        print("FAIL: OOM did not record kind=mallocfail (malloc hook -> crash box path broken)")
        return 1
    if crashes2 is None or crashes2 != crashes1 + 1:
        print(f"FAIL: crash count did not advance for the OOM fault ({crashes1} -> {crashes2})")
        return 1

    print(f"\nPASS: HardFault (PC={pc}) AND mallocfail both captured + survived reboot "
          f"(count {crashes0}->{crashes1}->{crashes2}); probe re-enumerated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
