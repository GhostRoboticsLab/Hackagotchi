/*
 * Hackagotchi — M3 OLED dashboard task (multi-screen renderer). SPDX-License-Identifier: MIT
 * See hackagotchi_dashboard.h for the architecture (lowest-prio render, snapshot-only reads, no button).
 *
 * Screen functions produce a TEXT MODEL (title + lines); the framework both (a) draws that model to the
 * OLED and (b) publishes the identical text for CDC1 self-attestation — so the attestation is faithful by
 * construction. A SHOW-SUCCESS counter (g_dash_shows) ticks only when ssd1306_show() actually ran (lock
 * acquired), distinct from the loop counter, so a dark/skipped panel cannot pass as alive.
 */

#include <stdio.h>
#include <stdarg.h>
#include <string.h>
#include <pico/stdlib.h>
#include <hardware/i2c.h>

#include "FreeRTOS.h"
#include "task.h"

#include "ssd1306.h"
#include "i2c1_bus.h"
#include "sd_gate.h"      // rec_snapshot_t + dash_get_rec_snapshot()
#include "hackagotchi_dashboard.h"

#ifndef DASH_I2C_ADDR
#define DASH_I2C_ADDR 0x3Cu
#endif
#ifndef ADVERSARIAL_STALL_MS
#define ADVERSARIAL_STALL_MS 0
#endif

// XIAO + Seeed expansion: OLED on I2C1, SDA=GP6, SCL=GP7 (shares the bus with the RTC @0x51).
#define DASH_I2C_INST   i2c1
#define DASH_REFRESH_MS 250u    // ~4 Hz redraw (clock ticks visibly; proven-safe rate from Gate 1)
#define DASH_CYCLE_MS  5000u    // auto-advance screens every 5 s (no button)
#define DASH_MAX_LINES    5     // content rows below the header (y=12,22,32,42,52 in the 8x5 font)
#define DASH_COLW        22     // 21 cols @ 6px pitch + NUL

TaskHandle_t dashboard_taskhandle;

volatile uint32_t g_dash_counter   = 0;
volatile uint32_t g_dash_stall_us  = 0;
volatile uint32_t g_dash_shows     = 0;
volatile int32_t  g_dash_screen    = 0;
volatile uint32_t g_dash_stack_free = 0;

// --- navigation intents (posted by CDC1/TUD, consumed by this task) ---
static volatile int32_t s_nav_delta = 0;    // accumulated next/prev steps
static volatile int32_t s_nav_abs   = -1;   // absolute screen target, -1 = none
void dash_nav_step(int delta) { __atomic_fetch_add(&s_nav_delta, delta, __ATOMIC_RELAXED); }
void dash_nav_to(int idx)     { __atomic_store_n(&s_nav_abs, idx, __ATOMIC_RELAXED); }

// --- render context handed to each screen fn ---
typedef struct {
    rec_snapshot_t snap;   // recorder snapshot (last-good if a read ever fails)
    bool     snap_ok;
    unsigned heap;
    uint32_t up_s;
    int      idx;
    int      count;
} dash_ctx_t;

// --- one screen's text model ---
typedef struct {
    char title[DASH_COLW];
    char line[DASH_MAX_LINES][DASH_COLW];
    int  nlines;
} dash_screen_t;

static void sline(dash_screen_t *s, const char *fmt, ...) {
    if (s->nlines >= DASH_MAX_LINES) return;
    va_list ap; va_start(ap, fmt);
    vsnprintf(s->line[s->nlines], DASH_COLW, fmt, ap);
    va_end(ap);
    s->nlines++;
}

// Human byte count -> "123", "12.3K", "1.2M" (max 7 chars).
static void fmt_bytes(char *out, size_t outsz, uint32_t b) {
    if (b < 1000u)            snprintf(out, outsz, "%u", (unsigned)b);
    else if (b < 1000000u)    snprintf(out, outsz, "%u.%uK", (unsigned)(b/1000u), (unsigned)((b/100u)%10u));
    else                      snprintf(out, outsz, "%u.%uM", (unsigned)(b/1000000u), (unsigned)((b/100000u)%10u));
}

