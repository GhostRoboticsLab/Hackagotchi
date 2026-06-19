#!/usr/bin/env bash
# gate0_check.sh — GATE 0: does the STOCK probe firmware halt/erase/flash a SEPARATE target?
#
# Hardware: a bare XIAO flashed with stock debugprobe.uf2 (../../setup.sh --build-stock),
# wired SWCLK/SWDIO/GND to a spare Raspberry Pi Pico target (its own USB power).
#
#   ./gate0_check.sh [path/to/blink.elf]      # default: fixtures/blink_a.elf
#
# Exit: 0 = PASS, 1 = FAIL (a check failed), 2 = can't run yet (no probe). ELF is optional —
# without it, list/info/erase/reset still run (SWD connectivity check); flash+verify are skipped.
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
# Portable timeout (macOS has none): prefer coreutils gtimeout, then timeout, else a kill-after shim.
# Load-bearing here — a bare 'probe-rs erase' with no bound hung a whole gate run for >150s.
if command -v gtimeout >/dev/null 2>&1; then TMO(){ gtimeout "$@"; }
elif command -v timeout  >/dev/null 2>&1; then TMO(){ timeout  "$@"; }
else TMO(){ local t="$1"; shift; "$@" & local p=$!; ( sleep "$t"; kill -9 "$p" 2>/dev/null ) & local w=$!; wait "$p" 2>/dev/null; local rc=$?; kill "$w" 2>/dev/null; return "$rc"; }; fi
# ELF is OPTIONAL: list/info/erase/reset prove SWD connectivity without one. The flash+verify
# steps are skipped (not failed) if it's missing, so you can confirm wiring the instant it's
# soldered — then build fixtures (fixtures/build_fixtures.sh) for the full download+verify pass.
HAVE_ELF=0; [ -f "$ELF" ] && HAVE_ELF=1

echo "=== GATE 0  $(date -u +%FT%TZ)  chip=$CHIP  elf=$([ $HAVE_ELF -eq 1 ] && basename "$ELF" || echo '(none — flash steps skipped)') ==="
"$HERE/pin_toolchain.sh" >"$OUT/toolchain.txt" 2>&1

echo "[1/5] probe-rs list"
probe-rs list >"$OUT/list.txt" 2>&1
# NB: "No debug probes were found." contains "debug" -> match only the probe TYPE string (CMSIS).
if grep -qi 'CMSIS' "$OUT/list.txt"; then pass "probe enumerated"; else bad "no CMSIS-DAP probe in 'probe-rs list' (is the XIAO flashed + plugged in?)"; cat "$OUT/list.txt"; fi

echo "[2/5] probe-rs info (reads target IDCODE over SWD)"
# NB: probe-rs info exits 0 even when the target doesn't answer (it just prints the error).
# Decide by CONTENT: a non-responding target prints "did not respond" / "unsuccessful".
TMO 30 probe-rs info --chip "$CHIP" --protocol swd >"$OUT/info.txt" 2>&1 || true
if grep -qiE 'did not respond|unsuccessful|communication with an access port' "$OUT/info.txt"; then
  bad "no target responded — check SWD wiring + target power (see $OUT/info.txt)"
else
  pass "target connected (IDCODE read)"
fi

echo "[3/5] full-chip mass-erase  (openocd bootrom block-erase: ~8s for 2MB)"
# NB: 'probe-rs erase --chip RP2040' is pathologically slow over CMSIS-DAP (>150s, effectively
# hangs) — it doesn't use the bootrom flash_range_erase block path. openocd's rp2040 flash driver
# does, erasing all 2MB in ~8s. So the full-recovery erase proof goes through openocd here; the
# per-region sector erase is additionally proven by 'download --verify' below.
if command -v openocd >/dev/null 2>&1; then
  if TMO 90 openocd -c "adapter driver cmsis-dap" -c "transport select swd" -c "adapter speed 1000" \
       -f target/rp2040.cfg -c "init" -c "reset halt" -c "flash erase_sector 0 0 last" -c "exit" \
       >"$OUT/erase.txt" 2>&1 && grep -q "erased sectors" "$OUT/erase.txt"; then
    pass "full 2MB mass-erase OK ($(grep -oE 'in [0-9.]+s' "$OUT/erase.txt" | tail -1))"
  else
    bad "mass-erase failed/timeout (see $OUT/erase.txt)"
  fi
else
  echo "  SKIP: openocd not found — full mass-erase not exercised (probe-rs erase is too slow to substitute)"
fi

if [ $HAVE_ELF -eq 1 ]; then
  echo "[4/5] probe-rs download --verify"
  if TMO 60 probe-rs download --chip "$CHIP" --verify "$ELF" >"$OUT/download_verify.txt" 2>&1; then pass "flash + verify OK"; else bad "download/verify failed (rc=$? — see $OUT/download_verify.txt)"; fi
else
  echo "[4/5] download --verify SKIPPED (no ELF — run fixtures/build_fixtures.sh for the full pass)"
fi

echo "[5/5] probe-rs reset (watch the target LED start blinking)"
if TMO 20 probe-rs reset --chip "$CHIP" >"$OUT/reset.txt" 2>&1; then pass "reset issued"; else bad "reset failed (rc=$?)"; fi

if command -v openocd >/dev/null 2>&1 && [ $HAVE_ELF -eq 1 ]; then
  echo "[+] openocd independent cross-check (write + verify_image, a SECOND tool reading back flash)"
  # Separate -c commands (not one concatenated string) so the 'verified N bytes' line actually prints;
  # explicit driver/transport/speed matches the [3/5] erase step and doesn't depend on interface cfg defaults.
  if TMO 120 openocd -c "adapter driver cmsis-dap" -c "transport select swd" -c "adapter speed 1000" \
       -f target/rp2040.cfg \
       -c "init" -c "reset halt" -c "flash write_image erase $ELF" -c "verify_image $ELF" -c "reset run" -c "exit" \
       >"$OUT/openocd.txt" 2>&1 && grep -q "verified" "$OUT/openocd.txt"; then
    pass "openocd verify_image OK ($(grep -oE 'verified [0-9]+ bytes' "$OUT/openocd.txt" | tail -1))"
  else
    bad "openocd cross-check failed (see $OUT/openocd.txt)"
  fi
else
  echo "[+] openocd cross-check skipped (no openocd, or no ELF)"
fi

echo "=== GATE 0: $([ $fail -eq 0 ] && echo PASS || echo FAIL) ===  evidence: $OUT/"
echo "    Re-run 5x for the '5/5 consecutive clean runs' bar."
exit $fail
