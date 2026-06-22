/*
 * Hackagotchi — on-device input (button + joystick) HW glue. SPDX-License-Identifier: MIT
 *
 * v1.2 "Companion". Button (XA008) on GP16 (a freed onboard-LED pin); joystick (XA011) via an ADS1115 on
 * the Grove I2C bus. R1: the button is polled on the SD task (20 ms, GPIO only — no bus) and the joystick
 * on the dashboard task (250 ms, same I2C owner as the OLED -> no mutex). Both lazy-init on first poll and
 * are no-ops unless HG_BUTTON / HG_JOYSTICK is built, so the default image is unchanged. Nothing here runs
 * at or above the DAP path. Inputs post atomic dashboard intents (dash_nav_step / dash_pet).
 */
#ifndef HG_INPUT_H
#define HG_INPUT_H

#include <stdint.h>

void hg_button_poll(uint32_t now_ms);     // call from the SD task each loop (~20 ms)
void hg_joystick_poll(uint32_t now_ms);   // call from the dashboard task each loop (~250 ms)

// CDC1 readback (HIL: prove the input actually reached firmware).
uint32_t hg_button_presses(void);   // taps registered since boot
int      hg_button_down(void);      // 1 if currently held
int      hg_joy_ok(void);           // 1 if the last ADS1115 read succeeded (module present)
int      hg_joy_x(void);            // last raw X code
int      hg_joy_y(void);            // last raw Y code
int      hg_joy_dir(void);          // last decoded JOY_* direction

#endif /* HG_INPUT_H */
