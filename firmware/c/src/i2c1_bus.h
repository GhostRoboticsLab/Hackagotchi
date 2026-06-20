/*
 * Hackagotchi — shared I2C1 bus. SPDX-License-Identifier: MIT
 *
 * GP6 SDA / GP7 SCL @ 400 kHz. The OLED (0x3C, DASH task) and the PCF8563 RTC (0x51, SD/recorder task)
 * share this bus from DIFFERENT FreeRTOS tasks, so every transaction MUST hold the bus mutex. Init is
 * idempotent and done once from main() before the scheduler starts, so the mutex exists before any
 * task takes it.
 */
#ifndef HACKAGOTCHI_I2C1_BUS_H
#define HACKAGOTCHI_I2C1_BUS_H

#include <stdbool.h>
#include <stdint.h>
#include "hardware/i2c.h"

#define I2C1_BUS_INST i2c1
#define I2C1_BUS_SDA  6u
#define I2C1_BUS_SCL  7u
#define I2C1_BUS_HZ   400000u

void i2c1_bus_init(void);                 // idempotent: i2c_init + gpio funcs + pullups + create mutex
bool i2c1_bus_lock(uint32_t timeout_ms);  // take the bus; false if not acquired (caller must skip I/O)
void i2c1_bus_unlock(void);

#endif /* HACKAGOTCHI_I2C1_BUS_H */
