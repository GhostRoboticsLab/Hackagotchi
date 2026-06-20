/*
 * Hackagotchi — M3 OLED dashboard task (multi-screen renderer). SPDX-License-Identifier: MIT
 *
 * Evolved from the Gate-1 OLED coexistence harness into the product dashboard: a screen table rendered
 * at the LOWEST priority (tskIDLE_PRIORITY), so the DAP/UART/USB tasks always preempt it and the ~23 ms
 * ssd1306_show() I2C burst never sits on the probe hot path (R1; proven by the M2 coexist soak).
 *
 * Concurrency: the dashboard READS recorder/RTC state ONLY via the SD-task-published snapshot
 * (dash_get_rec_snapshot, sd_gate.h) — it never touches g_rec/the freeze ring/the RTC directly (the M2
 * two-ring rule). Its only i2c1_bus_lock is ssd1306_show(); time comes from the snapshot's cached clock.
 *
 * Input: there is NO physical button (GP27 became SWDIO at Gate 1). Screens advance on an auto-cycle
 * timer and via CDC1 (dash_nav_step / dash_nav_to). The dashboard is the SOLE owner of the screen index;
 * CDC1 only posts intents (atomic slots) that the dashboard consumes + clamps.
 */
#ifndef HACKAGOTCHI_DASHBOARD_H
#define HACKAGOTCHI_DASHBOARD_H

#include <stdint.h>
#include <stddef.h>
#include "FreeRTOS.h"
#include "task.h"

// FreeRTOS task entry. Create at the LOWEST priority (tskIDLE_PRIORITY). See docs/engineering-plan.md §6.
void dashboard_task(void *ptr);

extern TaskHandle_t dashboard_taskhandle;

// --- self-attestation telemetry (read by cdc1_control.c). All plain volatiles: single writer (DASH
// task), single reader (USB task); a torn 32-bit read is harmless for monotonic-trend telemetry. ---
extern volatile uint32_t g_dash_counter;   // dashboard LOOP iterations (proves the task keeps looping)
extern volatile uint32_t g_dash_stall_us;  // measured duration of the last adversarial busy_wait (Gate-1)
extern volatile uint32_t g_dash_shows;     // M3.1: SUCCESSFUL ssd1306_show() count — proves frames reach
                                           //   the panel (incremented only inside the lock-acquired show
                                           //   branch), DISTINCT from g_dash_counter so a dark/skipped
                                           //   panel can't pass as "looping" (verify-the-verifier).
extern volatile int32_t  g_dash_screen;    // M3.1: current screen index (published by the dash task)
extern volatile uint32_t g_dash_stack_free;// M3.1: dashboard task stack high-water (words free), runtime proof

// --- M3.1 navigation intents, posted by CDC1 (TUD task), consumed by the dashboard (atomic slots) ---
void dash_nav_step(int delta);   // next/prev: accumulate +/-1 (relative)
void dash_nav_to(int idx);       // {"q":"screen","n":N}: absolute target
int  dash_screen_count(void);    // number of screens (for clamping / echo)

// --- M3.1 self-attestation: copy the EXACT rendered text of the current frame (title + lines, joined by
// '\n') into out[]; returns the current screen index. The text IS what was drawn to the OLED this frame
// (the framework draws the same text model it publishes), so a host test verifies content with no camera.
int  dash_get_attest(char *out, size_t outsz);

#endif // HACKAGOTCHI_DASHBOARD_H
