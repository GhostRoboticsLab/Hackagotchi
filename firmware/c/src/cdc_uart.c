/*
 * The MIT License (MIT)
 *
 * Copyright (c) 2021 Raspberry Pi (Trading) Ltd.
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in
 * all copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
 * THE SOFTWARE.
 *
 */

/*
 * HACKAGOTCHI FORK OVERLAY of debugprobe-v2.2.3 src/cdc_uart.c — Gate 2.
 * Diff vs upstream is exactly the // [HACKAGOTCHI] guards on the three CDC class callbacks:
 * upstream applied tud_cdc_line_coding_cb / line_state_cb / send_break_cb to the target UART
 * UNCONDITIONALLY. With a 2nd CDC (CDC1 = JSON control), the host opening/closing/setting-baud on
 * CDC1 would reprogram or SUSPEND the CDC0 UART bridge — breaking "CDC0 carries UART concurrently".
 * Guarding to CDC instance 0 (the UART) keeps CDC1 from touching the bridge.
 * The poll path (cdc_task) already targets CDC instance 0 implicitly (tud_cdc_*), so it is unchanged.
 */

#include <pico/stdlib.h>
#include "FreeRTOS.h"
#include "task.h"
#include "tusb.h"

#include "probe_config.h"
#include "uart_bridge.h"   // [HACKAGOTCHI] M1: IRQ-driven RX capture into a bounded SPSC ring

// [HACKAGOTCHI] CDC instance index of the target-UART bridge (CDC0). CDC1 (index 1) = JSON control.
#define CDC_ITF_UART 0

TaskHandle_t uart_taskhandle;
TickType_t last_wake, interval = 100;
volatile TickType_t break_expiry;
volatile bool timed_break;

// [HACKAGOTCHI] host->target overflow: bytes that couldn't be written to the host CDC FIFO. Upstream
// counted this but never surfaced it; expose it as bridge telemetry (see uart_bridge.h).
static volatile uint32_t cdc_tx_oe = 0;
uint32_t cdc_uart_tx_overflow(void) { return cdc_tx_oe; }

static uint8_t rx_buf[64];      /* target->host: drained from the SPSC ring, not the HW FIFO.
                                 * host->target is now byte-at-a-time (non-blocking), no tx_buf. */
// Actually s^-1 so 25ms
#define DEBOUNCE_MS 40
static uint debounce_ticks = 5;

#ifdef PROBE_UART_TX_LED
static volatile uint tx_led_debounce;
#endif

#ifdef PROBE_UART_RX_LED
static uint rx_led_debounce;
#endif

void cdc_uart_init(void) {
    gpio_set_function(PROBE_UART_TX, GPIO_FUNC_UART);
    gpio_set_function(PROBE_UART_RX, GPIO_FUNC_UART);
    gpio_set_pulls(PROBE_UART_TX, 1, 0);
    gpio_set_pulls(PROBE_UART_RX, 1, 0);
    uart_init(PROBE_UART_INTERFACE, PROBE_UART_BAUDRATE);
    uart_bridge_init(PROBE_UART_INTERFACE);  // [HACKAGOTCHI] arm IRQ-driven RX capture

#ifdef PROBE_UART_TX_LED
    tx_led_debounce = 0;
    gpio_init(PROBE_UART_TX_LED);
    gpio_set_dir(PROBE_UART_TX_LED, GPIO_OUT);
#endif
#ifdef PROBE_UART_RX_LED
    rx_led_debounce = 0;
    gpio_init(PROBE_UART_RX_LED);
    gpio_set_dir(PROBE_UART_RX_LED, GPIO_OUT);
#endif

#ifdef PROBE_UART_HWFC
    /* HWFC implies that hardware flow control is implemented and the
     * UART operates in "full-duplex" mode (See USB CDC PSTN120 6.3.12).
     * Default to pulling in the active direction, so an unconnected CTS
     * behaves the same as if CTS were not enabled. */
    gpio_set_pulls(PROBE_UART_CTS, 0, 1);
    gpio_set_function(PROBE_UART_RTS, GPIO_FUNC_UART);
    gpio_set_function(PROBE_UART_CTS, GPIO_FUNC_UART);
    uart_set_hw_flow(PROBE_UART_INTERFACE, true, true);
#else
#ifdef PROBE_UART_RTS
    gpio_init(PROBE_UART_RTS);
    gpio_set_dir(PROBE_UART_RTS, GPIO_OUT);
    gpio_put(PROBE_UART_RTS, 1);
#endif
#endif

#ifdef PROBE_UART_DTR
    gpio_init(PROBE_UART_DTR);
    gpio_set_dir(PROBE_UART_DTR, GPIO_OUT);
    gpio_put(PROBE_UART_DTR, 1);
#endif
}

