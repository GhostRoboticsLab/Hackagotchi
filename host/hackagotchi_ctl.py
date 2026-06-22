#!/usr/bin/env python3
# hackagotchi_ctl.py - host CLI for Hackagotchi's USB host-control commands.
#
# Hackagotchi (the XIAO UART bridge / black-box recorder, firmware in firmware/c/) accepts JSON
# command lines on its USB-CDC and replies with JSON. This is the companion driver for
# those commands so you don't have to hand-echo JSON at the port. Run with the venv:
#
#   .venv/bin/python host/hackagotchi_ctl.py status            # bridge state snapshot
#   .venv/bin/python host/hackagotchi_ctl.py freeze            # dump the recorder's freeze-frame
#   .venv/bin/python host/hackagotchi_ctl.py screen 3          # jump the bridge to a screen (0..11)
#   .venv/bin/python host/hackagotchi_ctl.py clear             # reset tx/rx/throughput/hits stats
#   .venv/bin/python host/hackagotchi_ctl.py watch             # live-tail the relayed telemetry
#   .venv/bin/python host/hackagotchi_ctl.py --port /dev/cu.usbmodemXXXX status
#
# The bridge is auto-detected by probing each /dev/cu.usbmodem* with {"q":"status"} and
# matching the "fw":"Hackagotchi" reply (the Pico's own port stays silent / isn't a bridge).
# Pure host-side: stdlib + pyserial, no device risk.

import sys
import re
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
        sys.exit("hackagotchi_ctl: needs pyserial (run with .venv/bin/python)")


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
    the fw:Hackagotchi reply. Concurrent (not one-at-a-time) so a slow/wedged sibling port
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
        sys.exit("hackagotchi_ctl: no /dev/cu.usbmodem* ports found")
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
                if r and r.get("fw") == "Hackagotchi":
                    found = p
                    break
        time.sleep(0.03)
    for s in handles.values():
        try:
            s.close()
        except Exception:
            pass
    if not found:
        sys.exit("hackagotchi_ctl: no Hackagotchi bridge found on /dev/cu.usbmodem* (try --port)")
    return found


def _print_status(st):
    if not st:
        print("(no reply)")
        return
    print("Hackagotchi  screen=%s  baud=%s  demo=%s" % (st.get("screen"), st.get("baud"), st.get("demo")))
    if st.get("dap_xfers") is not None:
        print("  probe    dap_xfers=%-8s dap_idle_ms=%s" % (st.get("dap_xfers"), st.get("dap_idle_ms")))
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


def _query_fresh(s, obj, want, settle=0.45):
    """For the async SD verbs (`ls`/`cat`/`tail`): the firmware returns the PREVIOUS result and
    queues a fresh read serviced off the DAP hot path by the low-prio SD task (R1 — FatFs is never
    touched from the control path). So query once to trigger the read, let the SD task run, then
    query again and return that now-fresh result."""
    _query(s, obj, wait=1.0, want=want)     # trigger; returns the stale previous result
    time.sleep(settle)                       # let the SD task service the queued read
    return _query(s, obj, wait=2.0, want=want)


def _log_index(name):
    """'log_007.txt' -> 7. The cat verb addresses logs by NUMBER (i:7 -> log_007.txt), not by
    list position, so `ls` advertises the number to pass to `cat`."""
    m = re.search(r"log_(\d+)\.txt", name or "")
    return int(m.group(1)) if m else None


def _print_lastfault(r):
    if not r or "fault" not in r:
        print("(no reply)")
        return
    f = r.get("fault")
    if not f or f in ({}, "null", "none"):
        print("no fault recorded (clean since last boot)")
        return
    print(json.dumps(f, indent=2) if isinstance(f, (dict, list)) else f)


def _print_baud(r):
    if not r:
        print("(no reply)")
        return
    if "err" in r:
        print("failed: %s (try one of the advertised options)" % r["err"])
        return
    opts = r.get("opts")
    if opts:
        print("baud=%s   options: %s" % (r.get("baud"), ", ".join(str(o) for o in opts)))
    else:
        print("baud set to %s" % r.get("baud"))


def _print_ls(r):
    if not r or "ls" not in r:
        print("(no reply)")
        return
    files = r.get("ls") or []
    print("SD logs: %s total, %s shown" % (r.get("n", len(files)), r.get("shown", len(files))))
    if not files:
        print("  (none)")
        return
    for name in files:
        idx = _log_index(name)
        print("  %-16s  %s" % (name, ("-> cat %d" % idx) if idx is not None else ""))


