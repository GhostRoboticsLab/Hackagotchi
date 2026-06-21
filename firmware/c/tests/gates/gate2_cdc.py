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
import os
import re
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


def behavioral_discover():
    """Identify CDC roles by BEHAVIOR, not by the (unstable) usbmodem suffix: the node answering
    {"q":"status"} as Hackagotchi is the CONTROL (CDC1); the other is the UART bridge (CDC0).
    Returns (control_node, bridge_node, n_answered)."""
    try:
        import serial
    except ImportError:
        return None, None, 0
    ctrl = bridge = None
    answered = 0
    for p in list_nodes():
        try:
            s = serial.Serial(p, 115200, timeout=0.5); s.dtr = True; time.sleep(0.15)
            s.reset_input_buffer(); s.write(b'{"q":"status"}\n'); s.flush(); time.sleep(0.4)
            r = s.read(400).decode(errors="replace"); s.close()
            if '"fw":"Hackagotchi"' in r:
                ctrl = p; answered += 1
            else:
                bridge = p
        except Exception:
            pass
    return ctrl, bridge, answered


def replug_stability(rounds):
    """Gate-2 deferral (a): node-map stability across physical replugs (+ a host reboot). After each
    operator-driven replug, RE-DISCOVER by behavior and assert the role is recoverable regardless of
    how macOS renumbered the suffix. Pass: every round has exactly 2 nodes, exactly 1 answers status
    (control), the other is silent (negative control). Records the suffix to document instability."""
    print("\n[deferral a] node-map stability across replug/reboot — role keyed on BEHAVIOR")
    print("    (do at least one round AFTER a host reboot — your choice which).")
    ok = True
    seen = []
    for i in range(rounds):
        input(f"  [{i+1}/{rounds}] unplug the probe, wait ~2s, replug (or reboot the host first), "
              f"wait for enumeration, then press Enter...")
        time.sleep(1.0)
        nodes = list_nodes()
        ctrl, bridge, answered = behavioral_discover()
        two, one, neg = len(nodes) == 2, (answered == 1 and ctrl is not None), bridge is not None
        rok = two and one and neg
        ok = ok and rok
        seen.append(ctrl)
        print(f"    round {i+1}: nodes={nodes} -> control={ctrl} bridge={bridge} "
              f"[2-nodes={two}, exactly-1-answers={one}, neg-control={neg}] {'OK' if rok else 'FAIL'}")
    suff = sorted({c for c in seen if c})
    print(f"    control node across rounds: {suff} "
          f"({'suffix STABLE' if len(suff) <= 1 else 'suffix MOVED — role still recovered by behavior'})")
    print(f"[deferral a] {'PASS' if ok else 'FAIL'}")
    return ok


