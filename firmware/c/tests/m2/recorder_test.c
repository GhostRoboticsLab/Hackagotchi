/*
 * Host unit test for the M2 recorder core (src/recorder.c) — the SAME code the firmware compiles.
 * SPDX-License-Identifier: MIT
 *
 * Pass/fail via an explicit CHECK() macro (NOT assert — assert no-ops under -DNDEBUG and would fake a
 * PASS). The recorder_hw_t seam is wired to in-memory mocks, so the whole state machine runs on the
 * host with no Pico, no SD, no RTC. Time is injected (now_ms), so wedge/heartbeat/throughput boundaries
 * are exercised deterministically.
 *
 *   cc -I firmware/c/src -Wall -Wextra -O2 firmware/c/tests/m2/recorder_test.c \
 *      firmware/c/src/recorder.c -o /tmp/recorder_test && /tmp/recorder_test
 * Verify-the-verifier (harness MUST be able to FAIL):
 *   cc -I firmware/c/src -DREC_SELFTEST_BREAK -O2 .../recorder_test.c .../recorder.c -o /tmp/rt_bad && /tmp/rt_bad; echo $?
 */
#include <stdio.h>
#include <string.h>

#include "recorder.h"

static int g_pass = 0, g_fail = 0;
#define CHECK(cond, msg) do { \
    if (cond) { g_pass++; } else { g_fail++; printf("  FAIL: %s\n", (msg)); } \
} while (0)

/* ---- in-memory mock of recorder_hw_t ---- */
static bool       mk_mounted;
static int        mk_max_idx;
static char       mk_cap[16384];
static size_t     mk_cap_len;
static int        mk_fault;        // 0=ok, 1=full, 2=write-error  (applies to sd_write)
static bool       mk_rtc_ok;
static rec_time_t mk_rtc;
static char       mk_alert_last[64];
static int        mk_alert_count;

static bool  m_mounted(void) { return mk_mounted; }
static int   m_maxidx(void)  { return mk_max_idx; }
static void *m_open(const char *name) { (void)name; return mk_mounted ? (void *)0x1 : NULL; }
static int   m_write(void *h, const void *buf, size_t n) {
    (void)h;
    if (mk_fault) return -1;
    if (mk_cap_len + n < sizeof mk_cap) { memcpy(mk_cap + mk_cap_len, buf, n); mk_cap_len += n; }
    return (int)n;
}
static void m_close(void *h) { (void)h; }
static bool m_full(void) { return mk_fault == 1; }
static bool m_rtc(rec_time_t *t) { if (mk_rtc_ok) { *t = mk_rtc; return true; } return false; }
static void m_alert(const char *txt, int lo, int hi) {
    (void)lo; (void)hi;
    snprintf(mk_alert_last, sizeof mk_alert_last, "%s", txt);
    mk_alert_count++;
}
static const recorder_hw_t MOCK = { m_mounted, m_maxidx, m_open, m_write, m_close, m_full, m_rtc, m_alert };

static void reset_mock(void) {
    mk_mounted = true; mk_max_idx = 0; mk_cap_len = 0; mk_fault = 0;
    mk_rtc_ok = false; mk_alert_count = 0; mk_alert_last[0] = '\0';
}
static int cap_has(const char *s) { mk_cap[mk_cap_len] = '\0'; return strstr(mk_cap, s) != NULL; }
static void feed(recorder_t *r, const char *s, uint32_t now) {  // simulate target bytes arriving
    recorder_note_rx(r, now, strlen(s));
    recorder_feed(r, (const uint8_t *)s, strlen(s), now);
}

