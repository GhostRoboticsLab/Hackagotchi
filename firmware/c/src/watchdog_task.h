/*
 * Hackagotchi — M1 reliability core: software watchdog. SPDX-License-Identifier: MIT
 *
 * A high-priority health task that feeds the lone RP2040 HW watchdog ONLY while the must-always-run
 * USB task keeps checking in. If that task wedges, the health task records the reason into the crash
 * box and reboots deterministically; if the health task ITSELF wedges, nothing feeds the HW WDT and
 * the chip hard-resets after the timeout. Either way a wedged probe recovers (into the crash box).
 *
 * Monitors the TUD task on purpose, NOT a low-priority task: a low-prio task legitimately fails to
 * run for seconds under heavy DAP/flash load (priority starvation), so watchdogging it would
 * false-positive and reset the probe MID-FLASH — the exact corruption we are trying to prevent. The
 * TUD task is high-priority and always loops; its silence means a true wedge. (DAP/UART/DASH
 * check-ins can be added once each task's cadence under load is characterised.)
 *
 * ARMED BY DEFAULT (shipping posture: a debug probe must never sit silently wedged). Safety rests on
 * the PRIORITY GUARANTEE: we monitor TUD (prio +2); DAP (prio +1) is lower, so flash load can never
 * starve TUD, and TUD goes silent only on a real wedge — so arm-by-default cannot false-fire under
 * normal load. That argument is soak-CORROBORATED (watchdog_soak.py: sustained DAP flash + CDC
 * firehose, no fire), not soak-proven (a soak can't show absence of a margin). The HW WDT (8 s)
 * backstops the watchdog task itself dying. wd_arm() remains as an idempotent re-arm.
 */
#ifndef HACKAGOTCHI_WATCHDOG_TASK_H
#define HACKAGOTCHI_WATCHDOG_TASK_H

#include <stdint.h>
#include <stdbool.h>
#include "FreeRTOS.h"
#include "task.h"

void watchdog_task(void *ptr);
extern TaskHandle_t watchdog_taskhandle;

// Liveness source + HIL test hook, defined in main.c (the TUD task's home).
extern volatile uint32_t g_tud_checkin;  // bumped every usb_thread loop — the watchdog's heartbeat
extern volatile bool     g_tud_wedge;    // HIL: set -> usb_thread self-wedges so the watchdog fires

// Idempotent re-arm (enables the HW WDT + stall->reboot). Armed by default; there is no software
// disarm — only a reboot returns to the (also-armed) default.
void wd_arm(void);
bool wd_is_armed(void);
uint32_t wd_max_gap_ms(void);  // worst-case observed TUD stall (peak since_ms); 0 = never missed a window

#endif // HACKAGOTCHI_WATCHDOG_TASK_H
