#!/usr/bin/env bash
# gate0_check.sh — GATE 0: does the STOCK probe firmware halt/erase/flash a SEPARATE target?
#
# Hardware: a bare XIAO flashed with stock debugprobe.uf2 (../../setup.sh --build-stock),
# wired SWCLK/SWDIO/GND to a spare Raspberry Pi Pico target (its own USB power).
#
#   ./gate0_check.sh [path/to/blink.elf]      # default: fixtures/blink_a.elf
#
# Exit: 0 = PASS (all checks), 1 = FAIL (a check failed), 2 = can't run yet (no probe / no ELF).
# Uses exit CODES (not log grepping) so "Verification failed" can't be mistaken for a pass.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
CHIP="${CHIP:-RP2040}"
ELF="${1:-$HERE/fixtures/blink_a.elf}"
OUT="$HERE/gate0"; mkdir -p "$OUT"
fail=0
pass(){ echo "  PASS: $*"; }
bad(){ echo "  FAIL: $*"; fail=1; }

command -v probe-rs >/dev/null 2>&1 || { echo "probe-rs not found (brew install probe-rs-tools)"; exit 2; }
[ -f "$ELF" ] || { echo "test ELF not found: $ELF  (run fixtures/build_fixtures.sh first)"; exit 2; }

echo "=== GATE 0  $(date -u +%FT%TZ)  chip=$CHIP  elf=$(basename "$ELF") ==="
"$HERE/pin_toolchain.sh" >"$OUT/toolchain.txt" 2>&1

echo "[1/5] probe-rs list"
probe-rs list >"$OUT/list.txt" 2>&1
# NB: "No debug probes were found." contains "debug" -> match only the probe TYPE string (CMSIS).
if grep -qi 'CMSIS' "$OUT/list.txt"; then pass "probe enumerated"; else bad "no CMSIS-DAP probe in 'probe-rs list' (is the XIAO flashed + plugged in?)"; cat "$OUT/list.txt"; fi

echo "[2/5] probe-rs info (reads target IDCODE over SWD)"
if probe-rs info --chip "$CHIP" --protocol swd >"$OUT/info.txt" 2>&1; then pass "target connected (IDCODE read)"; else bad "no IDCODE — check SWD wiring + target power (see $OUT/info.txt)"; fi

echo "[3/5] probe-rs erase"
if probe-rs erase --chip "$CHIP" >"$OUT/erase.txt" 2>&1; then pass "mass-erase 0-error"; else bad "erase failed (rc=$?)"; fi

echo "[4/5] probe-rs download --verify"
if probe-rs download --chip "$CHIP" --verify "$ELF" >"$OUT/download_verify.txt" 2>&1; then pass "flash + verify OK"; else bad "download/verify failed (rc=$? — see $OUT/download_verify.txt)"; fi

echo "[5/5] probe-rs reset (watch the target LED start blinking)"
if probe-rs reset --chip "$CHIP" >"$OUT/reset.txt" 2>&1; then pass "reset issued"; else bad "reset failed (rc=$?)"; fi

if command -v openocd >/dev/null 2>&1; then
  echo "[+] openocd independent cross-check (verify_image)"
  if openocd -f interface/cmsis-dap.cfg -f target/rp2040.cfg \
       -c "init; reset halt; flash write_image erase $ELF; verify_image $ELF; reset run; exit" \
       >"$OUT/openocd.txt" 2>&1; then pass "openocd verify_image OK"; else bad "openocd cross-check failed (see $OUT/openocd.txt)"; fi
else
  echo "[+] openocd not installed — skipping cross-check (recommended: brew install open-ocd)"
fi

echo "=== GATE 0: $([ $fail -eq 0 ] && echo PASS || echo FAIL) ===  evidence: $OUT/"
echo "    Re-run 5x for the '5/5 consecutive clean runs' bar."
exit $fail
