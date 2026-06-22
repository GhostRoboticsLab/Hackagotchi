/*
 * Hackagotchi — NeoPixel mood animation (PURE: no hardware deps). SPDX-License-Identifier: MIT
 *
 * Renders a chain of WS2812 pixels for a "mood" at a given time. A deterministic function of
 * (mood, now_ms, intensity, count) — no hardware, no globals — so tests/m_ui/neopixel_anim_test.c can
 * assert exact behaviour with no bench. feedback.c calls this from the +0 SD task and pushes the result
 * to the PIO (R1-safe). Output packing matches feedback.c's WS2812 helper: urgb = (g<<16)|(r<<8)|b.
 */
#ifndef HG_NEOPIXEL_ANIM_H
#define HG_NEOPIXEL_ANIM_H

#include <stdint.h>

enum {
    NP_MOOD_OFF = 0,   // dark
    NP_MOOD_IDLE,      // calm teal breathing (logging, no recent traffic)
    NP_MOOD_RX,        // green pulse travelling down the chain (recent target traffic)
    NP_MOOD_WARN,      // amber pulse
    NP_MOOD_FAULT,     // red fast blink (wedge / SD fault)
    NP_MOOD_PET,       // warm pink pulse (companion interaction)
    NP_MOOD_RAINBOW,   // hue rotation (demo / "alive")
    NP_MOOD__COUNT
};

// Render `count` pixels for `mood` at `now_ms`. `intensity` (0..255) is a global brightness cap.
// out[] entries are urgb-packed = (g<<16)|(r<<8)|b. No-op if out==NULL or count<=0.
void np_anim_render(uint32_t *out, int count, int mood, uint32_t now_ms, uint8_t intensity);

// Triangle wave 0..255 over period_ms (exposed for tests). Returns 0 if period_ms < 2.
uint8_t np_tri(uint32_t now_ms, uint32_t period_ms);

#endif /* HG_NEOPIXEL_ANIM_H */
