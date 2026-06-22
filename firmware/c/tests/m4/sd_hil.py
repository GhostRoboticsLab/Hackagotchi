#!/usr/bin/env python3
"""
sd_hil.py — M4.4 SD-explorer HIL. Proves the card can be browsed over CDC1 without the SD-owning task ever
handing FatFs across a task boundary: {"q":"ls"} lists log_*.txt files, {"q":"cat","i":N,"off":M} reads a
page of log_NNN.txt (the read happens in the SD task; CDC1 reads the result on a later call, like tail).
Camera-free + the SD-EXPLORER screen via self-attestation.

  ./sd_hil.py        # bar: all checks OK + "M4.4 SD EXPLORER: PASS"
"""
import os, sys, time, json, re
import serial
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from hil_ports import find_ctrl

CTRL = find_ctrl()               # CDC1 control — detected by behaviour (replug-proof)


def ctrl(s, query, wait=1.0):
    s.reset_input_buffer()
    s.write((query + "\n").encode()); s.flush()
    t0 = time.time(); buf = b""
    while time.time() - t0 < wait:
        buf += s.read(256)
    for l in reversed([x for x in buf.decode(errors="replace").splitlines() if x.strip().startswith("{")]):
        try:
            return json.loads(l)
        except Exception:
            continue
    return {}


def main():
    ok = True
    def chk(cnd, m):
        nonlocal ok
        print(("  OK  " if cnd else "  FAIL") + " " + m); ok = ok and cnd

    if not CTRL:
        print("no Hackagotchi control port found (is the probe connected?)"); return 2
    print("== M4.4 SD explorer HIL ==")
    c = serial.Serial(CTRL, 115200, timeout=0.4); c.dtr = True; time.sleep(0.15)

    rec = ctrl(c, '{"q":"rec"}'); cur_file = rec.get("file", ""); print("current log:", cur_file)
    m = re.search(r"log_(\d+)\.txt", cur_file)
    chk(m is not None, "recorder has a current log_NNN.txt")
    cur = int(m.group(1)) if m else 0

    ctrl(c, '{"q":"ls"}'); time.sleep(0.4)
    ls = ctrl(c, '{"q":"ls"}'); print("ls:", json.dumps(ls)[:200])
    chk(ls.get("n", 0) >= 1, "ls reports >= 1 log file")
    chk(any(re.fullmatch(r"log_\d+\.txt", f) for f in ls.get("ls", [])), "ls lists log_*.txt names")

    # cat the current log (async: returns the previous result + requests; call twice)
    ctrl(c, '{"q":"cat","i":%d,"off":0}' % cur); time.sleep(0.4)
    cat = ctrl(c, '{"q":"cat","i":%d,"off":0}' % cur); print("cat:", json.dumps(cat)[:180])
    chk(cat.get("file") == "log_%03d.txt" % cur, "cat returns the requested file name")
    chk(cat.get("len", 0) > 0, "cat returned data")
    chk("BLACK BOX" in cat.get("data", ""), "cat returns the on-disk log header (BLACK BOX ...)")

    # cat a non-existent log index
    ctrl(c, '{"q":"cat","i":999,"off":0}'); time.sleep(0.4)
    cat2 = ctrl(c, '{"q":"cat","i":999,"off":0}'); print("cat 999:", cat2)
    chk(cat2.get("len", 0) == 0 and cat2.get("eof") == 1, "cat of a missing file -> len 0, eof 1")

    chk(ctrl(c, '{"q":"cat"}').get("err") == "noi", "cat without an index -> err noi")

    # SD-EXPLORER screen (tool, index 8)
    ctrl(c, '{"q":"screen","n":8}'); time.sleep(0.4)
    sc = ctrl(c, '{"q":"screen"}'); print("sd screen:", sc.get("text"))
    txt = sc.get("text", "")
    chk("SD EXPLORER" in txt, "SD-EXPLORER screen title")
    chk("log files" in txt, "SD screen shows the log count")
    chk(cur_file in txt, "SD screen shows the current log file")

    c.close()
    print("\nM4.4 SD EXPLORER:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
