/*
 * Hackagotchi — M2 SD/recorder task. SPDX-License-Identifier: MIT  (see sd_gate.h)
 *
 * The single FatFs caller. At boot it runs the SD bring-up self-test (mount + write + read-back,
 * reported via CDC1 {"q":"sd"}), then becomes the black-box recorder: drains the recorder ring that
 * cdc_task tees into, runs the recorder core (recorder.c) against the carlk3 FatFs seam, and logs the
 * target UART to session files. LOW priority (idle+0, below DAP) — every FatFs/SPI op stays off the
 * DAP/USB hot path (R1). All recorder_t state is owned here (no other task touches it).
 */

#include "sd_gate.h"

#include <stdio.h>
#include <stdlib.h>   // atoi
#include <string.h>
#include <pico/stdlib.h>

#include "ff.h"            // ChaN FatFs (carlk3)
#include "probe_config.h"  // PROBE_UART_BAUDRATE (header baud)
#include "recorder.h"
#include "uart_bridge.h"

TaskHandle_t sd_gate_taskhandle;

#define SD_TEST_PATH "hg_sdgate.txt"

// --- bring-up self-test result (gate; {"q":"sd"}) ---
static volatile bool     s_done = false, s_mounted = false, s_write_ok = false, s_readback_ok = false;
static volatile uint32_t s_bytes = 0, s_free_kb = 0;
static volatile int      s_fr = -1;

static FATFS s_fs;   // the one mount, owned by this task

static void run_selftest(void) {
    static FIL fil;
    char line[64];
    int n = snprintf(line, sizeof line, "HACKAGOTCHI SD GATE up=%lu\n",
                     (unsigned long)(time_us_64() / 1000000ull));
    FRESULT fr = f_mount(&s_fs, "", 1);
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
    if (s_write_ok) {
        fr = f_open(&fil, SD_TEST_PATH, FA_READ);
        if (fr == FR_OK) {
            char rb[64]; UINT br = 0;
            fr = f_read(&fil, rb, sizeof rb, &br);
            f_close(&fil);
            if (fr == FR_OK && br == (UINT)n && memcmp(rb, line, (size_t)n) == 0) s_readback_ok = true;
        }
        s_fr = (int)fr;
    }
    DWORD fre = 0; FATFS *fsp = NULL;
    if (f_getfree("", &fre, &fsp) == FR_OK && fsp)
        s_free_kb = (uint32_t)((uint64_t)fre * fsp->csize * 512ull / 1024ull);
    s_done = true;
}

// ---- recorder_hw_t seam wired to carlk3 FatFs (this task is the ONLY FatFs caller) ----
static recorder_t g_rec;
static FIL        s_log_fil;          // reused per flush (open-append -> write -> close)
static FRESULT    s_log_fr = FR_OK;
static char       s_alert[24] = "";   // last recorder alert (M3: buzzer/LED; for now a CDC1 badge)

static bool  hw_mounted(void) { return s_mounted; }
static int   hw_max_log_index(void) {
    DIR dir; FILINFO fno; int mx = 0;
    if (f_findfirst(&dir, &fno, "", "log_*.txt") == FR_OK) {
        while (fno.fname[0]) {
            int v = atoi(fno.fname + 4);   // "log_" is 4 chars -> NNN
            if (v > mx) mx = v;
            if (f_findnext(&dir, &fno) != FR_OK) break;
        }
        f_closedir(&dir);
    }
    return mx;
}
static void *hw_open_append(const char *name) {
    s_log_fr = f_open(&s_log_fil, name, FA_OPEN_APPEND | FA_WRITE);
    return (s_log_fr == FR_OK) ? &s_log_fil : NULL;
}
static int hw_write(void *h, const void *buf, size_t n) {
    UINT bw = 0;
    s_log_fr = f_write((FIL *)h, buf, (UINT)n, &bw);
    return (s_log_fr == FR_OK) ? (int)bw : -1;
}
static void hw_close(void *h) { f_close((FIL *)h); }            // close flushes -> durable per session-flush
static bool hw_fault_full(void) { return s_log_fr == FR_DENIED; }  // FatFs "disk full"
static bool hw_rtc_read(rec_time_t *t) { (void)t; return false; }  // M2.4: PCF8563; uptime fallback for now
static void hw_alert(const char *text, int lo, int hi) {
    (void)lo; (void)hi;
    snprintf(s_alert, sizeof s_alert, "%s", text);
}
static const recorder_hw_t REC_HW = {
    hw_mounted, hw_max_log_index, hw_open_append, hw_write, hw_close, hw_fault_full, hw_rtc_read, hw_alert
};

