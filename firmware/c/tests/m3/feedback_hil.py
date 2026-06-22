#!/usr/bin/env python3
"""
feedback_hil.py — M3.3 event-feedback wiring (buzzer + NeoPixel from recorder events).

Drives the REAL recorder conditions over the UART loopback and asserts the state transitions that the
SD-task feedback driver maps to the HAL:
  * a watch-term line ("FATAL: ...") -> hits++       -> a buzzer blip
  * 8 s of silence after activity    -> wedge=1      -> red NeoPixel + alarm tone
  * resumed traffic                  -> wedge cleared -> recovery chirp + dim-green LED

Machine-checks BOTH the recorder transitions (hits/wedge via {"q":"rec"}) AND that the feedback layer was
actually driven on each edge: {"q":"fb"} returns the beep count + the applied NeoPixel colour, so the test
asserts the buzzer beeped (count climbed) and the pixel went RED on wedge / GREEN on recovery. The only
residual operator gap is whether the physical transducer/LED is present + audible/visible (the HAL itself
is proven in M3.0); a no-op feedback layer now FAILS here instead of passing.

CDC0 must be opened FIRST + settle (its line-coding re-inits uart0 / re-arms the RX IRQ) BEFORE uloop_on,
and connections held persistently (churning a CDC port wedges the macOS USB-CDC driver).
"""
import os, sys, time, json
import serial
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from hil_ports import find_ports


def main():
    D, C = find_ports()
    if not D or not C:
        print("missing CDC0/CDC1"); return 2
    ok = True
    def chk(c, m):
        nonlocal ok
        print(("  OK  " if c else "  FAIL") + " " + m); ok = ok and c

    with serial.Serial(D, 115200, timeout=1.0) as d, serial.Serial(C, 115200, timeout=0.4) as c:
        time.sleep(0.6)  # CDC0 line-coding re-init + IRQ re-arm settle

        def ctrl(q, wait=1.0):
            c.reset_input_buffer(); c.write((q + "\n").encode()); c.flush()
            t0 = time.time(); buf = b""
            while time.time() - t0 < wait: buf += c.read(256)
            for l in reversed([x for x in buf.decode(errors="replace").splitlines() if x.strip().startswith("{")]):
                try: return json.loads(l)
                except Exception: pass
            return {}

        # Establish a known alive + GREEN baseline first: loopback on, then a non-trigger "wake" byte to
        # clear any lingering wedge from a prior run / idle silence (the rx_ever sequencing artifact). This
        # makes the green-baseline assertion deterministic + order-independent (M4 closeout fix).
        lo = ctrl('{"q":"uloop_on"}'); print("uloop_on:", lo)
        chk(lo.get("uloop") == 1, "UART loopback enabled")
        d.reset_input_buffer(); d.write(b"wake\n"); d.flush(); time.sleep(1.5)
        print("baseline:", ctrl('{"q":"rec"}'))
        fb0 = ctrl('{"q":"fb"}'); print("fb baseline:", fb0)
        beeps0 = fb0.get("beeps", 0)
        crashes0 = ctrl('{"q":"status"}').get("crashes", -1)
        chk(fb0.get("g", 0) > 0 and fb0.get("r", 0) == 0, "status LED dim-GREEN while logging (no fault)")

        d.reset_input_buffer(); d.write(b"FATAL: trigger test\n"); d.flush(); time.sleep(1.5)
        r1 = ctrl('{"q":"rec"}'); print("after FATAL:", r1)
        chk(r1.get("rx", 0) > 0, "injected bytes reached the recorder (rx>0)")
        chk(r1.get("hits", 0) >= 1, "trigger-term hit -> hits>=1")
        fb1 = ctrl('{"q":"fb"}'); print("fb after FATAL:", fb1)
        chk(fb1.get("beeps", 0) > beeps0, "trigger-hit DROVE the buzzer (beep count climbed) -> BLIP")
        beeps1 = fb1.get("beeps", 0)

        print("...silent 9 s (expect a WEDGE: red + alarm)...")
        time.sleep(9.0)
        r2 = ctrl('{"q":"rec"}'); print("after silence:", r2)
        chk(r2.get("wedge", 0) == 1, "wedge fired after 8 s silence")
        fb2 = ctrl('{"q":"fb"}'); print("fb after wedge:", fb2)
        chk(fb2.get("beeps", 0) > beeps1, "wedge DROVE the buzzer (alarm tone)")
        chk(fb2.get("r", 0) > 0 and fb2.get("g", 0) == 0, "wedge DROVE the NeoPixel RED")
        beeps2 = fb2.get("beeps", 0)

        d.write(b"back alive\n"); d.flush(); time.sleep(1.5)
        r3 = ctrl('{"q":"rec"}'); print("after resume:", r3)
        chk(r3.get("wedge", 1) == 0, "wedge cleared on resume")
        fb3 = ctrl('{"q":"fb"}'); print("fb after recovery:", fb3)
        chk(fb3.get("beeps", 0) > beeps2, "recovery DROVE the buzzer (chirp)")
        chk(fb3.get("g", 0) > 0 and fb3.get("r", 0) == 0, "recovery returned the NeoPixel to GREEN")

        ctrl('{"q":"uloop_off"}')
        crashes1 = ctrl('{"q":"status"}').get("crashes", -2)
        # Delta-based: the feedback sequence must add ZERO crashes. An absolute ==0 false-fails after other
        # tests' deliberate {"q":"crash"} reboots bumped the cumulative counter (caught in the M4 closeout).
        chk(crashes1 == crashes0 >= 0, f"no crash through the sequence (crashes {crashes0}->{crashes1})")

    print("\nM3.3 EVENT TRANSITIONS:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
