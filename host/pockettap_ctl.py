#!/usr/bin/env python3
# pockettap_ctl.py - host CLI for PocketTap's USB host-control commands.
#
# PocketTap (the XIAO UART bridge / black-box recorder, dir pockettap/) accepts JSON
# command lines on its USB-CDC and replies with JSON. This is the companion driver for
# those commands so you don't have to hand-echo JSON at the port. Run with the venv:
#
#   .venv/bin/python tools/pockettap_ctl.py status            # bridge state snapshot
#   .venv/bin/python tools/pockettap_ctl.py freeze            # dump the recorder's freeze-frame
#   .venv/bin/python tools/pockettap_ctl.py screen 3          # jump the bridge to a screen (0..11)
#   .venv/bin/python tools/pockettap_ctl.py clear             # reset tx/rx/throughput/hits stats
#   .venv/bin/python tools/pockettap_ctl.py watch             # live-tail the relayed telemetry
#   .venv/bin/python tools/pockettap_ctl.py --port /dev/cu.usbmodemXXXX status
#
# The bridge is auto-detected by probing each /dev/cu.usbmodem* with {"q":"status"} and
# matching the "fw":"PocketTap" reply (the Pico's own port stays silent / isn't a bridge).
# Pure host-side: stdlib + pyserial, no device risk.

import sys
import glob
import time
import json
import argparse

BAUD = 115200


def _need_serial():
    try:
        import serial  # noqa: F401
        return serial
    except ImportError:
        sys.exit("pockettap_ctl: needs pyserial (run with .venv/bin/python)")


def _ports():
    return sorted(glob.glob("/dev/cu.usbmodem*"))


def _last_json(buf):
    """Return the last complete JSON-object line in a byte buffer, or None."""
    for ln in reversed(buf.split(b"\n")):
        ln = ln.strip().strip(b"\r")
        if ln.startswith(b"{") and ln.endswith(b"}"):
            try:
                return json.loads(ln.decode("utf-8", "replace"))
            except Exception:
                continue
    return None


def _query(s, obj, wait=2.0, want="status"):
    """Send a JSON command and return the first reply object carrying `want`."""
    try:
        s.reset_input_buffer()
    except Exception:
        pass
    s.write((json.dumps(obj) + "\n").encode())
    s.flush()
    t = time.time()
    buf = b""
    while time.time() - t < wait:
        d = s.read(512)
        if d:
            buf += d
            r = _last_json(buf)
            if r is not None and (want is None or want in r):
                return r
        else:
            time.sleep(0.02)
    return _last_json(buf)


def _open(serial, port):
    return serial.Serial(port, BAUD, timeout=0.2)


def _resolve(serial, args):
    """Find the bridge by probing all ports CONCURRENTLY with {"q":"status"} and matching
    the fw:PocketTap reply. Concurrent (not one-at-a-time) so a slow/wedged sibling port
    (the Pico's own CDC) can't eat the time budget or make detection flaky."""
    if args.port:
        return args.port
    handles, bufs = {}, {}
    for p in _ports():
        try:
            handles[p] = serial.Serial(p, BAUD, timeout=0)   # non-blocking
            bufs[p] = b""
        except Exception:
            pass
    if not handles:
        sys.exit("pockettap_ctl: no /dev/cu.usbmodem* ports found")
    for s in handles.values():
        try:
            s.write(b'{"q":"status"}\n')
            s.flush()
        except Exception:
            pass
    found = None
    t = time.time()
    while time.time() - t < 3.0 and not found:
        for p, s in handles.items():
            try:
                d = s.read(512)
            except Exception:
                continue
            if d:
                bufs[p] += d
                r = _last_json(bufs[p])
                if r and r.get("fw") == "PocketTap":
                    found = p
                    break
        time.sleep(0.03)
    for s in handles.values():
        try:
            s.close()
        except Exception:
            pass
    if not found:
        sys.exit("pockettap_ctl: no PocketTap bridge found on /dev/cu.usbmodem* (try --port)")
    return found


def _print_status(st):
    if not st:
        print("(no reply)")
        return
    print("PocketTap  screen=%s  baud=%s  demo=%s" % (st.get("screen"), st.get("baud"), st.get("demo")))
    print("  bytes    tx=%-8s rx=%-8s  throughput peak=%s B/s" % (st.get("tx"), st.get("rx"), st.get("tp_peak")))
    print("  recorder logging=%s  file=%s  sd=%s" % (st.get("logging"), st.get("log_file"), st.get("sd")))
    wedge = st.get("wedge")
    print("  target   wedge=%s  trigger_hits=%s%s" % (
        wedge, st.get("hits"), "   <-- TARGET WENT SILENT" if wedge else ""))


def _print_freeze(fr):
    if not fr:
        print("(no reply)")
        return
    n = fr.get("n", 0)
    print("freeze-frame: %d bytes  wedge=%s  since=%s  hits=%s" % (
        n, fr.get("wedge"), fr.get("since"), fr.get("hits")))
    hexs = (fr.get("hex") or "").split()
    asc = fr.get("ascii") or ""
    # 16 bytes per row with an ASCII gutter (a tiny hexdump of the target's last words)
    for i in range(0, len(hexs), 16):
        row = hexs[i:i + 16]
        print("  %04x  %-47s  %s" % (i, " ".join(row), asc[i:i + 16]))


def main():
    ap = argparse.ArgumentParser(description="Drive PocketTap over its USB host-control channel.")
    ap.add_argument("--port", help="bridge serial port (default: auto-detect)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status", help="print a bridge state snapshot")
    sub.add_parser("freeze", help="dump the recorder's freeze-frame (target's last words)")
    sp = sub.add_parser("screen", help="jump the bridge to a screen (0..11)")
    sp.add_argument("n", type=int)
    sub.add_parser("clear", help="reset tx/rx/throughput/hits + freeze-frame")
    w = sub.add_parser("watch", help="live-tail the relayed telemetry (Ctrl-C to stop)")
    w.add_argument("--seconds", type=float, default=0, help="auto-stop after N seconds (0 = until Ctrl-C)")
    args = ap.parse_args()

    serial = _need_serial()
    port = _resolve(serial, args)
    s = _open(serial, port)
    try:
        if args.cmd == "status":
            _print_status(_query(s, {"q": "status"}))
        elif args.cmd == "freeze":
            _print_freeze(_query(s, {"q": "freeze"}))
        elif args.cmd == "screen":
            r = _query(s, {"screen": args.n})
            print("OK -> screen %s" % r.get("screen") if r and r.get("status") == "OK"
                  else "failed: %s" % r)
        elif args.cmd == "clear":
            r = _query(s, {"clear": True}, want="cleared")
            print("cleared" if r and r.get("cleared") else "failed: %s" % r)
        elif args.cmd == "watch":
            print("# watching %s (Ctrl-C to stop)" % port)
            t0 = time.time()
            buf = b""
            try:
                while True:
                    d = s.read(512)
                    if d:
                        buf += d
                        *lines, buf = buf.split(b"\n")
                        for ln in lines:
                            sys.stdout.write(ln.decode("utf-8", "replace").rstrip("\r") + "\n")
                        sys.stdout.flush()
                    else:
                        time.sleep(0.02)
                    if args.seconds and time.time() - t0 > args.seconds:
                        break
            except KeyboardInterrupt:
                pass
    finally:
        s.close()


if __name__ == "__main__":
    main()
