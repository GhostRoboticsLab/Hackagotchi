#!/usr/bin/env bash
# gate1_soak_openocd.sh — GATE 1 twin of gate1_soak.sh, driven by the OpenOCD client instead of
# probe-rs. OpenOCD pipelines DAP transactions differently; the #189 SMP regression only showed
# under flash, so varying the host client widens coverage of the coexistence test.
#
#   ./gate1_soak_openocd.sh [N]    # default 200 (openocd flash is slower; run fewer than probe-rs)
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ELF_A="${ELF_A:-$HERE/fixtures/blink_a.elf}"
ELF_B="${ELF_B:-$HERE/fixtures/blink_b.elf}"
N="${1:-200}"
mkdir -p "$HERE/gate1"
log="$HERE/gate1/soak_openocd_$(date +%Y%m%dT%H%M%S).log"
# shellcheck source=lib_target_state.sh
. "$HERE/lib_target_state.sh"   # classify_target / target_hint: TARGET-glitch vs PROBE fault
fails=0; stalls=0; tgt=0

command -v openocd >/dev/null 2>&1 || { echo "openocd not found (brew install open-ocd)"; exit 2; }
for f in "$ELF_A" "$ELF_B"; do [ -f "$f" ] || { echo "missing fixture: $f"; exit 2; }; done

# portable timeout — stock macOS has no `timeout`. Prefer gtimeout (brew install coreutils),
# else a background+watchdog fallback. A timed-out call returns 124 (gtimeout) or 137 (kill -9).
if command -v gtimeout >/dev/null 2>&1; then TMO(){ gtimeout "$@"; }
elif command -v timeout  >/dev/null 2>&1; then TMO(){ timeout  "$@"; }
else TMO(){ local t="$1"; shift; "$@" & local p=$!; ( sleep "$t"; kill -9 "$p" 2>/dev/null ) & local w=$!; wait "$p" 2>/dev/null; local rc=$?; kill "$w" 2>/dev/null; return "$rc"; }; fi
is_stall(){ [ "$1" -eq 124 ] || [ "$1" -eq 137 ]; }

echo "GATE 1 openocd soak: N=$N  -> $log"
for i in $(seq 1 "$N"); do
  elf=$([ $((i % 2)) -eq 0 ] && echo "$ELF_A" || echo "$ELF_B")
  # Explicit driver/transport/speed (matches the Gate-0-proven gate0_check.sh invocation) rather
  # than `-f interface/cmsis-dap.cfg` — the explicit form is the one validated on this host/openocd.
  if ! TMO 60 openocd -c "adapter driver cmsis-dap" -c "transport select swd" -c "adapter speed 1000" \
        -f target/rp2040.cfg \
        -c "init" -c "reset halt" -c "flash write_image erase $elf" -c "verify_image $elf" \
        -c "reset run" -c "exit" \
        >>"$log" 2>&1; then
    rc=$?
    if is_stall "$rc"; then echo "STALL/TIMEOUT cycle $i" | tee -a "$log"; stalls=$((stalls+1));
    else
      cls=$(classify_target RP2040)
      if [ "$cls" = TARGET_GLITCH ]; then echo "TARGET-GLITCH cycle $i" | tee -a "$log"; tgt=$((tgt+1));
      else echo "FAIL(rc=$rc,$cls) cycle $i" | tee -a "$log"; fails=$((fails+1)); fi
      target_hint "$cls" | tee -a "$log"
    fi
    system_profiler SPUSBDataType 2>/dev/null | grep -iA6 CMSIS >>"$log" 2>&1
  fi
  [ $((i % 25)) -eq 0 ] && echo "  ...$i/$N (fails=$fails stalls=$stalls tgt=$tgt)"
done
echo "DONE N=$N fails=$fails stalls=$stalls target_glitch=$tgt" | tee -a "$log"
# PROBE verdict excludes target_glitch (AHB-AP gone = target brown-out/lockup, not a probe fault).
echo "PROBE VERDICT (openocd): $([ $((fails+stalls)) -eq 0 ] && echo PASS || echo FAIL)  (bar: 0 fails, 0 stalls)" | tee -a "$log"
[ "$tgt" -gt 0 ] && echo "TARGET/BENCH: $tgt glitch event(s) — power-cycle the target between sustained runs (NOT a probe bug)." | tee -a "$log"
exit $(( fails + stalls ))
