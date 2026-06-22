/* Host unit test for the pure button + joystick logic. SPDX-License-Identifier: MIT
 *   cc -I src tests/m_ui/input_logic_test.c src/input_logic.c -o /tmp/inp && /tmp/inp
 * No hardware. Verifies debounce, short vs long classification, bounce rejection, joystick deadzone +
 * dominant-axis decode, and one-event-per-flick edge detection.
 */
#include <assert.h>
#include <stdio.h>
#include "input_logic.h"

static void test_button(void) {
    btn_t b = {0};
    // press; not stable until the debounce window elapses
    assert(btn_update(&b, 1, 0u,  25u, 800u) == BTN_EV_NONE);
    assert(btn_update(&b, 1, 10u, 25u, 800u) == BTN_EV_NONE);
    int ev = btn_update(&b, 1, 30u, 25u, 800u);                 // 30 >= 25 -> commit DOWN
    assert((ev & BTN_EV_DOWN) && !(ev & BTN_EV_LONG));
    // release before the long threshold -> SHORT
    assert(btn_update(&b, 0, 100u, 25u, 800u) == BTN_EV_NONE);  // candidate up, not yet committed
    ev = btn_update(&b, 0, 130u, 25u, 800u);                    // commit UP
    assert((ev & BTN_EV_UP) && (ev & BTN_EV_SHORT) && !(ev & BTN_EV_LONG));

    // long press: LONG fires once while held, and release after a long hold yields no SHORT
    btn_t c = {0};
    btn_update(&c, 1, 0u, 25u, 800u);
    ev = btn_update(&c, 1, 30u, 25u, 800u);   assert(ev & BTN_EV_DOWN);
    ev = btn_update(&c, 1, 900u, 25u, 800u);  assert(ev & BTN_EV_LONG);     // held past 800 (t_press=30)
    ev = btn_update(&c, 1, 1000u, 25u, 800u); assert(!(ev & BTN_EV_LONG));  // only once
    btn_update(&c, 0, 1100u, 25u, 800u);
    ev = btn_update(&c, 0, 1130u, 25u, 800u);
    assert((ev & BTN_EV_UP) && !(ev & BTN_EV_SHORT));

    // bounce rejection: a blip shorter than the debounce window never commits a press
    btn_t d = {0};
    btn_update(&d, 1, 0u, 25u, 800u);
    assert(btn_update(&d, 0, 10u, 25u, 800u) == BTN_EV_NONE);
    assert(btn_update(&d, 0, 40u, 25u, 800u) == BTN_EV_NONE);   // settled up; never went down
}

static void test_joy(void) {
    const int C = 13200, D = 6000;
    assert(joy_dir(C, C, C, D) == JOY_C);
    assert(joy_dir(C, C + 7000, C, D) == JOY_UP);
    assert(joy_dir(C, C - 7000, C, D) == JOY_DOWN);
    assert(joy_dir(C + 7000, C, C, D) == JOY_RIGHT);
    assert(joy_dir(C - 7000, C, C, D) == JOY_LEFT);
    assert(joy_dir(C + 3000, C + 1000, C, D) == JOY_C);   // inside the deadzone

    joy_edge_t e = {0};
    assert(joy_edge(&e, JOY_C) == JOY_C);
    assert(joy_edge(&e, JOY_UP) == JOY_UP);   // fresh C->UP fires
    assert(joy_edge(&e, JOY_UP) == JOY_C);    // held -> no repeat
    assert(joy_edge(&e, JOY_C) == JOY_C);
    assert(joy_edge(&e, JOY_DOWN) == JOY_DOWN);
}

int main(void) {
    test_button();
    test_joy();
    printf("input_logic_test: OK\n");
    return 0;
}
