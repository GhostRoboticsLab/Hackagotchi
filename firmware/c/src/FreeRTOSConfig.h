/*
 * Hackagotchi — FreeRTOSConfig overlay. SPDX-License-Identifier: MIT
 *
 * Shadows upstream/debugprobe/src/FreeRTOSConfig.h on the src-first include path to override ONE knob
 * and defer everything else to upstream via #include_next (no full-copy maintenance — the only thing to
 * re-check on an upstream bump is this single override).
 *
 * WHY: right-size the FreeRTOS heap to measured use. Upstream sets 64 KB; measured runtime use is
 * ~20 KB (task stacks incl. the 4 KB SD task + 4 KB timer + idle + TCBs/queues + FatFs LFN mallocs).
 * 34 KB leaves ~14 KB free heap — ample. (Originally a copy_to_ram SRAM-pressure trim; the image now
 * runs from flash XIP so SRAM is no longer tight — 34 KB is kept as a measured value and can be raised
 * in M3 if the UI needs more, since there's now ~174 KB free SRAM.)
 */
#ifndef HACKAGOTCHI_FREERTOSCONFIG_OVERLAY
#define HACKAGOTCHI_FREERTOSCONFIG_OVERLAY

#include_next "FreeRTOSConfig.h"   /* upstream config (sets configTOTAL_HEAP_SIZE = 64*1024) */

#undef  configTOTAL_HEAP_SIZE
#define configTOTAL_HEAP_SIZE (34 * 1024)

#endif /* HACKAGOTCHI_FREERTOSCONFIG_OVERLAY */
