#!/usr/bin/env bash
# build_fixtures.sh — build TWO DISTINCT blink ELFs (different rates) so the Gate-1 soak's
# `--verify` is a genuine read-back diff, not a same-image pass that could mask a stuck write.
# Both still visibly blink the target's LED (different cadence) so a human can corroborate flashes.
#
# PREREQ: PICO_SDK_PATH set (or run ../../../setup.sh first) + arm-none-eabi-gcc + cmake.
#   ./build_fixtures.sh        # -> blink_a.elf (250ms) and blink_b.elf (80ms)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
: "${PICO_SDK_PATH:?set PICO_SDK_PATH (or run ../../../setup.sh which fetches the SDK)}"
command -v arm-none-eabi-gcc >/dev/null || { echo "arm-none-eabi-gcc not found — install the Arm toolchain"; exit 1; }
command -v cmake >/dev/null || { echo "cmake not found"; exit 1; }

gen() {  # $1=name  $2=delay_ms  $3=out.elf
  local name="$1" delay="$2" out="$3" d="$HERE/src/$1"
  mkdir -p "$d"
  cat > "$d/$name.c" <<EOF
#include "pico/stdlib.h"
int main(void) {
    const uint pin = PICO_DEFAULT_LED_PIN;   // GP25 on a plain Pico target
    gpio_init(pin); gpio_set_dir(pin, GPIO_OUT);
    while (true) { gpio_put(pin, 1); sleep_ms($delay); gpio_put(pin, 0); sleep_ms($delay); }
}
EOF
  cat > "$d/CMakeLists.txt" <<EOF
cmake_minimum_required(VERSION 3.13)
include(\$ENV{PICO_SDK_PATH}/external/pico_sdk_import.cmake)
project($name C CXX ASM)
pico_sdk_init()
add_executable($name $name.c)
target_link_libraries($name pico_stdlib)
pico_add_extra_outputs($name)
EOF
  ( cd "$d" && rm -rf build && mkdir build && cd build \
      && cmake .. -DPICO_SDK_PATH="$PICO_SDK_PATH" -DPICO_BOARD=pico >/dev/null \
      && make -j >/dev/null )
  cp "$d/build/$name.elf" "$HERE/$out"
  echo "  built $out ($(basename "$d/build/$name.elf"), ${delay}ms blink)"
}

echo "[fixtures] building two distinct blink ELFs (target = plain Pico)..."
gen blink_a 250 blink_a.elf
gen blink_b 80  blink_b.elf
echo "[fixtures] done -> $HERE/blink_a.elf  $HERE/blink_b.elf"
echo "[fixtures] sanity: they must differ ->"
cmp -s "$HERE/blink_a.elf" "$HERE/blink_b.elf" && echo "  ⚠️ IDENTICAL (bug!)" || echo "  OK: distinct images"
