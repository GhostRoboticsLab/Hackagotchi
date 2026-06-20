/*
 * Hackagotchi — M2 black-box recorder core. SPDX-License-Identifier: MIT
 *
 * Pure logic ported from the MicroPython recorder (firmware/micropython/main.py): session-numbered log
 * files, buffered flush, the VISIBLE-STOP-on-fault invariant (a black box must NEVER silently stop),
 * the wedge detector + freeze frame, trigger-term scan, heartbeat. It calls NO hardware directly —
 * only the injected recorder_hw_t seam — so the whole state machine compiles + unit-tests on the host
 * (tests/m2/recorder_test.c) with in-memory mocks. On-device the seam is wired to carlk3 FatFs + RTC.
 *
 * Concurrency boundary (the device wiring): the recorder_t is owned SOLELY by the low-priority recorder
 * task — no other task touches it (no races). The high-priority producer (cdc_task) shares only (a) the
 * SPSC staging ring it tees bytes into, and (b) two atomic liveness values (last-rx-ms, ever-active)
 * that the recorder task reads and passes into recorder_tick(). Stamping liveness in the PRODUCER (not
 * the consumer) means a backlogged recorder task cannot manufacture a false wedge. recorder_feed() does
 * the off-hot-path scan/freeze/buffer + counters; recorder_tick() is the periodic driver.
 */
#ifndef HACKAGOTCHI_RECORDER_H
#define HACKAGOTCHI_RECORDER_H

#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>

#define REC_FLUSH_THRESHOLD   64u     // flush when the log buffer reaches this many bytes
#define REC_FLUSH_IDLE_MS    500u     // ...or this long since the last write, if non-empty
#define REC_WEDGE_SILENCE_MS 8000u    // target silence (after being active) that declares a wedge (>)
#define REC_HEARTBEAT_MS    60000u    // periodic heartbeat marker so a wedge is time-bounded
#define REC_THROUGHPUT_MS    1000u    // throughput sampling period
#define REC_FREEZE_CAP         96u    // rolling freeze-frame ring (last N target bytes)
#define REC_LOGBUF_CAP        128u    // log staging buffer (> threshold + headroom)
#define REC_WATCH_LINE_CAP    200u    // assembled-line buffer for the trigger scan
#define REC_FILENAME_CAP       16u    // "log_NNN.txt" / "uart_log.txt"

typedef enum { REC_ERR_NONE = 0, REC_ERR_SD_FULL, REC_ERR_WRITE } rec_err_t;

typedef struct { uint16_t year; uint8_t mon, day, hour, min, sec; } rec_time_t;

// Injected hardware seam. Device impl -> carlk3 FatFs + PCF8563 + buzzer/LED; host test -> mocks.
typedef struct {
    bool  (*sd_mounted)(void);
    int   (*sd_max_log_index)(void);                  // max NNN among log_NNN.txt (0 if none/unmounted)
    void *(*sd_open_append)(const char *name);        // open-for-append; NULL on failure
    int   (*sd_write)(void *h, const void *buf, size_t n);  // bytes written; <0 on fault
    void  (*sd_close)(void *h);
    bool  (*sd_last_fault_full)(void);                // was the last sd_write/open fault "disk full"?
    bool  (*rtc_read)(rec_time_t *t);                 // false => time untrusted -> uptime fallback
    void  (*alert)(const char *text, int lo, int hi); // beep/LED/badge (records calls in the host mock)
} recorder_hw_t;

typedef struct {
    const recorder_hw_t *hw;
    uint32_t baud;

    bool     logging;
    char     filename[REC_FILENAME_CAP];
    rec_err_t last_err;

    uint8_t  logbuf[REC_LOGBUF_CAP];
    size_t   logbuf_len;
    uint32_t last_write_ms;
    uint32_t last_hb_ms;
    uint32_t last_tp_ms;

    // wedge detector (liveness — last_rx_ms / ever_active — is PRODUCER-sourced and passed into _tick)
    bool     wedge_active;
    char     wedge_since[24];
    uint8_t  freeze[REC_FREEZE_CAP];   // ring
    uint32_t freeze_total;             // total bytes ever fed (freeze holds the last min(CAP,total))

    // trigger-term line scan
    char     watch_line[REC_WATCH_LINE_CAP];
    size_t   watch_line_len;
    uint32_t watch_hits;
    char     watch_last[64];

    // counters / throughput
    uint32_t rx_total;
    uint32_t tp_accum;
    uint32_t tp_peak;
} recorder_t;

// Read-only snapshot for the CDC1 status layer (kept JSON-free so the core has no formatting deps).
typedef struct {
    bool     logging;
    const char *log_file;
    bool     sd_mounted;
    bool     wedge;
    uint32_t hits;
    rec_err_t last_err;
    uint32_t tp_peak;
    uint32_t rx_total;
} recorder_status_t;

void recorder_init(recorder_t *r, const recorder_hw_t *hw, uint32_t baud);

// Begin a session: pick the next log file, write the header, flush immediately. Returns false (and
// does not start) if the SD is not mounted — the caller surfaces that (e.g. buzz).
bool recorder_start(recorder_t *r, uint32_t now_ms);
void recorder_stop(recorder_t *r);

// CONSUMER (low-prio recorder task): process drained target bytes — log buffering + freeze ring +
// per-byte trigger scan + rx/throughput counters + clear a wedge on resume. Owns recorder_t.
void recorder_feed(recorder_t *r, const uint8_t *data, size_t n, uint32_t now_ms);

// Periodic driver: wedge detection (using the PRODUCER-sourced liveness passed in), heartbeat marker,
// throughput sample, idle flush. `rx_last_ms`/`rx_ever` come from the high-prio producer (atomic),
// NOT from the recorder task's own drain, so consumer backlog can't fake a wedge.
void recorder_tick(recorder_t *r, uint32_t now_ms, uint32_t rx_last_ms, bool rx_ever);

void recorder_get_status(const recorder_t *r, recorder_status_t *out);

// Copy the freeze ring's last `k` bytes in order (newlines->spaces, non-printable->'.') into out[]
// (NUL-terminated). For the M3 dashboard's live-UART tail view — but called ONLY by the recorder-owning
// task (the snapshot publisher), never cross-task against a live recorder_t (the ring is mutated by
// recorder_feed; reading it off-task would race the producer wrapping it).
void recorder_copy_tail(const recorder_t *r, size_t k, char *out, size_t outsz);

#endif // HACKAGOTCHI_RECORDER_H
