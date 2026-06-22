#!/usr/bin/env python3
"""
companion_hil.py — v1.2 "Companion" HIL: prove the NeoPixel-chain / button / joystick control surface is
in the running image and reacts. Two tiers:

  REQUIRED (machine-checked, can fail): {"q":"status"} carries px/btn/joy; mood/fill/btn/joy commands all
  return well-formed JSON with the expected keys. This catches a build that silently dropped the surface.

  LIVENESS (interactive, informational): you're prompted to press the button and waggle the stick; if the
  readback moves, that's a real end-to-end witness (HW wired + feature ON). If nothing moves it WARNs
  (feature OFF in this image, or not soldered yet) rather than failing — so the gate stays honest.

Build the image with the features on first, e.g.:
  HG_NEOPIXEL_COUNT=5 HG_BUTTON=ON HG_JOYSTICK=ON ./build_fork.sh   (then flash)

  .venv/bin/python tests/m_ui/companion_hil.py            # bar: "COMPANION SURFACE: PASS"
  .venv/bin/python tests/m_ui/companion_hil.py --no-interactive   # skip the press/waggle prompts

Hardware-blind-safe: exits 2 if no control port is found (can't run yet), 0 = pass, 1 = fail.
"""
import os, sys, time, json
import serial
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from hil_ports import find_ctrl

INTERACTIVE = "--no-interactive" not in sys.argv
CTRL = find_ctrl()
if not CTRL:
    print("companion_hil: no CDC1 control port found — can't run (wire the probe).")
    sys.exit(2)


def q(query, wait=0.8):
    s = serial.Serial(CTRL, 115200, timeout=0.3); s.dtr = True; time.sleep(0.15); s.reset_input_buffer()
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


fails, warns = [], []
def need(cond, msg):
    print(("  ok  " if cond else "  FAIL") + " " + msg)
    if not cond:
        fails.append(msg)
def note(cond, msg):
    print(("  ok  " if cond else "  warn") + " " + msg)
    if not cond:
        warns.append(msg)


print(f"== companion HIL on {CTRL} ==")

st = q('{"q":"status"}')
need(st.get("fw") == "Hackagotchi", f'status identifies firmware (ver={st.get("ver")})')
need("px" in st and "btn" in st and "joy" in st, f'status carries px/btn/joy ({{px:{st.get("px")}, btn:{st.get("btn")}, joy:{st.get("joy")}}})')
px = int(st.get("px", 0))
need(px >= 1, f'pixel count sane (px={px})')

# --- NeoPixel chain: mood + fill ---
m = q('{"q":"mood","n":4,"i":180}')                 # FAULT mood
need(m.get("mood") == 4 and m.get("i") == 180, f'mood command echoes ({m})')
f = q('{"q":"fill","r":0,"g":40,"b":0}')            # dim green over the whole chain
need(f.get("px") == px and isinstance(f.get("fill"), list), f'fill command echoes whole chain ({f})')
q('{"q":"mood","n":1}')                              # leave it idle-breathing

# --- button + joystick readback shape ---
b = q('{"q":"btn"}')
need("down" in b and "presses" in b, f'btn readback well-formed ({b})')
j = q('{"q":"joy"}')
need(all(k in j for k in ("ok", "x", "y", "dir")), f'joy readback well-formed ({j})')
note(int(j.get("ok", 0)) == 1, f'joystick (ADS1115) present on the bus (ok={j.get("ok")}) — warn if not wired/feature off')

# --- LIVENESS (interactive) ---
if INTERACTIVE:
    p0 = int(q('{"q":"btn"}').get("presses", 0))
    print("  >>> PRESS the button now (you have 8 s) ...")
    moved = False
    t0 = time.time()
    while time.time() - t0 < 8:
        if int(q('{"q":"btn"}').get("presses", 0)) > p0:
            moved = True; break
        time.sleep(0.4)
    note(moved, "button press registered (taps incremented)")

    print("  >>> WAGGLE the joystick up/down now (you have 8 s) ...")
    seen = set()
    t0 = time.time()
    while time.time() - t0 < 8:
        d = int(q('{"q":"joy"}').get("dir", 0))
        if d:
            seen.add(d)
        if len(seen) >= 1 and time.time() - t0 > 2:
            break
        time.sleep(0.3)
    note(len(seen) >= 1, f"joystick direction registered (dirs seen={sorted(seen)})")

print()
if fails:
    print(f"COMPANION SURFACE: FAIL ({len(fails)} required check(s)) — {fails}")
    sys.exit(1)
print(f"COMPANION SURFACE: PASS" + (f"  ({len(warns)} liveness warning(s): {warns})" if warns else ""))
sys.exit(0)
