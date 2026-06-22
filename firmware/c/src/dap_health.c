/* Hackagotchi — DAP transfer/health telemetry. SPDX-License-Identifier: MIT
 *
 * See dap_health.h. __wrap_DAP_ExecuteCommand is bound to the real symbol by the linker flag
 * -Wl,--wrap=DAP_ExecuteCommand (CMakeLists). The wrapper does the real DAP work first, THEN records
 * a non-blocking witness — so the count only ever reflects commands that actually completed.
 */
#include "dap_health.h"
#include "hardware/timer.h"   // time_us_32 — a single timer-register read, non-blocking (R1-safe)

// SINGLE writer: the DAP task, via __wrap_DAP_ExecuteCommand. Readers (the CDC1 status path, which
// runs at TUD priority) only READ these. 32-bit aligned word reads/writes are atomic on Cortex-M0+,
// and there is exactly one writer, so no lock is needed — never take a lock on the DAP path (R1).
static volatile uint32_t s_xfers   = 0;
static volatile uint32_t s_last_us = 0;
static volatile uint8_t  s_seen    = 0;

// The real symbol, renamed by --wrap. const-qualified to match DAP.h's prototype exactly.
extern uint32_t __real_DAP_ExecuteCommand(const uint8_t *request, uint8_t *response);

uint32_t __wrap_DAP_ExecuteCommand(const uint8_t *request, uint8_t *response) {
    uint32_t resp_len = __real_DAP_ExecuteCommand(request, response);  // do the actual probe work
    s_xfers++;                                                         // then witness it (non-blocking)
    s_last_us = time_us_32();
    s_seen = 1;
    return resp_len;
}

uint32_t dap_health_xfers(void) {
    return s_xfers;
}

uint32_t dap_health_idle_ms(void) {
    if (!s_seen) return 0;
    uint32_t dt_us = time_us_32() - s_last_us;   // unsigned wrap-safe delta (time_us_32 wraps ~71 min)
    return dt_us / 1000u;
}
