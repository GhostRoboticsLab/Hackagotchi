/*
 * Hackagotchi — M3 user-feedback HAL (NeoPixel status LED + buzzer). SPDX-License-Identifier: MIT  (see feedback.h)
 */
#include "feedback.h"

#include "pico/stdlib.h"
#include "hardware/pwm.h"
#include "hardware/clocks.h"
#include "hardware/pio.h"
#include "ws2812.pio.h"

#define BUZZER        29u   // D3 passive piezo (PWM)
#define NEOPIXEL_PIN  12u   // XIAO onboard WS2812 data
#define NEOPIXEL_PWR  11u   // XIAO NeoPixel power-enable (drive HIGH to power the pixel)
#define NP_BRIGHT     0x30u // modest level so a single bright pixel isn't glaring

// NeoPixel on pio1 (SWD owns pio0). Set once in feedback_init.
static PIO  s_np_pio = pio1;
static uint s_np_sm  = 0;
static bool s_np_ok  = false;

// Pending pixel request: bit31 = pending, low 24 = urgb (0x00GGRRBB). One 32-bit slot so a cross-task
// latch is a single aligned store; consumed (cleared) by feedback_service in the SD task.
static volatile uint32_t s_pixel_req = 0;

// Pending beep request: (hz << 16) | ms, 0 = none. Same single-slot atomic latch.
static volatile uint32_t s_beep_req = 0;
static bool     s_beeping = false;
static uint32_t s_beep_off_ms = 0;

static inline uint32_t urgb(uint8_t r, uint8_t g, uint8_t b) {  // pack for the WS2812 (GRB) helper
    return ((uint32_t)r << 8) | ((uint32_t)g << 16) | (uint32_t)b;
}
static inline void np_put(uint32_t u24) {                       // push one pixel; PIO clocks it in HW
    if (s_np_ok) pio_sm_put_blocking(s_np_pio, s_np_sm, u24 << 8u);
}

static void buzzer_on(uint16_t hz) {
    uint slice = pwm_gpio_to_slice_num(BUZZER);
    uint chan  = pwm_gpio_to_channel(BUZZER);
    const float div = 64.0f;                                    // keeps wrap in 16 bits across 50..12000 Hz
    uint32_t wrap = (uint32_t)((float)clock_get_hz(clk_sys) / (div * (float)hz));
    if (wrap < 2u) wrap = 2u;
    if (wrap > 65535u) wrap = 65535u;
    pwm_set_clkdiv(slice, div);
    pwm_set_wrap(slice, (uint16_t)wrap);
    pwm_set_chan_level(slice, chan, (uint16_t)(wrap / 2u));     // 50% duty
    pwm_set_enabled(slice, true);
}
static void buzzer_off(void) { pwm_set_enabled(pwm_gpio_to_slice_num(BUZZER), false); }

void feedback_init(void) {
    // Buzzer: PWM, silent.
    gpio_set_function(BUZZER, GPIO_FUNC_PWM);
    buzzer_off();
    // NeoPixel: power it, then bring up the PIO SM and blank it.
    gpio_init(NEOPIXEL_PWR); gpio_set_dir(NEOPIXEL_PWR, GPIO_OUT); gpio_put(NEOPIXEL_PWR, 1);
    if (pio_can_add_program(s_np_pio, &ws2812_program)) {
        uint off = pio_add_program(s_np_pio, &ws2812_program);
        ws2812_program_init(s_np_pio, s_np_sm, off, NEOPIXEL_PIN, 800000.0f, false);
        s_np_ok = true;
        np_put(0);   // off
    }
}

void feedback_pixel(uint8_t r, uint8_t g, uint8_t b) {
    s_pixel_req = 0x80000000u | (urgb(r, g, b) & 0x00FFFFFFu);  // pending + color
}

// Convenience colour mapping for the {"q":"led"} test command + simple status use. red/green -> the
// NeoPixel (the onboard RGB on GP16/17 proved an unreliable status channel — see feedback.h Finding M3-1).
void feedback_led(bool red, bool green) {
    if (red && green) feedback_pixel(NP_BRIGHT, NP_BRIGHT / 2u, 0);   // amber
    else if (red)     feedback_pixel(NP_BRIGHT, 0, 0);                // red
    else if (green)   feedback_pixel(0, NP_BRIGHT, 0);                // green
    else              feedback_pixel(0, 0, 0);                        // off
}

void feedback_beep(uint16_t hz, uint16_t ms) {
    if (hz < 50u)    hz = 50u;
    if (hz > 12000u) hz = 12000u;
    if (ms < 1u)     ms = 1u;
    if (ms > 2000u)  ms = 2000u;
    s_beep_req = ((uint32_t)hz << 16) | (uint32_t)ms;
}

void feedback_service(uint32_t now_ms) {
    uint32_t px = s_pixel_req;
    if (px & 0x80000000u) { s_pixel_req = 0; np_put(px & 0x00FFFFFFu); }

    uint32_t req = s_beep_req;
    if (req) {
        s_beep_req = 0;
        buzzer_on((uint16_t)(req >> 16));
        s_beep_off_ms = now_ms + (req & 0xFFFFu);
        s_beeping = true;
    }
    if (s_beeping && (int32_t)(now_ms - s_beep_off_ms) >= 0) {
        buzzer_off();
        s_beeping = false;
    }
}
