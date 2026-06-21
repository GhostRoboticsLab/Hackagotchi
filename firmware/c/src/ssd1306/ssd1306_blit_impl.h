/*
 * Hackagotchi — 1-bit sprite blit CORE. SPDX-License-Identifier: MIT
 *
 * The pure, hardware-free heart of ssd1306_blit() (M-UI-1, the UI-overhaul enabler). Kept in its own
 * pico-free header so a host unit test (tests/m_ui/blit_test.c) can verify the bit-packing math with no
 * panel and no toolchain — exactly how recorder.c is host-tested.
 *
 * ONE packing for both framebuffer AND sprites (byte-identical to ssd1306 draw_pixel, ssd1306.c:153):
 *   byte = buf[x + W*(y>>3)],  bit = (y & 7),  bit0 = TOPMOST pixel of the 8-px page,  1 = lit.
 * A sprite of sw columns x sh rows is sw * ceil(sh/8) bytes, column-major page-rows:
 *   spr[col + sw*(row>>3)], bit (row&7).  So a 24x24 sprite = 24*3 = 72 bytes, FLASH-resident (const).
 *
 * Blitting is PER-PIXEL and FULLY CLIPPED (x/y may be negative or run past the panel): it can never
 * index outside buf[0 .. W*(H>>3)-1]. This is the OOB-corruption guard a raw per-column byte-OR lacks
 * (the feasibility must-fix): draw_pixel clips, so this matches it. Set sprite bits act; CLEAR sprite
 * bits never touch the destination (1-bit transparency) — so OR preserves the background under the
 * sprite's empty pixels, ANDNOT punches holes, XOR flashes/inverts.
 *
 * Cost: a 24x24 sprite is at most 24*24 = 576 clipped bit-ops — trivial at idle priority / 4 Hz, no
 * floats. A byte-aligned fast path is a deliberate non-goal (correctness + clipping over micro-speed).
 */
#ifndef HG_SSD1306_BLIT_IMPL_H
#define HG_SSD1306_BLIT_IMPL_H

#include <stdint.h>

enum { HG_BLIT_OR = 0, HG_BLIT_ANDNOT = 1, HG_BLIT_XOR = 2 };

// Set/clear/flip ONE pixel, clipped. The only place that touches buf — so OOB is impossible by construction.
static inline void hg_blit_px(uint8_t *buf, int W, int H, int x, int y, int op) {
    if (x < 0 || y < 0 || x >= W || y >= H) return;     // clip — never index outside the framebuffer
    uint8_t *cell = &buf[x + W * (y >> 3)];
    uint8_t mask  = (uint8_t)(1u << (y & 7));
    if (op == HG_BLIT_ANDNOT)   *cell &= (uint8_t)~mask;
    else if (op == HG_BLIT_XOR) *cell ^= mask;
    else                        *cell |= mask;          // HG_BLIT_OR (default)
}

// Blit a packed 1-bit sprite into a 1-bit framebuffer at (x,y) with op. buf is W x H (H a multiple of 8).
static inline void hg_blit_into(uint8_t *buf, int W, int H,
                                const uint8_t *spr, int sw, int sh,
                                int x, int y, int op) {
    if (!buf || !spr || sw <= 0 || sh <= 0) return;
    int pages = (sh + 7) >> 3;
    for (int c = 0; c < sw; c++) {
        for (int p = 0; p < pages; p++) {
            uint8_t bits = spr[c + sw * p];
            if (!bits) continue;                        // whole sprite-page-column transparent
            int row0 = p << 3;
            for (int b = 0; b < 8; b++) {
                int row = row0 + b;
                if (row >= sh) break;                   // ragged bottom page
                if (bits & (1u << b)) hg_blit_px(buf, W, H, x + c, y + row, op);
            }
        }
    }
}

#endif // HG_SSD1306_BLIT_IMPL_H
