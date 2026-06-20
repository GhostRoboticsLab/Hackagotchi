/*
 * Hackagotchi — FreeRTOSConfig overlay. SPDX-License-Identifier: MIT
 *
 * Shadows upstream/debugprobe/src/FreeRTOSConfig.h on the src-first include path to override ONE knob
 * and defer everything else to upstream via #include_next (no full-copy maintenance — the only thing to
 * re-check on an upstream bump is this single override).
 *
 * WHY: the image is copy_to_ram (whole image in SRAM for deterministic SWD), and M2 adds carlk3 FatFs.
 * The FreeRTOS heap was 64 KB; measured runtime use is ~20 KB (task stacks incl. the 4 KB SD task +
 * 4 KB timer + idle + TCBs/queues + FatFs LFN mallocs). 34 KB leaves ~14 KB free heap — ample — while
 * reclaiming 30 KB of SRAM vs stock. (Was 44 KB; trimmed further in the M2 RAM-headroom pass.)
 */
#ifndef HACKAGOTCHI_FREERTOSCONFIG_OVERLAY
#define HACKAGOTCHI_FREERTOSCONFIG_OVERLAY

#include_next "FreeRTOSConfig.h"   /* upstream config (sets configTOTAL_HEAP_SIZE = 64*1024) */

#undef  configTOTAL_HEAP_SIZE
#define configTOTAL_HEAP_SIZE (34 * 1024)

#endif /* HACKAGOTCHI_FREERTOSCONFIG_OVERLAY */
