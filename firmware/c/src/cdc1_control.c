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
#include "hackagotchi_dashboard.h"  // g_dash_counter, g_dash_stall_us (self-attestation telemetry)
#include "crash_box.h"              // M1: lastfault readout + the crash HIL self-test

// Build-discriminating tags compiled into the status reply so the RUNNING firmware proves its OWN
// identity (closes the Gate-1 provenance gap: stock vs adversarial probe images were otherwise
// byte-identical in captured evidence). These mirror the CMake -D flags (PRIVATE on the target =>
// visible to this TU).
#ifndef ADVERSARIAL_STALL_MS
#define ADVERSARIAL_STALL_MS 0
#endif
#ifdef ADVERSARIAL_AT_DAP_PRIO
#define HACKA_DASH_PRIO 1   // dashboard runs AT DAP priority (adversarial contention build)
#else
#define HACKA_DASH_PRIO 0   // dashboard strictly below DAP (normal / product config)
#endif

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

  // M1 crash-box HIL self-test: force a real HardFault on demand so the gate can prove the box
  // captures a fault and surfaces it after the reboot. The store to an UNMAPPED address (0xF0000000
  // is outside every RP2040 region) bus-errors -> HardFault; the recorded PC lands in this file.
  // Does not return (the device reboots); no reply is sent — the host detects the re-enumeration.
  if (strstr(buf, "crash")) {
    *(volatile uint32_t *)0xF0000000u = 0xDEADBEEFu;
    return;  // unreachable
  }

  // M1: serve the last captured post-mortem (or {"fault":"none"} when clean).
  if (strstr(buf, "lastfault")) {
    char reply[200];
    int len = snprintf(reply, sizeof reply, "{\"fault\":%s}\n", crash_box_report());
    if (len > 0) {
      tud_cdc_n_write(itf, reply, (uint32_t) len);
      tud_cdc_n_write_flush(itf);
    }
    return;
  }

  // Minimal request match for Gate 2: any line containing "status" -> one-line JSON reply.
  // Full {"q":"..."} jsmn parsing is deferred to M1; Gate 2 only requires a valid JSON round-trip.
  if (strstr(buf, "status")) {
    char reply[160];
    unsigned heap = (unsigned) xPortGetFreeHeapSize();
    unsigned up   = (unsigned) (time_us_64() / 1000000ull);
    // fw/heap/up kept first + same shape for gate2_cdc.py compat; n/stall_cfg/stall_us/prio are the
    // self-attestation fields: n proves the dashboard task is LOOPING (monotonic), stall_us proves the
    // adversarial busy_wait actually FIRED (~50000us), stall_cfg+prio identify WHICH build is running.
    int len = snprintf(reply, sizeof reply,
                       "{\"fw\":\"Hackagotchi\",\"heap\":%u,\"up\":%u,"
                       "\"n\":%u,\"stall_cfg\":%d,\"stall_us\":%u,\"prio\":%d,\"crashes\":%u}\n",
                       heap, up,
                       (unsigned) g_dash_counter, (int) ADVERSARIAL_STALL_MS,
                       (unsigned) g_dash_stall_us, (int) HACKA_DASH_PRIO,
                       (unsigned) crash_box_count());
    if (len > 0) {
      tud_cdc_n_write(itf, reply, (uint32_t) len);
      tud_cdc_n_write_flush(itf);
    }
  }
}
