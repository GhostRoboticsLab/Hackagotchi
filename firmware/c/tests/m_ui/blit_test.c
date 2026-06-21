/*
 * Host unit test for the 1-bit sprite blit core (src/ssd1306/ssd1306_blit_impl.h) — the SAME header the
 * firmware compiles into ssd1306_blit(). SPDX-License-Identifier: MIT
 *
 * Pass/fail via an explicit CHECK() (NOT assert(), which no-ops under -DNDEBUG and would fake a PASS).
 * Proves the load-bearing claims of M-UI-1: bit-packing matches draw_pixel, the non-8-aligned cross-page
 * shift is correct, ANDNOT punches holes, XOR is its own inverse, and — the feasibility must-fix — an
 * off-panel blit NEVER corrupts a byte outside its clipped footprint (no OOB write).
 *
 * Build + run:
 *   cc -I firmware/c/src/ssd1306 -Wall -Wextra -O2 firmware/c/tests/m_ui/blit_test.c -o /tmp/blit_test
 *   /tmp/blit_test
 * Verify-the-verifier (the harness MUST be able to FAIL / exit nonzero):
 *   cc -I firmware/c/src/ssd1306 -DBLIT_SELFTEST_BREAK -O2 .../blit_test.c -o /tmp/blit_bad && /tmp/blit_bad; echo $?
 */
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "ssd1306_blit_impl.h"

static int g_pass = 0, g_fail = 0;
#define CHECK(cond, msg) do { \
    if (cond) { g_pass++; } else { g_fail++; printf("  FAIL: %s\n", (msg)); } \
} while (0)

/* A tiny 16x16 framebuffer: W=16, H=16 -> 2 pages -> 32 bytes. buf[x + 16*(y>>3)], bit (y&7). */
#define W 16
#define H 16
#define BUFSZ (W * (H / 8))

static int nonzero_bytes(const uint8_t *b, int n) {
    int c = 0; for (int i = 0; i < n; i++) if (b[i]) c++; return c;
}

int main(void) {
    uint8_t buf[BUFSZ];

    /* 1. aligned OR: exact byte layout matches the draw_pixel packing. */
    memset(buf, 0, BUFSZ);
    const uint8_t spr_2x8[] = { 0xFF, 0x0F };   /* col0 = rows0..7 lit; col1 = rows0..3 lit */
    hg_blit_into(buf, W, H, spr_2x8, 2, 8, 0, 0, HG_BLIT_OR);
    CHECK(buf[0] == 0xFF, "aligned OR col0");
    CHECK(buf[1] == 0x0F, "aligned OR col1");
    CHECK(nonzero_bytes(buf, BUFSZ) == 2, "aligned OR touched only 2 bytes");

#ifdef BLIT_SELFTEST_BREAK
    CHECK(buf[0] == 0x00, "INTENTIONAL FAIL (verify-the-verifier)");
#endif

    /* 2. non-8-aligned y: one column straddles two pages (the cross-page shift). */
    memset(buf, 0, BUFSZ);
    const uint8_t spr_1x8[] = { 0xFF };         /* 8 lit rows */
    hg_blit_into(buf, W, H, spr_1x8, 1, 8, 0, 3, HG_BLIT_OR);  /* dest rows 3..10 */
    CHECK(buf[0]  == 0xF8, "cross-page low (rows 3..7)");      /* bits 3..7 */
    CHECK(buf[W]  == 0x07, "cross-page high (rows 8..10)");    /* page1 bits 0..2 */

    /* 3. ANDNOT punches holes; clear sprite bits leave the background. */
    memset(buf, 0, BUFSZ);
    hg_blit_into(buf, W, H, spr_1x8, 1, 8, 0, 0, HG_BLIT_OR);  /* buf[0] = 0xFF */
    const uint8_t spr_hole[] = { 0x81 };                       /* bits 0 and 7 set */
    hg_blit_into(buf, W, H, spr_hole, 1, 8, 0, 0, HG_BLIT_ANDNOT);
    CHECK(buf[0] == 0x7E, "ANDNOT cleared rows 0 and 7 only");

    /* 4. XOR is its own inverse (flash on, flash off -> identity). */
    memset(buf, 0, BUFSZ);
    hg_blit_into(buf, W, H, spr_1x8, 1, 8, 5, 0, HG_BLIT_OR);
    uint8_t before5 = buf[5];
    hg_blit_into(buf, W, H, spr_1x8, 1, 8, 5, 0, HG_BLIT_XOR);
    hg_blit_into(buf, W, H, spr_1x8, 1, 8, 5, 0, HG_BLIT_XOR);
    CHECK(buf[5] == before5, "XOR twice == identity");

    /* 5a. OOB clip (right/bottom): an 8x8 all-lit sprite at x=12 spills cols 16..19 off-panel. */
    memset(buf, 0, BUFSZ);
    const uint8_t spr_8x8[] = { 0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF };
    hg_blit_into(buf, W, H, spr_8x8, 8, 8, 12, 0, HG_BLIT_OR);
    CHECK(buf[12]==0xFF && buf[13]==0xFF && buf[14]==0xFF && buf[15]==0xFF, "OOB right: in-bounds cols lit");
    CHECK(nonzero_bytes(buf, BUFSZ) == 4, "OOB right: exactly 4 bytes, no wrap/overrun");

    /* 5b. OOB clip (negative x): cols -3..4 -> only 0..4 land. */
    memset(buf, 0, BUFSZ);
    hg_blit_into(buf, W, H, spr_8x8, 8, 8, -3, 0, HG_BLIT_OR);
    CHECK(buf[0] && buf[4] && !buf[5], "OOB left: clipped to cols 0..4");
    CHECK(nonzero_bytes(buf, BUFSZ) == 5, "OOB left: exactly 5 bytes");

    /* 5c. fully off-panel writes nothing (canary: buffer stays pristine). */
    memset(buf, 0, BUFSZ);
    hg_blit_into(buf, W, H, spr_8x8, 8, 8, 100, 100, HG_BLIT_OR);
    hg_blit_into(buf, W, H, spr_8x8, 8, 8, -50, -50, HG_BLIT_OR);
    CHECK(nonzero_bytes(buf, BUFSZ) == 0, "fully off-panel is a no-op");

    if (g_fail == 0) { printf("PASS blit_test: %d checks\n", g_pass); return 0; }
    printf("FAIL blit_test: %d/%d failed\n", g_fail, g_pass + g_fail);
    return 1;
}
