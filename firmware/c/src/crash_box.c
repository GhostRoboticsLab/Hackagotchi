/*
 * Hackagotchi — M1 reliability core: the crash box. SPDX-License-Identifier: MIT
 * See crash_box.h for the rationale (probe-less post-mortem) and the storage/survival argument.
 */

#include "crash_box.h"

#include <stdio.h>
#include <string.h>
#include <pico/stdlib.h>
#include "hardware/watchdog.h"
#include "hardware/structs/watchdog.h"

#define CRASHBOX_MAGIC  0x48434231u  // 'H','C','B','1' — region-validity marker
#define SCRATCH_MAGIC   0x48434232u  // 'H','C','B','2' — watchdog-scratch mirror tag

// One post-mortem record. For a HardFault the full exception-stacked frame is captured; for the two
// software faults only pc/lr (the caller) and the kind/task are meaningful.
typedef struct {
    uint32_t magic;       // CRASHBOX_MAGIC once the region has been validated
    uint32_t count;       // total faults recorded since cold boot (accumulates across reboots)
    uint32_t unreported;  // 1 = a fault is captured but not yet surfaced
    uint32_t kind;        // crash_kind_t
    uint32_t r0, r1, r2, r3, r12, lr, pc, xpsr;  // exception-stacked frame (HardFault)
    uint32_t extra;       // reserved (e.g. fault detail); 0 for now
    char     task[16];    // offending task name when known ("" otherwise)
} crashbox_t;

// NOLOAD RAM: survives a warm/watchdog reset (see header). `used` so LTO/GC never drops it.
static crashbox_t __attribute__((section(".uninitialized_data"), used)) g_box;

// Default is the JSON literal `null` so `{"fault":%s}` is valid JSON when clean.
static char g_report[176] = "null";

static const char *kind_str(uint32_t k) {
    switch (k) {
        case CRASH_HARDFAULT:      return "hardfault";
        case CRASH_STACK_OVERFLOW: return "stackoverflow";
        case CRASH_MALLOC_FAIL:    return "mallocfail";
        case CRASH_WATCHDOG:       return "watchdog";
        default:                   return "none";
    }
}

// Mirror the essentials into the watchdog scratch registers — guaranteed to survive ANY reset on
// RP2040 (untouched by bootrom + crt0): an independent cross-check on the .uninitialized_data path.
static void mirror_to_scratch(void) {
    watchdog_hw->scratch[0] = SCRATCH_MAGIC;
    watchdog_hw->scratch[1] = g_box.kind;
    watchdog_hw->scratch[2] = g_box.pc;
    watchdog_hw->scratch[3] = g_box.lr;
    watchdog_hw->scratch[4] = g_box.count;
}

// Fault-context safe: no FreeRTOS calls, no malloc, no printf. Just word writes, then reboot.
static void record_common(uint32_t kind) {
    if (g_box.magic != CRASHBOX_MAGIC) {  // fault before crash_box_init() ran — start a fresh log
        memset(&g_box, 0, sizeof g_box);
        g_box.magic = CRASHBOX_MAGIC;
    }
    g_box.count++;
    g_box.unreported = 1;
    g_box.kind = kind;
}

static void __attribute__((noreturn)) reboot_now(void) {
    mirror_to_scratch();
    watchdog_reboot(0, 0, 0);          // pc=sp=0 -> normal boot; immediate
    while (1) tight_loop_contents();
}

// C half of the HardFault handler. `frame` -> the 8-word exception-stacked frame:
// [r0, r1, r2, r3, r12, lr, pc, xpsr]. Referenced only from the naked asm below, hence `used`.
__attribute__((used)) void crash_box_from_fault(uint32_t *frame) {
    record_common(CRASH_HARDFAULT);
    g_box.r0  = frame[0];
    g_box.r1  = frame[1];
    g_box.r2  = frame[2];
    g_box.r3  = frame[3];
    g_box.r12 = frame[4];
    g_box.lr  = frame[5];
    g_box.pc  = frame[6];
    g_box.xpsr= frame[7];
    g_box.extra = 0;
    g_box.task[0] = '\0';  // FreeRTOS API is unsafe from fault context — decode pc via addr2line
    reboot_now();
}

// HardFault vector — overrides the pico-sdk weak `isr_hardfault`. Naked: pick the stack pointer that
// holds the stacked frame (PSP if the fault came from a task, MSP from a handler — EXC_RETURN bit 2
// in LR) into r0, then tail-call the C handler. M0+-valid instructions only.
__attribute__((naked)) void isr_hardfault(void) {
    __asm volatile(
        "movs r0, #4                    \n"
        "mov  r1, lr                    \n"
        "tst  r0, r1                    \n"
        "beq  1f                        \n"
        "mrs  r0, psp                   \n"
        "b    2f                        \n"
        "1:                             \n"
        "mrs  r0, msp                   \n"
        "2:                             \n"
        "ldr  r1, =crash_box_from_fault \n"
        "bx   r1                        \n"
    );
}

void crash_box_panic_stack_overflow(const char *task_name) {
    record_common(CRASH_STACK_OVERFLOW);
    g_box.pc = (uint32_t)__builtin_return_address(0);
    g_box.lr = 0;
    g_box.extra = 0;
    if (task_name) {
        strncpy(g_box.task, task_name, sizeof g_box.task - 1);
        g_box.task[sizeof g_box.task - 1] = '\0';
    } else {
        g_box.task[0] = '\0';
    }
    reboot_now();
}

void crash_box_panic_malloc_failed(void) {
    record_common(CRASH_MALLOC_FAIL);
    g_box.pc = (uint32_t)__builtin_return_address(0);
    g_box.lr = 0;
    g_box.extra = 0;
    g_box.task[0] = '\0';
    reboot_now();
}

void crash_box_record_watchdog(const char *task_name) {
    record_common(CRASH_WATCHDOG);
    g_box.pc = (uint32_t)__builtin_return_address(0);
    g_box.lr = 0;
    g_box.extra = 0;
    if (task_name) {
        strncpy(g_box.task, task_name, sizeof g_box.task - 1);
        g_box.task[sizeof g_box.task - 1] = '\0';
    } else {
        g_box.task[0] = '\0';
    }
    reboot_now();
}

bool crash_box_init(void) {
    bool pending = (g_box.magic == CRASHBOX_MAGIC) && g_box.unreported;
    if (g_box.magic != CRASHBOX_MAGIC) {  // cold boot (or RAM lost): clean log
        memset(&g_box, 0, sizeof g_box);
        g_box.magic = CRASHBOX_MAGIC;
    }
    if (pending) {
        snprintf(g_report, sizeof g_report,
                 "{\"kind\":\"%s\",\"count\":%u,\"pc\":\"0x%08lx\",\"lr\":\"0x%08lx\","
                 "\"r0\":\"0x%08lx\",\"xpsr\":\"0x%08lx\",\"task\":\"%s\"}",
                 kind_str(g_box.kind), (unsigned)g_box.count,
                 (unsigned long)g_box.pc, (unsigned long)g_box.lr,
                 (unsigned long)g_box.r0, (unsigned long)g_box.xpsr, g_box.task);
        g_box.unreported = 0;  // surface once
    }
    return pending;
}

const char *crash_box_report(void) { return g_report; }

uint32_t crash_box_count(void) {
    return (g_box.magic == CRASHBOX_MAGIC) ? g_box.count : 0u;
}
