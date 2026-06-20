/*
 * Hackagotchi — M3 user-feedback HAL (status LEDs + buzzer). SPDX-License-Identifier: MIT
 *
 * The XIAO RP2040's only physical button (GP27) and one LED (GP26) were consumed by the Gate-1 SWD
 * remap (GP27=SWDIO, GP26=SWCLK), so on-device INPUT is auto-cycle + CDC1 control. OUTPUT survives:
 *   - NeoPixel STATUS LED = GP12 data + GP11 power (XIAO onboard WS2812) — the colour status indicator
 *   - BUZZER              = GP29 (D3) passive piezo, PWM tone           — the audible alert channel
 *   (BLUE GP25 is the probe's USB-connected LED — owned by usb_thread, NOT touched here.)
 *
 * M3.0 HW-RECONCILIATION FINDING (HIL, operator-observed): the buzzer works perfectly. The tiny onboard
 * RGB on GP16/GP17 is NOT a dependable status channel — the observed colour didn't match the nominal
 * R=17/G=16 mapping and it competes with the probe's GP25 blue USB-heartbeat. So M3 drives the bright,
 * fully colour-addressable onboard WS2812 NeoPixel (GP12/GP11) instead, via PIO (the SM clocks the
 * 800 kHz waveform in HARDWARE — the CPU only pushes 1 word, never blocking/masking IRQs → R1-safe).
 *
 * Everything here is NON-BLOCKING and serviced from the LOW-priority SD task (idle+0, below DAP), so a
 * beep dwell or pixel write can never sit on the DAP/USB hot path (R1). Callers just latch a request;
 * feedback_service() (called each SD-task tick) starts/stops the tone and pushes the pixel colour.
 */
#ifndef HACKAGOTCHI_FEEDBACK_H
#define HACKAGOTCHI_FEEDBACK_H

#include <stdint.h>
#include <stdbool.h>

// Bring up the LED GPIOs + the buzzer PWM slice (silent). Call once in main() before the scheduler.
void feedback_init(void);

// Service the pending beep + LED state. Call every SD-task loop iteration with the current ms clock.
void feedback_service(uint32_t now_ms);

// Latch a non-blocking beep request (started/stopped by feedback_service). hz clamped 50..12000,
// ms clamped 1..2000. Safe to call from any task (single 32-bit store).
void feedback_beep(uint16_t hz, uint16_t ms);

// Set the NeoPixel to a convenience colour from red/green flags (off / red / green / amber). Safe to
// call from any task (latches a request serviced by feedback_service).
void feedback_led(bool red, bool green);

// Set the NeoPixel to an arbitrary RGB colour (0..255 each; keep modest — one pixel is bright). Safe
// to call from any task.
void feedback_pixel(uint8_t r, uint8_t g, uint8_t b);

#endif // HACKAGOTCHI_FEEDBACK_H
