/* Hackagotchi — ADS1115 I2C ADC driver. SPDX-License-Identifier: MIT  (see header) */
#include "ads1115.h"
#include <pico/stdlib.h>

#define ADS_REG_CONV   0x00u
#define ADS_REG_CONF   0x01u
#define ADS_TIMEOUT_US 2000

bool ads1115_read(i2c_inst_t *i2c, uint8_t addr, uint8_t channel, int16_t *out) {
    if (!out || channel > 3u) return false;

    // OS=1 (start) | MUX=100+ch (AINx vs GND) | PGA=001 (±4.096V) | MODE=1 (single-shot)
    // | DR=111 (860 SPS) | COMP_QUE=11 (comparator off).
    uint16_t mux = (uint16_t)(0x4u | channel);
    uint16_t cfg = (uint16_t)(0x8000u | (uint16_t)(mux << 12) | (0x1u << 9) | (0x1u << 8) | (0x7u << 5) | 0x3u);

    uint8_t w[3] = { ADS_REG_CONF, (uint8_t)(cfg >> 8), (uint8_t)(cfg & 0xFFu) };
    if (i2c_write_timeout_us(i2c, addr, w, 3, false, ADS_TIMEOUT_US) != 3) return false;

    // 860 SPS -> ~1.16 ms conversion; wait with margin. sleep_us busy-waits but is fully preemptible on the
    // +0 task (it never masks IRQs), so the DAP/USB path is unaffected (R1).
    sleep_us(1500);

    uint8_t reg = ADS_REG_CONV;
    if (i2c_write_timeout_us(i2c, addr, &reg, 1, true, ADS_TIMEOUT_US) != 1) return false;
    uint8_t rd[2];
    if (i2c_read_timeout_us(i2c, addr, rd, 2, false, ADS_TIMEOUT_US) != 2) return false;

    *out = (int16_t)(((uint16_t)rd[0] << 8) | (uint16_t)rd[1]);
    return true;
}
