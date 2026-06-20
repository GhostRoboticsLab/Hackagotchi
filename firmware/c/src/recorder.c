/*
 * Hackagotchi — M2 black-box recorder core. SPDX-License-Identifier: MIT  (see recorder.h)
 * Ported from firmware/micropython/main.py. No hardware calls — only the recorder_hw_t seam.
 */

#include "recorder.h"

#include <stdio.h>
#include <string.h>

static const char *const WATCH_TERMS[] = { "ERROR", "FATAL", "Traceback", "panic", "BUSY-TIMEOUT" };
#define WATCH_TERM_COUNT (sizeof WATCH_TERMS / sizeof WATCH_TERMS[0])

// ---- timestamps: RTC wall-clock if trusted, else uptime-relative (main.py log_stamp) ----
static void stamp(recorder_t *r, uint32_t now_ms, char *buf, size_t bufsz) {
    rec_time_t t;
    if (r->hw->rtc_read && r->hw->rtc_read(&t))
        snprintf(buf, bufsz, "%04u-%02u-%02u %02u:%02u:%02u",
                 t.year, t.mon, t.day, t.hour, t.min, t.sec);
    else
        snprintf(buf, bufsz, "+%us", (unsigned)(now_ms / 1000u));
}

// ---- the load-bearing flush: buffered write, VISIBLE-STOP on fault (never silently stop) ----
static void flush(recorder_t *r, uint32_t now_ms) {
    if (!r->logging || r->logbuf_len == 0) return;
    if (!r->hw->sd_mounted()) return;

    bool ok = false;
    void *h = r->hw->sd_open_append(r->filename);
    if (h) {
        int wr = r->hw->sd_write(h, r->logbuf, r->logbuf_len);
        r->hw->sd_close(h);
        ok = (wr >= 0 && (size_t)wr == r->logbuf_len);
    }
    if (ok) {
        r->logbuf_len = 0;
        r->last_write_ms = now_ms;
        return;
    }
    // Write fault -> stop VISIBLY: classify, badge, alert. (main.py flush_log_buffer fault path.)
    r->logging = false;
    r->last_err = (r->hw->sd_last_fault_full && r->hw->sd_last_fault_full()) ? REC_ERR_SD_FULL
                                                                             : REC_ERR_WRITE;
    if (r->hw->alert)
        r->hw->alert(r->last_err == REC_ERR_SD_FULL ? "SD FULL" : "WRITE ERR", 400, 400);
}

// Append to the log buffer; flush when full / at threshold; `force` flushes a marker out immediately.
static void emit(recorder_t *r, const void *data, size_t n, uint32_t now_ms, bool force) {
    if (!r->logging) return;
    const uint8_t *p = (const uint8_t *)data;
    while (n > 0) {
        if (r->logbuf_len >= REC_LOGBUF_CAP) { flush(r, now_ms); if (!r->logging) return; }
        size_t space = REC_LOGBUF_CAP - r->logbuf_len;
        size_t chunk = (n < space) ? n : space;
        memcpy(r->logbuf + r->logbuf_len, p, chunk);
        r->logbuf_len += chunk;
        p += chunk;
        n -= chunk;
        if (r->logbuf_len >= REC_FLUSH_THRESHOLD) { flush(r, now_ms); if (!r->logging) return; }
    }
    if (force && r->logbuf_len > 0) flush(r, now_ms);
}

// Read the freeze ring's last `k` target bytes in order, newlines->spaces, non-printable->'.'.
static void freeze_read_last(const recorder_t *r, size_t k, char *out, size_t outsz) {
    size_t have = (r->freeze_total < REC_FREEZE_CAP) ? r->freeze_total : REC_FREEZE_CAP;
    size_t take = (k < have) ? k : have;
    size_t start = (size_t)r->freeze_total - take;
    size_t o = 0;
    for (size_t i = 0; i < take && o + 1 < outsz; i++) {
        uint8_t c = r->freeze[(start + i) % REC_FREEZE_CAP];
        if (c == '\n' || c == '\r') c = ' ';
        else if (c < 32 || c > 126) c = '.';
        out[o++] = (char)c;
    }
    out[o] = '\0';
}

// Substring-match the assembled line against the watch terms (first match wins). Called once per line.
static void scan_line(recorder_t *r) {
    if (r->watch_line_len == 0) return;
    r->watch_line[r->watch_line_len] = '\0';
    for (size_t k = 0; k < WATCH_TERM_COUNT; k++) {
        if (strstr(r->watch_line, WATCH_TERMS[k])) {
            r->watch_hits++;
            snprintf(r->watch_last, sizeof r->watch_last, "%s: %s", WATCH_TERMS[k], r->watch_line);
            if (r->hw->alert) {
                char a[24];
                snprintf(a, sizeof a, "HIT %s", WATCH_TERMS[k]);
                r->hw->alert(a, 0, 0);
            }
            break;
        }
    }
}

void recorder_init(recorder_t *r, const recorder_hw_t *hw, uint32_t baud) {
    memset(r, 0, sizeof *r);
    r->hw = hw;
    r->baud = baud;
}

