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

#endif // HACKAGOTCHI_DASHBOARD_H