bool cdc_task(void)
{
    static int was_connected = 0;
    uint rx_len = 0;
    bool keep_alive = false;

    // [HACKAGOTCHI] Drain bytes the RX IRQ already captured into the SPSC ring (the HW FIFO is emptied
    // by the IRQ the instant data arrives, so no firehose overflow between polls). Bytes captured while
    // the host is disconnected accumulate in the ring (bounded) until it drains or overflows.
    rx_len = uart_bridge_read(rx_buf, sizeof(rx_buf));

    if (tud_cdc_connected()) {
        was_connected = 1;
        int written = 0;
        /* Implicit overflow if we don't write all the bytes to the host.
         * Also throw away bytes if we can't write... */
        if (rx_len) {
#ifdef PROBE_UART_RX_LED
          gpio_put(PROBE_UART_RX_LED, 1);
          rx_led_debounce = debounce_ticks;
#endif
          written = MIN(tud_cdc_write_available(), rx_len);
          if (rx_len > written)
              cdc_tx_oe++;

          if (written > 0) {
            tud_cdc_write(rx_buf, written);
            tud_cdc_write_flush();
          }
        } else {
#ifdef PROBE_UART_RX_LED
          if (rx_led_debounce)
            rx_led_debounce--;
          else
            gpio_put(PROBE_UART_RX_LED, 0);
#endif
        }

      /* [HACKAGOTCHI] Host -> target, NON-BLOCKING. Upstream used uart_write_blocking(), which
       * busy-waits the highest-priority bridge task (prio +3, above DAP) until the bytes drain into
       * the TX FIFO — up to ~133 ms at 1200 baud, delaying DAP/TUD. Instead push only what the TX FIFO
       * can take right now and leave the rest in the CDC FIFO; USB then back-pressures the host. No
       * spin, no loss. (uart_putc_raw can't be used unguarded — it blocks on a full FIFO.) */
      if (tud_cdc_available() && uart_is_writable(PROBE_UART_INTERFACE)) {
#ifdef PROBE_UART_TX_LED
        gpio_put(PROBE_UART_TX_LED, 1);
        tx_led_debounce = debounce_ticks;
#endif
        while (uart_is_writable(PROBE_UART_INTERFACE) && tud_cdc_available()) {
          uint8_t ch;
          if (tud_cdc_read(&ch, 1) != 1) break;
          uart_get_hw(PROBE_UART_INTERFACE)->dr = ch;  // FIFO has space (guarded) -> non-blocking
        }
      } else {
#ifdef PROBE_UART_TX_LED
          if (tx_led_debounce)
            tx_led_debounce--;
          else
            gpio_put(PROBE_UART_TX_LED, 0);
#endif
      }
      /* Pending break handling */
      if (timed_break) {
        if (((int)break_expiry - (int)xTaskGetTickCount()) < 0) {
          timed_break = false;
          uart_set_break(PROBE_UART_INTERFACE, false);
#ifdef PROBE_UART_TX_LED
          tx_led_debounce = 0;
#endif
        } else {
          keep_alive = true;
        }
      }
    } else if (was_connected) {
      tud_cdc_write_clear();
      uart_set_break(PROBE_UART_INTERFACE, false);
      timed_break = false;
      was_connected = 0;
#ifdef PROBE_UART_TX_LED
      tx_led_debounce = 0;
#endif
      cdc_tx_oe = 0;
    }
    return keep_alive;
}

void cdc_thread(void *ptr)
{
  BaseType_t delayed;
  last_wake = xTaskGetTickCount();
  bool keep_alive;
  /* Threaded with a polling interval that scales according to linerate */
  while (1) {
    keep_alive = cdc_task();
    if (!keep_alive) {
      delayed = xTaskDelayUntil(&last_wake, interval);
        if (delayed == pdFALSE)
          last_wake = xTaskGetTickCount();
    }
  }
}

