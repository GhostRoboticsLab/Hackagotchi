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
 * SAFETY: disarmed by default — the HW WDT is not even enabled until wd_arm() is called over CDC1.
 * A freshly flashed image therefore cannot reboot-loop; arming is an explicit, observable action.
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

// Arm enforcement (enables the HW WDT + stall->reboot). One-way for the session; default disarmed.
void wd_arm(void);
bool wd_is_armed(void);

#endif // HACKAGOTCHI_WATCHDOG_TASK_H
