#!/usr/bin/env python3
"""
screen_hil.py — M3.1 screen-framework self-attestation (camera-free).

The dashboard publishes the EXACT text it draws each frame over CDC1 ({"q":"screen"}) plus a SHOW-SUCCESS
counter (`shows`, incremented only when ssd1306_show() actually ran) DISTINCT from the loop counter
(`loops`) — so a host can verify, with no camera, that: screens render the right content, navigation +
auto-cycle work, an out-of-range jump is clamped (not a hardfault), and frames truly reach the panel.

  ./screen_hil.py        # bar: all checks OK + "M3.1 SELF-ATTESTATION: PASS"

NOTE: the OLED being physically lit is anchored once by an operator glance (self-attestation proves the
data layer + that show() succeeded, not photons) — the panel is known-good since Gate 1.
"""
import sys, time, json
CTRL = "/dev/cu.usbmodem21204"
import serial


def main():
    s = serial.Serial(CTRL, 115200, timeout=0.3)
    s.dtr = True; time.sleep(0.2); s.reset_input_buffer()

    def ctrl(q, wait=1.0):
        s.reset_input_buffer(); s.write((q + "\n").encode()); s.flush()
        t0 = time.time(); buf = b""
        while time.time() - t0 < wait: buf += s.read(256)
        for l in reversed([x for x in buf.decode(errors="replace").splitlines() if x.strip().startswith("{")]):
            try: return json.loads(l)
            except Exception: pass
        return {"raw": buf.decode(errors="replace")[:120]}

    ok = True
    def chk(c, m):
        nonlocal ok
        print(("  OK  " if c else "  FAIL") + " " + m); ok = ok and c

    # M3.2 screen order: 0 HOME(cat) · 1 SNIFFER · 2 RECORDER · 3 THROUGHPUT · 4 WATCHDOG · 5 CLOCK
    ctrl('{"q":"screen","n":0}'); time.sleep(0.5)
    sc0 = ctrl('{"q":"screen"}'); print("screen0:", sc0)
    chk(sc0.get("screen") == 0, "on screen 0")
    chk(sc0.get("n") == 6, "6 screens registered")
    chk("HACKAGOTCHI" in sc0.get("text", ""), "screen 0 = HOME/mascot (HACKAGOTCHI)")
    sh0 = sc0.get("shows", 0)

    ctrl('{"q":"next"}'); time.sleep(0.5)
    sc1 = ctrl('{"q":"screen"}'); print("screen1:", sc1)
    chk(sc1.get("screen") == 1, "next -> screen 1")
    chk("UART RX LOG" in sc1.get("text", ""), "screen 1 = SNIFFER")

    ctrl('{"q":"screen","n":2}'); time.sleep(0.5)
    sc2 = ctrl('{"q":"screen"}'); print("screen2:", sc2)
    chk(sc2.get("screen") == 2 and "RECORDER" in sc2.get("text", ""), "screen 2 = RECORDER")
    rec = ctrl('{"q":"rec"}')
    chk(rec.get("file", "X") in sc2.get("text", ""), "RECORDER shows the live snapshot filename")

    for nm, n, key in [("THROUGHPUT", 3, "THROUGHPUT"), ("WATCHDOG", 4, "WATCHDOG"), ("CLOCK", 5, "CLOCK")]:
        ctrl('{"q":"screen","n":%d}' % n); time.sleep(0.5)
        chk(key in ctrl('{"q":"screen"}').get("text", ""), f"screen {n} = {nm}")

    ctrl('{"q":"screen","n":0}'); ctrl('{"q":"prev"}'); time.sleep(0.5)
    chk(ctrl('{"q":"screen"}').get("screen") == 5, "prev from 0 wraps to last screen (5)")

    ctrl('{"q":"screen","n":99}'); time.sleep(0.5)
    scC = ctrl('{"q":"screen"}'); print("after n=99:", scC.get("screen"))
    chk(0 <= scC.get("screen", -1) < scC.get("n", 0), "out-of-range clamped (no hardfault)")
    chk(ctrl('{"q":"status"}').get("crashes", -1) == 0, "no crash from the clamp")

    ctrl('{"q":"screen","n":0}'); time.sleep(0.5)
    a = ctrl('{"q":"screen"}').get("screen"); time.sleep(6.0); b = ctrl('{"q":"screen"}').get("screen")
    print(f"auto-cycle {a} -> {b}")
    chk(a == 0 and b != 0, "auto-cycle advances with no input (~5s)")

    sc2 = ctrl('{"q":"screen"}')
    print(f"loops={sc2.get('loops')} shows={sc2.get('shows')} dstack={sc2.get('dstack')}")
    chk(sc2.get("shows", 0) > sh0, "show-success counter climbing (frames flush to panel)")
    chk(sc2.get("dstack", 0) > 50, "dashboard stack high-water healthy")

    s.close()
    print("\nM3.1 SELF-ATTESTATION:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
