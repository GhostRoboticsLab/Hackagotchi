/*
 * Hackagotchi — CDC1 JSON control channel. SPDX-License-Identifier: MIT
 *
 * CDC1 (instance 1) is a LINE-oriented request/response control port, separate from CDC0 (the target-
 * UART bridge in cdc_uart.c). Each request is one line of JSON — {"q":"<command>"} — and each reply is
 * one line of JSON. M1 replaces the Gate-2 strstr() prototype with a real jsmn parse over a bounded
 * line buffer, so a command is matched on the STRUCTURED value of the "q" key, not a substring:
 * {"note":"status please"} no longer false-triggers `status` the way the strstr prototype did.
 *
 * Commands: status, dump, lastfault, wd_arm, next, prev (request/response); crash, wd_test, bootsel
 * (no reply — the device faults/wedges/reboots and the host detects re-enumeration).
 *
 * Runs in the tud_task()/usb_thread (TUD task) context, so replies are same-task-safe and never touch
 * the DAP/SWD path.
 */

#include <string.h>
#include <stdio.h>
#include <stdbool.h>
#include <pico/stdlib.h>

#include "pico/bootrom.h"           // reset_usb_boot for {"q":"bootsel"}

#include "FreeRTOS.h"
#include "task.h"
#include "tusb.h"

#define JSMN_STATIC                 // keep jsmn symbols file-local (header-only, single TU)
#include "jsmn.h"

#include "probe_config.h"           // PROBE_UART_INTERFACE (for the uart loopback HIL test)
#include "hackagotchi_dashboard.h"  // g_dash_counter, g_dash_stall_us (self-attestation telemetry)
#include "crash_box.h"              // lastfault readout + the crash HIL self-test
#include "watchdog_task.h"          // wd_arm + g_tud_wedge (watchdog control + HIL test)
#include "uart_bridge.h"            // uart ring stats + loopback toggle (CDC0 bridge HIL test)

// Build-discriminating tags compiled into the status reply so the RUNNING firmware proves its OWN
// identity (closes the Gate-1 provenance gap). Mirror the CMake -D flags (PRIVATE on the target).
#ifndef ADVERSARIAL_STALL_MS
#define ADVERSARIAL_STALL_MS 0
#endif
#ifdef ADVERSARIAL_AT_DAP_PRIO
#define HACKA_DASH_PRIO 1
#else
#define HACKA_DASH_PRIO 0
#endif

#define CDC_ITF_CONTROL 1  // CDC1 = JSON control (CDC0 / instance 0 = UART bridge, in cdc_uart.c)
#define LINE_MAX 128       // bounded request line buffer — overflow resets it, never overruns
#define MAX_TOK  16        // enough tokens for our small {"q":"..."} requests

// Page-navigation intent: next/prev move it. The single-screen Gate-1 harness ignores it today; the
// M3 dashboard will consume it to pick a screen. Echoed in every reply so a host can drive nav now.
static int s_page = 0;

// Count of rx-callbacks that ended holding a partial line (= a request spanned >1 USB packet and the
// line buffer reassembled it). Exposed as `frag` so the HIL fragmentation test can prove the
// reassembly path actually ran, instead of trusting host-side packetization timing.
static uint32_t s_partial = 0;

static void reply(uint8_t itf, const char *s) {
  tud_cdc_n_write(itf, s, (uint32_t) strlen(s));
  tud_cdc_n_write_flush(itf);
}

// The status/telemetry line. "fw" stays first (gate2_cdc.py compat); n/stall_*/prio self-attest the
// build; crashes/wd_armed/page expose the M1 reliability + nav state.
// NOTE: reply/token buffers are `static`, NOT stack — this callback runs only in the single (non-
// reentrant) TUD task, and ~0.5 KB of JSON locals on the small USB task stack overflows it (corrupts
// the USB endpoint state -> the host sees ENXIO). Keep big buffers off this stack.
static void write_status(uint8_t itf) {
  static char r[240];
  int len = snprintf(r, sizeof r,
                     "{\"fw\":\"Hackagotchi\",\"heap\":%u,\"up\":%u,\"n\":%u,"
                     "\"stall_cfg\":%d,\"stall_us\":%u,\"prio\":%d,"
                     "\"crashes\":%u,\"wd_armed\":%d,\"wd_gap\":%u,\"page\":%d,"
                     "\"urx_drop\":%u,\"urx_hw\":%u,\"utx_drop\":%u,\"frag\":%u}\n",
                     (unsigned) xPortGetFreeHeapSize(),
                     (unsigned) (time_us_64() / 1000000ull),
                     (unsigned) g_dash_counter, (int) ADVERSARIAL_STALL_MS,
                     (unsigned) g_dash_stall_us, (int) HACKA_DASH_PRIO,
                     (unsigned) crash_box_count(), (int) wd_is_armed(), (unsigned) wd_max_gap_ms(),
                     s_page,
                     (unsigned) uart_bridge_drops(), (unsigned) uart_bridge_highwater(),
                     (unsigned) cdc_uart_tx_overflow(), (unsigned) s_partial);
  if (len > 0) reply(itf, r);
}

