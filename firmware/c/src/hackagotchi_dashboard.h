/*
 * Hackagotchi — M3 OLED dashboard task (multi-screen renderer). SPDX-License-Identifier: MIT
 *
 * Evolved from the Gate-1 OLED coexistence harness into the product dashboard: a screen table rendered
 * at the LOWEST priority (tskIDLE_PRIORITY), so the DAP/UART/USB tasks always preempt it and the ~23 ms
 * ssd1306_show() I2C burst never sits on the probe hot path (R1; proven by the M2 coexist soak).
 *
 * Concurrency: the dashboard READS recorder state ONLY via the SD-task-published snapshot
 * (dash_get_rec_snapshot, sd_gate.h) — it never touches g_rec/the freeze ring directly (the M2 two-ring
 * rule). The OLED is the SOLE device on I2C1 and the dashboard its only user, so the bus needs no mutex —
 * ssd1306_show() runs unlocked, ACK-gated (shows < loops on a dark/NAKing panel).
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
bool dash_hex_toggle(void);      // M4: toggle the SNIFFER hex view; returns the new mode (1=hex)
bool dash_hex_mode(void);        // M4: current SNIFFER hex-view mode
void dash_macro_mark(int i);     // M4.2: mark macro i as the last sent (for the MACRO screen)

// --- M-UI-5 companion interaction (CDC1-posted intents, consumed + clamped by the dashboard) ---
void dash_pet(void);             // {"q":"pet"}: a happy cat beat (heart overlay + chirp)
void dash_ghost_summon(int on);  // {"q":"summon"}=1 / {"q":"banish"}=0 / {"q":"ghost"}=-1 (auto): force ghost state
void dash_char_enable(int on);   // {"q":"ghost","on":0/1}: character layer off=pure-instrument / on=companion
int  dash_char_enabled(void);    // current character-layer state (for the CDC1 reply echo)
void dash_exorcise(void);        // {"q":"exorcise"}: the exorcism dissolve (host fires it after a clean flash)
void dash_theme(int dense);      // {"q":"theme","n":0/1}: calm=reduced-motion / dense=full motion

// --- M3.1 self-attestation: copy the EXACT rendered text of the current frame (title + lines, joined by
// '\n') into out[]; returns the current screen index. The text IS what was drawn to the OLED this frame
// (the framework draws the same text model it publishes), so a host test verifies content with no camera.
int  dash_get_attest(char *out, size_t outsz);

#endif // HACKAGOTCHI_DASHBOARD_H
