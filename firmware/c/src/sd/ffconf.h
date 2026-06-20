/*
 * Hackagotchi — FatFs config overlay. SPDX-License-Identifier: MIT
 *
 * Shadows carlk3's src/include/ffconf.h on the src-first include path to trim features we don't use,
 * shrinking ff.c (smaller flash image; originally an SRAM trim under copy_to_ram, now flash). Everything
 * else is deferred to the upstream ffconf via #include_next — so the only thing to re-check on a carlk3
 * bump is these few overrides.
 *
 * We KEEP ff.c (the FatFs core), FF_USE_LFN, and FF_USE_FIND (used by the log-index scan). We turn off
 * exFAT (cards <=32 GB are FAT32; our card is FAT32) + mkfs/expand (we never format or pre-allocate),
 * which removes those code paths from ff.c.
 */
#ifndef HACKAGOTCHI_FFCONF_OVERLAY
#define HACKAGOTCHI_FFCONF_OVERLAY

#include_next "ffconf.h"   /* carlk3's ffconf (next on the -I path) */

#undef  FF_LBA64
#define FF_LBA64      0     /* 32-bit LBA (SD <=2 TB); 64-bit LBA would require exFAT */
#undef  FF_FS_EXFAT
#define FF_FS_EXFAT   0     /* FAT12/16/32 only — drops the (large) exFAT path from ff.c */
#undef  FF_USE_MKFS
#define FF_USE_MKFS   0     /* we never f_mkfs a card (mount existing FAT only) */
#undef  FF_USE_EXPAND
#define FF_USE_EXPAND 0     /* no f_expand */

#endif /* HACKAGOTCHI_FFCONF_OVERLAY */
