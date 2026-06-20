/*
 * Hackagotchi — PCF8563 RTC (I2C1 @ 0x51). SPDX-License-Identifier: MIT
 *
 * Read/set wall-clock time for the black-box recorder's log stamps. Shares I2C1 with the OLED, so all
 * access goes through i2c1_bus_lock(). read() returns false when the time is not trustworthy (chip
 * absent, I2C error, or the VL low-voltage flag set after a power loss) -> recorder falls back to the
 * uptime "+Ns" stamp. set() writes the clock and clears VL.
 *
 * Register map (read from 0x02): VL_seconds, minutes, hours, days, weekdays, century_months, years
 * (all BCD; VL = bit7 of seconds; century = bit7 of months).
 */
#ifndef HACKAGOTCHI_RTC_PCF8563_H
#define HACKAGOTCHI_RTC_PCF8563_H

#include <stdbool.h>
#include <stdint.h>

typedef struct { uint16_t year; uint8_t mon, day, hour, min, sec; } rtc_dt_t;

bool rtc_pcf8563_present(void);            // does 0x51 ACK on the bus?
bool rtc_pcf8563_read(rtc_dt_t *out);      // false if absent / I2C error / VL set (time not trusted)
bool rtc_pcf8563_set(const rtc_dt_t *t);   // set the clock (clears the VL low-voltage flag)

#endif /* HACKAGOTCHI_RTC_PCF8563_H */
