/*
 * Hackagotchi — Gate-1 OLED coexistence harness (NOT the product dashboard).
 * SPDX-License-Identifier: MIT
 */
#ifndef HACKAGOTCHI_DASHBOARD_H
#define HACKAGOTCHI_DASHBOARD_H

#include "FreeRTOS.h"
#include "task.h"

// FreeRTOS task entry. Create at the LOWEST priority (tskIDLE_PRIORITY), so the DAP/UART/USB
// tasks always preempt it. See docs/engineering-plan.md §6 (GATE 1).
void dashboard_task(void *ptr);

extern TaskHandle_t dashboard_taskhandle;

// Self-attestation telemetry (read by cdc1_control.c's status reply). Proving the dashboard task
// actually LOOPS (g_dash_counter monotonic) and that the adversarial busy_wait actually FIRED
// (g_dash_stall_us measured live ~= ADVERSARIAL_STALL_MS*1000) — closes the Gate-1 provenance +
// dashboard-liveness gaps without a GP0 loopback jumper. Plain volatiles: single writer (DASH task),
// single reader (USB task); a torn 32-bit read is harmless for monotonic-trend telemetry.
extern volatile uint32_t g_dash_counter;   // dashboard loop iterations (OLED frame counter n)
extern volatile uint32_t g_dash_stall_us;  // measured duration of the last adversarial busy_wait (us)

#endif // HACKAGOTCHI_DASHBOARD_H
