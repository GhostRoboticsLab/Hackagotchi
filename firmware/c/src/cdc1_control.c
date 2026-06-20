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
#include <stdlib.h>   // atoi (numeric jsmn values for beep/led test commands)
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
#include "sd_gate.h"                // M2: SD bring-up self-test result ({"q":"sd"})
#include "feedback.h"               // M3.0: LED/buzzer HW-reconciliation test commands

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

// Screen navigation: the M3 dashboard OWNS the screen index; CDC1 only posts intents (dash_nav_step /
// dash_nav_to) that the dashboard consumes + clamps. The current index is read back from g_dash_screen.

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
                     "\"crashes\":%u,\"wd_armed\":%d,\"wd_gap\":%u,\"tud\":%u,\"page\":%d,"
                     "\"urx_drop\":%u,\"urx_hw\":%u,\"utx_drop\":%u,\"frag\":%u}\n",
                     (unsigned) xPortGetFreeHeapSize(),
                     (unsigned) (time_us_64() / 1000000ull),
                     (unsigned) g_dash_counter, (int) ADVERSARIAL_STALL_MS,
                     (unsigned) g_dash_stall_us, (int) HACKA_DASH_PRIO,
                     (unsigned) crash_box_count(), (int) wd_is_armed(), (unsigned) wd_max_gap_ms(),
                     (unsigned) g_tud_checkin, (int) g_dash_screen,
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
  char r[40];
  int len = snprintf(r, sizeof r, "{\"page\":%d,\"n\":%d}\n", (int)g_dash_screen, dash_screen_count());
  if (len > 0) reply(itf, r);
}