def live_uart_during_dap(control, uart, secs):
    """Gate-2 deferral (b): CDC0 carries live UART CONCURRENTLY with a DAP flash. Uses the firmware's
    internal PL011 loopback (uloop_on) so no jumper/target-UART wire is needed; gate1_soak.sh supplies
    the concurrent DAP flash load (needs the SWD target + fixtures). Bar: flash 0 stalls; firmware
    urx_drop/utx_drop deltas 0 (no bytes lost on the bridge); CDC1 status answered throughout."""
    try:
        import serial
    except ImportError:
        print("pyserial not installed"); return 2
    soak = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gate1_soak.sh")
    if not os.path.exists(soak):
        print(f"missing {soak} (needed for the concurrent DAP load)"); return 2

    def stat(c):
        c.reset_input_buffer(); c.write(b'{"q":"status"}\n'); c.flush(); time.sleep(0.15)
        for l in reversed(c.read(400).decode(errors="replace").splitlines()):
            if l.strip().startswith("{"):
                try:
                    return json.loads(l)
                except Exception:
                    pass
        return {}

    print(f"\n[deferral b] live UART (internal loopback) during a DAP flash soak — control={control} uart={uart}")
    # open the BRIDGE first + settle (re-inits uart0 / re-arms RX IRQ), THEN control
    b = serial.Serial(uart, 115200, timeout=0.4); b.dtr = True; time.sleep(0.6); b.reset_input_buffer()
    c = serial.Serial(control, 115200, timeout=0.6); c.dtr = True; time.sleep(0.2); c.reset_input_buffer()
    c.write(b'{"q":"uloop_on"}\n'); c.flush(); time.sleep(0.3); c.read(200)
    s0 = stat(c)
    flash = subprocess.Popen(["bash", soak, "150"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    pat = b"HACKAGOTCHI_LIVEUART_0123456789\n"
    sent = recv = ctrl_ok = ctrl_tot = 0
    t0 = time.time()
    while flash.poll() is None and time.time() - t0 < secs:
        b.reset_input_buffer(); b.write(pat); b.flush(); sent += 1; time.sleep(0.04)
        if pat.strip() in b.read(len(pat) + 16).strip():
            recv += 1
        ctrl_tot += 1
        if stat(c).get("fw") == "Hackagotchi":
            ctrl_ok += 1
    out, _ = flash.communicate()
    s1 = stat(c)
    c.write(b'{"q":"uloop_off"}\n'); c.flush(); b.close(); c.close()

    done = next((l for l in out.splitlines() if l.startswith("DONE")), "")
    m = re.search(r"fails=(\d+)\s+stalls=(\d+)", done)
    fails = int(m.group(1)) if m else -1
    stalls = int(m.group(2)) if m else -1
    d_urx = s1.get("urx_drop", 0) - s0.get("urx_drop", 0)
    d_utx = s1.get("utx_drop", 0) - s0.get("utx_drop", 0)
    print(f"  flash: fails={fails} stalls={stalls} | loopback recv {recv}/{sent} | "
          f"urx_drop +{d_urx} utx_drop +{d_utx} | CDC1 answered {ctrl_ok}/{ctrl_tot}")
    ok = (stalls == 0 and d_urx == 0 and d_utx == 0 and ctrl_ok == ctrl_tot and recv >= max(1, sent * 9 // 10))
    print(f"[deferral b] {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--control", help="the CONTROL CDC node (CDC1) for {\"q\":\"status\"}")
    ap.add_argument("--uart", help="the UART-bridge CDC node (CDC0), for reference")
    ap.add_argument("--n", type=int, default=100, help="round-trip count (bar: 100/100)")
    ap.add_argument("--map", action="store_true", help="just dump the name->node mapping aids")
    ap.add_argument("--replug-rounds", type=int, default=0,
                    help="deferral (a): N operator-driven replug/reboot rounds; assert role by behavior")
    ap.add_argument("--live-uart", action="store_true",
                    help="deferral (b): stream CDC0 (internal loopback) during a DAP flash soak")
    ap.add_argument("--secs", type=int, default=60, help="--live-uart duration cap (s)")
    args = ap.parse_args()

    print(f"=== GATE 2  {time.strftime('%FT%TZ', time.gmtime())} ===")
    nodes = list_nodes()
    print(f"[1] /dev/cu.usbmodem* nodes: {nodes or '(none)'}")
    pp = probe_present()
    print(f"[2] CMSIS-DAP still binds (probe-rs list): "
          + ("yes" if pp else ("NO" if pp is False else "probe-rs not installed")))

    if args.map:
        map_names(); return 0
    if args.replug_rounds:
        return 0 if replug_stability(args.replug_rounds) else 1
    if not nodes:
        print("No usbmodem nodes — flash the Gate-2 fork + plug in. Exiting (2).")
        return 2
    if len(nodes) < 2:
        print("FAIL: expected TWO nodes (CDC0 UART + CDC1 control); found one. 2nd CDC not enumerating.")
        return 1

    if args.live_uart:
        ctrl, ubridge = args.control, args.uart
        if not (ctrl and ubridge):
            dctrl, dbridge, _ = behavioral_discover()
            ctrl = ctrl or dctrl; ubridge = ubridge or dbridge
        if not (ctrl and ubridge):
            print("--live-uart needs both nodes identified (pass --control/--uart)"); return 2
        return live_uart_during_dap(ctrl, ubridge, args.secs)

    if not args.control:
        print("\nTwo nodes present. Identify which is the CONTROL CDC (CDC1) — run with --map to see")
        print("the interface names, then re-run:  ./gate2_cdc.py --control <node> --uart <node>")
        map_names()
        return 2

    print(f"[3] round-trip on control={args.control}" + (f" (uart={args.uart})" if args.uart else ""))
    rc = round_trip(args.control, args.n)
    verdict = {0: "PASS", 1: "FAIL", 2: "INCOMPLETE"}[rc]
    print(f"=== GATE 2: {verdict} ===  (close the deferrals with: --replug-rounds 4 (node-map stability,")
    print("    incl. a host reboot) and --live-uart (CDC0 live UART concurrent with a DAP flash soak).)")
    return rc


if __name__ == "__main__":
    sys.exit(main())
