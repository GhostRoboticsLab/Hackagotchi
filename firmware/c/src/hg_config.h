/*
 * Hackagotchi — runtime config store. SPDX-License-Identifier: MIT
 *
 * A small settings store shared by the CDC1 control surface (which uses/mutates it) and the dashboard
 * (which displays it). Grows across M4: macros (M4.2), baud (M4.3). M4.5 adds load/save to a KV file on
 * the SD card. Defaults mirror the original MicroPython firmware's bridge_cfg.
 *
 * Concurrency (disclosed, benign): the writer is the CDC1/TUD task; readers are the dashboard + SD tasks.
 * `baud` is an aligned uint32_t (atomic load/store on Cortex-M0+, never torn). Macro STRINGS can briefly
 * tear if a setmacro lands while a reader is mid-copy — effect is cosmetic only (the OLED self-heals next
 * frame; the config file is re-validated, junk-tolerant, on load) and config edits are infrequent single
 * user actions. Not a memory-safety or R1 issue. Promote to a published snapshot / SD-task-applied intent
 * only if concurrent macro editing ever becomes a real use case (kept out of the snapshot to avoid
 * regrowing it — snapshot size drives the M4.1 DAP-contention caveat).
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

// Baud rates offered by the BAUD selector (matches the MicroPython firmware). hg_set_baud validates
// against this set; the hardware reconfig is applied by the UART owner (cdc_uart_set_baud_request).
extern const uint32_t HG_BAUDS[];
extern const int      HG_N_BAUDS;
uint32_t hg_baud(void);                          // current configured target-UART baud
bool     hg_set_baud(uint32_t b);                // false if b is not one of HG_BAUDS

// SD persistence (KV text). The SD task does the file I/O; these just (de)serialize the in-memory config.
int  hg_config_serialize(char *out, size_t outsz);    // -> KV text; returns the byte count written
void hg_config_apply_kv(const char *buf, size_t len); // parse + apply KV text (tolerates junk lines)

#endif // HACKAGOTCHI_HG_CONFIG_H
