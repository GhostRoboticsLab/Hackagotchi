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

echo "GATE 1 soak: N=$N chip=$CHIP  A=$(basename "$ELF_A") B=$(basename "$ELF_B")  -> $log"
echo "Confirm BEFORE running: probe-rs info reads the target on the REMAPPED pins, OLED counter is ticking." | tee -a "$log"

for i in $(seq 1 "$N"); do
  elf=$([ $((i % 2)) -eq 0 ] && echo "$ELF_A" || echo "$ELF_B")
  if ! timeout 30 probe-rs download --chip "$CHIP" --verify "$elf" >>"$log" 2>&1; then
    rc=$?
    if [ "$rc" -eq 124 ]; then
      echo "STALL/TIMEOUT cycle $i" | tee -a "$log"; stalls=$((stalls+1))
    else
      echo "FAIL(rc=$rc) cycle $i" | tee -a "$log"; fails=$((fails+1))
    fi
    probe-rs list >>"$log" 2>&1
    system_profiler SPUSBDataType 2>/dev/null | grep -iA6 CMSIS >>"$log" 2>&1
  fi
  # independent re-verify (a separate connection — catches a download that lied about verifying)
  if ! timeout 30 probe-rs verify --chip "$CHIP" "$elf" >>"$log" 2>&1; then
    echo "REVERIFY-MISMATCH cycle $i" | tee -a "$log"; fails=$((fails+1))
  fi
  [ $((i % 50)) -eq 0 ] && echo "  ...$i/$N (fails=$fails stalls=$stalls)"
done

echo "DONE N=$N fails=$fails stalls=$stalls" | tee -a "$log"
echo "GATE 1: $([ $((fails+stalls)) -eq 0 ] && echo PASS || echo FAIL)  (bar: 0 fails, 0 stalls)"
echo "Also confirm: OLED counter advanced throughout; heap min-ever-free stable (heap_plot.py)."
exit $(( fails + stalls ))
