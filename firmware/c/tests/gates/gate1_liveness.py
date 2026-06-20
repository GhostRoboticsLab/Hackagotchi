#!/usr/bin/env python3
"""gate1_liveness.py — machine-capture liveness + SELF-ATTESTATION during the Gate-1 soak via CDC1.

Polls the CDC1 JSON control channel while gate1_soak.sh hammers the target over DAP. The firmware's
status reply self-attests its build and that the stressor fires, so the capture proves — at rank-1,
without any GP0 loopback jumper — all of:

  * up monotonic + advancing   => system never crashed/rebooted under DAP+CDC+dashboard load
  * CDC1 answers every poll     => USB never wedged while the DAP soak ran (the coexistence claim)
  * n monotonic + advancing     => the DASHBOARD TASK kept looping (NOT just system-alive — closes the
                                   frozen-but-alive gap the CDC1-only liveness could not)
  * stall_us ~= stall_cfg*1000  => the adversarial busy_wait actually executed (stressor really fired)
  * prio constant (1 => at DAP) => which build is running (provenance, from the firmware itself)
  * heap stable                 => no leak in the (no-FreeRTOS-alloc) harness

  ./gate1_liveness.py --control /dev/cu.usbmodemXXXX --secs 600 --interval 5 --out gate1/liveness.csv

Exit: 0 = PASS (replies clean, up & n monotonic and ADVANCED), 1 = FAIL, 2 = could not run.
"""
import argparse
import json
import sys
import time

try:
    import serial  # pyserial
except ImportError:
    print("pyserial not installed: use the project .venv python")
    sys.exit(2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--control", required=True, help="CDC1 control node (answers {\"q\":\"status\"})")
    ap.add_argument("--secs", type=float, default=600)
    ap.add_argument("--interval", type=float, default=5.0)
    ap.add_argument("--out", help="CSV output path")
    a = ap.parse_args()

    try:
        p = serial.Serial(a.control, 115200, timeout=2)
    except Exception as e:
        print(f"could not open control node {a.control}: {e}")
        return 2

    t0 = time.time()
    rows = []           # (t_rel, up, heap, n, stall_us, prio)
    last_up = -1
    last_n = -1
    nonmono_up = 0
    nonmono_n = 0
    fails = 0
    prios = set()
    stalls = []
    print(f"=== GATE 1 liveness+self-attest (CDC1={a.control}, {a.secs:.0f}s @ {a.interval}s) ===", flush=True)
    while time.time() - t0 < a.secs:
        try:
            p.reset_input_buffer()
            p.write(b'{"q":"status"}\n')
            o = json.loads(p.readline().decode(errors="replace").strip())
            up = int(o["up"]); heap = int(o["heap"])
            n = int(o.get("n", -1)); stall_us = int(o.get("stall_us", -1)); prio = int(o.get("prio", -1))
            up_ok = up >= last_up
            n_ok = (n < 0) or (n >= last_n)        # n monotonic (ignore if field absent)
            if not up_ok: nonmono_up += 1
            if not n_ok: nonmono_n += 1
            last_up = up
            if n >= 0: last_n = n
            if prio >= 0: prios.add(prio)
            if stall_us >= 0: stalls.append(stall_us)
            trel = round(time.time() - t0, 1)
            rows.append((trel, up, heap, n, stall_us, prio))
            flag = "OK" if (up_ok and n_ok) else ("UP!" if not up_ok else "N-FROZEN!")
            print(f"t={trel:7.1f}s up={up:5d} heap={heap} n={n:6d} stall_us={stall_us} prio={prio}  {flag}", flush=True)
        except Exception as e:
            fails += 1
            print(f"t={time.time()-t0:7.1f}s  NO/BAD REPLY ({e})", flush=True)
        time.sleep(a.interval)
    p.close()

    if rows:
        ups = [r[1] for r in rows]; heaps = [r[2] for r in rows]; ns = [r[3] for r in rows if r[3] >= 0]
        print(f"\nSUMMARY samples={len(rows)} reply-fails={fails} nonmono-up={nonmono_up} nonmono-n={nonmono_n}")
        print(f"  uptime : {ups[0]}s..{ups[-1]}s  monotonic={'YES' if nonmono_up==0 else 'NO'} advanced={ups[-1]-ups[0]}s")
        if ns:
            print(f"  n(dash): {ns[0]}..{ns[-1]}  monotonic={'YES' if nonmono_n==0 else 'NO'} advanced={ns[-1]-ns[0]}  (proves DASHBOARD looped)")
        print(f"  heap   : min={min(heaps)} max={max(heaps)} drift={max(heaps)-min(heaps)}B")
        if stalls:
            print(f"  stall  : min={min(stalls)}us max={max(stalls)}us  (busy_wait fired; ~50000=50ms => adversarial build)")
        print(f"  prio   : {sorted(prios)}  (1 => dashboard AT DAP priority = adversarial contention build)")
        if a.out:
            with open(a.out, "w") as f:
                f.write("t_rel,up,heap,n,stall_us,prio\n")
                for r in rows: f.write(",".join(str(x) for x in r) + "\n")
            print(f"  csv -> {a.out}")
    else:
        print("\nSUMMARY  no samples captured")

    # PASS requires: clean replies, system alive (up monotonic), AND dashboard alive (n monotonic & advanced)
    n_advanced = bool(ns) and (ns[-1] > ns[0]) if rows else False
    rc = 0 if (rows and fails == 0 and nonmono_up == 0 and nonmono_n == 0 and n_advanced) else 1
    print(f"LIVENESS+SELFATTEST: {'PASS' if rc == 0 else 'FAIL'}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
