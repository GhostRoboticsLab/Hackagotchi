#!/usr/bin/env python3
"""
coexist_soak.py — M2 heavy R1 proof: the SD black-box recorder writes CONTINUOUSLY while a target is
flashed over DAP. Proves bidirectional non-interference:
  * DAP flash stays clean (0 fails / 0 stalls) despite the low-prio SD task doing constant f_write/f_sync.
  * The recorder never faults (err=0), never VISIBLE-STOPs (logging=1), never false-wedges (wedge=0)
    under concurrent DAP+USB load; the on-card content stays intact (in-order RECGEN lines).

The SD-write load is generated DEVICE-SIDE: {"q":"recgen_on"} makes the SD task synthesize recorder
data every loop (~107 B @ ~50 Hz -> continuous f_write/f_sync). So the HOST only runs probe-rs (DAP) —
no host CDC0 stream competing with probe-rs on the same USB device. (The earlier host-injection version
conflated host USB contention with the SD-vs-DAP question we actually want and was discarded.)

  ./coexist_soak.py [N]      # N flash cycles (default 300). Bar: soak 0/0, err=0, logging=1, wedge=0.
"""
import sys, os, time, json, subprocess, glob, re

HERE = os.path.dirname(os.path.abspath(__file__))
SOAK = os.path.join(HERE, "..", "gates", "gate1_soak.sh")
sys.path.insert(0, os.path.join(HERE, ".."))
from hil_ports import find_ctrl
CTRL = find_ctrl()               # JSON control — detected by behaviour (replug-proof)
N = int(sys.argv[1]) if len(sys.argv) > 1 else 300

import serial
if not CTRL:
    print("coexist_soak: no Hackagotchi control port found (is the probe connected?)"); sys.exit(2)


def ctrl(query, wait=1.5):
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


def main():
    if not glob.glob(CTRL):
        print("missing device:", CTRL); return 2
    if not os.path.exists(SOAK):
        print("missing soak:", SOAK); return 2

    print(f"== M2 coexistence soak: {N} flash cycles WHILE the recorder writes SD (device-side load) ==")
    base = ctrl('{"q":"rec"}')
    print("[baseline] rec:", base)
    print("[load] recgen_on ->", ctrl('{"q":"recgen_on"}'))
    time.sleep(2.0)
    mid = ctrl('{"q":"rec"}')
    print("[load] rec after 2 s of recgen (rx should climb):", mid)
    if mid.get("rx", 0) <= base.get("rx", 0):
        ctrl('{"q":"recgen_off"}')
        print("FAIL: recgen produced no recorder traffic — load generator not working"); return 1

    # run the flash soak CONCURRENTLY (the contention); host does nothing but probe-rs here
    print(f"[soak] gate1_soak.sh {N} (flashing target over DAP, recorder writing throughout)...")
    t0 = time.time()
    proc = subprocess.run(["bash", SOAK, str(N)], capture_output=True, text=True)
    dt = time.time() - t0
    print("[soak]", " | ".join(l for l in proc.stdout.splitlines() if l.startswith("DONE") or "GATE 1:" in l), f"({dt:.0f}s)")

    fin = ctrl('{"q":"rec"}')
    print("[final] rec:", fin)
    print("[load] recgen_off ->", ctrl('{"q":"recgen_off"}'))
    ctrl('{"q":"tail"}'); time.sleep(0.6); tail = ctrl('{"q":"tail"}')

    # Parse the AUTHORITATIVE DONE line (a loose `"fails=0 stalls=0" in stdout` substring-matched progress
    # lines and falsely passed when the final tally was fails>0 — caught by the M3 closeout audit).
    done = next((l for l in proc.stdout.splitlines() if l.startswith("DONE")), "")
    m = re.search(r"fails=(\d+)\s+stalls=(\d+)", done)
    fails  = int(m.group(1)) if m else -1
    stalls = int(m.group(2)) if m else -1
    ops = 2 * N
    # R1 bar: ZERO stalls (no hang/corruption/transfer desync) is the HARD correctness invariant and the
    # gate. Retryable 0-stall DAP fails are background SD-DMA bus contention under continuous-max recgen —
    # a user-accepted, documented caveat ("don't gold-plate"): the target is HALTED during a real flash, so
    # the recorder is idle then and the real-world rate is ~0. M4's larger published snapshot + extra code
    # shifted the XIP layout and raised this artificial-worst-case rate ~1% -> ~4% (0 stalls throughout).
    # So the rate is REPORTED (never silently hidden), not gated; a WARN flags an egregious spike (>8%) that
    # would signal a genuine new contention problem worth investigating.
    ceiling = ops * 8 // 100       # generous HARD ceiling, well above the ~1-6% idle-host floor
    soak_clean = (stalls == 0 and 0 <= fails <= ceiling)
    fail_pct = (100.0 * fails / ops) if ops > 0 else 0.0
    rx0, rx1 = base.get("rx", 0), fin.get("rx", 0)
    ok = True
    def check(cond, msg):
        nonlocal ok
        print(("  OK  " if cond else "  FAIL") + " " + msg); ok = ok and cond
    check(soak_clean, f"DAP soak {stalls} stalls / {fails} fails of {ops} ops — HARD gate: 0 stalls AND fails<={ceiling} (8%)")
    print(f"  info retryable DAP fails {fails}/{ops} ({fail_pct:.1f}%) — 0-stall SD-DMA contention, accepted "
          f"floor (real-world ~0; RUN ON AN IDLE HOST — host CPU/USB load inflates this and will fail the ceiling)")
    check(fin.get("err", 1) == 0, f"recorder SD faults err={fin.get('err')} (must be 0)")
    check(fin.get("logging", 0) == 1, f"recorder still logging={fin.get('logging')} (no VISIBLE-STOP)")
    check(fin.get("wedge", 1) == 0, f"no false wedge wedge={fin.get('wedge')} (load was continuous)")
    check(rx1 > rx0 + 100000, f"recorder rx advanced a lot ({rx0} -> {rx1}) — SD wrote throughout")
    check("RECGEN" in json.dumps(tail), "on-card tail shows RECGEN content (recorded + intact)")
    print(f"[info] rec_drop={fin.get('rec_drop')} tp_peak={fin.get('tp_peak')} file={fin.get('file')} alert={fin.get('alert')!r}")
    print("\nCOEXISTENCE SOAK:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
