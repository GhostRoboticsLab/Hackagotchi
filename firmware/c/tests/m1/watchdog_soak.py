#!/usr/bin/env python3
"""
M1 watchdog arm-by-default SAFETY soak.  SPDX-License-Identifier: MIT

Claim under test (corroboration, not proof — see note):
  With the SW watchdog ARMED BY DEFAULT, sustained heavy load on the MONITORED task (TUD) does NOT
  spuriously reboot the probe: `up` only increases, `crashes` never increments.

The watchdog monitors TUD, so the load must hit TUD, not just DAP. This soak therefore drives BOTH
concurrently: a background thread flashing the target over DAP (USB vendor transfers -> TUD) AND a
foreground CDC0 loopback "firehose" (USB CDC IN+OUT -> TUD + the bridge task). If TUD ever stalled past
the 4 s window under this, the armed watchdog would fire -> `up` resets / `crashes` jumps -> FAIL.

NOTE ON STRENGTH: a soak cannot positively prove the ABSENCE of a false-fire margin. The real safety
guarantee is the PRIORITY argument (TUD prio +2 > DAP +1, TUD always has work and is never starved);
this soak CORROBORATES it under real sustained load. To avoid a silent no-op pass, it requires that
real flashing actually happened (flash_ok >= MIN) and real CDC traffic flowed.

Run (from firmware/c):  .venv/bin/python tests/m1/watchdog_soak.py [seconds]
"""
import glob
import subprocess
import sys
import threading
import time

import serial  # pyserial

BAUD = 115200
FIX = ["tests/gates/fixtures/blink_a.elf", "tests/gates/fixtures/blink_b.elf"]
FIREHOSE = b"HACKAGOTCHI_WD_SOAK_FIREHOSE_0123456789_ABCDEFGHIJKLMNOP\n"  # 56 B, pumped via CDC0 loopback
MIN_FLASHES = 5  # below this, the DAP load was a no-op -> soak invalid (closes the silent-pass path)


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


def find_ports():
    cands = sorted(glob.glob("/dev/cu.usbmodem*"))
    ctrl = None
    for p in cands:
        try:
            with serial.Serial(p, BAUD, timeout=0.6) as s:
                s.reset_input_buffer()
                s.write(b'{"q":"status"}\n')
                s.flush()
                time.sleep(0.5)
                if "Hackagotchi" in s.read(400).decode(errors="replace"):
                    ctrl = p
                    break
        except Exception:
            pass
    if not ctrl:
        return None, None
    data = [p for p in cands if p != ctrl]
    return (data[0] if data else None), ctrl


def status(c):
    c.reset_input_buffer()
    c.write(b'{"q":"status"}\n')
    c.flush()
    time.sleep(0.4)
    return c.read(400).decode(errors="replace").strip()


