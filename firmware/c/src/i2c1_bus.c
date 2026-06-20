/* Hackagotchi — shared I2C1 bus (mutex + one-time bring-up). SPDX-License-Identifier: MIT */
#include "i2c1_bus.h"
#include <pico/stdlib.h>
#include "FreeRTOS.h"
#include "semphr.h"

static SemaphoreHandle_t s_mtx;
static bool s_inited;

void i2c1_bus_init(void) {
    if (s_inited) return;
    i2c_init(I2C1_BUS_INST, I2C1_BUS_HZ);
    gpio_set_function(I2C1_BUS_SDA, GPIO_FUNC_I2C);
    gpio_set_function(I2C1_BUS_SCL, GPIO_FUNC_I2C);
    gpio_pull_up(I2C1_BUS_SDA);
    gpio_pull_up(I2C1_BUS_SCL);
    s_mtx = xSemaphoreCreateMutex();   // priority-inheritance mutex (recursive not needed)
    s_inited = true;
}

bool i2c1_bus_lock(uint32_t timeout_ms) {
    if (!s_mtx) return false;           // init must run before any task locks; degrade safely if not
    return xSemaphoreTake(s_mtx, pdMS_TO_TICKS(timeout_ms)) == pdTRUE;
}

void i2c1_bus_unlock(void) {
    if (s_mtx) xSemaphoreGive(s_mtx);
}
