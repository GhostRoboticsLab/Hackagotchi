// board_pockettap_config.h — DRAFT XIAO RP2040 board config for the PocketDebugger fork.
//
// This replaces debugprobe's stock board_pico_config.h (SWCLK=GP2, SWDIO=GP3, RESET=GP1,
// UART=GP4/GP5) — EVERY stock pin collides with PocketTap. See docs/engineering-plan.md §6.
//
// ┌──────────────────────────────────────────────────────────────────────────────────────┐
// │ CURRENT PocketTap pin usage (XIAO RP2040 + expansion) — what SWD must avoid:           │
// │   GP0  (D6)  UART0 TX  -> target tap            GP1  (D7)  UART0 RX  -> target tap      │
// │   GP2  (D8)  SD SPI SCK                          GP3  (D10) SD SPI MOSI                 │
// │   GP4  (D9)  SD SPI MISO                         GP28 (D2)  SD CS / PWM-gen out         │
// │   GP6  (D4)  I2C SDA (OLED 0x3C + RTC 0x51)      GP7  (D5)  I2C SCL                     │
// │   GP26 (D0/A0) green LED + ADC scope input      GP27 (D1)  user button                 │
// │   GP29 (D3)  buzzer (PWM)                        GP25 blue LED / GP17 red LED (onboard) │
// └──────────────────────────────────────────────────────────────────────────────────────┘
//
// ⚠️ SWCLK/SWDIO BELOW ARE A CANDIDATE, NOT FINAL. The physical soldering decision picks the
//    two pads. A wrong choice fails Gate 1 SILENTLY as "no IDCODE". Before the Gate-1 soak,
//    validate the soldered header with:  probe-rs info --chip RP2040 --protocol swd
//
// Pin-selection constraints:
//   * Must be two pads broken out on the XIAO that are NOT in the table above (or reclaimed
//     from it — e.g. dropping the buzzer/button/scope frees a pad, at a feature cost).
//   * ⚠️ VERIFY against v2.2.3's probe.pio whether SWCLK/SWDIO must be ADJACENT GPIOs (the PIO
//     program may assume consecutive pins). If so, pick an adjacent pair. GP26/GP27 are adjacent.
//   * Only SWCLK, SWDIO, GND are mandatory (3-wire). RESET is optional (connect-under-reset).
//
// Candidate (reclaims GP26=green-LED+ADC-scope and GP27=button — confirm this trade at solder time):
#ifndef BOARD_POCKETTAP_CONFIG_H
#define BOARD_POCKETTAP_CONFIG_H

// --- SWD (TBD — reconcile these MACRO NAMES with the actual debugprobe-v2.2.3 board header) ---
#define PROBE_PIN_SWCLK   26   // TODO(solder): candidate — verify reach + adjacency + free
#define PROBE_PIN_SWDIO   27   // TODO(solder): candidate — verify reach + adjacency + free
#define PROBE_PIN_RESET    1   // TODO: optional target nRST; GP1 is the UART tap — leave unused unless reworked

// --- UART bridge: tap the target's serial on UART0 GP0/GP1 (matches the jancumps XIAO fork) ---
#define PROBE_UART_TX      0
#define PROBE_UART_RX      1
#define PROBE_UART_INTERFACE uart0
#define PROBE_UART_BAUDRATE  115200

// --- Status LED ---
#define PROBE_PIN_LED     25   // onboard blue

// --- PIO state machine for SWD (stock uses pio0 SM0; keep SM0 reserved for the probe) ---
#define PROBE_SM           0

// NOTE: the OLED (I2C GP6/GP7), microSD (SPI0 GP2/3/4/CS28), RTC, buzzer, and button are driven
// by the PocketTap DASHBOARD task (added at Gate 1+), NOT by the probe core. The probe owns
// pio0 SM0 + the SWD/UART/LED pins above; the dashboard must avoid those. See engineering-plan §4.1.

#endif // BOARD_POCKETTAP_CONFIG_H
