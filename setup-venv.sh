#!/usr/bin/env sh
# setup-venv.sh — create the Python venv the host tooling expects and install requirements.txt.
#
# Every doc says "run with .venv/bin/python …" but nothing created it; this does. It builds one
# venv at the repo root and symlinks firmware/c/.venv -> ../.venv so BOTH conventions resolve to
# the same interpreter:
#
#   .venv/bin/python host/hackagotchi_ctl.py status              # from the repo root (host CLI)
#   (cd firmware/c && .venv/bin/python tests/m4/macro_hil.py)    # from firmware/c (HIL suites)
#
# Idempotent: re-running just upgrades the packages. Pure host-side — never touches the device.
set -eu

ROOT="$(cd "$(dirname "$0")" && pwd)"
VENV="$ROOT/.venv"
PY="${PYTHON:-python3}"

if [ ! -d "$VENV" ]; then
    echo "creating venv at $VENV"
    "$PY" -m venv "$VENV"
fi

echo "installing requirements.txt"
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet -r "$ROOT/requirements.txt"

# Make the firmware/c HIL convention (.venv/bin/python from firmware/c) resolve to the same venv.
if [ -d "$ROOT/firmware/c" ] && [ ! -e "$ROOT/firmware/c/.venv" ]; then
    ln -s ../../.venv "$ROOT/firmware/c/.venv"
    echo "linked firmware/c/.venv -> ../../.venv"
fi

echo
echo "done. Try:"
echo "    .venv/bin/python host/hackagotchi_ctl.py status"
echo "    python3 host/tests/ctl_selftest.py        # no hardware needed"