def _print_macros(r):
    if not r or "macros" not in r:
        print("(no reply)")
        return
    macros = r.get("macros") or []
    if not macros:
        print("  (no macros configured)")
        return
    for i, m in enumerate(macros):
        print("  [%d] %r" % (i, m))


def _do_bootsel(s, port):
    """Send {"q":"bootsel"} — the firmware calls reset_usb_boot() immediately, so there is NO
    reply and the control port re-enumerates as the BOOTSEL mass-storage device. Don't wait for
    a reply (waiting would just time out on a vanished port)."""
    try:
        s.write(b'{"q":"bootsel"}\n')
        s.flush()
    except Exception:
        pass     # the port may already be tearing down — expected
    print("sent bootsel: %s is dropping to BOOTSEL (no reply expected)." % port)
    print("the device is now USB mass-storage 'RPI-RP2'. flash it with:")
    print("    picotool load -x firmware/c/build/hackagotchi_probe.uf2")


def _cat(s, idx, off, read_all):
    """Read SD log #idx. With read_all, page through to EOF (off advances by each chunk's len)."""
    total = 0
    while True:
        r = _query_fresh(s, {"q": "cat", "i": idx, "off": off}, want="file")
        if not r or "file" not in r:
            print("\n(no reply at off=%d)" % off)
            return
        data = r.get("data") or ""
        sys.stdout.write(data)
        ln = r.get("len", len(data))
        total += ln
        if not read_all or r.get("eof") or ln == 0:
            break
        off = r.get("off", off) + ln
    sys.stdout.flush()


