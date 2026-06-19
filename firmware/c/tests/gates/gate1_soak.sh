#!/usr/bin/env bash
# gate1_soak.sh — GATE 1 (make-or-break): the FORK + remapped SWD + ONE low-prio OLED task must
# survive a sustained flash loop with ZERO DAP corruption/stall while the OLED refreshes.
#
# Strategy (see engineering-plan.md §6):
#   * alternate TWO distinct images so --verify is a real read-back diff (not a same-image pass)
#   * wrap every probe-rs call in `timeout` so a DAP hang shows as a detected STALL, not a freeze
#   * run an INDEPENDENT second `probe-rs verify` each cycle (guards a lying download-verify)
#   * dump probe + USB state on the first failure for forensics
#
#   ./gate1_soak.sh [N]        # N cycles, default 1000 (bar: 0 fails, 0 stalls). Stretch: 5000.
#
# PREREQ: validate the SOLDERED SWD pins FIRST:  probe-rs info --chip RP2040 --protocol swd
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
CHIP="${CHIP:-RP2040}"
ELF_A="${ELF_A:-$HERE/fixtures/blink_a.elf}"
ELF_B="${ELF_B:-$HERE/fixtures/blink_b.elf}"
N="${1:-1000}"
mkdir -p "$HERE/gate1"
log="$HERE/gate1/soak_$(date +%Y%m%dT%H%M%S).log"
fails=0; stalls=0

command -v probe-rs >/dev/null 2>&1 || { echo "probe-rs not found"; exit 2; }
for f in "$ELF_A" "$ELF_B"; do [ -f "$f" ] || { echo "missing fixture: $f (run fixtures/build_fixtures.sh)"; exit 2; }; done

# portable timeout — stock macOS has no `timeout`. Prefer gtimeout (brew install coreutils),
# else a background+watchdog fallback. A timed-out call returns 124 (gtimeout) or 137 (kill -9).
if command -v gtimeout >/dev/null 2>&1; then TMO(){ gtimeout "$@"; }
elif command -v timeout  >/dev/null 2>&1; then TMO(){ timeout  "$@"; }
else TMO(){ local t="$1"; shift; "$@" & local p=$!; ( sleep "$t"; kill -9 "$p" 2>/dev/null ) & local w=$!; wait "$p" 2>/dev/null; local rc=$?; kill "$w" 2>/dev/null; return "$rc"; }; fi
is_stall(){ [ "$1" -eq 124 ] || [ "$1" -eq 137 ]; }

echo "GATE 1 soak: N=$N chip=$CHIP  A=$(basename "$ELF_A") B=$(basename "$ELF_B")  -> $log"
echo "Confirm BEFORE running: probe-rs info reads the target on the REMAPPED pins, OLED counter is ticking." | tee -a "$log"

# Provenance banner — tee proof-of-which-firmware/pins into the log so a reader can attribute the run
# to the locked GP26/27 fork (the CMSIS serial is the RP2040 flash unique-id, NOT firmware-specific).
{ echo "=== PROVENANCE $(date -u +%FT%TZ) ==="; probe-rs list 2>&1 | grep -i cmsis
  echo "--- probe-rs info (target must answer on the REMAPPED pins) ---"
  TMO 25 probe-rs info --chip "$CHIP" --protocol swd 2>&1 | grep -iE "Part:|ROM Table|Multidrop|did not respond"
  echo "=== END PROVENANCE ==="; } >>"$log" 2>&1

for i in $(seq 1 "$N"); do
  elf=$([ $((i % 2)) -eq 0 ] && echo "$ELF_A" || echo "$ELF_B")
  if ! TMO 30 probe-rs download --chip "$CHIP" --verify "$elf" >>"$log" 2>&1; then
    rc=$?
    if is_stall "$rc"; then
      echo "STALL/TIMEOUT cycle $i" | tee -a "$log"; stalls=$((stalls+1))
    else
      echo "FAIL(rc=$rc) cycle $i" | tee -a "$log"; fails=$((fails+1))
    fi
    probe-rs list >>"$log" 2>&1
    system_profiler SPUSBDataType 2>/dev/null | grep -iA6 CMSIS >>"$log" 2>&1
  fi
  # independent re-verify (a separate connection — catches a download that lied about verifying).
  # CRITICAL: `probe-rs verify` (0.31) prints "Verification failed: contents do not match" but STILL
  # EXITS 0 on a mismatch — so we must decide by STDOUT, never by exit code (the old `if ! ...` was a
  # no-op guard). A stall still shows via the timeout exit code.
  vout=$(TMO 30 probe-rs verify --chip "$CHIP" "$elf" 2>&1); vrc=$?
  echo "$vout" >>"$log"
  if is_stall "$vrc"; then
    echo "REVERIFY-STALL cycle $i" | tee -a "$log"; stalls=$((stalls+1))
  elif echo "$vout" | grep -q "Verification failed" || ! echo "$vout" | grep -q "Verification successful"; then
    echo "REVERIFY-MISMATCH cycle $i" | tee -a "$log"; fails=$((fails+1))
  fi
  [ $((i % 50)) -eq 0 ] && echo "  ...$i/$N (fails=$fails stalls=$stalls)"
done

echo "DONE N=$N fails=$fails stalls=$stalls" | tee -a "$log"
echo "GATE 1: $([ $((fails+stalls)) -eq 0 ] && echo PASS || echo FAIL)  (bar: 0 fails, 0 stalls)"
echo "Also confirm: OLED counter advanced throughout; heap min-ever-free stable (heap_plot.py)."
exit $(( fails + stalls ))
