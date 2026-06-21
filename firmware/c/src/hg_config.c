/* Hackagotchi — runtime config store (macros + baud) + SD persistence (KV text). SPDX-License-Identifier: MIT */
#include "hg_config.h"
#include "probe_config.h"   // PROBE_UART_BAUDRATE (the boot default)
#include <stdio.h>          // snprintf
#include <stdlib.h>         // atoi
#include <string.h>         // strncmp, memcpy

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

// --- SD persistence: a tiny line-based KV file (the device's own; robust to partial/garbage lines, no
// jsmn token limits). The CDC1 wire protocol stays JSON; this is just the on-card storage format. ---
int hg_config_serialize(char *out, size_t outsz) {
    int o = snprintf(out, outsz, "baud=%lu\n", (unsigned long)s_baud);
    for (int i = 0; i < HG_N_MACROS; i++)
        o += snprintf(out + (size_t)o, outsz - (size_t)o, "macro%d=%s\n", i, s_macros[i]);
    return o;
}

void hg_config_apply_kv(const char *buf, size_t len) {
    size_t i = 0;
    while (i < len) {
        size_t j = i;                               // line = [i, j)
        while (j < len && buf[j] != '\n' && buf[j] != '\r') j++;
        size_t ll = j - i;
        const char *line = buf + i;
        if (ll > 5 && !strncmp(line, "baud=", 5)) {
            hg_set_baud((uint32_t)atoi(line + 5));   // atoi stops at the EOL non-digit (line isn't NUL'd)
        } else if (ll > 7 && !strncmp(line, "macro", 5) && line[5] >= '0' && line[5] <= '9' && line[6] == '=') {
            int idx = line[5] - '0';
            char tmp[HG_MACRO_MAX];
            size_t vlen = ll - 7; if (vlen >= sizeof tmp) vlen = sizeof tmp - 1;
            memcpy(tmp, line + 7, vlen); tmp[vlen] = '\0';
            hg_set_macro(idx, tmp);
        }
        i = j;
        while (i < len && (buf[i] == '\n' || buf[i] == '\r')) i++;
    }
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
