/*
 * Hackagotchi — M3 OLED dashboard task (multi-screen renderer). SPDX-License-Identifier: MIT
 * See hackagotchi_dashboard.h for the architecture (lowest-prio render, snapshot-only reads, no button).
 *
 * M3.2 ports the full feasible MicroPython screen family (firmware/micropython/main.py): the cat mascot
 * (draw_cat, ported pixel-for-pixel), Home/bridge stats, live-UART sniffer, throughput sparkline,
 * watchdog/flight-recorder, recorder status, and a clock. Screens the static pin map forbids (scope/PWM/
 * logic-analyzer/I2C-scanner) are intentionally absent; the button menus (macro/baud/SD-explorer) are M4.
 *
 * Screen fns draw graphics DIRECTLY to the OLED (the cat/sparkline aren't expressible as text) and ALSO
 * fill a text attestation model. The SHOW-SUCCESS counter (g_dash_shows, ticked only when ssd1306_show()
 * ran) + an operator glance keep the render honest where the text model can't (a dark panel can't pass).
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

#define DASH_I2C_INST   i2c1    // OLED on I2C1 GP6/GP7 (sole device on the bus — no mutex)
#define DASH_REFRESH_MS 250u    // ~4 Hz (proven-safe coexistence rate from Gate 1 / M2 soaks)
#define DASH_CYCLE_MS  6000u    // auto-advance screens every 6 s (no button)
#define DASH_MAX_LINES    6     // attestation text lines
#define DASH_COLW        22     // 21 cols @ 6px pitch + NUL
#define TP_RING          60     // throughput sparkline history (bytes/sec samples)

TaskHandle_t dashboard_taskhandle;

volatile uint32_t g_dash_counter   = 0;
volatile uint32_t g_dash_stall_us  = 0;
volatile uint32_t g_dash_shows     = 0;
volatile int32_t  g_dash_screen    = 0;
volatile uint32_t g_dash_stack_free = 0;

// --- navigation intents (posted by CDC1/TUD, consumed here) ---
static volatile int32_t s_nav_delta = 0;
static volatile int32_t s_nav_abs   = -1;
void dash_nav_step(int delta) { __atomic_fetch_add(&s_nav_delta, delta, __ATOMIC_RELAXED); }
void dash_nav_to(int idx)     { __atomic_store_n(&s_nav_abs, idx, __ATOMIC_RELAXED); }

// M4: hex-sniffer view mode (SNIFFER screen toggles ASCII<->hex). Dashboard-local; flipped over CDC1
// {"q":"hex"}. A plain bool is fine — single writer (the CDC1 handler), read by the render loop.
static volatile bool s_hex_mode = false;
bool dash_hex_toggle(void) { s_hex_mode = !s_hex_mode; return s_hex_mode; }
bool dash_hex_mode(void)   { return s_hex_mode; }

// --- derived dashboard state (updated once per frame, read by the screen fns) ---
typedef struct {
    rec_snapshot_t snap;
    bool     snap_ok;
    unsigned heap;
    uint32_t up_s;
    uint32_t now_ms;
    int      idx, count;
    uint32_t frame;       // animation tick
    bool     active;      // target UART traffic seen recently (drives the cat)
    uint32_t idle_s;      // seconds since the last RX (for the watchdog screen)
    uint32_t tp_now;      // current bytes/sec
} dash_ctx_t;

typedef struct {
    char title[DASH_COLW];
    char line[DASH_MAX_LINES][DASH_COLW];
    int  nlines;
} dash_screen_t;

// throughput history (file-static; persists across frames)
static uint16_t s_tp_ring[TP_RING];
static int      s_tp_count = 0;
static uint32_t s_tp_last_ms = 0, s_tp_last_rx = 0;
// activity tracking
static uint32_t s_last_rx = 0, s_last_rx_ms = 0;

// ---------------- small text/format + attestation helpers ----------------

static void aline(dash_screen_t *s, const char *fmt, ...) {  // record an attestation line (no draw)
    if (s->nlines >= DASH_MAX_LINES) return;
    va_list ap; va_start(ap, fmt);
    vsnprintf(s->line[s->nlines], DASH_COLW, fmt, ap);
    va_end(ap);
    s->nlines++;
}

static void hdr(ssd1306_t *d, dash_screen_t *s, const char *title) {  // title @y0 + divider @y9
    snprintf(s->title, DASH_COLW, "%s", title);
    ssd1306_draw_string(d, 2, 0, 1, s->title);
    ssd1306_draw_line(d, 0, 9, 127, 9);
}

// draw a left-column text row (x=4, y=12+r*10) AND record it for attestation (drawn == attested)
static void row(ssd1306_t *d, dash_screen_t *s, int r, const char *fmt, ...) {
    char buf[DASH_COLW];
    va_list ap; va_start(ap, fmt);
    vsnprintf(buf, sizeof buf, fmt, ap);
    va_end(ap);
    ssd1306_draw_string(d, 4, 12 + r * 10, 1, buf);
    if (s->nlines < DASH_MAX_LINES) { snprintf(s->line[s->nlines], DASH_COLW, "%s", buf); s->nlines++; }
}

static void fmt_bytes(char *out, size_t outsz, uint32_t b) {
    if (b < 1000u)         snprintf(out, outsz, "%u", (unsigned)b);
    else if (b < 1000000u) snprintf(out, outsz, "%u.%uK", (unsigned)(b/1000u), (unsigned)((b/100u)%10u));
    else                   snprintf(out, outsz, "%u.%uM", (unsigned)(b/1000000u), (unsigned)((b/100000u)%10u));
}

// auto-scaled line graph of data[0..n) into (x,y,w,h) — ported from main.py draw_sparkline
static void sparkline(ssd1306_t *d, const uint16_t *data, int n, int x, int y, int w, int h) {
    if (n <= 0 || w < 2 || h < 2) return;
    uint16_t lo = data[0], hi = data[0];
    for (int i = 1; i < n; i++) { if (data[i] < lo) lo = data[i]; if (data[i] > hi) hi = data[i]; }
    int rng = (hi - lo) ? (hi - lo) : 1;
    ssd1306_draw_line(d, x, y + h - 1, x + w - 1, y + h - 1);   // baseline
    int px_prev = 0, py_prev = 0;
    for (int i = 0; i < n; i++) {
        int px = x + (i * (w - 1)) / (n > 1 ? n - 1 : 1);
        int py = y + h - 1 - (int)((long)(h - 1) * (data[i] - lo) / rng);
        if (i) ssd1306_draw_line(d, px_prev, py_prev, px, py);
        px_prev = px; py_prev = py;
    }
}

// ---------------- the cat mascot (ported pixel-for-pixel from main.py draw_cat) ----------------
// ssd1306 maps: rect->draw_empty_square, fill_rect(.,1)->draw_square, line->draw_line, pixel->draw_pixel,
// pixel(.,0)->clear_pixel, text->draw_string. The mascot lives at the right of the Home screen.
static void draw_cat(ssd1306_t *d, bool active, uint32_t tick, const char *last_type) {
    static bool     last_active = false;
    static uint32_t yawn_end = 0;
    uint32_t now = (uint32_t)(time_us_64() / 1000ull);
    if (active && !last_active) yawn_end = now + 1200u;
    last_active = active;
    bool yawning = active && (now < yawn_end);

    int cx = 94, cy = 28;
    if (!active) cy += (int)((tick / 8u) % 2u);              // sleeping chest-breath

    ssd1306_draw_empty_square(d, cx, cy, 28, 20);            // head
    ssd1306_draw_line(d, cx, cy, cx + 5, cy - 8);           // ears
    ssd1306_draw_line(d, cx + 5, cy - 8, cx + 10, cy);
    ssd1306_draw_line(d, cx + 18, cy, cx + 23, cy - 8);
    ssd1306_draw_line(d, cx + 23, cy - 8, cx + 27, cy);
    ssd1306_draw_pixel(d, cx + 14, cy + 12);                 // nose
    ssd1306_draw_line(d, cx - 4, cy + 10, cx + 2, cy + 11);  // whiskers
    ssd1306_draw_line(d, cx - 4, cy + 13, cx + 2, cy + 13);
    ssd1306_draw_line(d, cx + 26, cy + 11, cx + 32, cy + 10);
    ssd1306_draw_line(d, cx + 26, cy + 13, cx + 32, cy + 13);

    uint32_t tail = (tick / 4u) % 3u;                        // wagging tail
    int tx = cx + 27, ty = cy + 15;
    if (tail == 0)      { ssd1306_draw_line(d, tx, ty, tx + 4, ty - 2); ssd1306_draw_line(d, tx + 4, ty - 2, tx + 6, ty - 6); }
    else if (tail == 1) { ssd1306_draw_line(d, tx, ty, tx + 5, ty);     ssd1306_draw_line(d, tx + 5, ty, tx + 7, ty - 3); }
    else                { ssd1306_draw_line(d, tx, ty, tx + 4, ty + 2); ssd1306_draw_line(d, tx + 4, ty + 2, tx + 6, ty); }

    if (yawning) {
        ssd1306_draw_line(d, cx + 4, cy + 8, cx + 10, cy + 8);
        ssd1306_draw_line(d, cx + 18, cy + 8, cx + 24, cy + 8);
        ssd1306_draw_square(d, cx + 11, cy + 13, 6, 5);
        int bx = cx - 18, by = cy - 13;
        ssd1306_draw_empty_square(d, bx, by, 26, 11);
        ssd1306_draw_line(d, bx + 16, by + 10, cx + 2, cy + 2);
        ssd1306_draw_string(d, bx + 2, by + 2, 1, "yawn");
    } else if (active) {
        ssd1306_draw_square(d, cx + 4, cy + 5, 6, 6);        // eyes wide
        ssd1306_draw_square(d, cx + 18, cy + 5, 6, 6);
        ssd1306_clear_pixel(d, cx + 5, cy + 6);              // pupils
        ssd1306_clear_pixel(d, cx + 19, cy + 6);
        if ((tick / 3u) % 2u == 0) ssd1306_draw_square(d, cx + 12, cy + 14, 5, 3);   // mouth
        else ssd1306_draw_line(d, cx + 13, cy + 15, cx + 15, cy + 15);
        int bx = cx - 13, by = cy - 13;                      // TX/RX bubble
        ssd1306_draw_empty_square(d, bx, by, 21, 11);
        ssd1306_draw_line(d, bx + 14, by + 10, cx + 2, cy + 2);
        ssd1306_draw_string(d, bx + 3, by + 2, 1, last_type);
        ssd1306_draw_pixel(d, 45 + (int)((tick * 7u) % 40u), 26);   // flying data particles
        ssd1306_draw_pixel(d, 45 + (int)(((tick + 3u) * 7u) % 40u), 42);
    } else {
        bool blink = (tick % 40u) >= 37u;
        if (blink) {
            ssd1306_draw_line(d, cx + 4, cy + 8, cx + 10, cy + 8);
            ssd1306_draw_line(d, cx + 18, cy + 8, cx + 24, cy + 8);
            ssd1306_draw_line(d, cx + 13, cy + 14, cx + 15, cy + 14);
        } else {
            for (int off = 0; off <= 14; off += 14) {       // sleeping curved eyes
                ssd1306_draw_pixel(d, cx + 4 + off, cy + 8);
                for (int k = 5; k <= 9; k++) ssd1306_draw_pixel(d, cx + k + off, cy + 9);
                ssd1306_draw_pixel(d, cx + 10 + off, cy + 8);
            }
            ssd1306_draw_line(d, cx + 13, cy + 14, cx + 15, cy + 14);
            uint32_t z = (tick / 6u) % 3u;                  // floating Z's
            ssd1306_draw_string(d, cx - 12 + (int)z * 4, cy - 8 - (int)z * 3, 1, z == 0 ? "z" : "Z");
        }
    }
}

// ---------------- screens ----------------

// 0 — HOME / mascot: brand + bridge/recorder stats (left) + the cat (right).
static void screen_home(const dash_ctx_t *c, ssd1306_t *d, dash_screen_t *s) {
    hdr(d, s, "HACKAGOTCHI");
    char rx[12]; fmt_bytes(rx, sizeof rx, c->snap.rx_total);
    ssd1306_draw_string(d, 4, 12, 1, "rx"); ssd1306_draw_string(d, 20, 12, 1, rx);
    char up[12];
    if (c->up_s >= 60) snprintf(up, sizeof up, "%lum%02lus", (unsigned long)(c->up_s/60), (unsigned long)(c->up_s%60));
    else               snprintf(up, sizeof up, "%lus", (unsigned long)c->up_s);
    ssd1306_draw_string(d, 4, 22, 1, "up"); ssd1306_draw_string(d, 20, 22, 1, up);
    ssd1306_draw_string(d, 4, 32, 1, c->snap.logging ? "REC" : "off");
    if (c->snap.alert[0]) { ssd1306_draw_string(d, 28, 32, 1, "!"); }
    draw_cat(d, c->active, c->frame, "RX");
    // attestation summary
    aline(s, "rx %s", rx); aline(s, "up %s", up);
    aline(s, "%s%s", c->snap.logging ? "REC" : "off", c->snap.alert[0] ? " !" : "");
    aline(s, "cat:%s", c->active ? "active" : "idle");
}

// 1 — SNIFFER: live UART tail (the recorder freeze tail), wrapped to 21-col lines.
static void screen_sniffer(const dash_ctx_t *c, ssd1306_t *d, dash_screen_t *s) {
    if (s_hex_mode) {   // M4: hex view — 5 bytes/row (uppercase) + ASCII gutter, last min(30,n) raw bytes
        hdr(d, s, "HEX SNIFFER");
        const uint8_t *b = c->snap.raw;
        int n = c->snap.rawn;
        if (n == 0) { row(d, s, 0, "(no traffic yet)"); return; }
        for (int r = 0; r * 5 < n && r < 6; r++) {
            char ln[DASH_COLW]; int o = 0, base = r * 5;
            for (int i = 0; i < 5 && base + i < n; i++)
                o += snprintf(ln + o, sizeof ln - (size_t)o, "%02X ", b[base + i]);
            while (o < 15 && o < (int)sizeof ln - 1) ln[o++] = ' ';   // pad to the ASCII gutter
            for (int i = 0; i < 5 && base + i < n && o < (int)sizeof ln - 1; i++) {
                uint8_t ch = b[base + i];
                ln[o++] = (ch >= 32 && ch <= 126) ? (char)ch : '.';
            }
            ln[o] = '\0';
            ssd1306_draw_string(d, 2, 11 + r * 9, 1, ln);
            if (s->nlines < DASH_MAX_LINES) { snprintf(s->line[s->nlines], DASH_COLW, "%s", ln); s->nlines++; }
        }
        return;
    }
    hdr(d, s, "UART RX LOG");
    const char *t = c->snap.tail;
    int len = (int)strlen(t);
    // show the LAST 4 wrapped rows (21 cols each) of the tail
    int rows = (len + 20) / 21; if (rows < 1) rows = 1;
    int first = rows > 4 ? rows - 4 : 0;
    int shown = 0;
    for (int r = first; r < rows && shown < 4; r++, shown++) {
        char buf[DASH_COLW];
        int off = r * 21, n = len - off; if (n > 21) n = 21; if (n < 0) n = 0;
        memcpy(buf, t + off, (size_t)n); buf[n] = '\0';
        ssd1306_draw_string(d, 2, 12 + shown * 10, 1, buf);
        if (s->nlines < DASH_MAX_LINES) { snprintf(s->line[s->nlines], DASH_COLW, "%s", buf); s->nlines++; }
    }
    if (len == 0) row(d, s, 0, "(no traffic yet)");
}

// 2 — RECORDER: black-box status (entirely from the snapshot).
static void screen_recorder(const dash_ctx_t *c, ssd1306_t *d, dash_screen_t *s) {
    const rec_snapshot_t *r = &c->snap;
    hdr(d, s, "RECORDER");
    if (!r->sd_mounted) { row(d, s, 0, "SD not mounted"); return; }
    row(d, s, 0, "%s %s", r->logging ? "REC" : "off", r->file);
    char rx[12]; fmt_bytes(rx, sizeof rx, r->rx_total);
    row(d, s, 1, "rx %s  drop %u", rx, (unsigned)r->rec_drop);
    row(d, s, 2, "peak %u B/s", (unsigned)r->tp_peak);
    row(d, s, 3, "wedge:%s hits:%u", r->wedge ? "YES" : "no", (unsigned)r->hits);
    if (r->alert[0]) row(d, s, 4, "! %s", r->alert);
}

// 3 — THROUGHPUT: now/peak/total + a live bytes/sec sparkline.
static void screen_throughput(const dash_ctx_t *c, ssd1306_t *d, dash_screen_t *s) {
    hdr(d, s, "THROUGHPUT");
    char now[12], peak[12]; fmt_bytes(now, sizeof now, c->tp_now); fmt_bytes(peak, sizeof peak, c->snap.tp_peak);
    char l0[DASH_COLW]; snprintf(l0, sizeof l0, "now %s/s", now);
    ssd1306_draw_string(d, 4, 12, 1, l0);
    char pk[DASH_COLW]; snprintf(pk, sizeof pk, "pk %s/s", peak);
    ssd1306_draw_string(d, 70, 12, 1, pk);
    ssd1306_draw_empty_square(d, 2, 24, 124, 38);
    if (s_tp_count > 0) sparkline(d, s_tp_ring, s_tp_count, 5, 26, 118, 34);
    aline(s, "now %s/s", now); aline(s, "pk %s/s", peak);
}

// 4 — WATCHDOG: flight-recorder status + the target's last words.
static void screen_watchdog(const dash_ctx_t *c, ssd1306_t *d, dash_screen_t *s) {
    const rec_snapshot_t *r = &c->snap;
    hdr(d, s, "WATCHDOG");
    if (r->wedge) {
        // blink the WEDGE line (draw only on the lit phase); attest stays stable so the HIL sees it.
        if ((c->frame / 3u) % 2u == 0) ssd1306_draw_string(d, 4, 12, 1, "** WEDGE **");
        aline(s, "** WEDGE **");
    } else if (r->rx_total > 0) {
        row(d, s, 0, "Target LIVE idle %lus", (unsigned long)c->idle_s);
    } else {
        row(d, s, 0, "Target: waiting...");
    }
    row(d, s, 1, "hits:%u", (unsigned)r->hits);
    if (r->alert[0]) row(d, s, 2, "%.21s", r->alert);
    ssd1306_draw_line(d, 0, 40, 127, 40);
    ssd1306_draw_string(d, 4, 42, 1, "freeze-frame:");
    char ff[DASH_COLW]; int len = (int)strlen(r->tail);
    int off = len > 21 ? len - 21 : 0;
    snprintf(ff, sizeof ff, "%s", len ? r->tail + off : "(nothing yet)");
    ssd1306_draw_string(d, 4, 52, 1, ff);
    if (s->nlines < DASH_MAX_LINES) { snprintf(s->line[s->nlines], DASH_COLW, "ff:%s", ff); s->nlines++; }
}

// 5 — UPTIME: big uptime-since-boot + free heap (no RTC; the probe has no wall-clock).
static void screen_uptime(const dash_ctx_t *c, ssd1306_t *d, dash_screen_t *s) {
    hdr(d, s, "UPTIME");
    uint32_t up = c->up_s;
    char hms[12]; snprintf(hms, sizeof hms, "%02u:%02u:%02u",
                           (unsigned)(up / 3600u), (unsigned)((up / 60u) % 60u), (unsigned)(up % 60u));
    ssd1306_draw_string(d, 16, 22, 2, hms);          // scale 2 = big
    char sub[22];
    if (up >= 86400u) snprintf(sub, sizeof sub, "%ud up  heap %uK", (unsigned)(up / 86400u), (unsigned)(c->heap / 1024u));
    else              snprintf(sub, sizeof sub, "heap %uK free", (unsigned)(c->heap / 1024u));
    ssd1306_draw_string(d, 8, 50, 1, sub);
    aline(s, "%s", hms); aline(s, "%s", sub);
}

static void (*const SCREENS[])(const dash_ctx_t *, ssd1306_t *, dash_screen_t *) = {
    screen_home, screen_sniffer, screen_recorder, screen_throughput, screen_watchdog, screen_uptime,
};
#define N_SCREENS ((int)(sizeof(SCREENS) / sizeof(SCREENS[0])))
int dash_screen_count(void) { return N_SCREENS; }

// --- published attestation (seqlock; the text the framework recorded this frame) ---
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

// --- pick the active screen: absolute > relative > auto-cycle; clamp/wrap on the reader side ---
static int next_index(int idx, uint32_t now, uint32_t *last_cycle) {
    int32_t a = __atomic_exchange_n(&s_nav_abs, -1, __ATOMIC_RELAXED);
    int32_t dl = __atomic_exchange_n(&s_nav_delta, 0, __ATOMIC_RELAXED);
    bool manual = false;
    if (a >= 0)       { idx = a; manual = true; }
    else if (dl != 0) { idx += (int)dl; manual = true; }
    else if ((uint32_t)(now - *last_cycle) >= DASH_CYCLE_MS) { idx++; *last_cycle = now; }
    if (manual) *last_cycle = now;
    idx = ((idx % N_SCREENS) + N_SCREENS) % N_SCREENS;
    return idx;
}

void dashboard_task(void *ptr) {
    (void)ptr;
    i2c1_bus_init();

    static ssd1306_t disp;
    disp.external_vcc = false;   // MUST set before init (charge-pump on, else dark panel)
    bool ok = false;
    ok = ssd1306_init(&disp, 128, 64, DASH_I2C_ADDR, DASH_I2C_INST);   // sole bus owner — no lock

    static dash_ctx_t ctx;          // static: keep the snapshot copy off the 4 KB task stack
    static dash_screen_t scr;
    static rec_snapshot_t last_good;
    int idx = 0;
    uint32_t last_cycle = (uint32_t)(time_us_64() / 1000ull);
    TickType_t wake = xTaskGetTickCount();

    for (;;) {
        uint32_t now = (uint32_t)(time_us_64() / 1000ull);
        g_dash_counter++;

#if ADVERSARIAL_STALL_MS > 0
        uint64_t _t0 = time_us_64();
        busy_wait_us((uint32_t)ADVERSARIAL_STALL_MS * 1000u);
        g_dash_stall_us = (uint32_t)(time_us_64() - _t0);
#endif

        // gather context (snapshot-only reads)
        if (dash_get_rec_snapshot(&ctx.snap)) { last_good = ctx.snap; ctx.snap_ok = true; }
        else { ctx.snap = last_good; ctx.snap_ok = false; }
        ctx.heap   = (unsigned)xPortGetFreeHeapSize();
        ctx.up_s   = (uint32_t)(time_us_64() / 1000000ull);
        ctx.now_ms = now;
        ctx.count  = N_SCREENS;
        ctx.frame  = g_dash_counter;

        // activity (drives the cat) + idle seconds
        if (ctx.snap.rx_total > s_last_rx) { s_last_rx = ctx.snap.rx_total; s_last_rx_ms = now; }
        ctx.active = (now - s_last_rx_ms) < 2500u && s_last_rx > 0;
        ctx.idle_s = s_last_rx_ms ? (now - s_last_rx_ms) / 1000u : 0;

        // throughput sample (1 Hz) -> sparkline ring + now bytes/sec
        if (now - s_tp_last_ms >= 1000u) {
            uint32_t d = (s_tp_last_rx && ctx.snap.rx_total >= s_tp_last_rx) ? ctx.snap.rx_total - s_tp_last_rx : 0;
            ctx.tp_now = d;
            if (s_tp_count < TP_RING) s_tp_ring[s_tp_count++] = (uint16_t)(d > 65535u ? 65535u : d);
            else { memmove(s_tp_ring, s_tp_ring + 1, (TP_RING - 1) * sizeof s_tp_ring[0]); s_tp_ring[TP_RING - 1] = (uint16_t)(d > 65535u ? 65535u : d); }
            s_tp_last_rx = ctx.snap.rx_total; s_tp_last_ms = now;
        } else if (s_tp_count) {
            ctx.tp_now = s_tp_ring[s_tp_count - 1];
        }

        idx = next_index(idx, now, &last_cycle);
        ctx.idx = idx;
        g_dash_screen = idx;

        memset(&scr, 0, sizeof scr);
        if (ok) {
            ssd1306_clear(&disp);
            SCREENS[idx](&ctx, &disp, &scr);
            // Tick the show-success counter ONLY when the panel ACKed the burst (ssd1306_show >= 0) — so a
            // NAKing/absent OLED (or a 1 MHz bus a board's pullups can't sustain) gives shows < loops, the
            // genuine dark-panel / FM+ integrity detector (per the M3 closeout audit).
            int w = ssd1306_show(&disp);
            if (w >= 0) g_dash_shows++;
        } else {
            SCREENS[idx](&ctx, &disp, &scr);   // still publish attestation even if the panel is absent
        }
        publish_attest(&scr, idx);

        g_dash_stack_free = (uint32_t)uxTaskGetStackHighWaterMark(NULL);
        xTaskDelayUntil(&wake, pdMS_TO_TICKS(DASH_REFRESH_MS));
    }
}
