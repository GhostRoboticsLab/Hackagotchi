/*
 * Hackagotchi — M1 reliability core: software watchdog task. SPDX-License-Identifier: MIT
 * See watchdog_task.h for the rationale (monitor the high-prio TUD task; disarmed by default).
 */

#include "watchdog_task.h"
#include "crash_box.h"

#include <pico/stdlib.h>
#include "hardware/watchdog.h"

#define WD_FEED_MS        500u   // health-task period: feed the HW WDT + sample the heartbeat
#define WD_HW_TIMEOUT_MS 8000u   // HW WDT timeout — backstop for the health task ITSELF wedging
#define WD_TUD_STALL_MS  4000u   // TUD must check in within this window or it is declared wedged

TaskHandle_t watchdog_taskhandle;

static volatile bool s_armed = false;

void wd_arm(void)      { s_armed = true; }
bool wd_is_armed(void) { return s_armed; }

void watchdog_task(void *ptr) {
    (void)ptr;

    uint32_t last_checkin = 0;
    uint32_t since_ms = 0;
    bool hw_on = false;
    TickType_t wake = xTaskGetTickCount();

    for (;;) {
        if (s_armed) {
            if (!hw_on) {
                // Arm on the first armed cycle: enable the HW WDT and start fresh from the current
                // heartbeat (so arming never inherits a stale "already stalled" reading).
                last_checkin = g_tud_checkin;
                since_ms = 0;
                watchdog_enable(WD_HW_TIMEOUT_MS, 1);  // pause_on_debug = 1
                hw_on = true;
            }

            uint32_t now = g_tud_checkin;
            if (now != last_checkin) {
                last_checkin = now;
                since_ms = 0;
            } else {
                since_ms += WD_FEED_MS;
            }

            if (since_ms >= WD_TUD_STALL_MS)
                crash_box_record_watchdog("TUD");  // records the reason, then reboots — no return

            watchdog_update();  // we reached here => the health task is alive; feed the HW WDT
        }
        // Disarmed: fully inert — the HW WDT is never enabled, so no reboot can occur.

        xTaskDelayUntil(&wake, pdMS_TO_TICKS(WD_FEED_MS));
    }
}
