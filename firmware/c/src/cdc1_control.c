/*
 * Hackagotchi — Gate 2 CDC1 JSON control channel. SPDX-License-Identifier: MIT
 *
 * CDC1 (instance 1) is a tiny request/response control port, separate from CDC0 (the target-UART
 * bridge in cdc_uart.c). It answers {"q":"status"} with one line of JSON. This is the Gate-2
 * round-trip surface; the full jsmn-based control protocol is an M1 concern.
 */

#include <string.h>
#include <stdio.h>
#include <pico/stdlib.h>

#include "FreeRTOS.h"
#include "task.h"
#include "tusb.h"

#define CDC_ITF_CONTROL 1  // CDC1 = JSON control (CDC0 / instance 0 = UART bridge, owned by cdc_uart.c)

// TinyUSB invokes this on CDC RX for ANY instance. We own ONLY CDC1; CDC0's bytes are left in their
// FIFO for cdc_task()'s poller (it reads instance 0). Runs in the tud_task()/usb_thread context, so
// the reply write is same-task-safe and never touches the DAP/SWD path.
void tud_cdc_rx_cb(uint8_t itf)
{
  if (itf != CDC_ITF_CONTROL) return;

  char buf[96];
  uint32_t n = tud_cdc_n_read(itf, buf, sizeof(buf) - 1);
  if (n == 0) return;
  buf[n] = '\0';

  // Minimal request match for Gate 2: any line containing "status" -> one-line JSON reply.
  // Full {"q":"..."} jsmn parsing is deferred to M1; Gate 2 only requires a valid JSON round-trip.
  if (strstr(buf, "status")) {
    char reply[96];
    unsigned heap = (unsigned) xPortGetFreeHeapSize();
    unsigned up   = (unsigned) (time_us_64() / 1000000ull);
    int len = snprintf(reply, sizeof reply,
                       "{\"fw\":\"Hackagotchi\",\"heap\":%u,\"up\":%u}\n", heap, up);
    if (len > 0) {
      tud_cdc_n_write(itf, reply, (uint32_t) len);
      tud_cdc_n_write_flush(itf);
    }
  }
}
