/*
 * Hackagotchi — user-feedback HAL (WS2812 NeoPixel chain + buzzer). SPDX-License-Identifier: MIT  (see feedback.h)
 *
 * v1.2 generalises the single onboard pixel to a CHAIN of HG_NEOPIXEL_COUNT WS2812s on GP12 (onboard =
 * index 0, then an external strip soldered to the GP12 castellation). Default HG_NEOPIXEL_COUNT=1 keeps
 * v1.1 behaviour exactly (one pixel, manual status colour). With a strip, callers can drive an animated
 * MOOD (neopixel_anim.c). Everything is still latched cross-task and serviced from the +0 SD task
 * (feedback_service) — the CPU only pushes words to the PIO, never blocking the DAP/USB path (R1).
 */
#include "feedback.h"
#include "neopixel_anim.h"

#include "pico/stdlib.h"
#include "hardware/pwm.h"
#include "hardware/clocks.h"
#include "hardware/pio.h"
#include "ws2812.pio.h"

#define BUZZER        29u   // D3 passive piezo (PWM)
#define NEOPIXEL_PIN  12u   // XIAO onboard WS2812 data (external strip chains off this line)
#define NEOPIXEL_PWR  11u   // XIAO NeoPixel power-enable (onboard pixel only; power a strip from the 5V pad)
#define NP_BRIGHT     0x30u // modest level so a single bright pixel isn't glaring

#ifndef HG_NEOPIXEL_COUNT
#define HG_NEOPIXEL_COUNT 1 // onboard pixel only (v1.1 default); set >1 when an external strip is soldered
#endif
#define NPX HG_NEOPIXEL_COUNT

// NeoPixel on pio1 (SWD owns pio0). Set once in feedback_init.
static PIO  s_np_pio = pio1;
static uint s_np_sm  = 0;
static bool s_np_ok  = false;

static uint32_t s_pixels[NPX];      // current colours (urgb GRB-packed)
static uint32_t s_shown[NPX];       // last frame pushed to the strip (push only on change)
static bool     s_manual_dirty = true;

// mode: MANUAL (feedback_pixel/fill/led) vs ANIM (feedback_mood)
enum { FB_MANUAL = 0, FB_ANIM = 1 };
static volatile int     s_mode = FB_MANUAL;
static volatile int     s_mood = -1;
static volatile uint8_t s_intensity = 200u;

// Cross-task request latches (each a single aligned store; consumed by feedback_service on the SD task).
static volatile uint32_t s_pixel_req = 0;   // bit31 pending | 24-bit colour -> pixel 0 (back-compat)
static volatile uint32_t s_fill_req  = 0;   // bit31 pending | 24-bit colour -> whole chain
static volatile uint32_t s_mood_req  = 0;   // bit31 pending | mood<<8 | intensity

// Pending beep request: (hz << 16) | ms, 0 = none.
static volatile uint32_t s_beep_req = 0;
static bool     s_beeping = false;
static uint32_t s_beep_off_ms = 0;

// Readback for HIL ({"q":"fb"}).
static volatile uint32_t s_beep_count = 0;
static volatile uint32_t s_last_color = 0;
uint32_t feedback_beep_count(void) { return s_beep_count; }
uint32_t feedback_color(void)      { return s_last_color; }   // packed urgb: (g<<16)|(r<<8)|b
bool     feedback_is_beeping(void) { return s_beeping; }
int      feedback_pixel_count(void){ return NPX; }
int      feedback_mood_get(void)   { return s_mode == FB_ANIM ? s_mood : -1; }

static inline uint32_t urgb(uint8_t r, uint8_t g, uint8_t b) {  // pack for the WS2812 (GRB) helper
    return ((uint32_t)r << 8) | ((uint32_t)g << 16) | (uint32_t)b;
}
static void np_show(void) {                                     // push the whole chain; PIO clocks it in HW
    if (!s_np_ok) return;
    for (int i = 0; i < NPX; i++) pio_sm_put_blocking(s_np_pio, s_np_sm, s_pixels[i] << 8u);
    for (int i = 0; i < NPX; i++) s_shown[i] = s_pixels[i];
}
static bool np_changed(void) {
    for (int i = 0; i < NPX; i++) if (s_pixels[i] != s_shown[i]) return true;
    return false;
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
    // NeoPixel: power the onboard pixel, then bring up the PIO SM and blank the chain.
    gpio_init(NEOPIXEL_PWR); gpio_set_dir(NEOPIXEL_PWR, GPIO_OUT); gpio_put(NEOPIXEL_PWR, 1);
    for (int i = 0; i < NPX; i++) { s_pixels[i] = 0; s_shown[i] = 0; }
    if (pio_can_add_program(s_np_pio, &ws2812_program)) {
        uint off = pio_add_program(s_np_pio, &ws2812_program);
        ws2812_program_init(s_np_pio, s_np_sm, off, NEOPIXEL_PIN, 800000.0f, false);
        s_np_ok = true;
        np_show();   // off
    }
}

void feedback_pixel(uint8_t r, uint8_t g, uint8_t b) {
    s_pixel_req = 0x80000000u | (urgb(r, g, b) & 0x00FFFFFFu);  // pending + color (pixel 0)
}

void feedback_fill(uint8_t r, uint8_t g, uint8_t b) {
    s_fill_req = 0x80000000u | (urgb(r, g, b) & 0x00FFFFFFu);   // pending + color (whole chain)
}

void feedback_mood(int mood, uint8_t intensity) {
    if (mood < 0) mood = 0;
    s_mood_req = 0x80000000u | ((uint32_t)((unsigned)mood & 0xFFu) << 8) | (uint32_t)intensity;
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
    // ---- pixel / fill / mood latches (manual sets switch out of anim mode) ----
    uint32_t fr = s_fill_req;
    if (fr & 0x80000000u) {
        s_fill_req = 0; uint32_t c = fr & 0x00FFFFFFu;
        for (int i = 0; i < NPX; i++) s_pixels[i] = c;
        s_mode = FB_MANUAL; s_last_color = c; s_manual_dirty = true;
    }
    uint32_t px = s_pixel_req;
    if (px & 0x80000000u) {
        s_pixel_req = 0; uint32_t c = px & 0x00FFFFFFu;
        s_pixels[0] = c;
        s_mode = FB_MANUAL; s_last_color = c; s_manual_dirty = true;
    }
    uint32_t mr = s_mood_req;
    if (mr & 0x80000000u) {
        s_mood_req = 0;
        s_mood = (int)((mr >> 8) & 0xFFu);
        s_intensity = (uint8_t)(mr & 0xFFu);
        s_mode = FB_ANIM;
    }

    if (s_mode == FB_ANIM) {
        np_anim_render(s_pixels, NPX, s_mood, now_ms, s_intensity);
        s_last_color = s_pixels[0];
        if (np_changed()) np_show();
    } else if (s_manual_dirty) {
        s_manual_dirty = false;
        np_show();
    }

    // ---- buzzer (edge-driven, unchanged from M3) ----
    uint32_t req = s_beep_req;
    if (req) {
        s_beep_req = 0;
        buzzer_on((uint16_t)(req >> 16));
        s_beep_off_ms = now_ms + (req & 0xFFFFu);
        s_beeping = true;
        s_beep_count++;
    }
    if (s_beeping && (int32_t)(now_ms - s_beep_off_ms) >= 0) {
        buzzer_off();
        s_beeping = false;
    }
}
