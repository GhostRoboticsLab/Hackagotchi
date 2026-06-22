#!/usr/bin/env python3
"""
baud_hil.py — M4.3 baud-selector HIL. Proves the target-UART baud is reconfigurable at runtime over CDC1
({"q":"baud","v":N}), validated against the offered set, reflected on the BAUD screen, and that the UART
path still works after the reconfig (a macro loops back at the new rate). SWD is a separate PIO so a baud
change never touches the DAP path; the cumulative R1 soak at the M4 closeout confirms 0 stalls.

  ./baud_hil.py        # bar: all checks OK + "M4.3 BAUD SELECT: PASS"
"""
import os, sys, time, json
import serial
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from hil_ports import find_ports

UART, CTRL = find_ports()        # CDC0 bridge, CDC1 control — detected by behaviour (replug-proof)
OPTS = [9600, 19200, 38400, 57600, 115200]


def ctrl(s, query, wait=1.0):
    s.reset_input_buffer()
    s.write((query + "\n").encode()); s.flush()
    t0 = time.time(); buf = b""
    while time.time() - t0 < wait:
        buf += s.read(256)
    for l in reversed([x for x in buf.decode(errors="replace").splitlines() if x.strip().startswith("{")]):
        try:
            return json.loads(l)
        except Exception:
            continue
    return {}


def tail(c):
    ctrl(c, '{"q":"tail"}'); time.sleep(0.6)
    return json.dumps(ctrl(c, '{"q":"tail"}'))


def main():
    ok = True
    def chk(cnd, m):
        nonlocal ok
        print(("  OK  " if cnd else "  FAIL") + " " + m); ok = ok and cnd

    if not CTRL or not UART:
        print("missing CDC0/CDC1 (is the probe connected?)"); return 2
    print("== M4.3 baud selector HIL ==")
    c = serial.Serial(CTRL, 115200, timeout=0.4); c.dtr = True; time.sleep(0.15)
    u = serial.Serial(UART, 115200, timeout=0.4); u.dtr = True; time.sleep(0.6)  # re-inits uart0
    print("loopback on:", ctrl(c, '{"q":"uloop_on"}'))

    b0 = ctrl(c, '{"q":"baud"}'); print("baud:", b0)
    chk(b0.get("baud") == 115200, "boots at 115200")
    chk(b0.get("opts") == OPTS, "offers the expected baud set")

    chk(ctrl(c, '{"q":"baud","v":9600}').get("baud") == 9600, '{"q":"baud","v":9600} accepted')
    time.sleep(0.4)
    chk(ctrl(c, '{"q":"baud"}').get("baud") == 9600, "baud now reads 9600")

    # UART still works at the new rate: send macro 1 (PING), it loops back through the recorder
    ctrl(c, '{"q":"macro","i":1}'); time.sleep(0.6)
    chk("PING" in tail(c), "UART still functional after the change (PING looped back at 9600)")

    chk(ctrl(c, '{"q":"baud","v":12345}').get("err") == "badbaud", "invalid baud -> err badbaud")

    ctrl(c, '{"q":"screen","n":7}'); time.sleep(0.4)
    sc = ctrl(c, '{"q":"screen"}'); print("baud screen:", sc.get("text"))
    txt = sc.get("text", "")
    chk("BAUD SELECT" in txt, "BAUD screen title")
    chk(">9600 *" in txt, "BAUD screen marks the current rate (>9600 *)")
    chk("115200" in txt, "BAUD screen lists the options")

    chk(ctrl(c, '{"q":"baud","v":115200}').get("baud") == 115200, "restored to 115200")

    ctrl(c, '{"q":"uloop_off"}')
    u.close(); c.close()
    print("\nM4.3 BAUD SELECT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
