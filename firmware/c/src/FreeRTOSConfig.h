/*
 * Hackagotchi — FreeRTOSConfig overlay. SPDX-License-Identifier: MIT
 *
 * Shadows upstream/debugprobe/src/FreeRTOSConfig.h on the src-first include path to override ONE knob
 * and defer everything else to upstream via #include_next (no full-copy maintenance — the only thing to
 * re-check on an upstream bump is this single override).
 *
 * WHY: the image is copy_to_ram (whole image in SRAM for deterministic SWD), and M2 adds carlk3 FatFs
 * (~4 KB .bss over budget). The FreeRTOS heap was 64 KB but actual use is ~23 KB (task stacks ~14 KB +
 * the 4 KB timer task + idle + TCBs/queues + FatFs LFN mallocs). Shrinking it to 44 KB reclaims 20 KB
 * of SRAM — comfortably fitting FatFs now and the M2 recorder later, while keeping copy_to_ram intact.
 */
#ifndef HACKAGOTCHI_FREERTOSCONFIG_OVERLAY
#define HACKAGOTCHI_FREERTOSCONFIG_OVERLAY

#include_next "FreeRTOSConfig.h"   /* upstream config (sets configTOTAL_HEAP_SIZE = 64*1024) */

#undef  configTOTAL_HEAP_SIZE
#define configTOTAL_HEAP_SIZE (44 * 1024)

#endif /* HACKAGOTCHI_FREERTOSCONFIG_OVERLAY */