// M3.1 self-attestation: the current screen index + the EXACT text the dashboard drew this frame, plus
// the show-success / loop counters. A host test asserts content + that frames actually flush (shows
// climbing), with no camera. Newlines in the rendered text become '|'; '"'/'\' are escaped.
static void write_screen(uint8_t itf) {
  static char txt[160];
  int idx = dash_get_attest(txt, sizeof txt);
  static char esc[200];
  size_t o = 0;
  for (size_t i = 0; txt[i] && o + 2 < sizeof esc; i++) {
    char c = txt[i];
    if (c == '\n') esc[o++] = '|';
    else if (c == '"' || c == '\\') { esc[o++] = '\\'; esc[o++] = c; }
    else if (c >= 32 && c <= 126) esc[o++] = c;
  }
  esc[o] = '\0';
  static char r[280];
  int len = snprintf(r, sizeof r,
                     "{\"screen\":%d,\"n\":%d,\"shows\":%u,\"loops\":%u,\"dstack\":%u,\"text\":\"%s\"}\n",
                     idx, dash_screen_count(), (unsigned)g_dash_shows, (unsigned)g_dash_counter,
                     (unsigned)g_dash_stack_free, esc);
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

// Read the integer value of top-level key `key` (a jsmn PRIMITIVE number). atoi() stops at the token's
// trailing delimiter (the value isn't NUL-terminated in `js`, but ',' / '}' bounds it). Returns true iff found.
static bool get_int(const char *js, const jsmntok_t *tok, int ntok, const char *key, int *out) {
  for (int i = 1; i + 1 < ntok; i++) {
    if (tok_eq(js, &tok[i], key) && tok[i + 1].type == JSMN_PRIMITIVE) {
      *out = atoi(js + tok[i + 1].start);
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
  if (!strcmp(q, "wd_reset"))  { wd_gap_reset(); reply(itf, "{\"wd_gap\":0}\n"); return; }
  if (!strcmp(q, "sd"))        { static char r[160]; sd_gate_status_json(r, sizeof r); reply(itf, r); return; }
  if (!strcmp(q, "rec"))       { static char r[256]; sd_rec_status_json(r, sizeof r); reply(itf, r); return; }
  // {"q":"tail"}: request a tail read (SD task does the FatFs read off the hot path) AND return the
  // PREVIOUS read — so send it twice (request, then collect) to verify on-card log content.
  if (!strcmp(q, "tail"))      { static char r[256]; sd_rec_tail_json(r, sizeof r); sd_rec_tail_request(); reply(itf, r); return; }
  if (!strcmp(q, "next"))      { dash_nav_step(+1); write_page(itf); return; }
  if (!strcmp(q, "prev"))      { dash_nav_step(-1); write_page(itf); return; }
  // {"q":"screen"} -> report the current screen + rendered-text attestation (HIL: content + frames-flush).
  // {"q":"screen","n":N} -> jump to screen N (clamped by the dashboard), then report.
  if (!strcmp(q, "screen"))    { int v; if (get_int(line, tok, n, "n", &v)) dash_nav_to(v); write_screen(itf); return; }
  // UART-bridge HIL self-test: PL011 internal loopback (TX->RX in-chip) — round-trip CDC0 with no jumper.
  if (!strcmp(q, "uloop_on"))  { uart_bridge_set_loopback(PROBE_UART_INTERFACE, true);  reply(itf, "{\"uloop\":1}\n"); return; }
  if (!strcmp(q, "uloop_off")) { uart_bridge_set_loopback(PROBE_UART_INTERFACE, false); reply(itf, "{\"uloop\":0}\n"); return; }
  // Reliability HIL hook: exhaust the FreeRTOS heap so vApplicationMallocFailedHook fires -> crash box
  // records kind=mallocfail + reboots (directly proves the malloc-fail path, not just the shared code).
  if (!strcmp(q, "oom_test"))  { for (;;) (void) pvPortMalloc(1024); return; /* hook reboots first */ }
  // M2 coexistence soak: device-side recorder load (continuous SD writes, no host UART traffic) so a
  // concurrent probe-rs flash soak measures pure SD-vs-DAP contention without host USB confounds.
  if (!strcmp(q, "recgen_on"))  { sd_recgen_set(true);  reply(itf, "{\"recgen\":1}\n"); return; }
  if (!strcmp(q, "recgen_off")) { sd_recgen_set(false); reply(itf, "{\"recgen\":0}\n"); return; }
  // M3.0 HW-reconciliation: drive the buzzer (GP29) + the WS2812 NeoPixel (GP12/GP11) to confirm the
  // outputs work post-SWD-remap. {"q":"led"} maps red/green flags to the NeoPixel via feedback_led ->
  // feedback_pixel — NOT the onboard GP17/16 RGB, which Finding M3-1 abandoned as an unreliable channel.
  // Non-blocking (the SD task's feedback_service does the actual drive/dwell).
  // {"q":"beep","hz":2000,"ms":120}  /  {"q":"led","r":1,"g":0}  /  {"q":"pixel","r":..,"g":..,"b":..}
  if (!strcmp(q, "beep")) {
    int hz = 2000, ms = 120; get_int(line, tok, n, "hz", &hz); get_int(line, tok, n, "ms", &ms);
    feedback_beep((uint16_t)(hz < 0 ? 0 : hz), (uint16_t)(ms < 0 ? 0 : ms));
    char r[40]; snprintf(r, sizeof r, "{\"beep\":%d,\"ms\":%d}\n", hz, ms); reply(itf, r); return;
  }
  if (!strcmp(q, "led")) {
    int rr = 0, gg = 0; get_int(line, tok, n, "r", &rr); get_int(line, tok, n, "g", &gg);
    feedback_led(rr != 0, gg != 0);
    char r[32]; snprintf(r, sizeof r, "{\"led_r\":%d,\"led_g\":%d}\n", rr ? 1 : 0, gg ? 1 : 0); reply(itf, r); return;
  }
  // {"q":"pixel","r":0..255,"g":..,"b":..} — drive the NeoPixel to an arbitrary colour (HW-reconcile/test).
  if (!strcmp(q, "pixel")) {
    int rr = 0, gg = 0, bb = 0;
    get_int(line, tok, n, "r", &rr); get_int(line, tok, n, "g", &gg); get_int(line, tok, n, "b", &bb);
    #define CLAMP8(v) ((uint8_t)((v) < 0 ? 0 : (v) > 255 ? 255 : (v)))
    feedback_pixel(CLAMP8(rr), CLAMP8(gg), CLAMP8(bb));
    #undef CLAMP8
    char r[48]; snprintf(r, sizeof r, "{\"pixel\":[%d,%d,%d]}\n", rr, gg, bb); reply(itf, r); return;
  }
  // M3 closeout HIL: feedback-layer readback — proves drive_feedback drove the buzzer/NeoPixel on events.
  if (!strcmp(q, "fb")) {
    uint32_t c = feedback_color();
    char r[72];
    snprintf(r, sizeof r, "{\"beeps\":%u,\"beeping\":%d,\"r\":%u,\"g\":%u,\"b\":%u}\n",
             (unsigned)feedback_beep_count(), feedback_is_beeping() ? 1 : 0,
             (unsigned)((c >> 8) & 0xFFu), (unsigned)((c >> 16) & 0xFFu), (unsigned)(c & 0xFFu));
    reply(itf, r); return;
  }

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