// ---- async tail read (CDC1 {"q":"tail"} content proof; the read happens HERE, off the hot path) ----
static volatile bool   s_tail_req = false;
static char            s_tail_buf[192];
static volatile size_t s_tail_len = 0;

static void do_tail_read(void) {
    FIL f;
    s_tail_len = 0;
    if (f_open(&f, g_rec.filename, FA_READ) != FR_OK) return;
    FSIZE_t sz = f_size(&f);
    FSIZE_t off = (sz > sizeof s_tail_buf) ? sz - sizeof s_tail_buf : 0;
    UINT br = 0;
    if (f_lseek(&f, off) == FR_OK) f_read(&f, s_tail_buf, sizeof s_tail_buf, &br);
    f_close(&f);
    s_tail_len = br;
}

void sd_gate_task(void *ptr) {
    (void)ptr;
    run_selftest();
    if (s_mounted) {
        recorder_init(&g_rec, &REC_HW, PROBE_UART_BAUDRATE);
        recorder_start(&g_rec, (uint32_t)(time_us_64() / 1000ull));   // auto-start logging at boot
    }
    static uint8_t drain[256];
    for (;;) {
        uint32_t now = (uint32_t)(time_us_64() / 1000ull);
        size_t n = uart_bridge_rec_read(drain, sizeof drain);
        if (n) recorder_feed(&g_rec, drain, n, now);
        recorder_tick(&g_rec, now, uart_bridge_rx_last_ms(), uart_bridge_rx_ever());
        if (s_tail_req) { do_tail_read(); s_tail_req = false; }
        vTaskDelay(pdMS_TO_TICKS(20));
    }
}

void sd_gate_status_json(char *out, unsigned outsz) {
    snprintf(out, outsz,
             "{\"sd\":%d,\"done\":%d,\"write\":%d,\"readback\":%d,"
             "\"bytes\":%u,\"free_kb\":%u,\"fr\":%d}\n",
             (int)s_mounted, (int)s_done, (int)s_write_ok, (int)s_readback_ok,
             (unsigned)s_bytes, (unsigned)s_free_kb, (int)s_fr);
}

void sd_rec_status_json(char *out, unsigned outsz) {
    recorder_status_t st;
    recorder_get_status(&g_rec, &st);
    snprintf(out, outsz,
             "{\"logging\":%d,\"file\":\"%s\",\"rx\":%u,\"wedge\":%d,\"hits\":%u,"
             "\"err\":%d,\"tp_peak\":%u,\"rec_drop\":%u,\"alert\":\"%s\"}\n",
             (int)st.logging, st.log_file, (unsigned)st.rx_total, (int)st.wedge,
             (unsigned)st.hits, (int)st.last_err, (unsigned)st.tp_peak,
             (unsigned)uart_bridge_rec_drops(), s_alert);
}

void sd_rec_tail_request(void) { s_tail_req = true; }

void sd_rec_tail_json(char *out, unsigned outsz) {
    // emit the captured tail as a JSON string with non-printables escaped to '.'
    size_t len = s_tail_len;
    if (len > 160) len = 160;
    char esc[164];
    size_t o = 0;
    for (size_t i = 0; i < len && o + 1 < sizeof esc; i++) {
        char c = s_tail_buf[i];
        esc[o++] = (c >= 32 && c <= 126 && c != '"' && c != '\\') ? c : '.';
    }
    esc[o] = '\0';
    snprintf(out, outsz, "{\"tail_len\":%u,\"tail\":\"%s\"}\n", (unsigned)s_tail_len, esc);
}
