#!/usr/bin/env python3
"""
hex_hil.py — M4.1 hex-sniffer HIL. Proves the SNIFFER screen toggles ASCII<->hex over CDC1 ({"q":"hex"})
and the hex view renders the ACTUAL raw target bytes (uppercase hex + ASCII gutter), camera-free via the
dashboard self-attestation ({"q":"screen"} text model).

Pattern (matches uart_bridge_hil.py / feedback_hil.py): open CDC0 FIRST + settle (line-coding re-inits
uart0, clearing loopback), THEN uloop_on, inject a known marker via internal loopback (GP0->GP1), THEN
assert on CDC1. Persistent connections (churning a CDC port wedges macOS USB-CDC).

  ./hex_hil.py        # bar: all checks OK + "M4.1 HEX SNIFFER: PASS"
"""
import sys, time, json
import serial

UART = "/dev/cu.usbmodem21202"   # CDC0 UART bridge
CTRL = "/dev/cu.usbmodem21204"   # CDC1 JSON control
MARK = "HEXMODE42"               # 9 printable bytes -> hex 48 45 58 4D 4F 44 45 34 32 ('HEX' = 48 45 58)


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


def main():
    ok = True
    def chk(c, m):
        nonlocal ok
        print(("  OK  " if c else "  FAIL") + " " + m); ok = ok and c

    print("== M4.1 hex sniffer HIL ==")
    c = serial.Serial(CTRL, 115200, timeout=0.4); c.dtr = True; time.sleep(0.15)
    u = serial.Serial(UART, 115200, timeout=0.4); u.dtr = True; time.sleep(0.6)  # re-inits uart0
    print("loopback on:", ctrl(c, '{"q":"uloop_on"}'))

    # inject the marker via internal loopback -> RX IRQ -> ring -> recorder freeze ring
    u.write(MARK.encode()); u.flush(); time.sleep(0.8)

    # normalize to ASCII mode (hex toggles; end on OFF regardless of prior state)
    if ctrl(c, '{"q":"hex"}').get("hex") == 1:
        ctrl(c, '{"q":"hex"}')

    ctrl(c, '{"q":"screen","n":1}'); time.sleep(0.4)
    a = ctrl(c, '{"q":"screen"}'); print("ascii:", a.get("text"))
    chk("UART RX LOG" in a.get("text", ""), "ASCII mode title = UART RX LOG")
    chk(MARK in a.get("text", ""), f"ASCII sniffer shows the injected marker ({MARK})")

    h = ctrl(c, '{"q":"hex"}'); print("hex toggle:", h)
    chk(h.get("hex") == 1, '{"q":"hex"} -> hex:1')
    time.sleep(0.4)
    hs = ctrl(c, '{"q":"screen"}'); print("hex:", hs.get("text"))
    txt = hs.get("text", "")
    chk("HEX SNIFFER" in txt, "hex mode title = HEX SNIFFER")
    chk("48 45 58" in txt, "hex view shows the marker bytes (48 45 58 = 'HEX')")
    # The ASCII gutter is the text after the 15-col hex field on each row; the 5-bytes/row wrap can split
    # the marker across rows (e.g. ".HEXM"|"ODE42" when a stray RX byte shifts alignment), so rejoin the
    # gutters across rows before checking — the hex bytes above already prove the render is correct.
    gutter = "".join(row[15:] for row in txt.split("|")[1:])
    chk("HEXMODE42" in gutter, "ASCII gutter (rejoined across rows) shows the marker")

    b = ctrl(c, '{"q":"hex"}'); print("hex toggle back:", b)
    chk(b.get("hex") == 0, '{"q":"hex"} -> hex:0 (back to ASCII)')
    ctrl(c, '{"q":"screen","n":1}'); time.sleep(0.4)   # re-assert SNIFFER (the 6 s auto-cycle may have advanced)
    chk("UART RX LOG" in ctrl(c, '{"q":"screen"}').get("text", ""), "returned to ASCII mode")

    ctrl(c, '{"q":"uloop_off"}')
    u.close(); c.close()
    print("\nM4.1 HEX SNIFFER:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
