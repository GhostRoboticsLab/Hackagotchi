/*
 * Hackagotchi — SDIO stubs. SPDX-License-Identifier: MIT
 *
 * We use the SD card over SPI0 (SD_IF_SPI), never SDIO — so the CMake build drops carlk3's SDIO sources
 * (rp2040_sdio.c + sd_card_sdio.c, ~11 KB of code that would otherwise sit in RAM under copy_to_ram).
 * But sd_card.c hard-references two SDIO symbols (in its `case SD_IF_SDIO:` dispatch and a status path),
 * so the linker still needs them resolved. These stubs satisfy that; they are NEVER called at runtime
 * because our hw_config.c declares SD_IF_SPI only. If a future board adds an SDIO card, re-include the
 * real SDIO sources (drop the EXCLUDE REGEX in CMakeLists) instead of these stubs.
 */
#include "sd_card.h"

void sd_sdio_ctor(sd_card_t *sd_card_p) { (void)sd_card_p; }

bool rp2040_sdio_get_sd_status(sd_card_t *sd_card_p, uint8_t response[64]) {
    (void)sd_card_p;
    (void)response;
    return false;
}
