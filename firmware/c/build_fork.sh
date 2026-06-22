#!/usr/bin/env bash
# build_fork.sh — build the Hackagotchi probe fork (debugprobe-v2.2.3 overlay + OLED coexistence task).
#
# Reuses the PROVEN RP2040 C-build recipe: pinned Arm GCC 13.3.Rel1 + the existing pico-sdk 2.2.0
# (NOT the host's system GCC 16.1). Run ./setup.sh first to fetch upstream/debugprobe.
#
#   ./build_fork.sh                 # normal Gate-1 image  -> build/hackagotchi_probe.uf2
#   ADVERSARIAL_STALL_MS=50 ./build_fork.sh   # adversarial 50 ms-stall variant (separate image)
#
# Overridable env: FW_BUILD_DIR, GCC_DIR, PICO_SDK_PATH, BUILD_DIR.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
# Per-machine toolchain root. Don't bake an absolute path into the repo: set FW_BUILD_DIR (or
# GCC_DIR / PICO_SDK_PATH directly) in your env, or drop a gitignored build_fork.local.sh next to this.
[ -f "$HERE/build_fork.local.sh" ] && . "$HERE/build_fork.local.sh"
FW_BUILD_DIR="${FW_BUILD_DIR:-$HOME/fw-build}"
GCC_DIR="${GCC_DIR:-$FW_BUILD_DIR/arm-gnu-toolchain-13.3.rel1-darwin-arm64-arm-none-eabi}"
PICO_SDK_PATH="${PICO_SDK_PATH:-$FW_BUILD_DIR/micropython/lib/pico-sdk}"
BUILD_DIR="${BUILD_DIR:-$HERE/build}"
ADVERSARIAL_STALL_MS="${ADVERSARIAL_STALL_MS:-0}"
ADVERSARIAL_AT_DAP_PRIO="${ADVERSARIAL_AT_DAP_PRIO:-OFF}"
# Pin the DAP/USB transaction hot path into SRAM (XIP-cache-contention fix). ON = v1.1+ shipping default;
# set HG_PIN_DAP=OFF to reproduce the pre-fix XIP image for an A/B soak.
HG_PIN_DAP="${HG_PIN_DAP:-ON}"
# M5: release semver compiled into the firmware (reported by {"q":"status"} as "ver"). Override with
# VERSION=1.0.0 ./build_fork.sh ; CI passes the workflow `version` input. Default = untagged dev build.
HG_VERSION="${VERSION:-${HG_VERSION:-0.0.0-dev}}"

[ -x "$GCC_DIR/bin/arm-none-eabi-gcc" ] || { echo "pinned Arm GCC not found at $GCC_DIR/bin"; exit 1; }
[ -d "$PICO_SDK_PATH" ] || { echo "pico-sdk not found at $PICO_SDK_PATH"; exit 1; }
[ -d "$HERE/upstream/debugprobe" ] || { echo "upstream/debugprobe missing — run ./setup.sh first"; exit 1; }

export PATH="$GCC_DIR/bin:$PATH"
export PICO_SDK_PATH
export PICO_TOOLCHAIN_PATH="$GCC_DIR"

# The pico-sdk needs its own TinyUSB submodule for debugprobe (MicroPython leaves it uninitialised,
# vendoring its own). Populate it once if missing (additive — does not affect MicroPython builds).
if [ ! -f "$PICO_SDK_PATH/lib/tinyusb/src/tusb.h" ]; then
    echo "[build] initialising pico-sdk lib/tinyusb submodule (one-time)…"
    git -C "$PICO_SDK_PATH" submodule update --init lib/tinyusb
fi

echo "[build] gcc      : $(arm-none-eabi-gcc --version | head -1)"
echo "[build] pico-sdk : $PICO_SDK_PATH"
echo "[build] stall    : ADVERSARIAL_STALL_MS=$ADVERSARIAL_STALL_MS"
echo "[build] pin-dap  : HG_PIN_DAP=$HG_PIN_DAP"
echo "[build] version  : HG_VERSION=$HG_VERSION"
echo "[build] out dir  : $BUILD_DIR"

rm -rf "$BUILD_DIR" && mkdir -p "$BUILD_DIR"
cd "$BUILD_DIR"
cmake "$HERE" \
    -DPICO_SDK_PATH="$PICO_SDK_PATH" \
    -DADVERSARIAL_STALL_MS="$ADVERSARIAL_STALL_MS" \
    -DADVERSARIAL_AT_DAP_PRIO="$ADVERSARIAL_AT_DAP_PRIO" \
    -DHG_PIN_DAP="$HG_PIN_DAP" \
    -DHG_VERSION="$HG_VERSION" \
    -DCMAKE_EXPORT_COMPILE_COMMANDS=ON
make -j

echo
echo "[build] DONE:"
ls -la "$BUILD_DIR"/hackagotchi_probe.uf2 "$BUILD_DIR"/hackagotchi_probe.elf 2>/dev/null
arm-none-eabi-size "$BUILD_DIR/hackagotchi_probe.elf" 2>/dev/null || true
echo "[build] Flash: BOOTSEL the XIAO, then  picotool load -x $BUILD_DIR/hackagotchi_probe.uf2"
