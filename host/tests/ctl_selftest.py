#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Pure-host self-test for hackagotchi_ctl.py. Feeds CANNED device replies through the CLI's
# parsing/dispatch helpers via a mock serial — no pyserial, no hardware — so the host CLI's
# "it works" claim is a falsifiable green check (runnable in CI alongside the firmware host tests).
#
#   python3 host/tests/ctl_selftest.py                      # all checks PASS (exit 0)
#   HG_CTL_SELFTEST_BREAK=1 python3 host/tests/ctl_selftest.py   # verify-the-verifier: MUST FAIL (exit 1)
#
# The break mode flips one expectation so we can prove the harness is capable of going red — a test
# that cannot fail is a silent pass.

import io
import os
import sys
import contextlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import hackagotchi_ctl as ctl  # noqa: E402

ctl.time.sleep = lambda *a, **k: None  # don't actually sleep through the async-verb settle delays

BREAK = os.environ.get("HG_CTL_SELFTEST_BREAK") == "1"
_fails = 0


def check(name, got, want):
    global _fails
    ok = got == want
    print(("ok  " if ok else "FAIL") + "  " + name)
    if not ok:
        print("       got : %r" % (got,))
        print("       want: %r" % (want,))
        _fails += 1


class FakeSerial:
    """Returns each canned chunk on successive read()s, then b'' — mimics a CDC1 reply stream."""

    def __init__(self, chunks):
        self.chunks = list(chunks)
        self.written = []

    def reset_input_buffer(self):
        pass

    def write(self, b):
        self.written.append(b)
        return len(b)

    def flush(self):
        pass

    def read(self, n=512):
        return self.chunks.pop(0) if self.chunks else b""

    def close(self):
        pass


def cap(fn, *a, **k):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fn(*a, **k)
    return buf.getvalue()


# 1) _query returns the reply object carrying the wanted key
r = ctl._query(FakeSerial([b'{"baud":115200,"opts":[9600,115200]}\n']), {"q": "baud"}, wait=0.5, want="baud")
check("_query returns the keyed reply", (r or {}).get("baud"), 115200)

# 2) _query skips non-JSON noise and unkeyed lines, returning only when the wanted key arrives
fs = FakeSerial([b"garbage line\n", b'{"other":1}\n', b'{"fault":{"kind":"hardfault"}}\n'])
r = ctl._query(fs, {"q": "lastfault"}, wait=0.5, want="fault")
check("_query waits past noise for the wanted key", (r or {}).get("fault"), {"kind": "hardfault"})

# 3) cat addresses logs by NUMBER parsed from the ls filename
check("_log_index parses the log number", ctl._log_index("log_007.txt"), 7)
check("_log_index on a non-log name", ctl._log_index("README"), None)

# 4) printers render the salient fields
out = cap(ctl._print_ls, {"ls": ["log_001.txt", "log_007.txt"], "n": 2, "shown": 2})
check("_print_ls advertises the cat number", "-> cat 7" in out and "log_001.txt" in out, True)
out = cap(ctl._print_lastfault, {"fault": {}})
check("_print_lastfault clean-boot path", "no fault recorded" in out, True)
out = cap(ctl._print_lastfault, {"fault": {"kind": "mallocfail", "pc": "0x1000abcd"}})
check("_print_lastfault shows a real fault", "mallocfail" in out, True)
out = cap(ctl._print_baud, {"err": "badbaud"})
check("_print_baud surfaces an error", "failed" in out, True)
out = cap(ctl._print_macros, {"macros": ["reboot", "help"]})
check("_print_macros lists entries", "[0]" in out and "reboot" in out, True)

# 5) cat --all pages through to EOF using off+len (each async verb = trigger + fresh read)
chunks = [
    b'{"file":"log_003.txt","off":0,"len":4,"eof":0,"data":"AAAA"}\n',  # off=0 trigger (stale)
    b'{"file":"log_003.txt","off":0,"len":4,"eof":0,"data":"AAAA"}\n',  # off=0 fresh
    b'{"file":"log_003.txt","off":4,"len":3,"eof":1,"data":"BBB"}\n',   # off=4 trigger
    b'{"file":"log_003.txt","off":4,"len":3,"eof":1,"data":"BBB"}\n',   # off=4 fresh (eof)
]
out = cap(ctl._cat, FakeSerial(chunks), 3, 0, True)
check("_cat --all concatenates chunks to EOF", out, "AAAABBB")

# 6) bootsel sends the verb and never blocks waiting on the (vanished) port for a reply
fs = FakeSerial([])  # no reply ever
out = cap(ctl._do_bootsel, fs, "/dev/cu.fake")
check("bootsel writes the verb", any(b"bootsel" in w for w in fs.written), True)
check("bootsel prints reflash guidance", "picotool load -x" in out, True)

# verify-the-verifier: under BREAK, flip one expectation so the harness MUST be able to go red
if BREAK:
    check("[break] deliberately-wrong expectation", ctl._log_index("log_007.txt"), 999)

print()
if _fails:
    print("ctl_selftest: FAILED — %d check(s)" % _fails)
    sys.exit(1)
print("ctl_selftest: all checks passed")
sys.exit(0)
