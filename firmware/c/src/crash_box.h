/*
 * Hackagotchi — M1 reliability core: the crash box (post-mortem fault diagnosis).
 * SPDX-License-Identifier: MIT
 *
 * The probe routinely runs PROBE-LESS (it IS the debugger — nothing is attached to debug IT). A
 * silent HardFault, stack overflow, or malloc failure would otherwise vanish without a trace. The
 * crash box snapshots a post-mortem the instant a fault fires, parks it in RAM that SURVIVES the
 * reboot, and the next boot surfaces it over CDC1 (`{"q":"lastfault"}`) and the UART0 stdio log.
 * (pico-sdk #228 / the canonical Cortex-M fault-dump pattern.)
 *
 * Cortex-M0+ exposes only ONE fault vector (HardFault — there is no MemManage/Bus/Usage fault, and
 * no stack-limit register), so this single handler is the entire on-chip fault surface. The two
 * software-detected faults FreeRTOS catches (stack overflow, malloc failure) feed the same box via
 * its hooks, so every fault path lands in one place.
 *
 * Storage (verified against memmap_copy_to_ram.ld): the record lives in `.uninitialized_data`
 * (NOLOAD) — outside [__bss_start__, __bss_end__], so crt0 never zeroes it and the copy_to_ram
 * bootrom load never overwrites it; it therefore survives a warm/watchdog reset (and is garbage on a
 * COLD power-on, which `magic` guards). The essentials are also mirrored into the RP2040 watchdog
 * scratch registers — an independent, guaranteed-survival cross-check.
 */
#ifndef HACKAGOTCHI_CRASH_BOX_H
#define HACKAGOTCHI_CRASH_BOX_H

#include <stdint.h>
#include <stdbool.h>

typedef enum {
    CRASH_NONE           = 0,
    CRASH_HARDFAULT      = 1,
    CRASH_STACK_OVERFLOW = 2,
    CRASH_MALLOC_FAIL    = 3,
    CRASH_WATCHDOG       = 4,  // SW-watchdog caught a monitored task stalled
} crash_kind_t;

// Call ONCE early in main(), after stdio is up. If a fault was pending from the previous run it is
// formatted into an internal buffer (crash_box_report) and the pending flag is cleared (report-once);
// on a cold boot the region is initialised clean. Returns true iff a fault was just reported.
bool crash_box_init(void);

// The formatted last-fault line — JSON, host-parseable; "none" until a fault has been captured.
// Stable pointer, safe to hand to the CDC1 reply.
const char *crash_box_report(void);

// Total faults recorded since cold boot (accumulates across reboots).
uint32_t crash_box_count(void);

// Record a software-detected fault (called from the FreeRTOS hooks) then reboot via the watchdog.
// Does not return.
void crash_box_panic_stack_overflow(const char *task_name) __attribute__((noreturn));
void crash_box_panic_malloc_failed(void) __attribute__((noreturn));

// Record a SW-watchdog stall (the named task stopped checking in) then reboot. Does not return.
void crash_box_record_watchdog(const char *task_name) __attribute__((noreturn));

#endif // HACKAGOTCHI_CRASH_BOX_H
