/*
 * Hackagotchi — M1: interrupt-driven UART RX capture. SPDX-License-Identifier: MIT
 * See uart_bridge.h for the rationale (the polling bridge loses bytes at speed).
 */

#include "uart_bridge.h"
#include "spsc_ring.h"

#include "hardware/irq.h"
#include "hardware/regs/uart.h"   // UART_UARTCR_LBE_BITS

#define RX_RING_CAP 4096u         // power of two; absorbs bursts while USB/CDC drains

static uint8_t     s_buf[RX_RING_CAP];
static spsc_ring_t s_ring;
static uart_inst_t *s_uart;

// M2: second staging ring (cdc_task -> recorder task) + producer-sourced RX liveness.
#define REC_RING_CAP 4096u
static uint8_t     s_rec_buf[REC_RING_CAP];
static spsc_ring_t s_rec_ring;
static volatile uint32_t s_rx_last_ms = 0;
static volatile bool     s_rx_ever    = false;

// Producer (IRQ context): drain the HW FIFO into the ring. Reading the data register clears the RX
// (and timeout) interrupt; looping until !readable guarantees we exit and the IRQ deasserts. No
// FreeRTOS calls here. Error flags in the upper DR bits are ignored (we take the low 8 data bits).
static void uart_rx_irq(void) {
    while (uart_is_readable(s_uart))
        spsc_push(&s_ring, (uint8_t)(uart_get_hw(s_uart)->dr & 0xFFu));
}

void uart_bridge_init(uart_inst_t *uart) {
    spsc_init(&s_ring, s_buf, RX_RING_CAP);
    spsc_init(&s_rec_ring, s_rec_buf, REC_RING_CAP);
    s_rx_last_ms = 0;
    s_rx_ever = false;
    s_uart = uart;
    uint irq = (uart == uart0) ? UART0_IRQ : UART1_IRQ;
    irq_set_exclusive_handler(irq, uart_rx_irq);
    irq_set_enabled(irq, true);
    uart_set_irq_enables(uart, true /*rx*/, false /*tx*/);  // RX + RX-timeout, no TX IRQ
}

void uart_bridge_rearm(uart_inst_t *uart) {
    // uart_deinit/uart_init in the baud-change callback clears the UART's IMSC; the NVIC handler is
    // still registered, so just re-enable the RX interrupt. Ring contents/counters are preserved.
    uart_set_irq_enables(uart, true, false);
}

size_t uart_bridge_read(uint8_t *dst, size_t max) { return spsc_pop(&s_ring, dst, max); }

uint32_t uart_bridge_drops(void)     { return s_ring.drops; }
uint32_t uart_bridge_highwater(void) { return s_ring.highwater; }

void uart_bridge_set_loopback(uart_inst_t *uart, bool on) {
    if (on) hw_set_bits(&uart_get_hw(uart)->cr, UART_UARTCR_LBE_BITS);
    else    hw_clear_bits(&uart_get_hw(uart)->cr, UART_UARTCR_LBE_BITS);
}

// --- M2 recorder tee (cdc_task = sole producer; recorder task = sole consumer; SPSC invariant held) ---
void uart_bridge_tee(const uint8_t *data, size_t n, uint32_t now_ms) {
    if (n == 0) return;
    s_rx_last_ms = now_ms;   // producer-sourced liveness (single uint32 write; recorder reads it)
    s_rx_ever = true;
    for (size_t i = 0; i < n; i++) spsc_push(&s_rec_ring, data[i]);  // drop-on-full counted in the ring
}
size_t   uart_bridge_rec_read(uint8_t *dst, size_t max) { return spsc_pop(&s_rec_ring, dst, max); }
uint32_t uart_bridge_rec_drops(void)  { return s_rec_ring.drops; }
uint32_t uart_bridge_rx_last_ms(void) { return s_rx_last_ms; }
bool     uart_bridge_rx_ever(void)    { return s_rx_ever; }
