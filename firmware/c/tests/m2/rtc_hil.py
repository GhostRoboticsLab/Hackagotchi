#!/usr/bin/env python3
"""
rtc_hil.py — M2.4 PCF8563 RTC HIL test. Proves: the RTC at I2C1 0x51 is present, settable, ticking,
and that the black-box recorder stamps log entries with WALL-CLOCK time (not the uptime "+Ns" fallback)
once the clock is trusted — end-to-end through the i2c1 bus mutex shared with the OLED.

Steps:
  1. {"q":"time"} -> RTC present.
  2. {"q":"settime","t":"<host now>"} -> set (clears VL low-voltage flag).
  3. {"q":"time"} -> reads back the set time (within a few seconds) and valid=1.
  4. wait 3 s, {"q":"time"} -> advanced ~3 s (it's actually ticking, not a static echo).
  5. force a reboot ({"q":"crash"}) -> the recorder opens a NEW session file whose header is stamped
     from the (retained) RTC -> {"q":"tail"} header shows "<year>-..." not "+0s".

  ./rtc_hil.py
"""
import sys, time, json, glob
from datetime import datetime, timedelta
import serial

CTRL = "/dev/cu.usbmodem21204"


def q(query, wait=1.5):
    s = serial.Serial(CTRL, 115200, timeout=0.4)
    s.dtr = True; time.sleep(0.15); s.reset_input_buffer()
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


def find_port(timeout=30):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if glob.glob(CTRL):
            try:
                r = q('{"q":"status"}')
                if r:
                    return r
            except Exception:
                pass
        time.sleep(0.5)
    return None


def parse_t(s):
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")


def main():
    ok = True
    def check(cond, msg):
        nonlocal ok
        print(("  OK  " if cond else "  FAIL") + " " + msg); ok = ok and cond

    print("== M2.4 PCF8563 RTC HIL ==")
    t0 = q('{"q":"time"}')
    print("[present] time:", t0)
    check(t0.get("rtc") == 1, "RTC present at I2C1 0x51 (ACK)")
    if t0.get("rtc") != 1:
        print("\nRTC HIL: FAIL (no RTC on the bus — is the XIAO on the expansion board?)")
        return 1

    # 2) set to host wall-clock
    now = datetime.now().replace(microsecond=0)
    setstr = now.strftime("%Y-%m-%d %H:%M:%S")
    r = q('{"q":"settime","t":"%s"}' % setstr)
    print(f"[set] settime {setstr} ->", r)
    check(r.get("set") == 1, "settime accepted (set=1)")

    # 3) read back
    rb = q('{"q":"time"}')
    print("[readback] time:", rb)
    check(rb.get("valid") == 1, "time now valid (VL cleared)")
    try:
        delta = abs((parse_t(rb["t"]) - now).total_seconds())
        check(delta <= 3, f"readback within 3 s of set ({delta:.0f}s): {rb.get('t')}")
    except Exception as e:
        check(False, f"readback parse failed: {e}")

    # 4) prove it ticks
    time.sleep(3.0)
    rb2 = q('{"q":"time"}')
    print("[tick] time after ~3 s:", rb2)
    try:
        adv = (parse_t(rb2["t"]) - parse_t(rb["t"])).total_seconds()
        check(2 <= adv <= 6, f"clock advanced ~3 s (got {adv:.0f}s) — it's running, not static")
    except Exception as e:
        check(False, f"tick parse failed: {e}")

    # 5) end-to-end: reboot -> new session header stamped from the retained RTC
    print("[reboot] forcing {\"q\":\"crash\"} -> new recorder session ...")
    try:
        q('{"q":"crash"}', wait=0.4)
    except Exception:
        pass
    time.sleep(2.0)
    st = find_port(30)
    check(st is not None, "probe re-enumerated after reboot")
    q('{"q":"tail"}')            # request a fresh tail read
    time.sleep(0.7)
    tail = q('{"q":"tail"}')     # collect it
    print("[stamp] tail:", json.dumps(tail)[:240])
    tj = json.dumps(tail)
    yr = str(now.year)
    check(yr in tj, f"new-session log stamp uses wall-clock (contains {yr}), not '+Ns' uptime")

    print("\nRTC HIL:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