void tud_cdc_line_coding_cb(uint8_t itf, cdc_line_coding_t const* line_coding)
{
  if (itf != CDC_ITF_UART) return;  // [HACKAGOTCHI] CDC1 (control) must not reprogram the target UART
  uart_parity_t parity;
  uint data_bits, stop_bits;
  /* Set the tick thread interval to the amount of time it takes to
   * fill up half a FIFO. Millis is too coarse for integer divide.
   */
  uint32_t micros = (1000 * 1000 * 16 * 10) / MAX(line_coding->bit_rate, 1);
  /* Modifying state, so park the thread before changing it. */
  if (tud_cdc_connected())
    vTaskSuspend(uart_taskhandle);
  interval = MAX(1, micros / ((1000 * 1000) / configTICK_RATE_HZ));
  debounce_ticks = MAX(1, configTICK_RATE_HZ / (interval * DEBOUNCE_MS));
  probe_info("New baud rate %ld micros %ld interval %lu\n",
                  line_coding->bit_rate, micros, interval);
  uart_deinit(PROBE_UART_INTERFACE);
  tud_cdc_write_clear();
  tud_cdc_read_flush();
  uart_init(PROBE_UART_INTERFACE, line_coding->bit_rate);

  switch (line_coding->parity) {
  case CDC_LINE_CODING_PARITY_ODD:
    parity = UART_PARITY_ODD;
    break;
  case CDC_LINE_CODING_PARITY_EVEN:
    parity = UART_PARITY_EVEN;
    break;
  default:
    probe_info("invalid parity setting %u\n", line_coding->parity);
    /* fallthrough */
  case CDC_LINE_CODING_PARITY_NONE:
    parity = UART_PARITY_NONE;
    break;
  }

  switch (line_coding->data_bits) {
  case 5:
  case 6:
  case 7:
  case 8:
    data_bits = line_coding->data_bits;
    break;
  default:
    probe_info("invalid data bits setting: %u\n", line_coding->data_bits);
    data_bits = 8;
    break;
  }

  /* The PL011 only supports 1 or 2 stop bits. 1.5 stop bits is translated to 2,
   * which is safer than the alternative. */
  switch (line_coding->stop_bits) {
  case CDC_LINE_CONDING_STOP_BITS_1_5:
  case CDC_LINE_CONDING_STOP_BITS_2:
    stop_bits = 2;
  break;
  default:
    probe_info("invalid stop bits setting: %u\n", line_coding->stop_bits);
    /* fallthrough */
  case CDC_LINE_CONDING_STOP_BITS_1:
    stop_bits = 1;
  break;
  }

  uart_set_format(PROBE_UART_INTERFACE, data_bits, stop_bits, parity);
  uart_bridge_rearm(PROBE_UART_INTERFACE);  // [HACKAGOTCHI] re-enable RX IRQ after the uart re-init
  /* Windows likes to arbitrarily set/get line coding after dtr/rts changes, so
   * don't resume if we shouldn't */
  if(tud_cdc_connected())
    vTaskResume(uart_taskhandle);
}

void tud_cdc_line_state_cb(uint8_t itf, bool dtr, bool rts)
{
  if (itf != CDC_ITF_UART) return;  // [HACKAGOTCHI] CDC1 open/close must not suspend the UART bridge
#ifdef PROBE_UART_RTS
  gpio_put(PROBE_UART_RTS, !rts);
#endif
#ifdef PROBE_UART_DTR
  gpio_put(PROBE_UART_DTR, !dtr);
#endif

  /* CDC drivers use linestate as a bodge to activate/deactivate the interface.
   * Resume our UART polling on activate, stop on deactivate */
  if (!dtr) {
    vTaskSuspend(uart_taskhandle);
#ifdef PROBE_UART_RX_LED
    gpio_put(PROBE_UART_RX_LED, 0);
    rx_led_debounce = 0;
#endif
#ifdef PROBE_UART_TX_LED
    gpio_put(PROBE_UART_TX_LED, 0);
    tx_led_debounce = 0;
#endif
  } else
    vTaskResume(uart_taskhandle);
}

void tud_cdc_send_break_cb(uint8_t itf, uint16_t wValue) {
  if (itf != CDC_ITF_UART) return;  // [HACKAGOTCHI] only the UART bridge forwards a host BREAK
  switch(wValue) {
    case 0:
    uart_set_break(PROBE_UART_INTERFACE, false);
    timed_break = false;
#ifdef PROBE_UART_TX_LED
    tx_led_debounce = 0;
#endif
    break;
    case 0xffff:
    uart_set_break(PROBE_UART_INTERFACE, true);
    timed_break = false;
#ifdef PROBE_UART_TX_LED
    gpio_put(PROBE_UART_TX_LED, 1);
    tx_led_debounce = 1 << 30;
#endif
    break;
    default:
    uart_set_break(PROBE_UART_INTERFACE, true);
    timed_break = true;
#ifdef PROBE_UART_TX_LED
    gpio_put(PROBE_UART_TX_LED, 1);
    tx_led_debounce = 1 << 30;
#endif
    break_expiry = xTaskGetTickCount() + (wValue * (configTICK_RATE_HZ / 1000));
    break;
  }
}
