/*
 * Hackagotchi board-config SHIM. SPDX-License-Identifier: MIT
 *
 * WHY THIS FILE IS NAMED board_debug_probe_config.h:
 *   Upstream debugprobe's (unmodified) src/probe_config.h selects the board with:
 *       #ifdef DEBUG_ON_PICO  #include "board_pico_config.h"
 *       #else                 #include "board_debug_probe_config.h"
 *       #endif
 *   We do NOT define DEBUG_ON_PICO, so the #else fires. By placing THIS file in boards/ and putting
 *   boards/ FIRST on the compiler include path (see CMakeLists.txt), our copy shadows upstream's
 *   include/board_debug_probe_config.h for every translation unit — including the upstream .c files.
 *
 *   We can't shadow probe_config.h itself: the C quote-include rule searches the including file's
 *   OWN directory first, so upstream's .c files (next to upstream's probe_config.h) always pick up
 *   upstream's probe_config.h regardless of -I order. board_debug_probe_config.h is NOT adjacent to
 *   probe_config.h, so it DOES fall through to the -I search and our copy wins. Verified with
 *   `picotool info -a` (must show SWCLK=GP26/SWDIO=GP27, UART0, "Hackagotchi Probe").
 *
 *   Rebase note: if a future upstream renames this header or changes probe_config.h's board select,
 *   the build picks the wrong pins — the picotool-info check in the gate catches it loudly.
 */
#include "board_hackagotchi_config.h"
