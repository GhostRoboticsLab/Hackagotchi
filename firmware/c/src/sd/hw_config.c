/*
 * Hackagotchi — carlk3 no-OS-FatFS hardware config. SPDX-License-Identifier: Apache-2.0
 * (this file is the app-owned hw_config the library requires; modelled on the lib's simple example.)
 *
 * The microSD ground-truth pin lock (mirror of board_hackagotchi_config.h for SWD):
 *   SPI0  SCK=GP2 (D8), MOSI=GP3 (D10), MISO=GP4 (D9), CS=GP28 (D2).
 * These are STATICALLY owned by the SD bus — no runtime re-mux (c-firmware-analysis.md:75). SWD lives
 * on GP26/GP27 specifically to keep this bus free; the OLED is on I2C1 (GP6/7); UART tap on GP0/1.
 * GP28 is not an SPI0 HW pin (it's SPI1_RX) but CS is a plain software-driven GPIO here, so it's fine.
 */

#include "hw_config.h"

static spi_t spi0_cfg = {
    .hw_inst   = spi0,
    .sck_gpio  = 2,
    .mosi_gpio = 3,
    .miso_gpio = 4,
    .baud_rate = 12 * 1000 * 1000,  // 12 MHz to start; verify write+readback before raising (carlk3's
                                    // HF-radio signal-integrity warning over the expansion header)
    .spi_mode  = 0,
};

static sd_spi_if_t spi_if = {
    .spi     = &spi0_cfg,
    .ss_gpio = 28,                  // CS = GP28 (software-driven slave select)
};

static sd_card_t sd_card = {
    .type           = SD_IF_SPI,
    .spi_if_p       = &spi_if,
    .use_card_detect = false,       // no CD line broken out on the expansion header -> rely on FatFs rc
};

size_t sd_get_num(void) { return 1; }

sd_card_t *sd_get_by_num(size_t num) {
    return (0 == num) ? &sd_card : NULL;
}