static void write_lastfault(uint8_t itf) {
  static char r[200];
  int len = snprintf(r, sizeof r, "{\"fault\":%s}\n", crash_box_report());
  if (len > 0) reply(itf, r);
}

static void write_page(uint8_t itf) {
  char r[32];
  int len = snprintf(r, sizeof r, "{\"page\":%d}\n", s_page);
  if (len > 0) reply(itf, r);
}

// jsmn helper: does token `t` (within json string `js`) equal C-string `s`?
static bool tok_eq(const char *js, const jsmntok_t *t, const char *s) {
  return t->type == JSMN_STRING &&
         (int) strlen(s) == (t->end - t->start) &&
         strncmp(js + t->start, s, (size_t)(t->end - t->start)) == 0;
}

// Copy the value of the top-level "q" key into out[]. Returns true iff found as a string value.
static bool get_q(const char *js, const jsmntok_t *tok, int ntok, char *out, size_t outsz) {
  for (int i = 1; i + 1 < ntok; i++) {
    if (tok_eq(js, &tok[i], "q") && tok[i + 1].type == JSMN_STRING) {
      int vlen = tok[i + 1].end - tok[i + 1].start;
      if (vlen <= 0 || (size_t) vlen >= outsz) return false;
      memcpy(out, js + tok[i + 1].start, (size_t) vlen);
      out[vlen] = '\0';
      return true;
    }
  }
  return false;
}

// Parse + dispatch one complete JSON request line.
static void handle_line(uint8_t itf, const char *line, int len) {
  jsmn_parser p;
  static jsmntok_t tok[MAX_TOK];  // static: keep 256 B off the small TUD task stack (see write_status)
  jsmn_init(&p);
  int n = jsmn_parse(&p, line, (size_t) len, tok, MAX_TOK);
  if (n < 1 || tok[0].type != JSMN_OBJECT) { reply(itf, "{\"err\":\"badjson\"}\n"); return; }

  char q[24];
  if (!get_q(line, tok, n, q, sizeof q)) { reply(itf, "{\"err\":\"noq\"}\n"); return; }

  // Commands that do NOT return (device reboots / wedges; host detects re-enumeration).
  if (!strcmp(q, "bootsel")) { reset_usb_boot(0, 0); return; }
  if (!strcmp(q, "crash"))   { *(volatile uint32_t *)0xF0000000u = 0xDEADBEEFu; return; }
  if (!strcmp(q, "wd_test")) { g_tud_wedge = true; return; }

  // Request/response commands.
  if (!strcmp(q, "status"))    { write_status(itf); return; }
  if (!strcmp(q, "lastfault")) { write_lastfault(itf); return; }
  if (!strcmp(q, "dump"))      { write_status(itf); write_lastfault(itf); return; }
  if (!strcmp(q, "wd_arm"))    { wd_arm(); reply(itf, "{\"wd\":\"armed\"}\n"); return; }
  if (!strcmp(q, "next"))      { s_page++; write_page(itf); return; }
  if (!strcmp(q, "prev"))      { if (s_page > 0) s_page--; write_page(itf); return; }
  // UART-bridge HIL self-test: PL011 internal loopback (TX->RX in-chip) — round-trip CDC0 with no jumper.
  if (!strcmp(q, "uloop_on"))  { uart_bridge_set_loopback(PROBE_UART_INTERFACE, true);  reply(itf, "{\"uloop\":1}\n"); return; }
  if (!strcmp(q, "uloop_off")) { uart_bridge_set_loopback(PROBE_UART_INTERFACE, false); reply(itf, "{\"uloop\":0}\n"); return; }
  // Reliability HIL hook: exhaust the FreeRTOS heap so vApplicationMallocFailedHook fires -> crash box
  // records kind=mallocfail + reboots (directly proves the malloc-fail path, not just the shared code).
  if (!strcmp(q, "oom_test"))  { for (;;) (void) pvPortMalloc(1024); return; /* hook reboots first */ }

  reply(itf, "{\"err\":\"unknown\"}\n");
}

// TinyUSB CDC RX callback (ALL instances). We own ONLY CDC1; CDC0's bytes stay in their FIFO for
// cdc_task(). Bytes are accumulated into a BOUNDED line buffer and dispatched per newline, so a
// request split across USB packets is reassembled and an over-long line is dropped (never overruns).
void tud_cdc_rx_cb(uint8_t itf) {
  if (itf != CDC_ITF_CONTROL) return;

  static char line[LINE_MAX];
  static int  llen = 0;

  uint8_t buf[64];
  uint32_t n;
  while ((n = tud_cdc_n_read(itf, buf, sizeof buf)) > 0) {
    for (uint32_t i = 0; i < n; i++) {
      char c = (char) buf[i];
      if (c == '\n' || c == '\r') {
        if (llen > 0) { handle_line(itf, line, llen); llen = 0; }
      } else if (llen < LINE_MAX - 1) {
        line[llen++] = c;
      } else {
        llen = 0;  // over-long line: drop it defensively
        reply(itf, "{\"err\":\"toolong\"}\n");
      }
    }
  }
  if (llen > 0) s_partial++;  // ended holding a partial line -> a request spanned >1 packet
}
