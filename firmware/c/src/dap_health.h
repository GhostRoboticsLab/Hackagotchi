/* Hackagotchi — DAP transfer/health telemetry. SPDX-License-Identifier: MIT
 *
 * A firmware-side WITNESS to the R1 "0 DAP transfer stalls" invariant: a monotonic count of DAP
 * commands actually executed by the probe, plus the time since the last one. Every soak can then
 * cross-check that dap_xfers advanced by the expected amount and that the probe was live throughout
 * — a soak whose counter never moves is a silent pass.
 *
 * Wiring: a linker --wrap on DAP_ExecuteCommand (see CMakeLists + dap_health.c). DAP_ExecuteCommand
 * is a stable CMSIS-DAP API called cross-TU from upstream tusb_edpt_handler.c's dap_thread, so there
 * is NO upstream source shadow to re-diff on a debugprobe bump (cf. the v2.3.1 spike, backlog #8).
 *
 * R1: the tick runs ON the DAP task (the wrapper IS the execute call) and is strictly non-blocking —
 * a counter ++ and one timer-register read, nothing that can stall the DAP path.
 *
 * *** DAP-PATH CHANGE — this MUST be re-gated on hardware (Gate 1 soak + coexist_soak 300, 0 stalls
 *     AND unchanged retryable rate) before it is merged to main. It is intentionally on a branch. ***
 */
#ifndef HACKAGOTCHI_DAP_HEALTH_H
#define HACKAGOTCHI_DAP_HEALTH_H

#include <stdint.h>

uint32_t dap_health_xfers(void);    // monotonic count of DAP commands executed (single-writer, lock-free)
uint32_t dap_health_idle_ms(void);  // ms since the last DAP command (0 before the first one)

#endif /* HACKAGOTCHI_DAP_HEALTH_H */