static void pick_filename(recorder_t *r) {
    if (!r->hw->sd_mounted()) {
        snprintf(r->filename, REC_FILENAME_CAP, "uart_log.txt");
        return;
    }
    int mx = r->hw->sd_max_log_index ? r->hw->sd_max_log_index() : 0;
    snprintf(r->filename, REC_FILENAME_CAP, "log_%03d.txt", mx + 1);
}

bool recorder_start(recorder_t *r, uint32_t now_ms) {
    if (!r->hw->sd_mounted()) return false;
    r->last_err = REC_ERR_NONE;
    pick_filename(r);
    r->logging = true;
    r->logbuf_len = 0;

    char st[24];
    stamp(r, now_ms, st, sizeof st);
    char hdr[96];
    int n = snprintf(hdr, sizeof hdr, "\n=== BLACK BOX %s | start %s | baud %u ===\n",
                     r->filename, st, (unsigned)r->baud);
    emit(r, hdr, (size_t)n, now_ms, true);   // header flushed immediately

    r->last_write_ms = now_ms;
    r->last_hb_ms = now_ms;
    r->last_tp_ms = now_ms;
    return r->logging;   // false if the header flush already faulted
}

void recorder_stop(recorder_t *r) { r->logging = false; }

void recorder_feed(recorder_t *r, const uint8_t *data, size_t n, uint32_t now_ms) {
    r->rx_total += (uint32_t)n;
    r->tp_accum += (uint32_t)n;
    if (r->wedge_active) {             // drained resumed bytes -> RECOVERED edge (silent -> active)
        r->wedge_active = false;
        if (r->hw->alert) r->hw->alert("RECOVERED", 1600, 2400);
    }

    emit(r, data, n, now_ms, false);   // log buffering (flush at threshold); no-op if not logging

    for (size_t i = 0; i < n; i++) {   // freeze ring + trigger scan run regardless of logging
        uint8_t c = data[i];
        r->freeze[r->freeze_total % REC_FREEZE_CAP] = c;
        r->freeze_total++;
        if (c == '\n' || c == '\r') {
            scan_line(r);
            r->watch_line_len = 0;
        } else if (c >= 32 && c <= 126) {
            if (r->watch_line_len >= REC_WATCH_LINE_CAP - 1) {
                // overflow: keep the last half so a term near the end still matches (main.py trims to 200)
                size_t keep = REC_WATCH_LINE_CAP / 2;
                memmove(r->watch_line, r->watch_line + (r->watch_line_len - keep), keep);
                r->watch_line_len = keep;
            }
            r->watch_line[r->watch_line_len++] = (char)c;
        }
    }
}

void recorder_tick(recorder_t *r, uint32_t now_ms, uint32_t rx_last_ms, bool rx_ever) {
    // wedge: strictly > silence window, only after the target was ever active, fire ONCE per silence.
    // rx_last_ms/rx_ever are PRODUCER-sourced (passed in), so consumer backlog can't fake a wedge.
    if (!r->wedge_active && rx_ever && (now_ms - rx_last_ms) > REC_WEDGE_SILENCE_MS) {
        r->wedge_active = true;
        stamp(r, now_ms, r->wedge_since, sizeof r->wedge_since);
        if (r->logging) {
            char ff[88];
            freeze_read_last(r, 80, ff, sizeof ff);
            char line[160];
            int n = snprintf(line, sizeof line, "\n--- WEDGE %s last=[%s] ---\n", r->wedge_since, ff);
            emit(r, line, (size_t)n, now_ms, true);
        }
        if (r->hw->alert) {
            size_t sl = strlen(r->wedge_since);
            const char *tail = r->wedge_since + (sl > 8 ? sl - 8 : 0);
            char a[24];
            snprintf(a, sizeof a, "WEDGE %s", tail);
            r->hw->alert(a, 500, 900);
        }
    }

    if (r->logging && (now_ms - r->last_hb_ms) > REC_HEARTBEAT_MS) {
        char st[24];
        stamp(r, now_ms, st, sizeof st);
        char hb[64];
        int n = snprintf(hb, sizeof hb, "\n--- BB %s rx=%u ---\n", st, (unsigned)r->rx_total);
        emit(r, hb, (size_t)n, now_ms, true);
        r->last_hb_ms = now_ms;
    }

    if ((now_ms - r->last_tp_ms) >= REC_THROUGHPUT_MS) {
        if (r->tp_accum > r->tp_peak) r->tp_peak = r->tp_accum;
        r->tp_accum = 0;
        r->last_tp_ms = now_ms;
    }

    if (r->logging && r->logbuf_len > 0 && (now_ms - r->last_write_ms) > REC_FLUSH_IDLE_MS)
        flush(r, now_ms);
}

void recorder_get_status(const recorder_t *r, recorder_status_t *out) {
    out->logging    = r->logging;
    out->log_file   = r->filename;
    out->sd_mounted = r->hw->sd_mounted();
    out->wedge      = r->wedge_active;
    out->hits       = r->watch_hits;
    out->last_err   = r->last_err;
    out->tp_peak    = r->tp_peak;
    out->rx_total   = r->rx_total;
}
