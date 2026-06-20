/*
 * Hackagotchi — M1: interrupt-driven UART RX capture for the CDC0 bridge. SPDX-License-Identifier: MIT
 *
 * The stock debugprobe bridge POLLS the UART: it drains the 32-byte HW FIFO into a 32-byte buffer only
 * once per poll interval, so at speed the FIFO overflows between polls and target bytes are silently
 * lost (its own comment: "Reading from a firehose"). For a black-box UART recorder that loss defeats
 * the purpose. This module makes RX interrupt-driven: the RX IRQ (producer) drains the FIFO the instant
 * bytes arrive into a large bounded SPSC ring; the bridge task (consumer) drains the ring to CDC0 (and,
 * in M2, the SD recorder). Overflow is bounded + counted, never silent.
 */
#ifndef HACKAGOTCHI_UART_BRIDGE_H
#define HACKAGOTCHI_UART_BRIDGE_H

#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include "hardware/uart.h"

// Call once after uart_init(): clears the ring and arms the RX IRQ. Producer side.
void uart_bridge_init(uart_inst_t *uart);

// Re-enable the RX IRQ after a baud change re-inits the UART (clears its IMSC). Ring is preserved.
void uart_bridge_rearm(uart_inst_t *uart);

// CONSUMER (bridge task): drain up to `max` captured bytes into dst. Returns the count.
size_t uart_bridge_read(uint8_t *dst, size_t max);

uint32_t uart_bridge_drops(void);      // total target->host bytes dropped to ring-full
uint32_t uart_bridge_highwater(void);  // max ring fill observed (bytes) — burst headroom indicator

// Host->target overflow (bytes that couldn't fit the host CDC FIFO). Defined in cdc_uart.c; declared
// here to keep all UART-bridge telemetry getters in one place.
uint32_t cdc_uart_tx_overflow(void);

// PL011 internal loopback (TX wired to RX inside the chip) — a jumper-free HIL self-test of the full
// capture path. NOT a product feature; toggled only by the test command.
void uart_bridge_set_loopback(uart_inst_t *uart, bool on);

#endif // HACKAGOTCHI_UART_BRIDGE_H
