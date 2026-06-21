/*
 * Hackagotchi — runtime config store. SPDX-License-Identifier: MIT
 *
 * A small settings store shared by the CDC1 control surface (which uses/mutates it) and the dashboard
 * (which displays it). Grows across M4: macros (M4.2), baud (M4.3). M4.5 adds load/save to a JSON file
 * on the SD card. Defaults mirror the original MicroPython firmware's bridge_cfg.
 */
#ifndef HACKAGOTCHI_HG_CONFIG_H
#define HACKAGOTCHI_HG_CONFIG_H

#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>

#define HG_N_MACROS   6     // max macros (matches the MicroPython firmware)
#define HG_MACRO_MAX  15    // 14 visible chars + NUL (MicroPython truncates macros to 14)

const char *hg_macro(int i);                    // macro i text, or "" if i out of range / empty
void        hg_set_macro(int i, const char *s); // set macro i (truncated to 14); NULL/"" clears it

#endif // HACKAGOTCHI_HG_CONFIG_H
