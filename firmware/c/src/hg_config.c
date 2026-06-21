/* Hackagotchi — runtime config store (macros now; baud in M4.3). SPDX-License-Identifier: MIT */
#include "hg_config.h"

// Defaults mirror the MicroPython bridge_cfg["macros"].
static char s_macros[HG_N_MACROS][HG_MACRO_MAX] = { "AT", "PING", "STATUS", "RESET", "HELP", "HELLO" };

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
