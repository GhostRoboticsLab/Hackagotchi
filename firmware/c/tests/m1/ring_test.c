/*
 * Host unit test for the SPSC ring (src/spsc_ring.h) — the SAME header the firmware compiles.
 * SPDX-License-Identifier: MIT
 *
 * Build + run on the host (no hardware):
 *   cc -I firmware/c/src -Wall -Wextra -O2 firmware/c/tests/m1/ring_test.c -o /tmp/ring_test && /tmp/ring_test
 */
#include <assert.h>
#include <stdio.h>
#include <string.h>

#include "spsc_ring.h"

#define CAP 8u   /* small power of two so full + wraparound are easy to hit */

static uint8_t backing[CAP];
static spsc_ring_t r;

static void reset(void) { spsc_init(&r, backing, CAP); }

int main(void) {
    int checks = 0;
    uint8_t out[64];

    /* 1. empty */
    reset();
    assert(spsc_count(&r) == 0);
    assert(spsc_pop(&r, out, sizeof out) == 0);
    checks++;

    /* 2. push/pop preserves FIFO order */
    reset();
    for (uint8_t i = 0; i < 5; i++) assert(spsc_push(&r, (uint8_t)(0x10 + i)) == 1);
    assert(spsc_count(&r) == 5);
    size_t n = spsc_pop(&r, out, sizeof out);
    assert(n == 5);
    for (uint8_t i = 0; i < 5; i++) assert(out[i] == (uint8_t)(0x10 + i));
    assert(spsc_count(&r) == 0);
    checks++;

    /* 3. fill exactly to capacity, then the next push drops (and is counted) */
    reset();
    for (uint8_t i = 0; i < CAP; i++) assert(spsc_push(&r, i) == 1);
    assert(spsc_count(&r) == CAP);
    assert(r.highwater == CAP);
    assert(spsc_push(&r, 0xEE) == 0);     /* full -> drop */
    assert(spsc_push(&r, 0xEF) == 0);
    assert(r.drops == 2);
    assert(spsc_count(&r) == CAP);        /* unchanged by the dropped pushes */
    checks++;

    /* 4. wraparound: drain some, push more, verify order across the buffer boundary */
    reset();
    for (uint8_t i = 0; i < CAP; i++) spsc_push(&r, i);          /* head wrapped region filled */
    assert(spsc_pop(&r, out, 6) == 6);                            /* tail advances past 0..5 */
    for (uint8_t i = 0; i < 6; i++) assert(spsc_push(&r, (uint8_t)(0x80 + i)) == 1);  /* head wraps */
    /* remaining originals 6,7 then the 6 new ones, in order */
    n = spsc_pop(&r, out, sizeof out);
    assert(n == 8);
    assert(out[0] == 6 && out[1] == 7);
    for (uint8_t i = 0; i < 6; i++) assert(out[2 + i] == (uint8_t)(0x80 + i));
    checks++;

    /* 5. partial pop returns exactly max, leaves the rest */
    reset();
    for (uint8_t i = 0; i < 7; i++) spsc_push(&r, i);
    assert(spsc_pop(&r, out, 3) == 3);
    assert(out[0] == 0 && out[1] == 1 && out[2] == 2);
    assert(spsc_count(&r) == 4);
    checks++;

    /* 6. highwater tracks the peak, not the current depth */
    reset();
    for (uint8_t i = 0; i < CAP; i++) spsc_push(&r, i);
    spsc_pop(&r, out, CAP);
    assert(spsc_count(&r) == 0);
    assert(r.highwater == CAP);
    checks++;

    printf("PASS: spsc_ring %d/%d checks (FIFO order, full+drops, wraparound, partial, highwater)\n",
           checks, checks);
    return 0;
}
