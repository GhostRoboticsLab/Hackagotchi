// board_hackagotchi_config.h — XIAO RP2040 board config for the Hackagotchi probe fork.
//
// Replaces debugprobe's stock board_pico_config.h (SWCLK=GP2/SWDIO=GP3/UART=GP4,GP5) — every
// stock pin collides with the Hackagotchi expansion board. Structured to mirror the upstream
// board_pico_config.h EXACTLY (PROBE_IO_RAW, the topology Gate 0 validated on debugprobe_on_pico),
// changing only the pins. See docs/engineering-plan.md §6.
//
// ┌──────────────────────────────────────────────────────────────────────────────────────┐
// │ Hackagotchi pin usage (XIAO RP2040 + Seeed expansion) — what SWD must avoid:            │
// │   GP0  (D6)  UART0 TX  -> target tap            GP1  (D7)  UART0 RX  -> target tap      │
// │   GP2  (D8)  SD SPI SCK                          GP3  (D10) SD SPI MOSI                 │
// │   GP4  (D9)  SD SPI MISO                         GP28 (D2)  SD CS                       │
// │   GP6  (D4)  I2C1 SDA (OLED 0x3C only)           GP7  (D5)  I2C1 SCL                    │
// │   GP26 (D0)  green LED / ADC                     GP27 (D1)  user button                 │
// │   GP29 (D3)  buzzer (PWM)                        GP25 onboard blue LED (no pad)         │
// └──────────────────────────────────────────────────────────────────────────────────────┘
//
// SWD PIN CHOICE — SWCLK=GP26, SWDIO=GP27:
//   * MANDATORY adjacency: probe.pio's probe_sm_init() does
//       pio_sm_set_consecutive_pindirs(pio0, PROBE_SM, PROBE_PIN_OFFSET, 2, true)
//     with SWCLK as the side-set base and SWDIO = SWCLK+1. So SWDIO MUST equal SWCLK+1.
//     GP26/GP27 are adjacent and in the right order. PROBE_PIN_OFFSET = SWCLK.
//   * These are the only adjacent broken-out pair that keeps the product-critical buses intact
//     (UART tap GP0/1, SD GP2/3/4/28, I2C GP6/7); the cost is the user button (GP27) + GP26
//     LED/ADC, both sacrificable. The alternative adjacent pair GP0/GP1 would cost the UART tap,
//     which is core to the black-box recorder — so GP26/GP27 is the right product lock.
//   * SWDIO gets an internal pull-up (probe_gpio_init, idle-high per SWD spec). GP27 carries the
//     expansion button; if that line has a debounce cap it can break SWD at 1 MHz. THIS IS THE ONE
//     HARDWARE RISK — the Gate-1 pre-soak `probe-rs info --chip RP2040 --protocol swd` is the arbiter.
//     Do not press the button during a flash.
#ifndef BOARD_HACKAGOTCHI_CONFIG_H
#define BOARD_HACKAGOTCHI_CONFIG_H

// Direct connection (two GPIOs, no level shifter) — required so probe.h pulls in probe.pio.h.
#define PROBE_IO_RAW
// Bridge the target UART to a USB CDC interface.
#define PROBE_CDC_UART

// PIO config — SWCLK/SWDIO must be consecutive (SWDIO = SWCLK+1); PROBE_PIN_OFFSET is the base.
#define PROBE_SM 0
#define PROBE_PIN_OFFSET 26
#define PROBE_PIN_SWCLK (PROBE_PIN_OFFSET + 0) // GP26 = XIAO D0 (reclaims LED/ADC)
#define PROBE_PIN_SWDIO (PROBE_PIN_OFFSET + 1) // GP27 = XIAO D1 (reclaims user button)
// No target reset pin (3-wire SWD). Do NOT put RESET on GP1 — that is the UART RX tap.
#if false
#define PROBE_PIN_RESET 0
#endif

// UART bridge: tap the target's serial on UART0 GP0/GP1 (jancumps XIAO fork convention).
#define PROBE_UART_TX 0
#define PROBE_UART_RX 1
#define PROBE_UART_INTERFACE uart0
#define PROBE_UART_BAUDRATE 115200

// Status LED: XIAO onboard blue (GP25, active-low — the upstream usb_thread drives it high on
// ready, so on the XIAO it reads inverted; heartbeat only, not gate-critical).
#define PROBE_USB_CONNECTED_LED 25

#define PROBE_PRODUCT_STRING "Hackagotchi Probe (CMSIS-DAP)"

#endif // BOARD_HACKAGOTCHI_CONFIG_H
