/* Hackagotchi — on-device input (button + joystick) HW glue. SPDX-License-Identifier: MIT  (see header) */
#include "hg_input.h"
#include "input_logic.h"

#ifndef HG_BUTTON
#define HG_BUTTON 0
#endif
#ifndef HG_JOYSTICK
#define HG_JOYSTICK 0
#endif

#if HG_BUTTON || HG_JOYSTICK
#include "hackagotchi_dashboard.h"   // dash_nav_step / dash_pet (atomic intents)
#endif
#if HG_BUTTON
#include "feedback.h"                // chirp on a long-press pet
#endif
#ifndef HG_BUTTON_PIN
#define HG_BUTTON_PIN 16u            // freed onboard GREEN-LED GPIO (RED = GP17, reserved for a 2nd button)
#endif

#if HG_BUTTON || HG_JOYSTICK
#include <pico/stdlib.h>
#endif
#if HG_JOYSTICK
#include "ads1115.h"
#include "i2c1_bus.h"
#ifndef HG_JOY_ADDR
#define HG_JOY_ADDR 0x48u            // ADS1115 ADDR->GND
#endif
#ifndef HG_JOY_CH_X
#define HG_JOY_CH_X 0u               // joystick X on AIN0
#endif
#ifndef HG_JOY_CH_Y
#define HG_JOY_CH_Y 1u               // joystick Y on AIN1
#endif
// single-ended 3.3 V on the ±4.096 V FSR -> ~0..26400 codes; mid ~13200, deadzone ~6000.
#define HG_JOY_CENTER 13200
#define HG_JOY_DEAD   6000
#endif

static volatile uint32_t s_presses = 0;
static volatile int s_btn_down = 0;
static volatile int s_joy_ok = 0, s_joy_x = 0, s_joy_y = 0, s_joy_dir = JOY_C;

uint32_t hg_button_presses(void) { return s_presses; }
int hg_button_down(void) { return s_btn_down; }
int hg_joy_ok(void)  { return s_joy_ok; }
int hg_joy_x(void)   { return s_joy_x; }
int hg_joy_y(void)   { return s_joy_y; }
int hg_joy_dir(void) { return s_joy_dir; }

void hg_button_poll(uint32_t now_ms) {
#if HG_BUTTON
    static int inited = 0;
    static btn_t b;
    if (!inited) {
        gpio_init(HG_BUTTON_PIN);
        gpio_set_dir(HG_BUTTON_PIN, GPIO_IN);
        gpio_pull_up(HG_BUTTON_PIN);            // active-low: pressed pulls the pin to GND
        inited = 1;
    }
    int raw_down = gpio_get(HG_BUTTON_PIN) ? 0 : 1;
    s_btn_down = raw_down;
    int ev = btn_update(&b, raw_down, now_ms, 25u, 800u);
    if (ev & BTN_EV_SHORT) { dash_nav_step(+1); s_presses++; }       // tap  -> next screen
    if (ev & BTN_EV_LONG)  { dash_pet(); feedback_beep(1760, 80); }  // hold -> pet the cat
#else
    (void)now_ms;
#endif
}

void hg_joystick_poll(uint32_t now_ms) {
    (void)now_ms;
#if HG_JOYSTICK
    static joy_edge_t e;
    int16_t vx = 0, vy = 0;
    if (!ads1115_read(I2C1_BUS_INST, HG_JOY_ADDR, HG_JOY_CH_X, &vx) ||
        !ads1115_read(I2C1_BUS_INST, HG_JOY_ADDR, HG_JOY_CH_Y, &vy)) {
        s_joy_ok = 0;                                                // module absent/half-wired -> ignore
        return;
    }
    s_joy_ok = 1; s_joy_x = vx; s_joy_y = vy;
    int dir = joy_dir(vx, vy, HG_JOY_CENTER, HG_JOY_DEAD);
    s_joy_dir = dir;
    int edge = joy_edge(&e, dir);
    if (edge == JOY_UP)   dash_nav_step(-1);                         // flick up   -> previous screen
    if (edge == JOY_DOWN) dash_nav_step(+1);                         // flick down -> next screen
#endif
}
