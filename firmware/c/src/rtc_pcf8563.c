/* Hackagotchi — PCF8563 RTC driver (I2C1 @ 0x51, bus-mutexed). SPDX-License-Identifier: MIT */
#include "rtc_pcf8563.h"
#include "i2c1_bus.h"

#define RTC_ADDR    0x51u
#define RTC_REG_SEC 0x02u   // VL_seconds; then min, hour, day, weekday, century_month, year
#define LOCK_MS     100u    // bound the wait on the OLED's ~23 ms bursts; never block the recorder long
#define IO_US       4000    // per-transfer I2C timeout so a missing/stuck RTC can't hang the SD task

static inline uint8_t bcd2dec(uint8_t v) { return (uint8_t)((v >> 4) * 10u + (v & 0x0Fu)); }
static inline uint8_t dec2bcd(uint8_t v) { return (uint8_t)(((v / 10u) << 4) | (v % 10u)); }

bool rtc_pcf8563_present(void) {
    uint8_t reg = RTC_REG_SEC, b;
    if (!i2c1_bus_lock(LOCK_MS)) return false;
    int w = i2c_write_timeout_us(I2C1_BUS_INST, RTC_ADDR, &reg, 1, true, IO_US);
    int r = (w == 1) ? i2c_read_timeout_us(I2C1_BUS_INST, RTC_ADDR, &b, 1, false, IO_US) : -1;
    i2c1_bus_unlock();
    return r == 1;
}

bool rtc_pcf8563_read(rtc_dt_t *out) {
    if (!out) return false;
    uint8_t reg = RTC_REG_SEC, raw[7];
    if (!i2c1_bus_lock(LOCK_MS)) return false;
    int w = i2c_write_timeout_us(I2C1_BUS_INST, RTC_ADDR, &reg, 1, true, IO_US);
    int r = (w == 1) ? i2c_read_timeout_us(I2C1_BUS_INST, RTC_ADDR, raw, 7, false, IO_US) : -1;
    i2c1_bus_unlock();
    if (r != 7) return false;
    if (raw[0] & 0x80u) return false;                    // VL set => clock integrity lost => untrusted
    out->sec  = bcd2dec(raw[0] & 0x7Fu);
    out->min  = bcd2dec(raw[1] & 0x7Fu);
    out->hour = bcd2dec(raw[2] & 0x3Fu);
    out->day  = bcd2dec(raw[3] & 0x3Fu);
    /* raw[4] = weekday (unused) */
    out->mon  = bcd2dec(raw[5] & 0x1Fu);
    out->year = (uint16_t)(2000u + bcd2dec(raw[6]));     // 2000-2099 (century bit ignored)
    return true;
}

bool rtc_pcf8563_set(const rtc_dt_t *t) {
    if (!t) return false;
    uint8_t buf[8];
    buf[0] = RTC_REG_SEC;
    buf[1] = dec2bcd(t->sec) & 0x7Fu;                    // VL=0 here clears the low-voltage flag
    buf[2] = dec2bcd(t->min) & 0x7Fu;
    buf[3] = dec2bcd(t->hour) & 0x3Fu;
    buf[4] = dec2bcd(t->day) & 0x3Fu;
    buf[5] = 0;                                          // weekday (unused by us)
    buf[6] = dec2bcd(t->mon) & 0x1Fu;                    // century bit (7) = 0 => 20xx
    buf[7] = dec2bcd((uint8_t)(t->year % 100u));
    if (!i2c1_bus_lock(LOCK_MS)) return false;
    int w = i2c_write_timeout_us(I2C1_BUS_INST, RTC_ADDR, buf, sizeof buf, false, IO_US * 2);
    i2c1_bus_unlock();
    return w == (int)sizeof buf;
}
