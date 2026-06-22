/*
 * Hackagotchi — ADS1115 I2C ADC (joystick/rocker bridge on the shared I2C1 / Grove bus).
 * SPDX-License-Identifier: MIT
 *
 * Read ONLY from the dashboard task (the OLED's task) so I2C1 keeps a single owner and needs no mutex.
 * When HG_JOYSTICK is built, i2c1_bus.h drops the bus to 400 kHz (ADS1115 max). Every transfer is
 * timeout-bounded, so a missing/half-wired module returns false instead of wedging the +0 task.
 */
#ifndef HG_ADS1115_H
#define HG_ADS1115_H

#include <stdbool.h>
#include <stdint.h>
#include "hardware/i2c.h"

// Single-shot read of single-ended channel (0..3) vs GND. PGA ±4.096 V, 860 SPS. Returns false on any
// I2C error/timeout; on success *out = signed 16-bit conversion code.
bool ads1115_read(i2c_inst_t *i2c, uint8_t addr, uint8_t channel, int16_t *out);

#endif /* HG_ADS1115_H */
