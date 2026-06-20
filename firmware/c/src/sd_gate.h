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

#include "FreeRTOS.h"
#include "task.h"

void sd_gate_task(void *ptr);
extern TaskHandle_t sd_gate_taskhandle;

// One-line JSON of the bring-up self-test result (for the CDC1 {"q":"sd"} reply).
void sd_gate_status_json(char *out, unsigned outsz);

// M2 recorder status ({"q":"rec"}) + async tail-of-current-log readout ({"q":"tail"} — request, then
// read on a later call; the file read happens in the SD task, never on the CDC1/hot path).
void sd_rec_status_json(char *out, unsigned outsz);
void sd_rec_tail_request(void);
void sd_rec_tail_json(char *out, unsigned outsz);

#endif // HACKAGOTCHI_SD_GATE_H
