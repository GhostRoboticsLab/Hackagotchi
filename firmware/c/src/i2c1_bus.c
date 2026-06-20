/* Hackagotchi — I2C1 one-time bring-up. Single owner (OLED on the dashboard task), no mutex. SPDX-License-Identifier: MIT */
#include "i2c1_bus.h"
#include <pico/stdlib.h>

static bool s_inited;

void i2c1_bus_init(void) {
    if (s_inited) return;
    i2c_init(I2C1_BUS_INST, I2C1_BUS_HZ);
    gpio_set_function(I2C1_BUS_SDA, GPIO_FUNC_I2C);
    gpio_set_function(I2C1_BUS_SCL, GPIO_FUNC_I2C);
    gpio_pull_up(I2C1_BUS_SDA);   // weak internal pulls; FM+ leans on the board's external pullups
    gpio_pull_up(I2C1_BUS_SCL);
    s_inited = true;
}
