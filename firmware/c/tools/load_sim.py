#!/usr/bin/env python3
"""
load_sim.py — simulate sustained target RX load on the Hackagotchi probe (bench util).

Turns on the device-side recorder load generator (recgen) over CDC1 so the recorder's rx
climbs continuously with no real target wired — exercising the live dashboard: the ghost
goes LIVE, the cat HUNTS, the SNIFFER streams, and the THROUGHPUT sparkline maxes. It
monitors the rate live and turns the generator OFF automatically on exit (Ctrl-C / kill /
closing the shell), so the dashboard returns to dozing the moment you stop it.

Usage (use the project venv python — needs pyserial):
    .venv/bin/python firmware/c/tools/load_sim.py            # run until you close it
    .venv/bin/python firmware/c/tools/load_sim.py --secs 30  # run for 30s then stop
    .venv/bin/python firmware/c/tools/load_sim.py --port /dev/cu.usbmodemXXXX

With no --port it autodetects the CDC1 control port (the one that answers {"q":"status"}
with "fw":"Hackagotchi") — the usbmodem suffix is not stable across replug.

Manual reset if it ever lingers:  printf '{"q":"recgen_off"}\\n' > <control-port>

Note: recgen writes continuously to the SD card (~a few KB/s, the device's fixed rate), so
it's for test sessions, not for leaving on for hours.
"""
import argparse
import atexit
import glob
import json
import signal
import sys
import time

import serial


def _read_json(s, w):
    t0 = time.time()
    b = b""
    while time.time() - t0 < w:
        b += s.read(256)
    for l in reversed([x for x in b.decode(errors="replace").splitlines() if x.strip().startswith("{")]):
        try:
            return json.loads(l)
        except Exception:
            pass
    return {}


def _cmd(s, c, w=0.6):
    try:
        s.reset_input_buffer()
        s.write((c + "\n").encode())
        s.flush()
    except Exception:
        return {}
    return _read_json(s, w)


def autodetect():
    for port in sorted(glob.glob("/dev/cu.usbmodem*")):
        try:
            s = serial.Serial(port, 115200, timeout=0.4)
            s.dtr = True
            time.sleep(0.2)
            ans = _cmd(s, '{"q":"status"}', 0.8)
            s.close()
            if ans.get("fw") == "Hackagotchi":
                return port
        except Exception:
            continue
    return None


def main():
    ap = argparse.ArgumentParser(description="Simulate sustained target RX load on the Hackagotchi probe.")
    ap.add_argument("--port", help="CDC1 control port (default: autodetect the Hackagotchi control port)")
    ap.add_argument("--secs", type=float, default=0, help="run for N seconds then stop (default 0 = until closed)")
    args = ap.parse_args()

    port = args.port or autodetect()
    if not port:
        sys.exit("error: no Hackagotchi control port found (pass --port /dev/cu.usbmodemXXXX)")

    s = serial.Serial(port, 115200, timeout=0.4)
    s.dtr = True
    time.sleep(0.3)
    s.reset_input_buffer()

    def stop(*_a):
        _cmd(s, '{"q":"recgen_off"}')
        print("\n[load_sim] stopped (recgen_off sent); dashboard dozes in ~2.5s.", flush=True)
        try:
            s.close()
        except Exception:
            pass
        sys.exit(0)

    atexit.register(lambda: _cmd(s, '{"q":"recgen_off"}'))
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, stop)

    print(f"[load_sim] {port}: high RX load on (recgen). Close / Ctrl-C to stop.", flush=True)
    _cmd(s, '{"q":"recgen_on"}')
    deadline = time.time() + args.secs if args.secs > 0 else None
    last_rx, last_t = None, time.time()
    while True:
        rec = _cmd(s, '{"q":"rec"}')
        rx, now = rec.get("rx"), time.time()
        rate = f"{int((rx - last_rx) / max(now - last_t, 0.001))}" if isinstance(rx, int) and isinstance(last_rx, int) else "?"
        last_rx, last_t = rx, now
        print(f"[load_sim] rx_total={rx}  ~{rate} B/s  logging={rec.get('logging')}  "
              f"wedge={rec.get('wedge')}  -> ghost LIVE / cat HUNTING", flush=True)
        if deadline and now >= deadline:
            stop()
        time.sleep(2)


if __name__ == "__main__":
    main()
