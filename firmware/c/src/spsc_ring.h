/*
 * Hackagotchi — lock-free single-producer / single-consumer byte ring. SPDX-License-Identifier: MIT
 *
 * One producer (e.g. a UART RX IRQ) calls spsc_push; one consumer (the bridge task) calls spsc_pop.
 * The producer owns `head`, the consumer owns `tail`; both are free-running uint32 counters masked to
 * the buffer (CAP must be a power of two). A release fence orders the data write before the head
 * advance, and an acquire fence orders the head read before the data read — so the consumer never
 * reads a slot the producer hasn't finished writing. Correct on single-core (IRQ vs task) and on SMP.
 *
 * Header-only + hardware-independent on purpose: the firmware (uart_bridge.c) and the host unit test
 * (tests/m1/ring_test.c) compile the SAME code, so the ring's correctness is proven off-target.
 */
#ifndef HACKAGOTCHI_SPSC_RING_H
#define HACKAGOTCHI_SPSC_RING_H

#include <stdint.h>
#include <stddef.h>

typedef struct {
    uint8_t *buf;
    uint32_t cap_mask;        // CAP - 1 (CAP must be a power of two)
    volatile uint32_t head;   // producer-owned
    volatile uint32_t tail;   // consumer-owned
    volatile uint32_t drops;  // bytes dropped because the ring was full
    volatile uint32_t highwater;  // max fill ever observed (bytes)
} spsc_ring_t;

static inline void spsc_init(spsc_ring_t *r, uint8_t *buf, uint32_t cap_pow2) {
    r->buf = buf;
    r->cap_mask = cap_pow2 - 1u;
    r->head = r->tail = r->drops = r->highwater = 0u;
}

// Current occupancy. Safe to call from either side (read-only).
static inline uint32_t spsc_count(const spsc_ring_t *r) { return r->head - r->tail; }

// PRODUCER ONLY. Returns 1 on success, 0 if the ring was full (drop counted).
static inline int spsc_push(spsc_ring_t *r, uint8_t c) {
    uint32_t count = r->head - r->tail;
    if (count > r->cap_mask) {            // count == CAP -> full
        r->drops++;
        return 0;
    }
    r->buf[r->head & r->cap_mask] = c;
    __atomic_thread_fence(__ATOMIC_RELEASE);  // data visible before head advances
    r->head++;
    if (count + 1u > r->highwater) r->highwater = count + 1u;
    return 1;
}

// CONSUMER ONLY. Copies up to `max` bytes into dst; returns the count copied.
static inline size_t spsc_pop(spsc_ring_t *r, uint8_t *dst, size_t max) {
    size_t n = 0;
    while (n < max && r->tail != r->head) {
        __atomic_thread_fence(__ATOMIC_ACQUIRE);  // head read before data read
        dst[n++] = r->buf[r->tail & r->cap_mask];
        r->tail++;
    }
    return n;
}

#endif // HACKAGOTCHI_SPSC_RING_H