def main():
    secs = int(sys.argv[1]) if len(sys.argv) > 1 else 80
    data_port, ctrl_port = find_ports()
    if not ctrl_port or not data_port:
        print("FAIL: need both CDC nodes (CDC0 data + CDC1 control)")
        return 1
    print(f"CDC0={data_port} CDC1={ctrl_port}; soaking ~{secs}s (DAP flash thread + CDC0 firehose)")

    flash = {"ok": 0, "fail": 0, "stop": False}

    def flasher():
        i = 0
        while not flash["stop"]:
            elf = FIX[i % 2]
            i += 1
            try:
                r = subprocess.run(["probe-rs", "download", "--chip", "RP2040", elf],
                                   capture_output=True, text=True, timeout=60)
                if r.returncode == 0:
                    flash["ok"] += 1
                else:
                    flash["fail"] += 1
                    print(f"  [flash rc={r.returncode}] {r.stderr.strip()[:90]}")
            except Exception as e:
                flash["fail"] += 1
                print(f"  [flash EXC] {e}")

    up0 = cr0 = None
    last_up = -1
    fh_bytes = 0
    fired = False
    with serial.Serial(data_port, BAUD, timeout=1.0) as d, serial.Serial(ctrl_port, BAUD, timeout=1.0) as c:
        time.sleep(0.6)
        c.write(b'{"q":"uloop_on"}\n')
        c.flush()
        time.sleep(0.4)
        c.read(100)

        # Zero the watchdog's stall peak so wd_gap reflects ONLY this run (not the boot floor) — without
        # this, wd_gap is a stale latched value and any margin check on it is constant-true.
        c.write(b'{"q":"wd_reset"}\n')
        c.flush()
        time.sleep(0.3)
        c.read(100)

        base = status(c)
        up0, cr0, armed = field_int(base, "up"), field_int(base, "crashes"), field_int(base, "wd_armed")
        tud0 = field_int(base, "tud")
        print(f"[baseline] {base}")
        if armed != 1:
            print("FAIL: watchdog is not armed by default (wd_armed != 1)")
            return 1
        if tud0 is None:
            print("FAIL: status has no tud field — wrong/old firmware")
            return 1
        last_up = up0

        t = threading.Thread(target=flasher, daemon=True)
        t.start()

        t0 = time.time()
        i = 0
        while time.time() - t0 < secs:
            # CDC0 loopback firehose -> loads the monitored TUD task hard
            d.reset_input_buffer()
            d.write(FIREHOSE)
            d.flush()
            fh_bytes += len(FIREHOSE)
            time.sleep(0.04)
            d.read(len(FIREHOSE))
            if i % 25 == 0:  # health check every ~2 s
                st = status(c)
                up, cr = field_int(st, "up"), field_int(st, "crashes")
                if up is None or cr is None:
                    print("FAIL: lost the probe (no status) mid-soak")
                    flash["stop"] = True
                    return 1
                if cr != cr0 or up < last_up:
                    print(f"FAIL: watchdog/fault FIRED — up {last_up}->{up}, crashes {cr0}->{cr}")
                    fired = True
                    break
                last_up = up
                print(f"  t={int(time.time()-t0):2d}s up={up} crashes={cr} "
                      f"flash_ok={flash['ok']} flash_fail={flash['fail']} fh={fh_bytes//1024}KB")
            i += 1

        flash["stop"] = True
        t.join(timeout=65)
        final = status(c)
        up1, cr1 = field_int(final, "up"), field_int(final, "crashes")
        gap1 = field_int(final, "wd_gap")
        tud1 = field_int(final, "tud")
        c.write(b'{"q":"uloop_off"}\n')
        c.flush()
        print(f"[final] {final}")

    GAP_CEIL = 1500       # >=3 missed 500ms windows post-reset = TUD nearing the 4000ms stall threshold
    TUD_MIN_ADVANCE = 10000  # the heartbeat must have advanced a LOT -> load genuinely reached TUD
    tud_delta = (tud1 - tud0) if (tud1 is not None and tud0 is not None) else 0
    # verdict
    if fired:
        return 1
    if flash["ok"] < MIN_FLASHES:
        print(f"FAIL: only {flash['ok']} flashes succeeded (< {MIN_FLASHES}) — DAP load was a no-op, soak invalid")
        return 1
    # POSITIVE proof the load actually reached the MONITORED task (not just 'didn't reboot while idle').
    if tud_delta < TUD_MIN_ADVANCE:
        print(f"FAIL: TUD heartbeat only advanced {tud_delta} (< {TUD_MIN_ADVANCE}) — load did not reach "
              f"the monitored task, soak inconclusive")
        return 1
    if cr1 != cr0:
        print(f"FAIL: crashes changed {cr0}->{cr1}")
        return 1
    if up1 is None or up0 is None or up1 < up0:
        print(f"FAIL: up not monotonic ({up0}->{up1}) — probe rebooted")
        return 1
    # wd_gap was RESET at soak start, so this is the worst missed-window count DURING this run (not the
    # boot floor). Healthy = 0; climbing = TUD nearing the stall threshold.
    if gap1 is None or gap1 >= GAP_CEIL:
        print(f"FAIL: wd_gap={gap1}ms (since reset) reached/exceeded {GAP_CEIL}ms — TUD stalled under load")
        return 1
    print(f"\nPASS: under real load (TUD heartbeat +{tud_delta}, {flash['ok']} flashes [{flash['fail']} "
          f"failed], {fh_bytes//1024}KB firehose) the armed watchdog did NOT false-fire: "
          f"up {up0}->{up1} monotonic, crashes steady at {cr1}, wd_gap {gap1}ms (since reset) << 4000ms")
    return 0


if __name__ == "__main__":
    sys.exit(main())
