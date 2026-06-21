#!/usr/bin/env python3
"""
macro_hil.py — M4.2 macro-sender HIL. Proves macros are ACTUALLY transmitted out the target UART (verified
end-to-end by internal loopback: inject -> uart0 TX -> RX -> recorder freeze ring), the macro list is the
expected default, the MACRO screen (index 6) renders + marks the last sent, and that a tool screen is NOT
auto-cycled. Camera-free via self-attestation + the recorder tail.

Pattern: open CDC0 FIRST + settle (re-inits uart0), uloop_on, then drive over CDC1 with persistent conns.

  ./macro_hil.py        # bar: all checks OK + "M4.2 MACRO SENDER: PASS"
"""
import sys, time, json
import serial

UART = "/dev/cu.usbmodem21202"   # CDC0 UART bridge
CTRL = "/dev/cu.usbmodem21204"   # CDC1 JSON control
DEFAULT = ["AT", "PING", "STATUS", "RESET", "HELP", "HELLO"]


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
    ctrl(c, '{"q":"tail"}'); time.sleep(0.6)          # async: request, then collect on a later call
    return json.dumps(ctrl(c, '{"q":"tail"}'))


def main():
    ok = True
    def chk(cnd, m):
        nonlocal ok
        print(("  OK  " if cnd else "  FAIL") + " " + m); ok = ok and cnd

    print("== M4.2 macro sender HIL ==")
    c = serial.Serial(CTRL, 115200, timeout=0.4); c.dtr = True; time.sleep(0.15)
    u = serial.Serial(UART, 115200, timeout=0.4); u.dtr = True; time.sleep(0.6)  # re-inits uart0
    print("loopback on:", ctrl(c, '{"q":"uloop_on"}'))

    ms = ctrl(c, '{"q":"macros"}'); print("macros:", ms)
    chk(ms.get("macros") == DEFAULT, "default macro list matches MicroPython")

    snt = ctrl(c, '{"q":"macro","i":0}'); print("send 0:", snt)
    chk(snt.get("sent") == 0 and snt.get("macro") == "AT", '{"q":"macro","i":0} -> sent AT')
    time.sleep(0.5)
    t0 = tail(c); print("tail after AT:", t0[:140])
    chk("AT" in t0, "macro AT was actually TRANSMITTED (looped back into the recorder)")

    snt2 = ctrl(c, '{"q":"macro","i":2}'); print("send 2:", snt2)
    chk(snt2.get("macro") == "STATUS", '{"q":"macro","i":2} -> sent STATUS')
    time.sleep(0.5)
    chk("STATUS" in tail(c), "macro STATUS transmitted (looped back)")

    chk(ctrl(c, '{"q":"macro","i":9}').get("err") == "range", "out-of-range index -> err range")

    ctrl(c, '{"q":"screen","n":6}'); time.sleep(0.4)
    sc = ctrl(c, '{"q":"screen"}'); print("macro screen:", sc.get("text"))
    txt = sc.get("text", "")
    chk("MACRO SENDER" in txt, "MACRO screen title")
    chk("AT" in txt and "STATUS" in txt and "HELLO" in txt, "MACRO screen lists the macros")
    chk(">2 STATUS" in txt, "MACRO screen marks the last sent (>2 STATUS)")

    a = ctrl(c, '{"q":"screen"}').get("screen"); time.sleep(7.5)
    b = ctrl(c, '{"q":"screen"}').get("screen")
    chk(a == 6 and b == 6, "tool screen stays put (NOT auto-cycled past ~6 s)")

    ctrl(c, '{"q":"uloop_off"}')
    u.close(); c.close()
    print("\nM4.2 MACRO SENDER:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
