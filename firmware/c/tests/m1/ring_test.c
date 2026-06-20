/*
 * Host unit test for the SPSC ring (src/spsc_ring.h) — the SAME header the firmware compiles.
 * SPDX-License-Identifier: MIT
 *
 * Pass/fail is decided by an explicit CHECK() macro, NOT assert() — assert() no-ops under -DNDEBUG and
 * would let main() fall through to a fake "PASS". The PASS line is printed only if g_fail == 0, and the
 * count reflects checks actually evaluated.
 *
 * Build + run (functional + concurrent fence stress):
 *   cc -I firmware/c/src -Wall -Wextra -O2 -pthread firmware/c/tests/m1/ring_test.c -o /tmp/ring_test
 *   /tmp/ring_test
 * Verify-the-verifier (the harness MUST be able to emit FAIL / exit nonzero):
 *   cc -I firmware/c/src -DRING_SELFTEST_BREAK -O2 -pthread .../ring_test.c -o /tmp/ring_bad && /tmp/ring_bad; echo $?
 *
 * The concurrent test runs a real producer thread + consumer thread on this (arm64, weakly-ordered)
 * host, so the release/acquire fences in spsc_ring.h are actually exercised — a missing/wrong fence can
 * surface as a torn/reordered byte in the sequence check. (A full tsan run would want C11 _Atomic
 * indices instead of volatile+fences; that conversion is a noted future hardening — see M1_RESULTS.)
 */
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "spsc_ring.h"

static int g_pass = 0, g_fail = 0;
#define CHECK(cond, msg) do { \
    if (cond) { g_pass++; } else { g_fail++; printf("  FAIL: %s\n", (msg)); } \
} while (0)

#define CAP 8u  /* small power of two so full + wraparound are easy to hit */

static void functional(void) {
    uint8_t backing[CAP];
    spsc_ring_t r;
    uint8_t out[64];

    spsc_init(&r, backing, CAP);
    CHECK(spsc_count(&r) == 0, "fresh ring not empty");
    CHECK(spsc_pop(&r, out, sizeof out) == 0, "pop on empty returned bytes");

    spsc_init(&r, backing, CAP);
    for (uint8_t i = 0; i < 5; i++) CHECK(spsc_push(&r, (uint8_t)(0x10 + i)) == 1, "push failed");
    CHECK(spsc_count(&r) == 5, "count != 5 after 5 pushes");
    size_t n = spsc_pop(&r, out, sizeof out);
    CHECK(n == 5, "pop count != 5");
    int order_ok = 1;
    for (uint8_t i = 0; i < 5; i++) if (out[i] != (uint8_t)(0x10 + i)) order_ok = 0;
    CHECK(order_ok, "FIFO order violated");

    spsc_init(&r, backing, CAP);
    for (uint8_t i = 0; i < CAP; i++) CHECK(spsc_push(&r, i) == 1, "fill push failed");
    CHECK(spsc_count(&r) == CAP, "count != CAP when full");
    CHECK(r.highwater == CAP, "highwater != CAP when full");
    CHECK(spsc_push(&r, 0xEE) == 0, "push on full did not drop");
    CHECK(spsc_push(&r, 0xEF) == 0, "push on full did not drop (2)");
    CHECK(r.drops == 2, "drops != 2");
    CHECK(spsc_count(&r) == CAP, "dropped pushes changed count");

    spsc_init(&r, backing, CAP);
    for (uint8_t i = 0; i < CAP; i++) spsc_push(&r, i);
    CHECK(spsc_pop(&r, out, 6) == 6, "partial drain != 6");
    for (uint8_t i = 0; i < 6; i++) CHECK(spsc_push(&r, (uint8_t)(0x80 + i)) == 1, "wrap push failed");
    n = spsc_pop(&r, out, sizeof out);
    CHECK(n == 8, "wraparound pop count != 8");
    int wrap_ok = (out[0] == 6 && out[1] == 7);
    for (uint8_t i = 0; i < 6; i++) if (out[2 + i] != (uint8_t)(0x80 + i)) wrap_ok = 0;
    CHECK(wrap_ok, "wraparound order violated");

#ifdef RING_SELFTEST_BREAK
    CHECK(0, "deliberate self-test failure (verify-the-verifier)");
#endif
}

/* ---- concurrent producer/consumer fence stress ---- */
#define STRESS_CAP   1024u
#define STRESS_OPS   4000000u  /* bytes streamed end-to-end */

static uint8_t   stress_buf[STRESS_CAP];
static spsc_ring_t stress_ring;
static volatile int seq_ok = 1;       /* set false by consumer on any out-of-sequence byte */
static volatile uint32_t consumed = 0;

static void *producer(void *arg) {
    (void)arg;
    for (uint32_t i = 0; i < STRESS_OPS; i++)
        while (!spsc_push(&stress_ring, (uint8_t)(i & 0xFFu))) { /* ring full -> retry, lose nothing */ }
    return NULL;
}

static void *consumer(void *arg) {
    (void)arg;
    uint8_t chunk[256];
    uint32_t expect = 0;
    while (consumed < STRESS_OPS) {
        size_t got = spsc_pop(&stress_ring, chunk, sizeof chunk);
        for (size_t k = 0; k < got; k++) {
            if (chunk[k] != (uint8_t)(expect & 0xFFu)) seq_ok = 0;  /* gap/dup/reorder/torn read */
            expect++;
        }
        consumed += got;
    }
    return NULL;
}

static void concurrent(void) {
    spsc_init(&stress_ring, stress_buf, STRESS_CAP);
    seq_ok = 1;
    consumed = 0;
    pthread_t tp, tc;
    pthread_create(&tp, NULL, producer, NULL);
    pthread_create(&tc, NULL, consumer, NULL);
    pthread_join(tp, NULL);
    pthread_join(tc, NULL);
    CHECK(consumed == STRESS_OPS, "concurrent: consumer did not receive every byte");
    CHECK(seq_ok, "concurrent: out-of-sequence byte (fence/ordering bug)");
}

int main(void) {
    printf("== spsc_ring host test ==\n");
    functional();
    concurrent();
    printf("checks: %d passed, %d failed\n", g_pass, g_fail);
    if (g_fail) {
        printf("FAIL\n");
        return 1;
    }
    printf("PASS: functional (FIFO/full/drops/wrap/partial/highwater) + %u-op concurrent fence stress\n",
           STRESS_OPS);
    return 0;
}
