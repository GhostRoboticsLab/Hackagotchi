/*
 * Hackagotchi — Gate-1 OLED coexistence harness.
 * SPDX-License-Identifier: MIT
 *
 * The make-or-break Gate-1 test (docs/engineering-plan.md §6): the LOWEST-priority core-0 FreeRTOS
 * task drives a real SSD1306 over I2C1 (GP6/GP7) in a tight loop while the DAP/UART/USB tasks run,
 * to prove a continuous "dashboard" load NEVER stalls or corrupts the SWD flash path over thousands
 * of flash cycles. debugprobe-v2.2.3 is SINGLE-CORE FreeRTOS (configNUM_CORES=1; SMP — and the #189
 * flash regression — came later), so there is no core to pin to: the guarantee is purely priority —
 * this task sits below DAP and is fully preemptible by it.
 *
 * Each ssd1306_show() is a ~23 ms blocking i2c_write_blocking burst (1 KB framebuffer @ 400 kHz) —
 * that IS the "blocking burst off the hot path" under test; preemption must keep DAP unaffected.
 *
 * This is the coexistence harness, NOT the product dashboard. No real SD/buzzer/button yet.
 *
 * Build knobs (CMake -D…):
 *   ADVERSARIAL_STALL_MS  if >0, busy_wait_us(ms*1000) each loop — the "slow SD write" proxy
 *                         (engineering-plan §4.1): a long non-yielding low-prio core-0 stall that
 *                         the higher-prio DAP task must preempt without flash corruption.
 *   DASH_I2C_ADDR (0x3C), DASH_I2C_HZ (400000)
 */

#include <stdio.h>
#include <pico/stdlib.h>
#include <hardware/i2c.h>

#include "FreeRTOS.h"
#include "task.h"

#include "ssd1306.h"
#include "hackagotchi_dashboard.h"

#ifndef DASH_I2C_ADDR
#define DASH_I2C_ADDR 0x3Cu
#endif
#ifndef DASH_I2C_HZ
#define DASH_I2C_HZ 400000u
#endif
#ifndef ADVERSARIAL_STALL_MS
#define ADVERSARIAL_STALL_MS 0
#endif

// XIAO + Seeed expansion: OLED on I2C1, SDA=GP6, SCL=GP7 (shares the bus with the RTC @0x51).
#define DASH_I2C_INST i2c1
#define DASH_I2C_SDA  6u
#define DASH_I2C_SCL  7u
#define DASH_REFRESH_MS 250u   // ~4 Hz

TaskHandle_t dashboard_taskhandle;

// Self-attestation telemetry (see header). Written only here, read by cdc1_control.c's status reply.
volatile uint32_t g_dash_counter = 0;
volatile uint32_t g_dash_stall_us = 0;

void dashboard_task(void *ptr) {
    (void)ptr;

    // Bring up I2C1 on GP6/GP7. These pins are independent of SWD (GP26/27) and the SD bus.
    i2c_init(DASH_I2C_INST, DASH_I2C_HZ);
    gpio_set_function(DASH_I2C_SDA, GPIO_FUNC_I2C);
    gpio_set_function(DASH_I2C_SCL, GPIO_FUNC_I2C);
    gpio_pull_up(DASH_I2C_SDA);
    gpio_pull_up(DASH_I2C_SCL);

    // The SSD1306 framebuffer is malloc()'d from the C-lib heap, NOT the FreeRTOS heap — so the
    // xPortGet*HeapSize() numbers below cleanly reflect task/RTOS allocations (the heap_4/heap_1
    // decision metric).
    ssd1306_t disp;
    // MUST set before init: external_vcc is the only field ssd1306_init() READS but does not set.
    // The expansion OLED runs off the internal charge pump, so false => init sends 0x8D,0x14 (pump
    // ON). A garbage stack value here sends 0x8D,0x10 (pump OFF) => no boost voltage => DARK panel.
    disp.external_vcc = false;
    bool ok = ssd1306_init(&disp, 128, 64, DASH_I2C_ADDR, DASH_I2C_INST);

    uint32_t counter = 0;
    char l0[22], l1[22], l2[22], l3[22];
    TickType_t wake = xTaskGetTickCount();

    for (;;) {
        counter++;
        g_dash_counter = counter;   // [HACKAGOTCHI] self-attest: proves THIS task kept looping
        unsigned freeh = (unsigned)xPortGetFreeHeapSize();
        unsigned minh  = (unsigned)xPortGetMinimumEverFreeHeapSize();

#if ADVERSARIAL_STALL_MS > 0
        // Slow-SD-write proxy: a long non-yielding stall in the lowest-prio task. The DAP task must
        // preempt this and finish flashes uncorrupted — that preemption is exactly what we validate.
        // Measure the ACTUAL elapsed time so the status reply proves the busy_wait truly fired (not
        // optimised away), closing the Gate-1 stressor-actually-ran provenance gap at runtime.
        uint64_t _stall_t0 = time_us_64();
        busy_wait_us((uint32_t)ADVERSARIAL_STALL_MS * 1000u);
        g_dash_stall_us = (uint32_t)(time_us_64() - _stall_t0);
#endif

        if (ok) {
            snprintf(l0, sizeof l0, "HACKAGOTCHI G1");
            snprintf(l1, sizeof l1, "OLED+DAP n=%lu", (unsigned long)counter);
            snprintf(l2, sizeof l2, "heap free %u", freeh);
            snprintf(l3, sizeof l3, "heap min  %u", minh);
            ssd1306_clear(&disp);
            ssd1306_draw_string(&disp, 0, 0, 1, l0);
            ssd1306_draw_string(&disp, 0, 16, 1, l1);
            ssd1306_draw_string(&disp, 0, 32, 1, l2);
            ssd1306_draw_string(&disp, 0, 48, 1, l3);
            ssd1306_show(&disp);  // ~23 ms blocking I2C burst — the hot-path-coexistence stress
        }

        // Best-effort machine-readable heap series for heap_plot.py, emitted on GP0 TX (uart0
        // stdio; the bridge UART is idle during the gate). Capture with any UART tap; the live
        // watermark on the OLED is the primary, always-available evidence.
        if ((counter & 0x3u) == 0u)
            printf("HEAP n=%lu free=%u min=%u stall=%d\n",
                   (unsigned long)counter, freeh, minh, (int)ADVERSARIAL_STALL_MS);

        xTaskDelayUntil(&wake, pdMS_TO_TICKS(DASH_REFRESH_MS));
    }
}
