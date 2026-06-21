/* Hackagotchi — runtime config store (macros + baud). SPDX-License-Identifier: MIT */
#include "hg_config.h"
#include "probe_config.h"   // PROBE_UART_BAUDRATE (the boot default)

// Defaults mirror the MicroPython bridge_cfg["macros"].
static char s_macros[HG_N_MACROS][HG_MACRO_MAX] = { "AT", "PING", "STATUS", "RESET", "HELP", "HELLO" };

const uint32_t HG_BAUDS[] = { 9600, 19200, 38400, 57600, 115200 };
const int      HG_N_BAUDS = (int)(sizeof HG_BAUDS / sizeof HG_BAUDS[0]);
static uint32_t s_baud = PROBE_UART_BAUDRATE;   // the UART boots at this rate (115200)

uint32_t hg_baud(void) { return s_baud; }

bool hg_set_baud(uint32_t b) {
    for (int i = 0; i < HG_N_BAUDS; i++)
        if (HG_BAUDS[i] == b) { s_baud = b; return true; }
    return false;
}

const char *hg_macro(int i) {
    return (i >= 0 && i < HG_N_MACROS) ? s_macros[i] : "";
}

void hg_set_macro(int i, const char *s) {
    if (i < 0 || i >= HG_N_MACROS) return;
    if (!s) s = "";
    size_t j = 0;
    for (; s[j] && j < HG_MACRO_MAX - 1; j++) s_macros[i][j] = s[j];
    s_macros[i][j] = '\0';
}
