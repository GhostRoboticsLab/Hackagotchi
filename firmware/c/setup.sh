#!/usr/bin/env bash
# setup.sh — fetch the pinned debugprobe base (and Pico SDK) so we can build the STOCK probe
# for Gate 0 and use it as the fork base. Does NOT modify upstream. See README.md + the
# engineering plan (docs/engineering-plan.md §2, §6).
#
#   ./setup.sh                 # clone debugprobe@v2.2.3 + submodules into upstream/
#   ./setup.sh --build-stock   # additionally build the stock standalone probe UF2 (needs Arm GCC + cmake)
#
# upstream/ is gitignored — it is fetched on demand, not vendored into this repo (the product
# fork will live on the org remote).
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
UPSTREAM="$HERE/upstream"
DP_TAG="debugprobe-v2.2.3"          # pinned: before the #189 SMP flash regression (commit 457e048)
DP_REPO="https://github.com/raspberrypi/debugprobe.git"
DP_DIR="$UPSTREAM/debugprobe"

mkdir -p "$UPSTREAM"

if [ -d "$DP_DIR/.git" ]; then
  echo "[setup] debugprobe already cloned at $DP_DIR (tag: $(git -C "$DP_DIR" describe --tags 2>/dev/null || echo '?'))"
else
  echo "[setup] cloning $DP_REPO @ $DP_TAG (recursive)..."
  git clone --branch "$DP_TAG" --depth 1 --recurse-submodules "$DP_REPO" "$DP_DIR"
fi
echo "[setup] debugprobe @ $(git -C "$DP_DIR" describe --tags 2>/dev/null || echo "$DP_TAG")"

# M2: carlk3 no-OS-FatFS-SD (SDIO+SPI) — FAT/SD library for the black-box recorder. Pinned, fetched
# into upstream/ (gitignored), NOT a submodule — same convention as debugprobe.
FATFS_TAG="v3.6.2"                   # latest tag (Apache-2.0; wraps ChaN FatFs R0.15)
FATFS_REPO="https://github.com/carlk3/no-OS-FatFS-SD-SDIO-SPI-RPi-Pico.git"
FATFS_DIR="$UPSTREAM/no-OS-FatFS"
if [ -d "$FATFS_DIR/.git" ]; then
  echo "[setup] FatFs already cloned at $FATFS_DIR (tag: $(git -C "$FATFS_DIR" describe --tags 2>/dev/null || echo '?'))"
else
  echo "[setup] cloning $FATFS_REPO @ $FATFS_TAG ..."
  git clone --branch "$FATFS_TAG" --depth 1 "$FATFS_REPO" "$FATFS_DIR"
fi
echo "[setup] FatFs @ $(git -C "$FATFS_DIR" describe --tags 2>/dev/null || echo "$FATFS_TAG")"

# Pico SDK: prefer an existing PICO_SDK_PATH; otherwise fetch a pinned copy beside upstream.
if [ -n "${PICO_SDK_PATH:-}" ] && [ -d "${PICO_SDK_PATH}" ]; then
  echo "[setup] using PICO_SDK_PATH=$PICO_SDK_PATH"
else
  SDK_DIR="$UPSTREAM/pico-sdk"
  SDK_TAG="2.2.0"                     # pinned: matches the runner cache + THIRD-PARTY-NOTICES + CMake (>=2)
  if [ ! -d "$SDK_DIR/.git" ]; then
    echo "[setup] PICO_SDK_PATH not set — cloning pico-sdk @ $SDK_TAG into $SDK_DIR (this is large)..."
    git clone --branch "$SDK_TAG" --depth 1 --recurse-submodules https://github.com/raspberrypi/pico-sdk.git "$SDK_DIR"
  fi
  export PICO_SDK_PATH="$SDK_DIR"
  echo "[setup] PICO_SDK_PATH=$PICO_SDK_PATH (pinned $SDK_TAG)"
fi

if [ "${1:-}" = "--build-stock" ]; then
  command -v cmake >/dev/null || { echo "[setup] cmake not found — install it to build"; exit 1; }
  command -v arm-none-eabi-gcc >/dev/null || { echo "[setup] arm-none-eabi-gcc not found — install the Arm toolchain"; exit 1; }
  echo "[setup] building STOCK standalone debugprobe (DEBUG_ON_PICO=OFF) for Gate 0..."
  BUILD="$DP_DIR/build"
  mkdir -p "$BUILD"
  ( cd "$BUILD" && cmake .. -DDEBUG_ON_PICO=OFF -DPICO_SDK_PATH="$PICO_SDK_PATH" && make -j )
  echo "[setup] built: $(ls "$BUILD"/*.uf2 2>/dev/null || echo '(no .uf2 found — check build output)')"
  echo "[setup] Flash the XIAO (BOOTSEL -> RPI-RP2), then run tests/gates/gate0_check.sh"
fi

echo "[setup] done."
