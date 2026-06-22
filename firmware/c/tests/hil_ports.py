# Shared HIL port discovery. SPDX-License-Identifier: MIT
#
# The /dev/cu.usbmodem* suffix is NOT stable across replug (and a 3rd device on the bench — e.g. a
# Pico W target — adds more nodes), so HIL scripts must identify the ports by BEHAVIOUR, never a
# hardcoded path. The control port (CDC1) is the one that answers {"q":"status"} as Hackagotchi; CDC0
# (the UART bridge) is the XIAO's OTHER interface — the usbmodem node whose suffix is nearest the
# control port (a separate device sorts far away numerically).
#
# Usage from a tests/<milestone>/foo.py script:
#   import os, sys
#   sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
#   from hil_ports import find_ctrl, find_ports
import glob
import re
import time

import serial

BAUD = 115200


def _candidates():
    return sorted(glob.glob("/dev/cu.usbmodem*"))


def find_ctrl(timeout=0.6):
    """The control port (CDC1): the node that answers {"q":"status"} with fw=Hackagotchi. None if absent."""
    for p in _candidates():
        try:
            with serial.Serial(p, BAUD, timeout=timeout) as s:
                s.reset_input_buffer()
                s.write(b'{"q":"status"}\n')
                s.flush()
                time.sleep(0.5)
                if "Hackagotchi" in s.read(400).decode(errors="replace"):
                    return p
        except Exception:
            pass
    return None


def _suffix(p):
    m = re.search(r"(\d+)$", p)
    return int(m.group(1)) if m else -1


def find_ports():
    """Return (CDC0 bridge, CDC1 control). (None, None) if no Hackagotchi; (None, ctrl) if only one node.
    CDC0 is the candidate whose usbmodem suffix is nearest the control port (same physical device)."""
    ctrl = find_ctrl()
    if not ctrl:
        return None, None
    others = [p for p in _candidates() if p != ctrl]
    if not others:
        return None, ctrl
    return min(others, key=lambda p: abs(_suffix(p) - _suffix(ctrl))), ctrl
