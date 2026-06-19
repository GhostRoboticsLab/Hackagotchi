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
fails=0; stalls=0

command -v openocd >/dev/null 2>&1 || { echo "openocd not found (brew install open-ocd)"; exit 2; }
for f in "$ELF_A" "$ELF_B"; do [ -f "$f" ] || { echo "missing fixture: $f"; exit 2; }; done

echo "GATE 1 openocd soak: N=$N  -> $log"
for i in $(seq 1 "$N"); do
  elf=$([ $((i % 2)) -eq 0 ] && echo "$ELF_A" || echo "$ELF_B")
  if ! timeout 60 openocd -f interface/cmsis-dap.cfg -f target/rp2040.cfg \
        -c "init; reset halt; flash write_image erase $elf; verify_image $elf; reset run; exit" \
        >>"$log" 2>&1; then
    rc=$?
    if [ "$rc" -eq 124 ]; then echo "STALL/TIMEOUT cycle $i" | tee -a "$log"; stalls=$((stalls+1));
    else echo "FAIL(rc=$rc) cycle $i" | tee -a "$log"; fails=$((fails+1)); fi
    system_profiler SPUSBDataType 2>/dev/null | grep -iA6 CMSIS >>"$log" 2>&1
  fi
  [ $((i % 25)) -eq 0 ] && echo "  ...$i/$N (fails=$fails stalls=$stalls)"
done
echo "DONE N=$N fails=$fails stalls=$stalls" | tee -a "$log"
echo "GATE 1 (openocd): $([ $((fails+stalls)) -eq 0 ] && echo PASS || echo FAIL)"
exit $(( fails + stalls ))