int main(void) {
    printf("== recorder core host test ==\n");
    recorder_t r;
    recorder_status_t st;

    /* A. file naming / session numbering */
    reset_mock(); recorder_init(&r, &MOCK, 115200);
    CHECK(recorder_start(&r, 1000), "start should succeed when mounted");
    recorder_get_status(&r, &st);
    CHECK(strcmp(st.log_file, "log_001.txt") == 0, "empty dir -> log_001.txt");
    reset_mock(); mk_max_idx = 7; recorder_init(&r, &MOCK, 115200); recorder_start(&r, 0);
    recorder_get_status(&r, &st);
    CHECK(strcmp(st.log_file, "log_008.txt") == 0, "max idx 7 -> log_008.txt");
    reset_mock(); mk_mounted = false; recorder_init(&r, &MOCK, 115200);
    CHECK(!recorder_start(&r, 0), "start returns false when SD not mounted");

    /* B. session header written + flushed immediately (rtc untrusted -> uptime stamp) */
    reset_mock(); recorder_init(&r, &MOCK, 115200);
    recorder_start(&r, 5000);
    CHECK(cap_has("=== BLACK BOX log_001.txt | start +5s | baud 115200 ==="), "header content+stamp");
    CHECK(mk_cap_len > 0, "header flushed immediately (before any feed)");

    /* C. flush triggers: <64 buffered, idle-flush after 500ms, 64 threshold flushes */
    reset_mock(); recorder_init(&r, &MOCK, 115200); recorder_start(&r, 0);
    size_t after_hdr = mk_cap_len;
    feed(&r, "0123456789", 10);                 // 10 bytes buffered
    CHECK(mk_cap_len == after_hdr, "small feed not yet flushed");
    recorder_tick(&r, 600);                      // >500ms idle -> flush
    CHECK(mk_cap_len > after_hdr, "idle flush after 500ms");
    reset_mock(); recorder_init(&r, &MOCK, 115200); recorder_start(&r, 0); after_hdr = mk_cap_len;
    char chunk[70]; memset(chunk, 'x', sizeof chunk); chunk[69] = '\0';
    feed(&r, chunk, 0);                          // 69 bytes >= 64 threshold -> flush
    CHECK(mk_cap_len > after_hdr, "threshold(64) flush");

    /* D. SD fault -> VISIBLE stop (classify + alert), and stays stopped */
    reset_mock(); recorder_init(&r, &MOCK, 115200); recorder_start(&r, 0);
    mk_fault = 1;                                // disk full
    int alerts_before = mk_alert_count;
    feed(&r, chunk, 0);                          // 69 bytes -> flush -> fault
    recorder_get_status(&r, &st);
    CHECK(!st.logging, "logging stops on write fault (visible, not silent)");
    CHECK(st.last_err == REC_ERR_SD_FULL, "fault classified SD_FULL");
    CHECK(mk_alert_count > alerts_before, "fault raised an alert");
    reset_mock(); recorder_init(&r, &MOCK, 115200); recorder_start(&r, 0);
    mk_fault = 2; feed(&r, chunk, 0); recorder_get_status(&r, &st);
    CHECK(st.last_err == REC_ERR_WRITE, "generic fault classified WRITE_ERR");

    /* E. wedge state machine (strict >8000ms, fire once, recovered) */
    reset_mock(); recorder_init(&r, &MOCK, 115200); recorder_start(&r, 0);
    recorder_tick(&r, 20000); recorder_get_status(&r, &st);
    CHECK(!st.wedge, "no wedge before any rx (ever_active false)");
    recorder_note_rx(&r, 20000, 5);
    recorder_tick(&r, 28000); recorder_get_status(&r, &st);
    CHECK(!st.wedge, "silence of exactly 8000ms does not wedge (strict >)");
    int a0 = mk_alert_count;
    recorder_tick(&r, 28001); recorder_get_status(&r, &st);
    CHECK(st.wedge, "silence of 8001ms wedges");
    CHECK(strncmp(mk_alert_last, "WEDGE", 5) == 0, "wedge fired a WEDGE alert");
    int a1 = mk_alert_count;
    recorder_tick(&r, 40000);                    // still silent
    CHECK(mk_alert_count == a1, "wedge fires only ONCE while still silent");
    (void)a0;
    recorder_note_rx(&r, 41000, 3); recorder_get_status(&r, &st);
    CHECK(!st.wedge, "rx resume clears the wedge");
    CHECK(strcmp(mk_alert_last, "RECOVERED") == 0, "recovered alert on resume");

    /* F. trigger-term scan: per line, first-match-break, flood guard */
    reset_mock(); recorder_init(&r, &MOCK, 115200); recorder_start(&r, 0);
    feed(&r, "all good here\n", 0); recorder_get_status(&r, &st);
    CHECK(st.hits == 0, "benign line -> no hit");
    feed(&r, "FATAL: boom\n", 0); recorder_get_status(&r, &st);
    CHECK(st.hits == 1, "FATAL line -> 1 hit");
    CHECK(strcmp(mk_alert_last, "HIT FATAL") == 0, "alert names the term");
    feed(&r, "ERROR and FATAL same line\n", 0); recorder_get_status(&r, &st);
    CHECK(st.hits == 2, "two terms one line -> exactly one more hit (first-match-break)");
    {   // 300-byte unterminated flood must not crash or over-run
        char flood[301]; memset(flood, 'A', 300); flood[300] = '\0';
        feed(&r, flood, 0);
        recorder_get_status(&r, &st);
        CHECK(st.hits == 2, "flood (no terminator, no term) -> no new hit, no crash");
    }

    /* G. freeze ring: last 80 target bytes surface in the WEDGE line */
    reset_mock(); recorder_init(&r, &MOCK, 115200); recorder_start(&r, 0);
    {   // feed 120 bytes; the last 80 should be 'B...B' (we feed 40 'A' then 80 'B')
        char as[41]; memset(as, 'A', 40); as[40] = '\0';
        char bs[81]; memset(bs, 'B', 80); bs[80] = '\0';
        feed(&r, as, 0); feed(&r, bs, 0);
        recorder_tick(&r, 9000);                 // >8000ms silence -> wedge writes the freeze line
        recorder_get_status(&r, &st);
        CHECK(st.wedge, "wedge fired for freeze test");
        char want[88]; memset(want, 'B', 80); want[80] = '\0';
        CHECK(cap_has(want) && cap_has("WEDGE"), "WEDGE line carries the last 80 freeze bytes");
    }

    /* H. heartbeat at 60s */
    reset_mock(); recorder_init(&r, &MOCK, 115200); recorder_start(&r, 0);
    recorder_note_rx(&r, 0, 50);
    recorder_tick(&r, 30000); CHECK(!cap_has("--- BB"), "no heartbeat before 60s");
    recorder_tick(&r, 60001); CHECK(cap_has("--- BB") && cap_has("rx=50"), "heartbeat at >60s with rx count");

    /* I. throughput sampler (per >=1000ms) */
    reset_mock(); recorder_init(&r, &MOCK, 115200); recorder_start(&r, 0);
    recorder_note_rx(&r, 0, 100);
    recorder_tick(&r, 1000); recorder_get_status(&r, &st);
    CHECK(st.tp_peak == 100, "throughput peak sampled");

    /* J. RTC wall-clock stamp when trusted */
    reset_mock(); mk_rtc_ok = true;
    mk_rtc = (rec_time_t){ .year = 2026, .mon = 6, .day = 20, .hour = 12, .min = 0, .sec = 5 };
    recorder_init(&r, &MOCK, 115200); recorder_start(&r, 999999);
    CHECK(cap_has("start 2026-06-20 12:00:05"), "RTC-trusted stamp is wall-clock");

#ifdef REC_SELFTEST_BREAK
    CHECK(0, "deliberate self-test failure (verify-the-verifier)");
#endif

    printf("checks: %d passed, %d failed\n", g_pass, g_fail);
    if (g_fail) { printf("FAIL\n"); return 1; }
    printf("PASS: recorder core (naming, header, flush, visible-stop, wedge, triggers, freeze, "
           "heartbeat, throughput, RTC)\n");
    return 0;
}