def _capture_shot(s, wait=9.0):
    """Send 'S' (a Pico reverse-channel command, char-forwarded through the bridge) and
    collect the framebuffer dump: a `SS> w=.. h=.. n=..` header, raw `SSD <b64>` data lines,
    and a `SS<` terminator. Returns (w, h, raw_bytes)."""
    import re
    import base64
    try:
        s.reset_input_buffer()
    except Exception:
        pass
    s.write(b"S")          # raw char -> not JSON, so the bridge forwards it to the Pico
    s.flush()
    t = time.time()
    buf = b""
    header = None
    data = []
    done = False
    while time.time() - t < wait and not done:
        d = s.read(1024)
        if not d:
            time.sleep(0.02)
            continue
        buf += d
        while b"\n" in buf:
            ln, buf = buf.split(b"\n", 1)
            txt = ln.strip().strip(b"\r").decode("utf-8", "replace")
            if "SS> " in txt:
                header = txt[txt.index("SS> "):]
                data = []                      # (re)start on a fresh header
            elif txt.startswith("SSD "):
                data.append(txt[4:])
            elif "SS<" in txt and header is not None:
                done = True
                break
            elif "SS!" in txt:
                sys.exit("eink-shot: device reported %r (is this an e-ink board?)" % txt)
    if not (header and done):
        sys.exit("eink-shot: no complete framebuffer (header=%s, %d data lines) -- retry"
                 % (bool(header), len(data)))
    m = re.search(r"w=(\d+) h=(\d+) n=(\d+)", header)
    if not m:
        sys.exit("eink-shot: bad header %r" % header)
    w, h, n = int(m.group(1)), int(m.group(2)), int(m.group(3))
    b64 = "".join(data)
    b64 = b64[:len(b64) - (len(b64) % 4)]          # drop any trailing partial group (dropped chunk)
    try:
        raw = base64.b64decode(b64)
    except Exception as e:
        sys.exit("eink-shot: base64 decode failed (%s) -- stream was corrupted, retry" % e)
    if len(raw) != n:
        print("# warn: decoded %d of %d bytes (%d%% -- some chunks dropped; missing area shows gray)"
              % (len(raw), n, 100 * len(raw) // n if n else 0))
    return w, h, raw


def _render_shot(w, h, raw, out, scale):
    """MONO_VLSB framebuffer -> grayscale PNG (ink bit=1 -> black). Falls back to a PGM
    (dependency-free) if Pillow is missing."""
    px = bytearray(w * h)
    for y in range(h):
        base = (y >> 3) * w
        sh = y & 7
        row = y * w
        for x in range(w):
            if base + x < len(raw):
                px[row + x] = 0 if ((raw[base + x] >> sh) & 1) else 255
            else:
                px[row + x] = 128                      # missing data -> gray
    try:
        from PIL import Image
        img = Image.frombytes("L", (w, h), bytes(px))
        if scale > 1:
            img = img.resize((w * scale, h * scale), Image.NEAREST)
        img.save(out)
    except ImportError:
        if not out.endswith(".pgm"):
            out = out.rsplit(".", 1)[0] + ".pgm"
        with open(out, "wb") as f:
            f.write(("P5\n%d %d\n255\n" % (w, h)).encode())
            f.write(bytes(px))
    print("eink-shot: %dx%d -> %s" % (w, h, out))


def main():
    ap = argparse.ArgumentParser(description="Drive Hackagotchi over its USB host-control channel.")
    ap.add_argument("--port", help="bridge serial port (default: auto-detect)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status", help="print a bridge state snapshot")
    sub.add_parser("freeze", help="dump the recorder's freeze-frame (target's last words)")
    sp = sub.add_parser("screen", help="jump the bridge to a screen (0..11)")
    sp.add_argument("n", type=int)
    sub.add_parser("clear", help="reset tx/rx/throughput/hits + freeze-frame")
    # --- post-mortem / maintenance ---
    sub.add_parser("lastfault", help="print the post-mortem crash box (survives a reboot)")
    sub.add_parser("dump", help="crash box + status, in one shot")
    sub.add_parser("bootsel", help="reset to BOOTSEL for a hands-free reflash (port drops; then picotool load -x)")
    # --- target UART ---
    bp = sub.add_parser("baud", help="read, or set, the target-UART baud")
    bp.add_argument("rate", nargs="?", type=int, help="new baud (omit to read current + valid options)")
    mp = sub.add_parser("macro", help="list macros, or send macro N out the target UART")
    mp.add_argument("i", nargs="?", type=int, help="macro index to send (omit to list)")
    # --- SD card / recorder ---
    sub.add_parser("sd", help="SD mount + bring-up status")
    sub.add_parser("rec", help="recorder state")
    sub.add_parser("tail", help="the on-card log tail")
    sub.add_parser("ls", help="list the SD card's log files")
    cp = sub.add_parser("cat", help="read an SD log by NUMBER (e.g. 'cat 7' -> log_007.txt)")
    cp.add_argument("n", type=int, help="log number (the index shown by 'ls')")
    cp.add_argument("--off", type=int, default=0, help="start byte offset (default 0)")
    cp.add_argument("--all", action="store_true", help="page through the whole file to EOF")
    w = sub.add_parser("watch", help="live-tail the relayed telemetry (Ctrl-C to stop)")
    w.add_argument("--seconds", type=float, default=0, help="auto-stop after N seconds (0 = until Ctrl-C)")
    sh = sub.add_parser("shot", help="screenshot the Pico's e-ink over the tap -> PNG")
    sh.add_argument("--out", default="eink_shot.png", help="output image path (default eink_shot.png)")
    sh.add_argument("--scale", type=int, default=2, help="integer upscale for visibility (default 2)")
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
        elif args.cmd == "lastfault":
            _print_lastfault(_query(s, {"q": "lastfault"}, want="fault"))
        elif args.cmd == "dump":
            _print_lastfault(_query(s, {"q": "lastfault"}, want="fault"))
            print("---")
            _print_status(_query(s, {"q": "status"}))
        elif args.cmd == "bootsel":
            _do_bootsel(s, port)
        elif args.cmd == "baud":
            if args.rate is None:
                _print_baud(_query(s, {"q": "baud"}, want="baud"))
            else:
                _print_baud(_query(s, {"q": "baud", "v": args.rate}, want=None))
        elif args.cmd == "macro":
            if args.i is None:
                _print_macros(_query(s, {"q": "macros"}, want="macros"))
            else:
                r = _query(s, {"q": "macro", "i": args.i}, want=None)
                if r and "sent" in r:
                    print("sent macro %d: %r" % (r["sent"], r.get("macro")))
                else:
                    print("failed: %s" % r)
        elif args.cmd in ("sd", "rec"):
            r = _query(s, {"q": args.cmd}, want=None)
            print(json.dumps(r, indent=2) if r else "(no reply)")
        elif args.cmd == "tail":
            r = _query_fresh(s, {"q": "tail"}, want="tail")
            print((r or {}).get("tail", "(no reply)"))
        elif args.cmd == "ls":
            _print_ls(_query_fresh(s, {"q": "ls"}, want="ls"))
        elif args.cmd == "cat":
            _cat(s, args.n, args.off, args.all)
        elif args.cmd == "shot":
            w_, h_, raw = _capture_shot(s)
            _render_shot(w_, h_, raw, args.out, args.scale)
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
