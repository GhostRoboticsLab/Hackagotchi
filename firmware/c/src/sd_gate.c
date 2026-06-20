/*
 * Hackagotchi — M2 SD bring-up gate. SPDX-License-Identifier: MIT  (see sd_gate.h)
 */

#include "sd_gate.h"

#include <stdio.h>
#include <string.h>
#include <pico/stdlib.h>

#include "ff.h"   // ChaN FatFs API (carlk3 INTERFACE include: upstream/no-OS-FatFS/src/ff15/source)

TaskHandle_t sd_gate_taskhandle;

#define SD_TEST_PATH "hg_sdgate.txt"

// Self-test result (written once by the SD task, read by CDC1). Plain volatiles: single writer, single
// reader; a torn read is harmless for one-shot status flags.
static volatile bool     s_done        = false;
static volatile bool     s_mounted     = false;
static volatile bool     s_write_ok    = false;
static volatile bool     s_readback_ok = false;
static volatile uint32_t s_bytes       = 0;
static volatile uint32_t s_free_kb     = 0;
static volatile int      s_fr          = -1;  // last FRESULT (0 == FR_OK)

static void run_selftest(void) {
    static FATFS fs;   // static (not stack): FatFs work areas are large
    static FIL   fil;
    char line[64];
    int n = snprintf(line, sizeof line, "HACKAGOTCHI SD GATE up=%lu\n",
                     (unsigned long)(time_us_64() / 1000000ull));

    FRESULT fr = f_mount(&fs, "", 1);   // "" = default volume; 1 = mount now (inits SPI+card)
    s_fr = (int)fr;
    if (fr != FR_OK) { s_done = true; return; }
    s_mounted = true;

    fr = f_open(&fil, SD_TEST_PATH, FA_CREATE_ALWAYS | FA_WRITE);
    if (fr == FR_OK) {
        UINT bw = 0;
        fr = f_write(&fil, line, (UINT)n, &bw);
        f_close(&fil);
        s_bytes = bw;
        if (fr == FR_OK && bw == (UINT)n) s_write_ok = true;
    }
    s_fr = (int)fr;

    if (s_write_ok) {                    // read it back and byte-compare
        fr = f_open(&fil, SD_TEST_PATH, FA_READ);
        if (fr == FR_OK) {
            char rb[64];
            UINT br = 0;
            fr = f_read(&fil, rb, sizeof rb, &br);
            f_close(&fil);
            if (fr == FR_OK && br == (UINT)n && memcmp(rb, line, (size_t)n) == 0)
                s_readback_ok = true;
        }
        s_fr = (int)fr;
    }

    DWORD fre_clust = 0;
    FATFS *fsp = NULL;
    if (f_getfree("", &fre_clust, &fsp) == FR_OK && fsp) {
        uint64_t free_kb = (uint64_t)fre_clust * fsp->csize * 512ull / 1024ull;
        s_free_kb = (uint32_t)free_kb;
    }
    s_done = true;
}

void sd_gate_task(void *ptr) {
    (void)ptr;
    run_selftest();
    for (;;) vTaskDelay(pdMS_TO_TICKS(1000));  // one-shot gate; idle (becomes the recorder in M2.3)
}

void sd_gate_status_json(char *out, unsigned outsz) {
    snprintf(out, outsz,
             "{\"sd\":%d,\"done\":%d,\"write\":%d,\"readback\":%d,"
             "\"bytes\":%u,\"free_kb\":%u,\"fr\":%d}\n",
             (int)s_mounted, (int)s_done, (int)s_write_ok, (int)s_readback_ok,
             (unsigned)s_bytes, (unsigned)s_free_kb, (int)s_fr);
}
