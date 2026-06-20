/*
 * Hackagotchi — I2C1 bus bring-up. SPDX-License-Identifier: MIT
 *
 * GP6 SDA / GP7 SCL. After the RTC was dropped the OLED (0x3C) is the SOLE device on this bus and the
 * dashboard task is its ONLY user — there is no cross-task sharing, so NO mutex: the task owns the bus
 * outright. Run at Fast-mode Plus (1 MHz) for a snappier full-frame flush (~1024 B: ~23 ms @ 400 kHz ->
 * ~9 ms @ 1 MHz). FM+ leans on the Seeed expansion board's external pullups (the internal pulls are far
 * too weak at 1 MHz); HIL-proven via the show-success counter (panel still ACKs) + a visual integrity
 * check — fall back to 400000u if a board's pullups can't sustain 1 MHz. Init is idempotent, done once.
 */
#ifndef HACKAGOTCHI_I2C1_BUS_H
#define HACKAGOTCHI_I2C1_BUS_H

#include "hardware/i2c.h"

#define I2C1_BUS_INST i2c1
#define I2C1_BUS_SDA  6u
#define I2C1_BUS_SCL  7u
#define I2C1_BUS_HZ   1000000u   // Fast-mode Plus; was 400000u (Fast-mode) while shared with the RTC

void i2c1_bus_init(void);        // idempotent: i2c_init + gpio funcs + pullups (no mutex — single owner)

#endif /* HACKAGOTCHI_I2C1_BUS_H */
