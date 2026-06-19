#!/usr/bin/env bash
# pin_toolchain.sh — record host toolchain versions so every gate log is reproducible.
# Never fails: a missing tool is reported as "not found".
set -uo pipefail

ver() {
  local bin="$1"; shift
  if command -v "$bin" >/dev/null 2>&1; then
    printf '%-22s ' "$bin:"; "$bin" "$@" 2>&1 | head -1
  else
    printf '%-22s not found\n' "$bin:"
  fi
}

echo "=== PocketDebugger toolchain snapshot $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
echo "host:                  $(sw_vers -productName 2>/dev/null) $(sw_vers -productVersion 2>/dev/null) ($(uname -m))"
ver probe-rs --version
ver openocd --version
ver picotool version
ver arm-none-eabi-gcc --version
ver cmake --version
ver python3 --version
echo "PICO_SDK_PATH:         ${PICO_SDK_PATH:-<unset>}"