// ---------------- screens ----------------

// Screen 0 — PROBE / home: identity, uptime, heap, clock. (DAP-activity is M3.3-optional.)
static void screen_probe(const dash_ctx_t *c, dash_screen_t *s) {
    snprintf(s->title, DASH_COLW, "HACKAGOTCHI");
    sline(s, "probe   up %lus", (unsigned long)c->up_s);
    sline(s, "heap    %u B", c->heap);
    if (c->snap_ok && c->snap.rtc_valid)
        sline(s, "clock   %02u:%02u:%02u", c->snap.rtc.hour, c->snap.rtc.min, c->snap.rtc.sec);
    else
        sline(s, "clock   --:--:--");
    sline(s, "screen  %d/%d", c->idx + 1, c->count);
}

// Screen 1 — RECORDER / black-box status (read-only, entirely from the published snapshot).
static void screen_recorder(const dash_ctx_t *c, dash_screen_t *s) {
    const rec_snapshot_t *r = &c->snap;
    snprintf(s->title, DASH_COLW, "RECORDER");
    if (!c->snap_ok)          { sline(s, "snapshot busy"); return; }
    if (!r->sd_mounted)       { sline(s, "SD not mounted"); return; }
    sline(s, "%s %s", r->logging ? "REC" : "off", r->file);
    char rx[12]; fmt_bytes(rx, sizeof rx, r->rx_total);
    sline(s, "rx %s  drop %u", rx, (unsigned)r->rec_drop);
    sline(s, "peak %u B/s", (unsigned)r->tp_peak);
    sline(s, "wedge:%s hits:%u", r->wedge ? "YES" : "no", (unsigned)r->hits);
    if (r->alert[0]) sline(s, "! %s", r->alert);
    else if (r->rtc_valid) sline(s, "clk %02u:%02u:%02u", r->rtc.hour, r->rtc.min, r->rtc.sec);
    else sline(s, "err:%d", r->last_err);
}

static void (*const SCREENS[])(const dash_ctx_t *, dash_screen_t *) = {
    screen_probe,
    screen_recorder,
};
#define N_SCREENS ((int)(sizeof(SCREENS) / sizeof(SCREENS[0])))
int dash_screen_count(void) { return N_SCREENS; }

// --- published attestation (seqlock; the EXACT text drawn this frame) ---
static volatile uint32_t s_attest_seq = 0;
static char s_attest_text[DASH_COLW * (DASH_MAX_LINES + 1)];
static int  s_attest_idx = 0;

static void publish_attest(const dash_screen_t *s, int idx) {
    static char buf[sizeof s_attest_text];
    int o = snprintf(buf, sizeof buf, "%s", s->title);
    for (int i = 0; i < s->nlines && o < (int)sizeof buf - 1; i++)
        o += snprintf(buf + o, sizeof buf - (size_t)o, "\n%s", s->line[i]);
    s_attest_seq++;
    __atomic_thread_fence(__ATOMIC_RELEASE);
    memcpy(s_attest_text, buf, sizeof s_attest_text);
    s_attest_idx = idx;
    __atomic_thread_fence(__ATOMIC_RELEASE);
    s_attest_seq++;
}

int dash_get_attest(char *out, size_t outsz) {
    int idx = 0;
    for (int t = 0; t < 16; t++) {
        uint32_t s1 = s_attest_seq;
        if (s1 & 1u) continue;
        __atomic_thread_fence(__ATOMIC_ACQUIRE);
        snprintf(out, outsz, "%s", s_attest_text);
        idx = s_attest_idx;
        __atomic_thread_fence(__ATOMIC_ACQUIRE);
        if (s1 == s_attest_seq) break;
    }
    return idx;
}

