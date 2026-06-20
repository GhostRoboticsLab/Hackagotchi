/*
 * Hackagotchi — M2 SD bring-up gate. SPDX-License-Identifier: MIT
 *
 * A LOW-priority FreeRTOS task (idle+0, strictly below DAP) that runs the foundational M2 hardware
 * proof once at boot: f_mount the microSD on SPI0 (GP2/3/4/CS28) → write a test file → read it back →
 * verify → report free space. The result is read back over CDC1 {"q":"sd"}. All SD/FatFs I/O happens
 * HERE, off the DAP/USB hot path (R1). This task is the seed of the M2 recorder (M2.3 turns it into
 * the spsc-ring-draining black-box writer).
 */
#ifndef HACKAGOTCHI_SD_GATE_H
#define HACKAGOTCHI_SD_GATE_H

#include <stdbool.h>
#include <stdint.h>
#include "FreeRTOS.h"
#include "task.h"

void sd_gate_task(void *ptr);
extern TaskHandle_t sd_gate_taskhandle;

// M3 published recorder snapshot (POD — no pointers). The SD/recorder task is the SOLE owner of
// recorder_t / the freeze ring; it publishes this consistent copy once per loop via a
// single-writer seqlock. EVERY other task (the dashboard render loop, the CDC1 status reply) reads it
// through dash_get_rec_snapshot() instead of touching g_rec across the task boundary — closing the
// two-ring concurrency boundary the M2 design established (and the latent race the old {"q":"rec"} had:
// it handed out a LIVE pointer into g_rec.filename + called hw->sd_mounted() from the wrong task).
typedef struct {
    bool      logging;
    bool      wedge;
    bool      sd_mounted;
    uint32_t  rx_total;
    uint32_t  hits;
    uint32_t  tp_peak;
    uint32_t  rec_drop;      // bytes the recorder ring dropped (uart_bridge_rec_drops)
    int       last_err;      // rec_err_t: 0=none, 1=SD full, 2=write error
    char      file[16];      // current log filename (bounded copy, never a live pointer)
    char      alert[24];     // last recorder alert text (trigger hit / fault badge)
    char      tail[80];      // printable tail of the freeze ring (live-UART view)
} rec_snapshot_t;

// Lock-free seqlock read of the published snapshot. Returns false only under (effectively impossible)
// sustained write contention; on false the caller should keep its previous copy.
bool dash_get_rec_snapshot(rec_snapshot_t *out);

// HIL hook: device-side recorder load generator for the SD-during-flash coexistence soak (continuous
// SD writes with no host UART traffic). Toggled over CDC1 ({"q":"recgen_on"}/{"q":"recgen_off"}).
void sd_recgen_set(bool on);

// One-line JSON of the bring-up self-test result (for the CDC1 {"q":"sd"} reply).
void sd_gate_status_json(char *out, unsigned outsz);

// M2 recorder status ({"q":"rec"}) + async tail-of-current-log readout ({"q":"tail"} — request, then
// read on a later call; the file read happens in the SD task, never on the CDC1/hot path).
void sd_rec_status_json(char *out, unsigned outsz);
void sd_rec_tail_request(void);
void sd_rec_tail_json(char *out, unsigned outsz);

#endif // HACKAGOTCHI_SD_GATE_H
