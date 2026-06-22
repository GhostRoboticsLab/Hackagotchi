#!/usr/bin/env python3
"""
config_hil.py — M4.5 settings-persistence HIL. Proves baud + macros survive a reboot via config.txt on the
SD card: set a non-default baud + macro -> reboot -> they're restored -> the restored baud is reflected in
the new session's log header. Then restores defaults so the device rests clean.

Reboots the device, so each query opens a fresh CDC1 connection (rtc_hil pattern).

  ./config_hil.py        # bar: all checks OK + "M4.5 PERSISTENCE: PASS"
"""
import os, sys, time, json, glob
import serial
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from hil_ports import find_ctrl

CTRL = find_ctrl()               # CDC1 control — detected by behaviour (replug-proof)


def q(query, wait=1.2):
    s = serial.Serial(CTRL, 115200, timeout=0.4); s.dtr = True; time.sleep(0.15); s.reset_input_buffer()
    s.write((query + "\n").encode()); s.flush()
    t0 = time.time(); buf = b""
    while time.time() - t0 < wait:
        buf += s.read(256)
    s.close()
    for l in reversed([x for x in buf.decode(errors="replace").splitlines() if x.strip().startswith("{")]):
        try:
            return json.loads(l)
        except Exception:
            continue
    return {}


def reboot():
    global CTRL
    try:
        q('{"q":"crash"}', wait=0.4)
    except Exception:
        pass
    time.sleep(2.0)
    t0 = time.time()
    while time.time() - t0 < 30:
        c = find_ctrl()          # re-detect: the usbmodem suffix can change across a reboot
        if c:
            CTRL = c
            if q('{"q":"status"}'):
                return True
        time.sleep(0.5)
    return False


def main():
    ok = True
    def chk(cnd, m):
        nonlocal ok
        print(("  OK  " if cnd else "  FAIL") + " " + m); ok = ok and cnd

    if not CTRL:
        print("no Hackagotchi control port found (is the probe connected?)"); return 2
    print("== M4.5 settings persistence HIL ==")
    print("set baud 9600:", q('{"q":"baud","v":9600}'))
    print("setmacro 0 M4TEST:", q('{"q":"setmacro","i":0,"s":"M4TEST"}'))
    time.sleep(0.8)   # let the SD task write config.txt
    chk(q('{"q":"baud"}').get("baud") == 9600, "baud set to 9600 pre-reboot")
    chk(q('{"q":"macros"}').get("macros", [None])[0] == "M4TEST", "macro 0 set to M4TEST pre-reboot")

    print("rebooting...")
    chk(reboot(), "re-enumerated after reboot")

    b2 = q('{"q":"baud"}'); print("baud after reboot:", b2)
    chk(b2.get("baud") == 9600, "baud PERSISTED across reboot (9600)")
    m2 = q('{"q":"macros"}'); print("macros after reboot:", m2)
    chk(m2.get("macros", [None])[0] == "M4TEST", "macro 0 PERSISTED across reboot (M4TEST)")

    q('{"q":"tail"}'); time.sleep(0.6); t = json.dumps(q('{"q":"tail"}'))
    chk("baud 9600" in t, "new session header logs the restored baud (baud 9600)")

    # restore defaults + reboot so the device rests clean for later tests
    print("restoring defaults...")
    q('{"q":"baud","v":115200}'); q('{"q":"setmacro","i":0,"s":"AT"}'); time.sleep(0.8)
    reboot()
    chk(q('{"q":"baud"}').get("baud") == 115200, "restored to 115200 + persisted")

    print("\nM4.5 PERSISTENCE:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
