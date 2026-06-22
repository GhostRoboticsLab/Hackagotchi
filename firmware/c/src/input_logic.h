/*
 * Hackagotchi — on-device input logic (PURE: button debounce + joystick decode). SPDX-License-Identifier: MIT
 *
 * No hardware deps — these are the testable FSMs behind hg_input.c. tests/m_ui/input_logic_test.c drives
 * them with synthetic time/levels. hg_input.c wires them to GP16 (button) and the ADS1115 (joystick) and
 * posts dashboard nav/pet intents. All callers run on the +0 tasks (never the DAP path).
 */
#ifndef HG_INPUT_LOGIC_H
#define HG_INPUT_LOGIC_H

#include <stdint.h>

/* ---- button: debounce + press classification ---- */
enum { BTN_EV_NONE = 0, BTN_EV_DOWN = 1, BTN_EV_UP = 2, BTN_EV_SHORT = 4, BTN_EV_LONG = 8 };

typedef struct {
    uint8_t  stable;       // committed debounced level (1 = pressed)
    uint8_t  cand;         // candidate level awaiting debounce
    uint8_t  long_fired;   // long-press already emitted for the current hold
    uint8_t  _pad;
    uint32_t t_change;     // when `cand` last changed
    uint32_t t_press;      // when `stable` last went down
} btn_t;

// Feed one debounced sample. raw_down = 1 when the button reads pressed. Returns an OR of BTN_EV_*.
// SHORT fires on release if the hold was shorter than long_ms; LONG fires once while still held.
int btn_update(btn_t *b, int raw_down, uint32_t now_ms, uint32_t debounce_ms, uint32_t long_ms);

/* ---- joystick: dominant-axis direction with a deadzone ---- */
enum { JOY_C = 0, JOY_UP, JOY_DOWN, JOY_LEFT, JOY_RIGHT };

// Decode raw ADC (x,y) about `center` with a `dead` zone. Sign convention: y above center = UP,
// x above center = RIGHT (flip the wiring or the channel if a stick reads inverted).
int joy_dir(int x, int y, int center, int dead);

typedef struct { int last; } joy_edge_t;
// Returns `dir` only on a fresh transition from a different direction into a non-center dir; else JOY_C.
// So one physical flick = one event (no auto-repeat).
int joy_edge(joy_edge_t *e, int dir);

#endif /* HG_INPUT_LOGIC_H */
