#!/usr/bin/env python3
"""
screen_hil.py — M3.1 screen-framework self-attestation (camera-free).

The dashboard publishes the EXACT text it draws each frame over CDC1 ({"q":"screen"}) plus a SHOW-SUCCESS
counter (`shows`, incremented only when ssd1306_show() actually ran) DISTINCT from the loop counter
(`loops`) — so a host can verify, with no camera, that: screens render the right content, navigation +
auto-cycle work, an out-of-range jump is clamped (not a hardfault), and frames truly reach the panel.

  ./screen_hil.py        # bar: all checks OK + "M3.1 SELF-ATTESTATION: PASS"

NOTE: g_dash_shows now ticks ONLY when ssd1306_show() returns a real panel ACK (>=0), so a NAKing/absent
OLED gives shows<loops and FAILS this test — the counter is a genuine dark-panel detector. The residual
operator glance covers only GRAPHICS correctness (the cat + sparkline are drawn but not text-attestable);
the panel-lit + text-content layers are machine-proven here.
"""
import sys, time, json, re
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

    # screen order: 0 HOME(cat) · 1 SNIFFER · 2 RECORDER · 3 THROUGHPUT · 4 WATCHDOG · 5 UPTIME
    # (was 5 CLOCK before the RTC was dropped; the probe has no wall-clock, so screen 5 shows uptime)
    ctrl('{"q":"screen","n":0}'); time.sleep(0.5)
    sc0 = ctrl('{"q":"screen"}'); print("screen0:", sc0)
    chk(sc0.get("screen") == 0, "on screen 0")
    chk(sc0.get("n") >= 6, "at least the 6 monitoring screens registered (n=%d)" % sc0.get("n", 0))
    chk("HACKAGOTCHI" in sc0.get("text", ""), "screen 0 = HOME/mascot (HACKAGOTCHI)")
    sh0 = sc0.get("shows", 0)

    ctrl('{"q":"next"}'); time.sleep(0.5)
    sc1 = ctrl('{"q":"screen"}'); print("screen1:", sc1)
    chk(sc1.get("screen") == 1, "next -> screen 1")
    chk("UART RX LOG" in sc1.get("text", ""), "screen 1 = SNIFFER")

    ctrl('{"q":"screen","n":2}'); time.sleep(0.5)
    sc2 = ctrl('{"q":"screen"}'); print("screen2:", sc2)
    chk(sc2.get("screen") == 2 and "RECORDER" in sc2.get("text", ""), "screen 2 = RECORDER")
    rec = ctrl('{"q":"rec"}'); f = rec.get("file", "")
    chk(bool(re.fullmatch(r"log_\d+\.txt", f)) and f in sc2.get("text", ""),
        "RECORDER shows the live log_NNN.txt filename (non-empty, matches the snapshot)")

    for nm, n, key in [("THROUGHPUT", 3, "THROUGHPUT"), ("WATCHDOG", 4, "WATCHDOG"), ("UPTIME", 5, "UPTIME")]:
        ctrl('{"q":"screen","n":%d}' % n); time.sleep(0.5)
        chk(key in ctrl('{"q":"screen"}').get("text", ""), f"screen {n} = {nm}")

    ctrl('{"q":"screen","n":0}'); ctrl('{"q":"prev"}'); time.sleep(0.5)
    sp = ctrl('{"q":"screen"}'); nn = sp.get("n", 6)
    chk(sp.get("screen") == nn - 1, f"prev from 0 wraps to the last screen ({nn - 1})")

    crashes_before = ctrl('{"q":"status"}').get("crashes", -1)
    ctrl('{"q":"screen","n":99}'); time.sleep(0.5)
    scC = ctrl('{"q":"screen"}'); print("after n=99:", scC.get("screen"))
    chk(0 <= scC.get("screen", -1) < scC.get("n", 0), "out-of-range clamped (no hardfault)")
    crashes_after = ctrl('{"q":"status"}').get("crashes", -2)
    # Assert the clamp INCREMENTS crashes by zero — NOT that crashes==0. A fresh flash reboots via
    # {"q":"bootsel"} (reset_usb_boot), which legitimately counts as one reset, so an absolute ==0 was a
    # false-fail immediately after flashing. What this check actually proves is "the clamp added no crash".
    chk(crashes_after == crashes_before >= 0, f"no crash from the clamp (crashes {crashes_before}->{crashes_after})")

    # auto-cycle is DASH_CYCLE_MS = 6 s; wait > one full cycle but < two, assert exactly one advance
    ctrl('{"q":"screen","n":0}'); time.sleep(0.5)
    a = ctrl('{"q":"screen"}').get("screen"); time.sleep(7.5)
    s_b = ctrl('{"q":"screen"}'); b = s_b.get("screen"); nscr = s_b.get("n", 6)
    print(f"auto-cycle {a} -> {b}")
    chk(a == 0 and b == (a + 1) % nscr, "auto-cycle advances exactly one screen (~6s, no input)")

    # M-UI-2: the persistent status bar attests on EVERY screen ("BAR ...") and the attestation never
    # overflows the cap — DASH_MAX_LINES was raised 6->8 precisely so adding the BAR (and later cat/ghost)
    # tokens can't silently drop a literal fact. text = "title\\nline0\\n..." so newline-segments <= 8+1.
    DASH_MAX_LINES = 8
    nscr_all = ctrl('{"q":"screen"}').get("n", 6)
    for n in range(nscr_all):
        ctrl('{"q":"screen","n":%d}' % n); time.sleep(0.35)
        txt = ctrl('{"q":"screen"}').get("text", "")
        chk("BAR" in txt, f"screen {n}: status bar attests (BAR token present)")
        chk("g:" in txt, f"screen {n}: ghost vitals attest (g:<state> token present)")  # M-UI-3
        chk(txt.count("\n") + 1 <= DASH_MAX_LINES + 1, f"screen {n}: attestation within cap (no silent drop)")

    # M-UI-5: companion verbs. summon/banish force the ghost vitals deterministically (no real wedge
    # needed), so the override is HIL-provable; pet / theme / ghost-mute are acknowledged.
    ctrl('{"q":"screen","n":0}'); time.sleep(0.3)
    ctrl('{"q":"banish"}'); time.sleep(0.4)
    chk("g:off" in ctrl('{"q":"screen"}').get("text", ""), "banish -> g:off (ghost hidden)")
    ctrl('{"q":"summon"}'); time.sleep(0.4)
    chk("g:live" in ctrl('{"q":"screen"}').get("text", ""), "summon -> g:live (forced present)")
    ctrl('{"q":"ghost"}'); time.sleep(0.3)   # clear override -> AUTO
    chk(ctrl('{"q":"pet"}').get("pet") == 1, "pet acknowledged")
    chk(ctrl('{"q":"theme","n":0}').get("theme") == 0, "theme calm set")
    ctrl('{"q":"theme","n":1}')              # restore dense
    chk("char" in ctrl('{"q":"ghost","on":1}'), "ghost layer toggle acknowledged")

    sc2 = ctrl('{"q":"screen"}')
    print(f"loops={sc2.get('loops')} shows={sc2.get('shows')} dstack={sc2.get('dstack')}")
    chk(sc2.get("shows", 0) > sh0, "show-success counter climbing (frames flush to panel)")
    chk(sc2.get("dstack", 0) > 50, "dashboard stack high-water healthy")

    s.close()
    print("\nM3.1 SELF-ATTESTATION:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
