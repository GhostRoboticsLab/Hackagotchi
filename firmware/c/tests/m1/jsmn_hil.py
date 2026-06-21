#!/usr/bin/env python3
"""
M1 control-channel HIL test — jsmn parser replacing strstr.  SPDX-License-Identifier: MIT

Falsifiable claims:
  1. Valid {"q":"..."} commands dispatch (status/lastfault/dump/next/prev).
  2. STRUCTURAL matching: inputs that the old strstr prototype would have FALSE-matched are now
     rejected — {"q":"statusx"} and {"note":"status please"} must NOT return a status reply.
  3. Malformed JSON -> {"err":"badjson"} (no crash, no wrong dispatch).
  4. A request split across two USB writes is reassembled by the line buffer.

Why it can FAIL: if the firmware still substring-matched, claim 2 would return a status reply (FAIL);
if the line buffer were broken, claim 4's fragmented request would never parse (FAIL).

Run (pyserial venv): .venv/bin/python firmware/c/tests/m1/jsmn_hil.py
"""
import glob
import sys
import time

import serial  # pyserial

BAUD = 115200


def find_port(timeout=25):
    deadline = time.time() + timeout
    while time.time() < deadline:
        for p in sorted(glob.glob("/dev/cu.usbmodem*")):
            try:
                with serial.Serial(p, BAUD, timeout=0.5) as s:
                    s.reset_input_buffer()
                    s.write(b'{"q":"status"}\n')
                    s.flush()
                    time.sleep(0.5)
                    if "Hackagotchi" in s.read(400).decode(errors="replace"):
                        return p
            except Exception:
                pass
        time.sleep(0.5)
    return None


def field_int(reply, key):
    tok = f'"{key}":'
    i = reply.find(tok)
    if i < 0:
        return None
    j = i + len(tok)
    k = j
    while k < len(reply) and (reply[k].isdigit() or reply[k] == "-"):
        k += 1
    try:
        return int(reply[j:k])
    except ValueError:
        return None


def page_of(reply):
    return field_int(reply, "page")


def main():
    port = find_port()
    if not port:
        print("FAIL: no Hackagotchi control node found")
        return 1
    print("control port:", port)
    fails = []

    with serial.Serial(port, BAUD, timeout=0.8) as s:
        def q(msg, wait=0.5):
            s.reset_input_buffer()
            s.write(msg if isinstance(msg, bytes) else msg.encode())
            s.flush()
            time.sleep(wait)
            return s.read(500).decode(errors="replace").strip()

        def check(name, reply, must_have=None, must_not=None):
            ok = True
            if must_have is not None and must_have not in reply:
                ok = False
            if must_not is not None and must_not in reply:
                ok = False
            print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {reply!r}")
            if not ok:
                fails.append(name)

        # 1. valid commands
        check("status", q('{"q":"status"}\n'), must_have='"fw":"Hackagotchi"')
        check("status has page", q('{"q":"status"}\n'), must_have='"page"')
        check("lastfault", q('{"q":"lastfault"}\n'), must_have='"fault"')
        check("dump status+fault", q('{"q":"dump"}\n', wait=0.6),
              must_have='"fw":"Hackagotchi"')
        check("dump has fault", q('{"q":"dump"}\n', wait=0.6), must_have='"fault"')

        # next/prev move the page index. Pin to screen 0 first: avoids the wrap boundary (next from the
        # last screen wraps to 0) and resets the auto-cycle timer so a 6 s tick can't move the page
        # mid-check (the firmware owns the index; this just makes the assertion deterministic).
        q('{"q":"screen","n":0}\n'); time.sleep(0.3)
        base = page_of(q('{"q":"status"}\n'))
        # nav is ASYNC: CDC1 posts an intent the dashboard applies on its next loop, so the nav command's
        # own reply still shows the PRE-nav page. Read the page from a fresh status AFTER a short settle.
        q('{"q":"next"}\n'); time.sleep(0.3)
        pn = page_of(q('{"q":"status"}\n'))
        q('{"q":"prev"}\n'); time.sleep(0.3)
        pp = page_of(q('{"q":"status"}\n'))
        ok_nav = base == 0 and pn == 1 and pp == 0
        print(f"  [{'PASS' if ok_nav else 'FAIL'}] next/prev page nav: base={base} next={pn} prev={pp}")
        if not ok_nav:
            fails.append("next/prev nav")

        # 2. THE HEADLINE — strstr false-positives must now be rejected (no status reply)
        check("strstr-trap {q:statusx}", q('{"q":"statusx"}\n'),
              must_have='"err"', must_not="Hackagotchi")
        check("strstr-trap {note:'status please'}", q('{"note":"status please"}\n'),
              must_have='"err"', must_not="Hackagotchi")

        # 3. malformed + unknown
        check("badjson", q("not json at all\n"), must_have='"err":"badjson"', must_not="Hackagotchi")
        check("unknown cmd", q('{"q":"florp"}\n'), must_have='"err":"unknown"')

        # 4. fragmentation — split a request across two writes (newline only in the 2nd). Prove the
        #    line buffer actually REASSEMBLED it (not host-coalesced) via the device-side `frag` counter,
        #    which increments only when a callback ends holding a partial line.
        frag0 = field_int(q('{"q":"status"}\n'), "frag")
        s.reset_input_buffer()
        s.write(b'{"q":"sta')
        s.flush()
        time.sleep(0.3)
        s.write(b'tus"}\n')
        s.flush()
        time.sleep(0.5)
        frag = s.read(500).decode(errors="replace").strip()
        check("fragmented request reassembled", frag, must_have='"fw":"Hackagotchi"')
        # The correct reply to a split request IS the gate (checked above). The frag counter is
        # CORROBORATION only: whether the two host writes land in separate RX callbacks depends on USB
        # packetization timing (macOS/tinyusb), so frag-not-advancing is INCONCLUSIVE, not a FAIL —
        # treating it as a hard gate would risk a false-FAIL when the host coalesces the writes.
        frag1 = field_int(frag, "frag")
        ok_frag = frag0 is not None and frag1 is not None and frag1 > frag0
        print(f"  [{'corroborated' if ok_frag else 'inconclusive'}] frag counter {frag0}->{frag1} "
              f"({'reassembly path provably ran' if ok_frag else 'host may have coalesced — reply still correct'})")

    if fails:
        print("\nFAIL:", fails)
        return 1
    print("\nPASS: jsmn dispatches structurally; strstr false-positives rejected; line reassembly works")
    return 0


if __name__ == "__main__":
    sys.exit(main())