// --- pick the active screen index: absolute > relative > auto-cycle; clamp/wrap on the reader side ---
static int next_index(int idx, uint32_t now, uint32_t *last_cycle) {
    int32_t a = __atomic_exchange_n(&s_nav_abs, -1, __ATOMIC_RELAXED);
    int32_t d = __atomic_exchange_n(&s_nav_delta, 0, __ATOMIC_RELAXED);
    bool manual = false;
    if (a >= 0)      { idx = a; manual = true; }
    else if (d != 0) { idx += (int)d; manual = true; }
    else if ((uint32_t)(now - *last_cycle) >= DASH_CYCLE_MS) { idx++; *last_cycle = now; }
    if (manual) *last_cycle = now;            // any manual nav resets the auto-cycle clock
    idx = ((idx % N_SCREENS) + N_SCREENS) % N_SCREENS;  // wrap/clamp (N_SCREENS > 0)
    return idx;
}

void dashboard_task(void *ptr) {
    (void)ptr;
    i2c1_bus_init();   // idempotent; main() already did it before the scheduler

    static ssd1306_t disp;
    disp.external_vcc = false;   // MUST set before init: charge-pump ON, else the panel stays dark
    bool ok = false;
    if (i2c1_bus_lock(200)) { ok = ssd1306_init(&disp, 128, 64, DASH_I2C_ADDR, DASH_I2C_INST); i2c1_bus_unlock(); }

    static dash_ctx_t ctx;          // static: keep the ~150 B snapshot copy off the 4 KB task stack
    static dash_screen_t scr;
    static rec_snapshot_t last_good; // reused when a snapshot read momentarily fails
    int idx = 0;
    uint32_t last_cycle = xTaskGetTickCount();
    TickType_t wake = xTaskGetTickCount();

    for (;;) {
        uint32_t now = (uint32_t)(time_us_64() / 1000ull);
        g_dash_counter++;

#if ADVERSARIAL_STALL_MS > 0
        uint64_t _t0 = time_us_64();
        busy_wait_us((uint32_t)ADVERSARIAL_STALL_MS * 1000u);
        g_dash_stall_us = (uint32_t)(time_us_64() - _t0);
#endif

        // gather context (snapshot-only reads — never touch g_rec/RTC directly)
        if (dash_get_rec_snapshot(&ctx.snap)) { last_good = ctx.snap; ctx.snap_ok = true; }
        else { ctx.snap = last_good; ctx.snap_ok = false; }
        ctx.heap  = (unsigned)xPortGetFreeHeapSize();
        ctx.up_s  = (uint32_t)(time_us_64() / 1000000ull);
        ctx.count = N_SCREENS;

        idx = next_index(idx, now, &last_cycle);
        ctx.idx = idx;
        g_dash_screen = idx;

        // build the text model
        memset(&scr, 0, sizeof scr);
        SCREENS[idx](&ctx, &scr);

        // render the SAME text model to the OLED
        if (ok) {
            ssd1306_clear(&disp);                                   // framebuffer-only — no bus lock
            ssd1306_draw_string(&disp, 0, 0, 1, scr.title);
            ssd1306_draw_line(&disp, 0, 9, 127, 9);
            for (int i = 0; i < scr.nlines; i++)
                ssd1306_draw_string(&disp, 0, 12 + i * 10, 1, scr.line[i]);
            // the ONE i2c1 hold: the ~23 ms blocking show. Count it ONLY on success (frame truly flushed).
            if (i2c1_bus_lock(200)) { ssd1306_show(&disp); i2c1_bus_unlock(); g_dash_shows++; }
        }

        // publish the identical text for camera-free self-attestation
        publish_attest(&scr, idx);

        g_dash_stack_free = (uint32_t)uxTaskGetStackHighWaterMark(NULL);
        xTaskDelayUntil(&wake, pdMS_TO_TICKS(DASH_REFRESH_MS));
    }
}
