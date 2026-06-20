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
#include "rtc_pcf8563.h"   // M2.4: PCF8563 wall-clock for log stamps
#include "feedback.h"      // M3.0: non-blocking LED/buzzer service (serviced from this low-prio task)

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
static bool hw_rtc_read(rec_time_t *t) {                            // PCF8563 wall-clock; false => uptime fallback
    rtc_dt_t dt;
    if (!rtc_pcf8563_read(&dt)) return false;                      // absent / I2C error / VL set (untrusted)
    t->year = dt.year; t->mon = dt.mon; t->day = dt.day;
    t->hour = dt.hour; t->min = dt.min; t->sec = dt.sec;
    return true;
}
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

// Device-side recorder load generator (HIL hook for the SD-during-flash coexistence soak). When on,
// the SD task synthesizes recorder data every loop -> continuous f_write/f_sync to the card, with NO
// host UART traffic. A concurrent probe-rs flash soak then measures pure SD-vs-DAP contention, without
// the host driving both DAP and a CDC0 stream (the confound that made the host-injection version useless).
static volatile bool s_recgen;
static uint32_t s_recgen_seq;
void sd_recgen_set(bool on) { s_recgen = on; }

// ---- M3 published recorder snapshot (single-writer seqlock; see sd_gate.h) ----
// Writer = THIS task only (publish_snapshot, once per loop after recorder_tick, when g_rec is internally
// consistent). Readers = the dashboard render loop + the CDC1 {"q":"rec"} reply. seq is even when stable,
// odd while being written; a reader retries until it copies across a stable, unchanged seq. The fences
// are belt-and-braces (the real protection on single-core RP2040 is the seq-retry against preemption).
static volatile uint32_t s_snap_seq = 0;
static rec_snapshot_t    s_snap;            // the published copy
static rtc_dt_t          s_rtc_cache;       // wall-clock cached here (~1 Hz) so the dashboard never
static bool              s_rtc_valid = false;  //   takes the i2c1 bus for time — only the OLED show does
static uint32_t          s_rtc_poll_ms = 0;

static void publish_snapshot(void) {
    rec_snapshot_t s;
    memset(&s, 0, sizeof s);
    if (s_mounted) {   // recorder_init/start only ran if mounted; g_rec.hw is NULL otherwise
        recorder_status_t st;
        recorder_get_status(&g_rec, &st);                       // SAFE: this IS the owning task
        s.logging  = st.logging;  s.wedge   = st.wedge;
        s.rx_total = st.rx_total; s.hits    = st.hits;
        s.tp_peak  = st.tp_peak;  s.last_err = (int)st.last_err;
        snprintf(s.file, sizeof s.file, "%s", st.log_file);     // bounded copy, not a live pointer
        recorder_copy_tail(&g_rec, sizeof s.tail - 1, s.tail, sizeof s.tail);
    }
    s.sd_mounted = s_mounted;
    s.rec_drop   = uart_bridge_rec_drops();
    snprintf(s.alert, sizeof s.alert, "%s", s_alert);
    s.rtc_valid  = s_rtc_valid;  s.rtc = s_rtc_cache;

    s_snap_seq++;                              // -> odd (write in progress)
    __atomic_thread_fence(__ATOMIC_RELEASE);
    s_snap = s;
    __atomic_thread_fence(__ATOMIC_RELEASE);
    s_snap_seq++;                              // -> even (stable)
}

bool dash_get_rec_snapshot(rec_snapshot_t *out) {
    for (int tries = 0; tries < 16; tries++) {
        uint32_t s1 = s_snap_seq;
        if (s1 & 1u) continue;                 // writer mid-update
        __atomic_thread_fence(__ATOMIC_ACQUIRE);
        *out = s_snap;
        __atomic_thread_fence(__ATOMIC_ACQUIRE);
        if (s1 == s_snap_seq) return true;     // unchanged across the copy
    }
    return false;
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
        if (s_recgen) {   // synthetic continuous SD-write load (coexistence soak); ~107 B/iter @ ~50 Hz
            static char gen[160];
            int gl = snprintf(gen, sizeof gen,
                "RECGEN %08lu the-quick-brown-fox-jumps-over-the-lazy-dog-0123456789-ABCDEFGHIJKLMNOPQRSTUVWXYZ\n",
                (unsigned long)s_recgen_seq++);
            if (gl > 0) recorder_feed(&g_rec, (const uint8_t *)gen, (size_t)gl, now);
        }
        recorder_tick(&g_rec, now, uart_bridge_rx_last_ms(), uart_bridge_rx_ever());
        if (s_tail_req) { do_tail_read(); s_tail_req = false; }
        // M3: cache the wall-clock here (~1 Hz) so the dashboard renders time with ZERO i2c1 access —
        // only the OLED show takes the bus, keeping the i2c1 contenders at two (no extra RTC reader).
        if (now - s_rtc_poll_ms >= 1000u) {
            s_rtc_poll_ms = now;
            rtc_dt_t dt;
            if (rtc_pcf8563_read(&dt)) { s_rtc_cache = dt; s_rtc_valid = true; }
            else s_rtc_valid = false;
        }
        publish_snapshot();          // M3: hand the dashboard + CDC1 a consistent copy of recorder state
        feedback_service(now);       // M3.0: drive the non-blocking buzzer-off + LEDs off the hot path
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
    // M3: read the SD-task-published snapshot, NOT g_rec directly. The old version called
    // recorder_get_status(&g_rec) from the TUD task — handing out a live pointer into g_rec.filename
    // (rewritten by recorder_start mid-snprintf -> torn/unterminated read) and calling hw->sd_mounted()
    // off the owning task. The snapshot closes that race for both this reply and the dashboard.
    rec_snapshot_t s;
    if (!dash_get_rec_snapshot(&s)) { snprintf(out, outsz, "{\"err\":\"busy\"}\n"); return; }
    snprintf(out, outsz,
             "{\"logging\":%d,\"file\":\"%s\",\"rx\":%u,\"wedge\":%d,\"hits\":%u,"
             "\"err\":%d,\"tp_peak\":%u,\"rec_drop\":%u,\"alert\":\"%s\"}\n",
             (int)s.logging, s.file, (unsigned)s.rx_total, (int)s.wedge,
             (unsigned)s.hits, s.last_err, (unsigned)s.tp_peak,
             (unsigned)s.rec_drop, s.alert);
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
