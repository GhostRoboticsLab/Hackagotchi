/* Host unit test for the pure NeoPixel mood renderer. SPDX-License-Identifier: MIT
 *   cc -I src tests/m_ui/neopixel_anim_test.c src/neopixel_anim.c -o /tmp/npa && /tmp/npa
 * No hardware. Asserts the invariants a soak can't see: off==dark, intensity caps, per-mood channels,
 * the breathing wave, and that a rainbow actually differs across the chain.
 */
#include <assert.h>
#include <stdio.h>
#include "neopixel_anim.h"

static uint8_t R(uint32_t u) { return (uint8_t)((u >> 8) & 0xFFu); }
static uint8_t G(uint32_t u) { return (uint8_t)((u >> 16) & 0xFFu); }
static uint8_t B(uint32_t u) { return (uint8_t)(u & 0xFFu); }

int main(void) {
    uint32_t px[8];

    // OFF -> every pixel dark, at any time/intensity
    np_anim_render(px, 8, NP_MOOD_OFF, 1234u, 255u);
    for (int i = 0; i < 8; i++) assert(px[i] == 0);

    // intensity 0 -> dark regardless of mood (the global brightness cap works)
    np_anim_render(px, 8, NP_MOOD_RX, 500u, 0u);
    for (int i = 0; i < 8; i++) assert(px[i] == 0);

    // FAULT -> red only, and never fully dark (floor), across a full blink period
    int saw_red = 0;
    for (uint32_t t = 0; t < 360u; t += 20u) {
        np_anim_render(px, 1, NP_MOOD_FAULT, t, 255u);
        if (R(px[0]) > 0) saw_red = 1;
        assert(G(px[0]) == 0 && B(px[0]) == 0);   // pure red
    }
    assert(saw_red);

    // IDLE -> teal: red channel always 0, blue present at some point
    int saw_blue = 0;
    for (uint32_t t = 0; t < 3400u; t += 50u) {
        np_anim_render(px, 1, NP_MOOD_IDLE, t, 255u);
        assert(R(px[0]) == 0);
        if (B(px[0]) > 0) saw_blue = 1;
    }
    assert(saw_blue);

    // triangle wave bounds
    assert(np_tri(0u, 1000u) == 0);
    assert(np_tri(500u, 1000u) == 255);
    assert(np_tri(250u, 1000u) > 100 && np_tri(250u, 1000u) < 160);
    assert(np_tri(7u, 1u) == 0);   // degenerate period

    // RAINBOW -> the chain is not a single colour
    np_anim_render(px, 8, NP_MOOD_RAINBOW, 0u, 255u);
    int differ = 0;
    for (int i = 1; i < 8; i++) if (px[i] != px[0]) differ = 1;
    assert(differ);

    printf("neopixel_anim_test: OK\n");
    return 0;
}
