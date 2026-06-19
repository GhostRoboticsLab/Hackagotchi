#!/usr/bin/env python3
"""gate2_cdc.py — GATE 2: the composite grows {DAP v2 + CDC0} -> {DAP v2 + CDC0 + CDC1} cleanly.

Checks:
  1. macOS enumerates exactly TWO /dev/cu.usbmodem* nodes,
  2. CMSIS-DAP still binds (probe-rs list still finds the probe),
  3. {"q":"status"} round-trips on the CONTROL CDC (CDC1) and returns valid JSON,
  4. helps map interface-NAME -> node (the numeric usbmodem suffix is NOT stable across replug).

Hardware-blind-safe: with no probe / no pyserial it prints what to do and exits 2.

  ./gate2_cdc.py                          # auto: enumerate + map, prompt for control node
  ./gate2_cdc.py --control /dev/cu.usbmodemXXXX2 [--uart /dev/cu.usbmodemXXXX1] [--n 100]

Exit: 0 = PASS, 1 = FAIL, 2 = can't run yet.
"""
import argparse
import glob
import json
import shutil
import subprocess
import sys
import time


def sh(*cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=30).stdout
    except Exception as e:
        return f"(error running {' '.join(cmd)}: {e})"


def list_nodes():
    return sorted(glob.glob("/dev/cu.usbmodem*"))


def probe_present():
    if not shutil.which("probe-rs"):
        return None
    out = sh("probe-rs", "list").lower()
    # NB: "No debug probes were found." contains "debug" -> match only the probe TYPE string.
    return "cmsis" in out


def map_names():
    """Best-effort: dump the descriptor info that ties an interface NAME to a callout node."""
    print("--- interface-name -> node mapping aids (read these to assign CDC0=UART / CDC1=Control) ---")
    print(sh("system_profiler", "SPUSBDataType"))
    print(sh("ioreg", "-p", "IOUSB", "-l", "-w0"))


def round_trip(control, n):
    try:
        import serial  # pyserial
    except ImportError:
        print("pyserial not installed:  pip install pyserial  (or use the project .venv)")
        return 2
    ok = 0
    lat = []
    try:
        p = serial.Serial(control, 115200, timeout=2)
    except Exception as e:
        print(f"could not open control node {control}: {e}")
        return 2
    for i in range(n):
        t0 = time.time()
        p.reset_input_buffer()
        p.write(b'{"q":"status"}\n')
        line = p.readline().decode(errors="replace").strip()
        try:
            obj = json.loads(line)
            if obj.get("fw"):
                ok += 1
                lat.append(time.time() - t0)
        except Exception:
            pass
    p.close()
    if lat:
        print(f"round-trip: {ok}/{n} valid JSON  (latency avg {1000*sum(lat)/len(lat):.1f} ms, max {1000*max(lat):.1f} ms)")
    else:
        print(f"round-trip: {ok}/{n} valid JSON  (no valid replies)")
    return 0 if ok == n else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--control", help="the CONTROL CDC node (CDC1) for {\"q\":\"status\"}")
    ap.add_argument("--uart", help="the UART-bridge CDC node (CDC0), for reference")
    ap.add_argument("--n", type=int, default=100, help="round-trip count (bar: 100/100)")
    ap.add_argument("--map", action="store_true", help="just dump the name->node mapping aids")
    args = ap.parse_args()

    print(f"=== GATE 2  {time.strftime('%FT%TZ', time.gmtime())} ===")
    nodes = list_nodes()
    print(f"[1] /dev/cu.usbmodem* nodes: {nodes or '(none)'}")
    pp = probe_present()
    print(f"[2] CMSIS-DAP still binds (probe-rs list): "
          + ("yes" if pp else ("NO" if pp is False else "probe-rs not installed")))

    if args.map:
        map_names(); return 0
    if not nodes:
        print("No usbmodem nodes — flash the Gate-2 fork + plug in. Exiting (2).")
        return 2
    if len(nodes) < 2:
        print("FAIL: expected TWO nodes (CDC0 UART + CDC1 control); found one. 2nd CDC not enumerating.")
        return 1

    if not args.control:
        print("\nTwo nodes present. Identify which is the CONTROL CDC (CDC1) — run with --map to see")
        print("the interface names, then re-run:  ./gate2_cdc.py --control <node> --uart <node>")
        map_names()
        return 2

    print(f"[3] round-trip on control={args.control}" + (f" (uart={args.uart})" if args.uart else ""))
    rc = round_trip(args.control, args.n)
    verdict = {0: "PASS", 1: "FAIL", 2: "INCOMPLETE"}[rc]
    print(f"=== GATE 2: {verdict} ===  (also confirm: probe-rs still works + CDC0 carries UART concurrently;")
    print("    mapping stable across 3 replug + 1 reboot)")
    return rc


if __name__ == "__main__":
    sys.exit(main())
