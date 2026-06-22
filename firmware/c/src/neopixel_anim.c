/* Hackagotchi — NeoPixel mood animation (pure, host-tested). SPDX-License-Identifier: MIT  (see header) */
#include "neopixel_anim.h"

static inline uint32_t urgb(uint8_t r, uint8_t g, uint8_t b) {
    return ((uint32_t)r << 8) | ((uint32_t)g << 16) | (uint32_t)b;   // WS2812 GRB packing
}
static inline uint8_t scale8(uint8_t v, uint8_t s) {
    return (uint8_t)(((uint16_t)v * (uint16_t)s) / 255u);
}

uint8_t np_tri(uint32_t now_ms, uint32_t period_ms) {
    if (period_ms < 2u) return 0;
    uint32_t p = now_ms % period_ms;
    uint32_t h = period_ms / 2u;
    uint32_t v = (p < h) ? (p * 255u / h) : (255u - (p - h) * 255u / h);
    return (uint8_t)v;
}

// breathing brightness with a floor, so a "calm" mood never goes fully dark
static uint8_t breathe(uint32_t now_ms, uint32_t period_ms, uint8_t floor) {
    uint8_t t = np_tri(now_ms, period_ms);
    uint16_t span = (uint16_t)(255u - floor);
    return (uint8_t)(floor + (uint16_t)((uint16_t)t * span / 255u));
}

// classic 0..255 colour wheel -> rgb
static void wheel(uint8_t pos, uint8_t *r, uint8_t *g, uint8_t *b) {
    pos = (uint8_t)(255u - pos);
    if (pos < 85u)        { *r = (uint8_t)(255u - pos * 3u); *g = 0;                       *b = (uint8_t)(pos * 3u); }
    else if (pos < 170u)  { pos = (uint8_t)(pos - 85u);  *r = 0;                       *g = (uint8_t)(pos * 3u); *b = (uint8_t)(255u - pos * 3u); }
    else                  { pos = (uint8_t)(pos - 170u); *r = (uint8_t)(pos * 3u);     *g = (uint8_t)(255u - pos * 3u); *b = 0; }
}

void np_anim_render(uint32_t *out, int count, int mood, uint32_t now_ms, uint8_t intensity) {
    if (!out || count <= 0) return;
    uint32_t span = (uint32_t)(count > 0 ? count : 1);
    for (int i = 0; i < count; i++) {
        uint8_t r = 0, g = 0, b = 0, br;
        switch (mood) {
        case NP_MOOD_IDLE:
            br = breathe(now_ms + (uint32_t)i * 120u, 3400u, 40u);
            r = 0; g = scale8(150u, br); b = scale8(200u, br);
            break;
        case NP_MOOD_RX: {
            uint8_t t = np_tri(now_ms + (uint32_t)i * (700u / span), 700u);   // pulse travels down the chain
            r = 0; g = scale8(255u, t); b = scale8(30u, t);
            break;
        }
        case NP_MOOD_WARN:
            br = breathe(now_ms, 600u, 30u);
            r = scale8(255u, br); g = scale8(95u, br); b = 0;
            break;
        case NP_MOOD_FAULT:
            br = breathe(now_ms, 360u, 35u);
            r = scale8(255u, br); g = 0; b = 0;
            break;
        case NP_MOOD_PET:
            br = breathe(now_ms, 900u, 80u);
            r = scale8(255u, br); g = scale8(40u, br); b = scale8(90u, br);
            break;
        case NP_MOOD_RAINBOW: {
            uint8_t pos = (uint8_t)(((now_ms / 8u) + (uint32_t)i * (256u / span)) & 0xFFu);
            wheel(pos, &r, &g, &b);
            break;
        }
        case NP_MOOD_OFF:
        default:
            break;
        }
        r = scale8(r, intensity); g = scale8(g, intensity); b = scale8(b, intensity);
        out[i] = urgb(r, g, b);
    }
}
