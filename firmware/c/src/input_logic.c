/* Hackagotchi — on-device input logic (pure, host-tested). SPDX-License-Identifier: MIT  (see header) */
#include "input_logic.h"

int btn_update(btn_t *b, int raw_down, uint32_t now_ms, uint32_t debounce_ms, uint32_t long_ms) {
    int ev = BTN_EV_NONE;
    uint8_t raw = raw_down ? 1u : 0u;

    if (raw != b->cand) { b->cand = raw; b->t_change = now_ms; }       // candidate moved -> restart debounce

    if (b->cand != b->stable && (now_ms - b->t_change) >= debounce_ms) {
        b->stable = b->cand;                                          // commit the debounced level
        if (b->stable) { ev |= BTN_EV_DOWN; b->t_press = now_ms; b->long_fired = 0; }
        else {
            ev |= BTN_EV_UP;
            if (!b->long_fired) ev |= BTN_EV_SHORT;                   // released before the long threshold
        }
    }

    if (b->stable && !b->long_fired && (now_ms - b->t_press) >= long_ms) {
        b->long_fired = 1; ev |= BTN_EV_LONG;                        // fire LONG once while still held
    }
    return ev;
}

int joy_dir(int x, int y, int center, int dead) {
    int dx = x - center, dy = y - center;
    int ax = dx < 0 ? -dx : dx;
    int ay = dy < 0 ? -dy : dy;
    if (ay >= ax) { if (ay > dead) return dy > 0 ? JOY_UP : JOY_DOWN; }
    else          { if (ax > dead) return dx > 0 ? JOY_RIGHT : JOY_LEFT; }
    return JOY_C;
}

int joy_edge(joy_edge_t *e, int dir) {
    int out = (dir != JOY_C && dir != e->last) ? dir : JOY_C;
    e->last = dir;
    return out;
}
