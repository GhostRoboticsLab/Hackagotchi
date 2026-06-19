import sys
import select
import time
import json
import math
from machine import UART, Pin, SoftI2C, ADC, PWM, time_pulse_us, reset

# ----------------- LED Setup -----------------
# Onboard user LEDs: GP25 (Blue), GP26 (Green), GP17 (Red). Active-low (0=ON, 1=OFF).
blue_led = Pin(25, Pin.OUT)
green_led = Pin(26, Pin.OUT)
red_led = Pin(17, Pin.OUT)

def set_leds(r, g, b):
    red_led.value(0 if r else 1)
    green_led.value(0 if g else 1)
    blue_led.value(0 if b else 1)

# Solid blue status during startup
set_leds(False, False, True)

# ----------------- Passive Buzzer Setup -----------------
# Buzzer is on GP29 (D3)
def beep(freq, ms):
    try:
        pwm = PWM(Pin(29))
        pwm.freq(freq)
        pwm.duty_u16(3000)
        time.sleep_ms(ms)
        pwm.duty_u16(0)
        pwm.deinit()
    except Exception:
        pass

# Boot indicator tone
beep(1500, 40)
time.sleep_ms(60)
beep(2200, 40)

# ----------------- User Button Setup -----------------
# Shield USER button is on GP27 (D1), active-low
button = Pin(27, Pin.IN, Pin.PULL_UP)

# ----------------- SSD1306 OLED Setup -----------------
oled_present = False
oled = None
try:
    import ssd1306
    # SCL is on GP7 (D5), SDA is on GP6 (D4).
    # Initialize I2C at 400kHz for rapid page updates.
    i2c = SoftI2C(scl=Pin(7), sda=Pin(6), freq=400000)
    if 0x3C in i2c.scan():
        oled = ssd1306.SSD1306_I2C(128, 64, i2c, addr=0x3C)
        oled_present = True
        print("OLED found and initialized at 0x3C.")
    else:
        print("OLED not found in I2C scan.")
except Exception as e:
    print("OLED configuration failed:", e)

# ----------------- Compact 5x7 font (data-dense screens) -----------------
# The built-in framebuf font is locked at 8x8 (16 cols x 8 rows, no scaling). To pack
# more onto the text-heavy screens (sniffer/hex, SD viewer, probe sidebar) we ship the
# canonical 5x7 "glcdfont": 5 column bytes per glyph, bit0 = top row .. bit6 = row 7.
# At a 6px advance that's 21 cols across 128px. Titles/menus keep the legible 8x8 font.
_F5x7 = bytes.fromhex(
    "0000000000"  # 0x20 space
    "00005f0000"  # !
    "0007000700"  # "
    "147f147f14"  # #
    "242a7f2a12"  # $
    "2313086462"  # %
    "3649552250"  # &
    "0005030000"  # '
    "001c224100"  # (
    "0041221c00"  # )
    "14083e0814"  # *
    "08083e0808"  # +
    "0050300000"  # ,
    "0808080808"  # -
    "0060600000"  # .
    "2010080402"  # /
    "3e5149453e"  # 0
    "00427f4000"  # 1
    "4261514946"  # 2
    "2141454b31"  # 3
    "1814127f10"  # 4
    "2745454539"  # 5
    "3c4a494930"  # 6
    "0171090503"  # 7
    "3649494936"  # 8
    "064949291e"  # 9
    "0036360000"  # :
    "0056360000"  # ;
    "0008142241"  # <
    "1414141414"  # =
    "4122140800"  # >
    "0201510906"  # ?
    "324979413e"  # @
    "7e1111117e"  # A
    "7f49494936"  # B
    "3e41414122"  # C
    "7f4141221c"  # D
    "7f49494941"  # E
    "7f09090901"  # F
    "3e4149497a"  # G
    "7f0808087f"  # H
    "00417f4100"  # I
    "2040413f01"  # J
    "7f08142241"  # K
    "7f40404040"  # L
    "7f020c027f"  # M
    "7f0408107f"  # N
    "3e4141413e"  # O
    "7f09090906"  # P
    "3e4151215e"  # Q
    "7f09192946"  # R
    "4649494931"  # S
    "01017f0101"  # T
    "3f4040403f"  # U
    "1f2040201f"  # V
    "3f4038403f"  # W
    "6314081463"  # X
    "0708700807"  # Y
    "6151494543"  # Z
    "007f414100"  # [
    "0204081020"  # backslash
    "0041417f00"  # ]
    "0402010204"  # ^
    "4040404040"  # _
    "0001020400"  # `
    "2054545478"  # a
    "7f48444438"  # b
    "3844444420"  # c
    "384444487f"  # d
    "3854545418"  # e
    "087e090102"  # f
    "0c5252523e"  # g
    "7f08040478"  # h
    "00447d4000"  # i
    "2040443d00"  # j
    "7f10284400"  # k
    "00417f4000"  # l
    "7c04180478"  # m
    "7c08040478"  # n
    "3844444438"  # o
    "7c14141408"  # p
    "081414187c"  # q
    "7c08040408"  # r
    "4854545420"  # s
    "043f444020"  # t
    "3c4040207c"  # u
    "1c2040201c"  # v
    "3c4030403c"  # w
    "4428102844"  # x
    "0c5050503c"  # y
    "4464544c44"  # z
    "0008364100"  # {
    "00007f0000"  # |
    "0041360800"  # }
    "0804081008"  # ~
)


def text_small(oled, s, x, y, c=1):
    # Render a string in the 5x7 font (6px advance). Clips at the right edge so a long
    # line never wraps into the next row. Falls back to blank for chars outside 0x20-0x7E.
    for ch in s:
        o = (ord(ch) - 0x20) * 5
        if 0 <= o <= len(_F5x7) - 5 and x + 5 <= 128:
            for col in range(5):
                bits = _F5x7[o + col]
                px = x + col
                yy = y
                while bits:
                    if bits & 1:
                        oled.pixel(px, yy, c)
                    bits >>= 1
                    yy += 1
        x += 6
        if x >= 128:
            break

# ----------------- SD Card Setup -----------------
sd_present = False
sd_mounted = False
sd_card_obj = None

def mount_sd():
    global sd_present, sd_mounted, sd_card_obj
    if sd_mounted:
        return True
    try:
        from machine import SPI
        import sdcard
        import os
        # CS on GP28 (D2), SPI0 on GP2 (D8), GP3 (D9), GP4 (D10)
        cs = Pin(28, Pin.OUT, value=1)
        spi = SPI(0, baudrate=10000000, polarity=0, phase=0, sck=Pin(2), mosi=Pin(3), miso=Pin(4))
        sd_card_obj = sdcard.SDCard(spi, cs)
        os.mount(sd_card_obj, "/sd")
        sd_mounted = True
        sd_present = True
        print("SD Card mounted successfully at /sd")
        return True
    except Exception as e:
        sd_mounted = False
        sd_card_obj = None
        print("SD Card mount failed:", e)
        return False

def unmount_sd():
    global sd_mounted, sd_card_obj
    if not sd_mounted:
        return True
    try:
        import os
        os.umount("/sd")
        sd_mounted = False
        sd_card_obj = None
        print("SD Card unmounted successfully.")
        return True
    except Exception as e:
        print("SD Card unmount failed:", e)
        return False

def ensure_sd_pins():
    if not sd_mounted:
        return False
    try:
        from machine import SPI
        Pin(28, Pin.OUT, value=1)
        SPI(0, baudrate=10000000, polarity=0, phase=0, sck=Pin(2), mosi=Pin(3), miso=Pin(4))
        return True
    except Exception:
        return False

# Attempt to mount SD card at boot
mount_sd()

_fx_trans_n = 0
def trigger_transition_wipe():
    # Multi-style screen transition; cycles each call for variety. Runs only on a screen
    # change, so the brief blocking (~6 OLED frames) never disrupts steady-state bridging.
    global _fx_trans_n
    if not (oled_present and oled is not None):
        return
    try:
        _fx_trans_n = (_fx_trans_n + 1) % 3
        if _fx_trans_n == 0:
            # Curtain: black closes in from both edges to the centre, lit leading rules.
            for x in range(0, 65, 11):
                oled.fill_rect(0, 0, x, 64, 0)
                oled.fill_rect(128 - x, 0, x, 64, 0)
                oled.vline(min(x, 127), 0, 64, 1)
                oled.vline(max(0, 127 - x), 0, 64, 1)
                oled.show()
        elif _fx_trans_n == 1:
            # Venetian blinds: 8 horizontal bands wipe down together.
            for h in range(2, 10, 2):
                for by in range(0, 64, 8):
                    oled.fill_rect(0, by, 128, min(h, 8), 0)
                oled.show()
        else:
            # Vertical scan-wipe: black sweeps left->right behind a bright scan bar.
            for x in range(0, 129, 22):
                oled.fill_rect(0, 0, x, 64, 0)
                if x < 128:
                    oled.fill_rect(min(x, 126), 0, 2, 64, 1)
                oled.show()
        oled.fill(0)
        oled.show()
    except Exception:
        pass

# ----------------- Persistent Config -----------------
def load_bridge_cfg():
    cfg = {"baud": 115200, "macros": ["AT", "PING", "STATUS", "RESET", "HELP", "HELLO"]}
    try:
        with open("bridge_cfg.json") as f:
            cfg.update(json.load(f))
    except Exception:
        pass
    return cfg

def save_bridge_cfg(cfg):
    try:
        with open("bridge_cfg.json", "w") as f:
            json.dump(cfg, f)
    except Exception:
        pass

bridge_cfg = load_bridge_cfg()

# ----------------- UART Setup -----------------
BAUDRATES = [9600, 19200, 38400, 57600, 115200]
BAUDRATE = bridge_cfg["baud"]
if BAUDRATE not in BAUDRATES:
    BAUDRATE = 115200

# Initialize hardware UART0. GPIO 0 = D6 (TX), GPIO 1 = D7 (RX).
uart = UART(0, baudrate=BAUDRATE, tx=Pin(0), rx=Pin(1), rxbuf=1024, txbuf=1024)

# Register polling handles
poll = select.poll()
poll.register(sys.stdin, select.POLLIN)
poll.register(uart, select.POLLIN)

# ----------------- Global State -----------------
# 0: Mascot/Stats, 1: Sniffer, 2: I2C Scanner, 3: Oscilloscope, 4: GPIO Monitor,
# 5: PWM Gen/Meter, 6: Macro Sender, 7: Baud rate menu, 8: Demo Trigger menu,
# 9: SD Explorer, 10: Watchdog (flight recorder), 11: Throughput meter
SCREEN_COUNT = 12
screen = 0
tx_bytes = 0
rx_bytes = 0

# ----------------- Flight-recorder watch state -----------------
# These run as ALWAYS-ON background monitors (not just when their screen is visible) -- the
# whole point of a black box. The Watchdog screen (10) surfaces the detail; the alerts fire
# globally (beep + LED + a log mark + a blinking header badge) wherever you are.
watch_terms = [str(t)[:14] for t in bridge_cfg.get("watch", ["ERROR", "FATAL", "Traceback", "panic", "BUSY-TIMEOUT"])]
watch_hits = 0
watch_last = ""            # last matched term + a snippet
_watch_line = ""           # RX line accumulator for substring matching
ever_active = False        # have we ever seen target traffic? (don't flag a wedge before)
last_rx_t = 0              # ticks_ms of the last received byte
wedge_active = False       # target went silent after being active = a wedge
wedge_since = ""           # wall-clock / uptime stamp when the wedge was detected
WEDGE_SILENCE_MS = 8000    # silence after activity that counts as a wedge
freeze_frame = bytearray() # rolling last ~96 bytes -- the target's dying words
alert_until = 0            # ticks_ms until the global alert badge stops blinking
alert_text = ""            # short alert label (shown on the Watchdog screen)
# Throughput meter
tp_hist = []               # bytes/sec samples (newest last), capped for the sparkline
tp_accum = 0               # bytes counted since the last 1 s sample
tp_last_t = 0
tp_peak = 0

# ----------------- UART Logger State -----------------
logging_active = False
log_buffer = bytearray()
last_log_write_t = 0
last_bb_hb = 0              # black-box heartbeat timer (stamps the log every 60s)
current_log_filename = "uart_log.txt"
last_log_err = ""          # last logger fault reason (SD FULL / WRITE ERR), shown on-screen

def get_next_log_filename():
    global current_log_filename
    if not sd_mounted:
        current_log_filename = "uart_log.txt"
        return current_log_filename
    try:
        import os
        ensure_sd_pins()
        files = os.listdir("/sd")
        max_idx = 0
        for f in files:
            if f.startswith("log_") and f.endswith(".txt"):
                try:
                    idx = int(f[4:-4])
                    if idx > max_idx:
                        max_idx = idx
                except ValueError:
                    pass
        new_idx = max_idx + 1
        current_log_filename = f"log_{new_idx:03d}.txt"
    except Exception:
        current_log_filename = "uart_log.txt"
    return current_log_filename

def log_uart_data(data):
    global log_buffer, last_log_write_t, logging_active
    if not logging_active or not sd_mounted:
        return
    if isinstance(data, str):
        log_buffer.extend(data.encode())
    else:
        log_buffer.extend(data)
    now = time.ticks_ms()
    if len(log_buffer) >= 64 or (time.ticks_diff(now, last_log_write_t) > 500 and len(log_buffer) > 0):
        flush_log_buffer()

def flush_log_buffer():
    global log_buffer, last_log_write_t, logging_active, current_log_filename, last_log_err
    if len(log_buffer) == 0 or not sd_mounted:
        return
    try:
        import os
        ensure_sd_pins()
        with open("/sd/" + current_log_filename, "ab") as f:
            f.write(log_buffer)
        log_buffer = bytearray()
        last_log_write_t = time.ticks_ms()
    except Exception as e:
        # A write fault stops the recorder, but it must be VISIBLE -- a silent stop on a
        # black box is the worst failure. Distinguish a full card (ENOSPC/errno 28) from a
        # generic write error so the on-screen badge tells the user which to fix.
        es = str(e)
        last_log_err = "SD FULL" if ("28" in es or "ENOSPC" in es or "No space" in es) else "WRITE ERR"
        print("Logger write failed (%s), stopping logger:" % last_log_err, e)
        logging_active = False
        log_buffer = bytearray()
        beep(400, 120)
        time.sleep_ms(60)
        beep(400, 120)      # distinctive low double-buzz = recorder died


# ----------------- RTC (PCF8563, expansion-board I2C @ 0x51) -----------------
# Battery-backed by a CR1220 coin cell, so wall-clock survives power loss. The black
# box stamps its session header + heartbeats with real time when the RTC reads valid;
# with no (or a dead) backup cell the VL flag is set and we fall back to uptime -- the
# log is still useful, just relative instead of absolute.
RTC_ADDR = 0x51


def _bcd(v):
    return (v >> 4) * 10 + (v & 0x0F)


def read_rtc():
    # (Y, mon, d, hh, mm, ss) or None if the RTC is absent or its time is untrusted.
    try:
        d = i2c.readfrom_mem(RTC_ADDR, 0x02, 7)   # sec,min,hr,day,wday,mon,yr (BCD)
        if d[0] & 0x80:                            # VL: integrity lost since last set
            return None
        return (2000 + _bcd(d[6]), _bcd(d[5] & 0x1f), _bcd(d[3] & 0x3f),
                _bcd(d[2] & 0x3f), _bcd(d[1] & 0x7f), _bcd(d[0] & 0x7f))
    except Exception:
        return None


def log_stamp():
    rtc = read_rtc()
    if rtc:
        return "%04d-%02d-%02d %02d:%02d:%02d" % rtc
    return "+%ds (no RTC batt)" % (time.ticks_diff(time.ticks_ms(), boot_ms) // 1000)


def start_logging():
    # Open a fresh session file + write a timestamped header. Returns False if the SD
    # won't mount (caller can buzz an error). The single entry point for every start --
    # boot auto-start, the Screen-9 menu, and the host {"cfg":{"logging":true}} path.
    global logging_active, log_buffer, last_log_err
    if not mount_sd():
        return False
    last_log_err = ""       # fresh session clears any prior fault badge
    get_next_log_filename()
    log_buffer.extend(("\n=== BLACK BOX %s | start %s | baud %d ===\n"
                       % (current_log_filename, log_stamp(), BAUDRATE)).encode())
    logging_active = True
    flush_log_buffer()      # persist the header at once, so a yanked card still has it
    return True


def stop_logging():
    global logging_active
    flush_log_buffer()
    logging_active = False


# Autonomous black box: optionally begin recording at power-on, so an untethered or
# overnight capture runs with nobody around to press START. Enable with
# {"cfg":{"log_on_boot":true}}; default off so we don't fill the card every boot.
if bridge_cfg.get("log_on_boot", False):
    if start_logging():
        print("Black box: auto-logging to", current_log_filename)


def draw_rec_indicator(oled, anim_tick):
    if logging_active and (anim_tick // 4) % 2 == 0:
        oled.fill_rect(92, 2, 4, 4, 1)
        oled.text("REC", 98, 0)


def draw_header(oled, title, anim_tick=0, demo=False, show_rec=False):
    # Slim title bar shared by every screen: title at y=0, divider rule at y=9. The old
    # per-screen idiom (title at y=2, rule at y=11, content at y=14) cost 14px before any
    # content; this costs ~9px, so every screen reclaims ~one content row. Content now
    # starts at y=11. demo/show_rec draw the corner badges the old code did inline.
    oled.text(title, 2, 0)
    if demo:
        oled.text("DEMO", 100, 0)
    elif show_rec:
        draw_rec_indicator(oled, anim_tick)
    oled.hline(0, 9, 128, 1)
    # Global alert badge: a blinking inverted "!" at the top-right while an alert is fresh
    # (a trigger hit or a target wedge). Drawn last so it shows on every screen, over REC.
    if alert_until and time.ticks_diff(alert_until, time.ticks_ms()) > 0 and (anim_tick // 2) % 2 == 0:
        oled.fill_rect(118, 0, 9, 9, 1)
        oled.text("!", 119, 0, 0)


def draw_sparkline(oled, data, x, y, w, h, c=1, baseline=False):
    # Auto-scaled line graph of `data` into the box (x,y,w,h). Reusable by the throughput
    # meter and any screen that wants a trend. Cheap: one line() per sample.
    n = len(data)
    if n == 0 or w < 2 or h < 2:
        return
    lo = min(data)
    hi = max(data)
    rng = (hi - lo) or 1
    if baseline:
        oled.hline(x, y + h - 1, w, c)
    prev = None
    for i in range(n):
        px = x + (i * (w - 1)) // max(1, n - 1)
        py = y + h - 1 - int((h - 1) * (data[i] - lo) / rng)
        if prev is not None:
            oled.line(prev[0], prev[1], px, py, c)
        prev = (px, py)


def draw_progress_bar(oled, x, y, w, h, frac, c=1):
    # Outlined bar filled to `frac` (0..1). Used for confirm timers and meters.
    if frac < 0:
        frac = 0.0
    elif frac > 1:
        frac = 1.0
    oled.rect(x, y, w, h, c)
    fw = int((w - 2) * frac)
    if fw > 0:
        oled.fill_rect(x + 1, y + 1, fw, h - 2, c)


def boot_splash():
    # Animated power-on identity card: the PocketTap wordmark wipes in behind a bright scan
    # bar, the underline grows with it, then the tagline + corner brackets settle in. One-shot
    # at boot (the only place a blocking animation is acceptable -- the loop isn't running yet).
    if not (oled_present and oled is not None):
        return
    try:
        title = "PocketTap"
        tx0 = 28
        full_w = len(title) * 8
        steps = 16
        for i in range(steps + 1):
            rv = i / steps
            oled.fill(0)
            oled.text(title, tx0, 14)
            cut = tx0 + int(full_w * rv)
            oled.fill_rect(cut, 10, 128 - cut, 18, 0)   # mask the not-yet-revealed tail
            if rv < 1.0:
                oled.fill_rect(min(cut, 126), 10, 2, 18, 1)  # bright leading scan bar
            oled.hline(22, 28, int(84 * rv), 1)          # underline grows with the reveal
            oled.show()
            time.sleep_ms(16)
        for i in range(4):
            oled.fill_rect(0, 34, 128, 30, 0)
            if i >= 1:
                text_small(oled, "black box for boards", 4, 40)
            if i >= 2:
                text_small(oled, "that go dark", 28, 50)
            if i >= 3:
                oled.hline(0, 0, 8, 1);    oled.vline(0, 0, 8, 1)        # top-left
                oled.hline(120, 0, 8, 1);  oled.vline(127, 0, 8, 1)      # top-right
                oled.hline(0, 63, 8, 1);   oled.vline(0, 56, 8, 1)       # bottom-left
                oled.hline(120, 63, 8, 1); oled.vline(127, 56, 8, 1)     # bottom-right
            oled.show()
            time.sleep_ms(140)
        time.sleep_ms(300)
    except Exception:
        pass

# Demo Mode status
demo_mode = bridge_cfg.get("demo_on_boot", False)
last_demo_switch_t = time.ticks_ms() if demo_mode else 0
boot_ms = time.ticks_ms()   # for the Screen 0 uptime stat

# Terminal sniffer history
sniffer_mode = 0  # 0: ASCII scrolling, 1: Hex dump
terminal_lines = ["", "", "", "", "", ""]   # 6 lines x 21 cols (rendered in the 5x7 font)
hex_history = []  # last 30 bytes for hex dump (6 rows x 5 bytes, 5x7 font)

yawn_end_t = 0
last_active_state = False

# Mascot: Cute Cat pixel art animation
def draw_cat(oled, active, anim_tick, last_type=""):
    global yawn_end_t, last_active_state
    
    # Clear the mascot frame area: x=86 to 127, y=12 to 63
    oled.fill_rect(86, 12, 42, 52, 0)
    
    # Check for state transition (Idle -> Active) to trigger a yawn
    if active and not last_active_state:
        yawn_end_t = time.ticks_ms() + 1200
    last_active_state = active
    
    is_yawning = active and (time.ticks_ms() < yawn_end_t)
    
    cx = 94
    cy = 28
    
    # If sleeping, add chest breathing animation
    if not active:
        breath = (anim_tick // 8) % 2
        cy += breath
        
    # Draw cat head outline
    oled.rect(cx, cy, 28, 20, 1)
    
    # Draw ears
    oled.line(cx, cy, cx + 5, cy - 8, 1)
    oled.line(cx + 5, cy - 8, cx + 10, cy, 1)
    oled.line(cx + 18, cy, cx + 23, cy - 8, 1)
    oled.line(cx + 23, cy - 8, cx + 27, cy, 1)
    
    # Draw nose
    oled.pixel(cx + 14, cy + 12, 1)
    
    # Draw whiskers
    oled.line(cx - 4, cy + 10, cx + 2, cy + 11, 1)
    oled.line(cx - 4, cy + 13, cx + 2, cy + 13, 1)
    oled.line(cx + 26, cy + 11, cx + 32, cy + 10, 1)
    oled.line(cx + 26, cy + 13, cx + 32, cy + 13, 1)
    
    # Draw tail (wagging tail animation)
    tail_stage = (anim_tick // 4) % 3
    tx = cx + 27
    ty = cy + 15
    if tail_stage == 0:
        oled.line(tx, ty, tx + 4, ty - 2, 1)
        oled.line(tx + 4, ty - 2, tx + 6, ty - 6, 1)
    elif tail_stage == 1:
        oled.line(tx, ty, tx + 5, ty, 1)
        oled.line(tx + 5, ty, tx + 7, ty - 3, 1)
    else:
        oled.line(tx, ty, tx + 4, ty + 2, 1)
        oled.line(tx + 4, ty + 2, tx + 6, ty, 1)

    if is_yawning:
        # State: Yawning wake transition -> shut eyes + wide open mouth + yawn bubble
        oled.line(cx + 4, cy + 8, cx + 10, cy + 8, 1)
        oled.line(cx + 18, cy + 8, cx + 24, cy + 8, 1)
        oled.fill_rect(cx + 11, cy + 13, 6, 5, 1)
        
        # Draw "YAWN!" bubble
        bx, by = cx - 18, cy - 13
        oled.rect(bx, by, 26, 11, 1)
        oled.line(bx + 16, by + 10, cx + 2, cy + 2, 1)
        oled.text("yawn", bx + 2, by + 2, 1)
        
    elif active:
        # State: Active data flow -> Eyes open wide + moving mouth + TX/RX bubble
        oled.fill_rect(cx + 4, cy + 5, 6, 6, 1)
        oled.fill_rect(cx + 18, cy + 5, 6, 6, 1)
        # Pupils
        oled.pixel(cx + 5, cy + 6, 0)
        oled.pixel(cx + 19, cy + 6, 0)
        
        # Mouth open/closed cycles
        if (anim_tick // 3) % 2 == 0:
            oled.fill_rect(cx + 12, cy + 14, 5, 3, 1)
        else:
            oled.line(cx + 13, cy + 15, cx + 15, cy + 15, 1)
            
        # Draw bubble
        bx, by = cx - 13, cy - 13
        oled.rect(bx, by, 21, 11, 1)
        oled.line(bx + 14, by + 10, cx + 2, cy + 2, 1)
        oled.text(last_type, bx + 3, by + 2, 1)
        
        # Flying data packet particles
        p1 = 45 + (anim_tick * 7) % 40
        p2 = 45 + ((anim_tick + 3) * 7) % 40
        oled.pixel(p1, 26, 1)
        oled.pixel(p2, 42, 1)
    else:
        # State: Idle -> Sleeping or blinking
        blink = (anim_tick % 40) >= 37
        if blink:
            # Brief blink (horizontal eye lines)
            oled.line(cx + 4, cy + 8, cx + 10, cy + 8, 1)
            oled.line(cx + 18, cy + 8, cx + 24, cy + 8, 1)
            oled.line(cx + 13, cy + 14, cx + 15, cy + 14, 1)
        else:
            # Sleeping (downward curved eye pixels)
            for offset in (0, 14):
                oled.pixel(cx + 4 + offset, cy + 8, 1)
                oled.pixel(cx + 5 + offset, cy + 9, 1)
                oled.pixel(cx + 6 + offset, cy + 9, 1)
                oled.pixel(cx + 7 + offset, cy + 9, 1)
                oled.pixel(cx + 8 + offset, cy + 9, 1)
                oled.pixel(cx + 9 + offset, cy + 9, 1)
                oled.pixel(cx + 10 + offset, cy + 8, 1)
            oled.line(cx + 13, cy + 14, cx + 15, cy + 14, 1)
            
            # Draw floating Z's
            z_stage = (anim_tick // 6) % 3
            zx = cx - 12 + z_stage * 4
            zy = cy - 8 - z_stage * 3
            oled.text("z" if z_stage == 0 else "Z", zx, zy, 1)

# Format standard numeric byte counts
def fmt_bytes(n):
    if n >= 1000000:
        return f"{n/1000000:.1f}M"
    if n >= 1000:
        return f"{n/1000:.1f}K"
    return str(n)

# Stream log parser
def add_to_terminal(b):
    global terminal_lines
    if b == 10:  # LF (\n) -> start a new line
        terminal_lines.append("")
        terminal_lines = terminal_lines[-6:]
    elif b == 13:  # CR (\r) -> ignore
        pass
    elif b == 9:  # Tab (\t) -> render as spaces
        add_to_terminal(32)
        add_to_terminal(32)
    else:
        if 32 <= b <= 126:
            c = chr(b)
        else:
            c = "."  # substitute unprintable codes with dot

        if len(terminal_lines[-1]) >= 21:   # 5x7 font fits 21 cols (was 16 in the 8x8 font)
            terminal_lines.append("")
            terminal_lines = terminal_lines[-6:]
        terminal_lines[-1] += c


def fire_alert(text, lo=900, hi=1600):
    # Raise a global, attention-grabbing alert: a two-tone chirp, the red LED, a blinking
    # header badge, and (if recording) a stamped line in the black box. Used by the trigger
    # watcher and the wedge detector -- the things you most want to know happened.
    global alert_until, alert_text
    alert_text = text[:18]
    alert_until = time.ticks_add(time.ticks_ms(), 6000)
    set_leds(True, False, False)
    beep(hi, 60)
    time.sleep_ms(35)
    beep(lo, 90)
    if logging_active:
        try:
            log_uart_data("\n--- ALERT %s %s ---\n" % (log_stamp(), text))
            flush_log_buffer()
        except Exception:
            pass


def feed_watch(data):
    # Per-RX hook: maintain the freeze-frame ring (the target's last words), scan completed
    # lines for any armed trigger term, and refresh the activity clock so the wedge detector
    # knows the target is alive. Cheap -- runs on every received chunk.
    global _watch_line, watch_hits, watch_last, freeze_frame, last_rx_t, ever_active
    global wedge_active, tp_accum
    last_rx_t = time.ticks_ms()
    ever_active = True
    tp_accum += len(data)
    # The target spoke -> any prior wedge is over.
    if wedge_active:
        wedge_active = False
        fire_alert("RECOVERED", lo=1600, hi=2400)
    # Rolling freeze-frame: keep only the last 96 bytes.
    freeze_frame.extend(data)
    if len(freeze_frame) > 96:
        freeze_frame[:] = freeze_frame[-96:]
    if not watch_terms:
        return
    for b in data:
        if b == 10 or b == 13:
            line = _watch_line
            _watch_line = ""
            if line:
                for term in watch_terms:
                    if term and term in line:
                        watch_hits += 1
                        watch_last = (term + ": " + line.strip())[:60]
                        fire_alert("HIT " + term)
                        break
        elif 32 <= b <= 126:
            _watch_line += chr(b)
            if len(_watch_line) > 200:       # guard against an unterminated flood
                _watch_line = _watch_line[-200:]

# ----------------- I2C Scanner Database -----------------
last_i2c_scan = 0
i2c_devices = []
KNOWN_I2C = {
    0x3C: "OLED (SSD1306)",
    0x51: "RTC (PCF8563)",
    0x68: "IMU (MPU6050)",
    0x76: "Baro (BME280)",
    0x77: "Baro (BMP280)",
    0x40: "Humid (AHT20)",
    0x44: "Temp (SHT30)",
    0x23: "Light (BH1750)"
}

def scan_i2c():
    global i2c_devices
    if oled_present:
        try:
            i2c_devices = sorted(i2c.scan())
        except Exception:
            pass

# ----------------- Screen 9 SD Explorer State -----------------
sd_menu_items = []
sd_menu_idx = 0
sd_confirm_pending = False
sd_confirm_t = 0

sd_view_active = False
sd_view_file = ""
sd_view_offset = 0

def get_file_lines(path, start_line, num_lines=4):
    lines = []
    try:
        ensure_sd_pins()
        with open(path, "r") as f:
            for _ in range(start_line):
                if not f.readline():
                    break
            for _ in range(num_lines):
                line = f.readline()
                if not line:
                    break
                clean_line = line.replace("\t", "    ").rstrip("\r\n")
                lines.append(clean_line)
    except Exception:
        pass
    return lines

def prepare_sd_explorer():
    global sd_menu_items, sd_menu_idx, sd_confirm_pending, sd_view_active
    sd_menu_idx = 0
    sd_confirm_pending = False
    sd_view_active = False
    
    # Auto-mount
    mount_sd()
    ensure_sd_pins()
    
    sd_menu_items = ["< BACK"]
    if sd_mounted:
        if logging_active:
            sd_menu_items.append("[STOP LOGGING]")
        else:
            sd_menu_items.append("[START LOGGING]")
        
        try:
            import os
            files = sorted(os.listdir("/sd"))
            for f in files:
                sd_menu_items.append(f)
        except Exception:
            pass
    else:
        sd_menu_items.append("[RETRY MOUNT]")

# ----------------- Analog Oscilloscope Setup -----------------
adc = ADC(Pin(26))  # A0 (GP26)
osc_samples = [62] * 80  # sweep x=0..79, height y=14..62
scope_mode = 1  # 0: 1ms/div, 1: 10ms/div, 2: 100ms/div, 3: FREEZE
scope_intervals_us = [100, 1000, 10000]
scope_names = ["1ms/div", "10ms/div", "100ms/div", "FREEZE"]

# Math: zero-crossing frequency estimator
def estimate_freq(samples, interval_us):
    s_min, s_max = min(samples), max(samples)
    if s_max - s_min < 4:  # Flat signal
        return 0.0
    mid = (s_max + s_min) / 2
    crossings = []
    last_state = samples[0] > mid
    for i in range(1, len(samples)):
        state = samples[i] > mid
        if state and not last_state:  # Rising crossing
            crossings.append(i)
        last_state = state
    if len(crossings) >= 2:
        cycles = len(crossings) - 1
        span_samples = crossings[-1] - crossings[0]
        duration_s = (span_samples * interval_us) / 1000000.0
        return cycles / duration_s
    return 0.0

# ----------------- GPIO Monitor & Logic Probe -----------------
PINS_TO_MONITOR = [
    (26, "D0"), (27, "D1"), (28, "D2"), (29, "D3"), (6, "D4"),
    (7, "D5"), (0, "D6"), (1, "D7"), (2, "D8"), (4, "D9"), (3, "D10")
]

# Set monitors to inputs by default
for p_num, label in PINS_TO_MONITOR:
    if p_num in (26, 28, 2, 4, 3):
        Pin(p_num, Pin.IN)

gpio_sel_idx = -1  # -1 means Grid Monitor mode; >=0 means detailed logic analyzer for highlighted pin
logic_samples = [48] * 80  # x=0..79, high=24, low=48

# ----------------- Signal Generator & Meter -----------------
GEN_FREQS = [0, 50, 100, 500, 1000, 5000, 10000, 20000]
gen_idx = 0  # Off by default
pwm_gen = None

def apply_signal_generator():
    global pwm_gen
    freq = GEN_FREQS[gen_idx]
    if freq == 0:
        if pwm_gen is not None:
            try:
                pwm_gen.deinit()
            except Exception:
                pass
            pwm_gen = None
        if sd_mounted:
            Pin(28, Pin.OUT, value=1)
        else:
            Pin(28, Pin.OUT).value(0)
    else:
        try:
            pwm_gen = PWM(Pin(28))
            pwm_gen.freq(freq)
            pwm_gen.duty_u16(32768)
        except Exception as e:
            print("Signal Gen error:", e)

# Setup GP2 as PWM meter input
meter_pin = Pin(2, Pin.IN)
pwm_freq_val = 0.0
pwm_duty_val = 0.0

def sample_pwm_meter():
    global pwm_freq_val, pwm_duty_val
    try:
        # Measures pulses with a 10ms timeout (covers signals down to 100Hz)
        high_us = time_pulse_us(meter_pin, 1, 10000)
        low_us = time_pulse_us(meter_pin, 0, 10000)
        if high_us > 0 and low_us > 0:
            period = high_us + low_us
            pwm_freq_val = 1000000.0 / period
            pwm_duty_val = (high_us * 100.0) / period
        else:
            pwm_freq_val = 0.0
            pwm_duty_val = 100.0 if meter_pin.value() == 1 else 0.0
    except Exception:
        pwm_freq_val = 0.0
        pwm_duty_val = 0.0

# ----------------- Macro Menu Navigation -----------------
# We add "DEMO MODE" to macro items to let the user trigger it from the UI
macro_items = ["< CANCEL"] + bridge_cfg["macros"][:6] + ["DEMO MODE"]
macro_idx = 0
macro_confirm_t = 0
macro_confirm_pending = False

# ----------------- Baud Select Navigation -----------------
menu_items = ["< CANCEL"] + [str(b) for b in BAUDRATES]
menu_idx = 0
baud_confirm_t = 0
baud_confirm_pending = False

# ----------------- Demo Trigger Navigation -----------------
demo_trigger_items = ["< CANCEL", "START NOW", "BOOT & RUN"]
demo_trigger_idx = 0
demo_trigger_confirm_t = 0
demo_trigger_confirm_pending = False

# ----------------- Exit Demo Helper -----------------
def exit_demo():
    global demo_mode, screen, tx_bytes, rx_bytes, terminal_lines, hex_history, bridge_cfg
    demo_mode = False
    trigger_transition_wipe()
    screen = 0
    tx_bytes = 0
    rx_bytes = 0
    terminal_lines = ["", "", "", "", "", ""]
    hex_history = []
    apply_signal_generator()
    if bridge_cfg.get("demo_on_boot", False):
        bridge_cfg["demo_on_boot"] = False
        save_bridge_cfg(bridge_cfg)
    beep(1000, 80)

# ----------------- Button Press Routing -----------------
def handle_short_press():
    global screen, menu_idx, baud_confirm_pending, baud_confirm_t
    global macro_idx, macro_confirm_pending, macro_confirm_t
    global gen_idx, scope_mode, sniffer_mode, gpio_sel_idx, terminal_lines
    
    if demo_mode:
        exit_demo()
        return

    beep(2000, 15)  # feedback
    
    if screen == 0:
        # Reset byte stats
        global tx_bytes, rx_bytes
        tx_bytes = 0
        rx_bytes = 0
        beep(2400, 15)
        time.sleep_ms(30)
        beep(2400, 15)
    elif screen == 1:
        # Toggle Sniffer mode (ASCII vs Hex dump)
        sniffer_mode ^= 1
    elif screen == 2:
        # Rescan I2C
        scan_i2c()
    elif screen == 3:
        # Cycle scope scale or freeze
        scope_mode = (scope_mode + 1) % 4
    elif screen == 4:
        # Cycle selected GPIO pin for logic analyzer view
        gpio_sel_idx += 1
        if gpio_sel_idx >= len(PINS_TO_MONITOR):
            gpio_sel_idx = -1  # return to grid monitor
        # Reset logic probe graph
        global logic_samples
        logic_samples = [48] * 80
    elif screen == 5:
        # Cycle Signal Gen frequency
        gen_idx = (gen_idx + 1) % len(GEN_FREQS)
        apply_signal_generator()
    elif screen == 6:
        # Cycle Macros
        macro_idx = (macro_idx + 1) % len(macro_items)
        macro_confirm_t = time.ticks_ms() + 2000
        macro_confirm_pending = True
    elif screen == 7:
        # Cycle Baud Rates
        menu_idx = (menu_idx + 1) % len(menu_items)
        baud_confirm_t = time.ticks_ms() + 2000
        baud_confirm_pending = True
    elif screen == 8:
        # Cycle Demo Trigger items
        global demo_trigger_idx, demo_trigger_confirm_pending, demo_trigger_confirm_t
        demo_trigger_idx = (demo_trigger_idx + 1) % len(demo_trigger_items)
        demo_trigger_confirm_t = time.ticks_ms() + 2000
        demo_trigger_confirm_pending = True
    elif screen == 9:
        # SD Card Explorer
        global sd_view_active, sd_view_offset, sd_view_file, sd_menu_idx, sd_confirm_t, sd_confirm_pending
        if sd_view_active:
            sd_view_offset += 5            # page by the 5 rows the viewer now shows
            lines = get_file_lines("/sd/" + sd_view_file, sd_view_offset, num_lines=5)
            if not lines:
                sd_view_active = False
                beep(1200, 60)
            else:
                beep(1800, 15)
        else:
            if len(sd_menu_items) > 0:
                sd_menu_idx = (sd_menu_idx + 1) % len(sd_menu_items)
                sd_confirm_t = time.ticks_ms() + 2000
                sd_confirm_pending = True
    elif screen == 10:
        # Watchdog: short-press = acknowledge (clear trigger hits + clear the wedge flag).
        global watch_hits, watch_last, wedge_active, alert_until
        watch_hits = 0
        watch_last = ""
        wedge_active = False
        alert_until = 0
        beep(2000, 20)
    elif screen == 11:
        # Throughput: short-press = reset the meter.
        global tp_peak, tp_accum
        tp_hist[:] = []
        tp_peak = 0
        tp_accum = 0
        beep(2000, 20)

def handle_long_press():
    global screen, menu_idx, baud_confirm_pending
    global macro_idx, macro_confirm_pending, gpio_sel_idx
    global demo_trigger_confirm_pending, demo_trigger_idx
    global sd_confirm_pending, sd_view_active
    
    if demo_mode:
        exit_demo()
        return

    # Transition chime
    beep(1500, 25)
    time.sleep_ms(15)
    beep(2200, 25)
    
    # Cancel confirmations & exit nested logic screens
    baud_confirm_pending = False
    macro_confirm_pending = False
    demo_trigger_confirm_pending = False
    sd_confirm_pending = False
    sd_view_active = False
    gpio_sel_idx = -1
    
    trigger_transition_wipe()
    
    # Switch screen
    screen = (screen + 1) % SCREEN_COUNT

    # Entry prepares
    if screen == 2:
        scan_i2c()
    elif screen == 6:
        macro_idx = 0
    elif screen == 7:
        menu_idx = 0
    elif screen == 8:
        demo_trigger_idx = 0
    elif screen == 9:
        prepare_sd_explorer()

# ----------------- Host JSON Line Interface -----------------
# Buffer to assemble incoming host serial lines
usb_rx_buf = ""

def process_host_command(line):
    global BAUDRATE, macro_items, bridge_cfg, demo_mode, last_demo_switch_t, screen, tx_bytes, rx_bytes, logging_active, watch_terms
    try:
        data = json.loads(line)
        if "cfg" in data:
            cfg = data["cfg"]
            changed = False
            
            # 1. Update Baudrate
            if "baud" in cfg and cfg["baud"] in BAUDRATES:
                BAUDRATE = cfg["baud"]
                uart.init(baudrate=BAUDRATE, tx=Pin(0), rx=Pin(1), rxbuf=1024, txbuf=1024)
                bridge_cfg["baud"] = BAUDRATE
                changed = True
                
            # 2. Update Macros
            if "macros" in cfg and isinstance(cfg["macros"], list):
                # Clean macros
                cleaned = [str(m)[:14] for m in cfg["macros"][:6]]
                bridge_cfg["macros"] = cleaned
                macro_items = ["< CANCEL"] + cleaned + ["DEMO MODE"]
                changed = True
                
            # 3. Toggle Demo Mode
            if "demo" in cfg:
                demo_mode = bool(cfg["demo"])
                if demo_mode:
                    last_demo_switch_t = time.ticks_ms()
                    screen = 0
                    tx_bytes = 0
                    rx_bytes = 0
                else:
                    screen = 0
                    apply_signal_generator()
                beep(2000, 40)
                changed = True
                
            # 4. Toggle Demo on Boot
            if "demo_on_boot" in cfg:
                bridge_cfg["demo_on_boot"] = bool(cfg["demo_on_boot"])
                changed = True

            # 4b. Black-box auto-start on boot
            if "log_on_boot" in cfg:
                bridge_cfg["log_on_boot"] = bool(cfg["log_on_boot"])
                changed = True

            # 4c. Hardware watchdog. Armed once at boot and cannot be disarmed, so this
            # only takes effect after the NEXT reboot -- intentional, to keep reflashing
            # safe (a WDT armed now could trip mid-cp at the REPL and corrupt main.py).
            if "wdt" in cfg:
                bridge_cfg["wdt"] = bool(cfg["wdt"])
                changed = True

            # 4d. Trigger-watch terms (live): each completed RX line is scanned for these
            # substrings; a match beeps, flashes, marks the log, and counts on the Watchdog.
            if "watch" in cfg and isinstance(cfg["watch"], list):
                watch_terms = [str(t)[:14] for t in cfg["watch"][:8]]
                bridge_cfg["watch"] = watch_terms
                changed = True

            # 5. Toggle UART Logging
            if "logging" in cfg:
                if bool(cfg["logging"]):
                    start_logging()
                else:
                    stop_logging()
                changed = True
            
            if changed:
                save_bridge_cfg(bridge_cfg)
                # Success notification
                beep(2500, 40)
                time.sleep_ms(40)
                beep(3000, 40)
                
                # Print response back to host
                res = {"status": "OK", "baud": BAUDRATE, "macros": bridge_cfg["macros"], "demo": demo_mode, "demo_on_boot": bridge_cfg.get("demo_on_boot", False), "logging": logging_active, "log_on_boot": bridge_cfg.get("log_on_boot", False), "log_file": current_log_filename, "wdt": bridge_cfg.get("wdt", False), "watch": watch_terms}
                print("\r\n" + json.dumps(res) + "\r\n")
                
                # Reset local visual selectors
                global menu_items
                menu_items = ["< CANCEL"] + [str(b) for b in BAUDRATES]
                return True
    except Exception as e:
        print(json.dumps({"status": "error", "msg": str(e)}))
    return False

# Initialize Signal Gen
apply_signal_generator()

# Runtime variables
last_activity_t = 0
last_type = "RX"
last_render = 0
anim_tick = 0

btn_active = False
btn_pressed_time = 0
btn_state = 1

print("\r\n================================================")
print(" PocketTap -- black-box recorder for dev boards")
print(" that go dark (Seeed XIAO RP2040 + expansion)")
print("Controls:")
print("  - SHORT Press: Cycle values / Clear stats / Toggle views")
print("  - LONG Press  (>0.5s): Cycle to next tool/app")
print("================================================")

boot_splash()

# --- Watchdog + fault-recovery state -------------------------------------------------
# The loop body runs under a PER-ITERATION try/except so a transient fault (a bad byte,
# an SD hiccup, an I2C glitch) never bricks the bridge -- it logs the fault, flashes the
# error LED, beeps, and carries on watching the target. Only a STORM of faults (a
# deterministic crash repeating every pass) escalates to a clean reboot. An OPTIONAL
# hardware WDT (fed once per pass) recovers from a true CPU hang (e.g. a blocked USB-CDC
# write). It is OFF by default: once armed it can't be disarmed, so a slow mpremote
# reflash paused at the REPL could trip it mid-write and corrupt main.py. Enable it for
# untethered black-box deployments (where you're not reflashing) with {"cfg":{"wdt":true}}.
wdt = None
if bridge_cfg.get("wdt", False):
    try:
        from machine import WDT
        wdt = WDT(timeout=8388)     # RP2040 hardware max (~8.4s)
    except Exception:
        wdt = None
loop_err_count = 0
last_err_t = time.ticks_ms()
last_loop_err = ""

while True:
    try:
        now_ms = time.ticks_ms()
        if wdt is not None:
            wdt.feed()

        # ----------------- Button Polling -----------------
        v = button.value()
        if v != btn_state:
            time.sleep_ms(15)  # debounce
            if button.value() == v:
                btn_state = v
                if btn_state == 0:  # Pressed
                    btn_active = True
                    btn_pressed_time = time.ticks_ms()
                else:  # Released
                    if btn_active:
                        btn_active = False
                        dur = time.ticks_diff(time.ticks_ms(), btn_pressed_time)
                        if dur >= 500:
                            handle_long_press()
                        else:
                            handle_short_press()
        
        # ----------------- Demo Mode Automation Loop -----------------
        if demo_mode:
            # 1. Cycle screens every 7 seconds
            if time.ticks_diff(now_ms, last_demo_switch_t) > 7000:
                last_demo_switch_t = now_ms
                trigger_transition_wipe()
                screen = (screen + 1) % SCREEN_COUNT
                beep(1800, 20)
                
                # Configure screens automatically for full visual loading
                if screen == 1:
                    sniffer_mode ^= 1  # Alternate between ASCII (0) and Hex (1)
                elif screen == 2:
                    i2c_devices = [0x3C, 0x51, 0x68, 0x77]
                elif screen == 4:
                    # Alternate between Pin Grid Monitor (-1) and Logic Analyzer Probe on D0 (0)
                    gpio_sel_idx = 0 if gpio_sel_idx == -1 else -1
                    logic_samples = [48] * 80
                elif screen == 9:
                    sd_menu_items = ["< BACK", "[START LOGGING]", "demo_log.csv", "sys_info.txt"]
                    sd_menu_idx = 0
                    sd_view_active = False
                elif screen == 10:
                    watch_hits = 3
                    watch_last = "FATAL: kernel panic on core1"
                    wedge_active = True
                    wedge_since = "12:34:50"
                    freeze_frame[:] = b"WiFi ok\nGET /api/data\nparsing..\nFATAL: panic core1"
                elif screen == 11:
                    tp_hist[:] = []
                    tp_peak = 480

            # 2. Simulate activity ticks
            anim_tick += 1  # speed up animations
            
            if screen == 0:
                tx_bytes += 128
                rx_bytes += 256
                last_activity_t = now_ms
                last_type = "TX" if (anim_tick // 4) % 2 == 0 else "RX"
            elif screen == 1:
                # Add rolling log payloads
                if anim_tick % 15 == 0:
                    demo_strings = [
                        "AT+PING", "PONG 12ms", "TEMP: 24.3 C", 
                        "HUMID: 45.1%", "PRES: 1013 hPa", "SYS: OK", 
                        "BATTERY: 87%", "GPS LOCK: 3D", "ALT: 124m"
                    ]
                    s = demo_strings[(anim_tick // 15) % len(demo_strings)]
                    for b in s.encode():
                        add_to_terminal(b)
                        hex_history.append(b)
                        if len(hex_history) > 30:
                            hex_history.pop(0)
                    add_to_terminal(10)
            elif screen == 3:
                # Generate clean sine wave
                for i in range(80):
                    val_sin = math.sin((i + anim_tick * 2) * 0.25)
                    osc_samples[i] = 38 - int(val_sin * 20)
            elif screen == 4:
                # Simulate pin logic pulses
                if gpio_sel_idx >= 0:
                    y_val = 24 if ((anim_tick // 4) % 2 == 0) else 48
                    logic_samples.pop(0)
                    logic_samples.append(y_val)
            elif screen == 5:
                pwm_freq_val = 1000.0
                pwm_duty_val = 50.0
            elif screen == 6:
                # Cycle menu selection highlight to simulate interaction
                macro_idx = (anim_tick // 15) % len(macro_items)
            elif screen == 7:
                # Cycle baud selection highlight to simulate interaction
                menu_idx = (anim_tick // 15) % len(menu_items)
            elif screen == 8:
                # Cycle Demo Trigger highlight to simulate interaction
                demo_trigger_idx = (anim_tick // 15) % len(demo_trigger_items)
            elif screen == 9:
                # Cycle SD Explorer highlight to simulate interaction
                if sd_menu_items:
                    sd_menu_idx = (anim_tick // 15) % len(sd_menu_items)
            elif screen == 11:
                # Synthesize a throughput wave for the meter sparkline
                tp_hist.append(240 + int(180 * math.sin(anim_tick * 0.3)))
                if len(tp_hist) > 100:
                    tp_hist.pop(0)

        # ----------------- Confirm Baud Select -----------------
        if screen == 7 and baud_confirm_pending and time.ticks_diff(now_ms, baud_confirm_t) > 0:
            baud_confirm_pending = False
            if menu_idx == 0:
                beep(1200, 60)
                screen = 0
            else:
                new_baud = int(menu_items[menu_idx])
                BAUDRATE = new_baud
                uart.init(baudrate=BAUDRATE, tx=Pin(0), rx=Pin(1), rxbuf=1024, txbuf=1024)
                
                # Save config
                bridge_cfg["baud"] = BAUDRATE
                save_bridge_cfg(bridge_cfg)
                
                beep(2400, 30)
                time.sleep_ms(50)
                beep(3000, 30)
                
                if oled_present:
                    oled.fill(0)
                    oled.rect(0, 0, 128, 64, 1)
                    oled.text("BAUDRATE SET", 16, 18)
                    oled.text(f"{BAUDRATE} bps", 20, 36)
                    oled.show()
                    time.sleep_ms(1200)
                trigger_transition_wipe()
                screen = 0
                
        # ----------------- Confirm Macro Sender -----------------
        if screen == 6 and macro_confirm_pending and time.ticks_diff(now_ms, macro_confirm_t) > 0:
            macro_confirm_pending = False
            if macro_idx == 0:
                beep(1200, 60)
                screen = 0
            elif macro_items[macro_idx] == "DEMO MODE":
                demo_mode = True
                last_demo_switch_t = time.ticks_ms()
                screen = 0
                tx_bytes = 0
                rx_bytes = 0
                beep(2000, 50)
                time.sleep_ms(80)
                beep(2500, 50)
                if oled_present:
                    oled.fill(0)
                    oled.rect(0, 0, 128, 64, 1)
                    oled.text("DEMO MODE", 28, 18)
                    oled.text("STARTING...", 24, 36)
                    oled.show()
                    time.sleep_ms(1200)
                trigger_transition_wipe()
            else:
                macro_text = macro_items[macro_idx]
                uart.write(macro_text + "\r\n")
                tx_bytes += len(macro_text) + 2
                log_uart_data(macro_text + "\r\n")
                last_activity_t = time.ticks_ms()
                last_type = "TX"
                
                beep(2200, 30)
                time.sleep_ms(40)
                beep(2600, 30)
                
                if oled_present:
                    oled.fill(0)
                    oled.rect(0, 0, 128, 64, 1)
                    oled.text("SENT MACRO", 20, 18)
                    oled.text(macro_text, 20, 36)
                    oled.show()
                    time.sleep_ms(1200)
                trigger_transition_wipe()
                screen = 0

        # ----------------- Confirm Demo Trigger -----------------
        if screen == 8 and demo_trigger_confirm_pending and time.ticks_diff(now_ms, demo_trigger_confirm_t) > 0:
            demo_trigger_confirm_pending = False
            if demo_trigger_idx == 0:
                beep(1200, 60)
                screen = 0
            elif demo_trigger_idx == 1:
                # START NOW
                demo_mode = True
                last_demo_switch_t = time.ticks_ms()
                screen = 0
                tx_bytes = 0
                rx_bytes = 0
                beep(2000, 50)
                time.sleep_ms(80)
                beep(2500, 50)
                if oled_present:
                    oled.fill(0)
                    oled.rect(0, 0, 128, 64, 1)
                    oled.text("DEMO MODE", 28, 18)
                    oled.text("STARTING...", 24, 36)
                    oled.show()
                    time.sleep_ms(1200)
                trigger_transition_wipe()
            elif demo_trigger_idx == 2:
                # BOOT & RUN
                bridge_cfg["demo_on_boot"] = True
                save_bridge_cfg(bridge_cfg)
                
                beep(1500, 50)
                time.sleep_ms(60)
                beep(2000, 50)
                time.sleep_ms(60)
                beep(2500, 50)
                
                if oled_present:
                    oled.fill(0)
                    oled.rect(0, 0, 128, 64, 1)
                    oled.text("PERSIST DEMO", 18, 14)
                    oled.text("BOOT CONFIGURED", 6, 28)
                    oled.text("REBOOTING...", 20, 44)
                    oled.show()
                    time.sleep_ms(1500)
                reset()

        # ----------------- Confirm SD Explorer -----------------
        if screen == 9 and sd_confirm_pending and time.ticks_diff(now_ms, sd_confirm_t) > 0:
            sd_confirm_pending = False
            item_text = sd_menu_items[sd_menu_idx]
            if item_text == "< BACK":
                beep(1200, 60)
                screen = 0
                trigger_transition_wipe()
            elif item_text == "[RETRY MOUNT]":
                prepare_sd_explorer()
                beep(2000, 30)
            elif item_text == "[START LOGGING]":
                if start_logging():
                    beep(2400, 30)
                    time.sleep_ms(50)
                    beep(2800, 30)
                else:
                    beep(800, 120)      # SD mount failed
                prepare_sd_explorer()
            elif item_text == "[STOP LOGGING]":
                stop_logging()
                beep(1200, 80)
                prepare_sd_explorer()
            else:
                sd_view_file = item_text
                sd_view_offset = 0
                sd_view_active = True
                beep(2200, 30)
                trigger_transition_wipe()

        # ----------------- Bidirectional USB <-> UART Bridge -----------------
        events = poll.poll(0)  # 100% non-blocking
        for fd, event in events:
            if fd == sys.stdin and (event & select.POLLIN):
                char = sys.stdin.buffer.read(1)
                if char:
                    # Assemble host lines for JSON escape checking
                    c = chr(char[0])
                    if c == "\n":
                        line = usb_rx_buf.strip()
                        usb_rx_buf = ""
                        # If a config command, intercept it
                        if line.startswith('{"cfg":') and process_host_command(line):
                            continue
                        else:
                            # Forward leftover line to UART
                            if line:
                                uart.write(line + "\n")
                                tx_bytes += len(line) + 1
                                log_uart_data(line + "\n")
                                last_activity_t = time.ticks_ms()
                                last_type = "TX"
                                set_leds(False, True, False)
                    elif c != "\r":
                        usb_rx_buf += c
                        if len(usb_rx_buf) > 512:
                            usb_rx_buf = ""
                            
                        # Standard raw forwarding on character bounds (character mode)
                        uart.write(char)
                        tx_bytes += len(char)
                        log_uart_data(char)
                        last_activity_t = time.ticks_ms()
                        last_type = "TX"
                        set_leds(False, True, False)
                        
            elif fd == uart and (event & select.POLLIN):
                if uart.any():
                    data = uart.read(uart.any())
                    if data:
                        # NOTE: blocking write, by design. Do NOT try to make it non-blocking by
                        # registering sys.stdout for POLLOUT in a poll() — on this MicroPython
                        # stdin/stdout are the same USB-CDC stream, so registering stdout kills
                        # stdin's POLLIN and silently breaks the reverse recovery channel
                        # (n/r/g/R/B). Tested + reverted 2026-06-19. During recovery the host is
                        # actively draining USB, so this never blocks in practice.
                        sys.stdout.buffer.write(data)
                        rx_bytes += len(data)
                        log_uart_data(data)
                        last_activity_t = time.ticks_ms()
                        last_type = "RX"
                        feed_watch(data)      # freeze-frame + trigger scan + activity clock
                        for b in data:
                            add_to_terminal(b)
                            # Feed hex history
                            hex_history.append(b)
                            if len(hex_history) > 30:
                                hex_history.pop(0)
                        set_leds(False, True, False)
        
        # Black-box heartbeat: stamp the log every 60s while recording, so that even if
        # the Pico goes silent (a wedge) the last marker bounds when it died.
        if logging_active and time.ticks_diff(now_ms, last_bb_hb) > 60000:
            last_bb_hb = now_ms
            log_uart_data("\n--- BB %s rx=%d ---\n" % (log_stamp(), rx_bytes))

        # --- Flight-recorder background monitors (always on, not just on their screen) ---
        # Wedge detector: the target was alive, then went silent past the threshold. THE
        # black-box event -- capture its dying words (the freeze-frame) and alert.
        if (not wedge_active) and ever_active and time.ticks_diff(now_ms, last_rx_t) > WEDGE_SILENCE_MS:
            wedge_active = True
            wedge_since = log_stamp()
            if logging_active:
                try:
                    ff = bytes(freeze_frame).decode("utf-8", "replace").replace("\n", " ")
                    log_uart_data("\n--- WEDGE %s last=[%s] ---\n" % (wedge_since, ff[-80:]))
                    flush_log_buffer()
                except Exception:
                    pass
            fire_alert("WEDGE " + wedge_since[-8:], lo=500, hi=900)
        # Throughput sampler: one bytes/sec sample per second feeds the meter sparkline.
        if time.ticks_diff(now_ms, tp_last_t) >= 1000:
            tp_last_t = now_ms
            tp_hist.append(tp_accum)
            if tp_accum > tp_peak:
                tp_peak = tp_accum
            tp_accum = 0
            if len(tp_hist) > 100:
                tp_hist.pop(0)

        # Periodic log flush check
        if logging_active and len(log_buffer) > 0 and time.ticks_diff(now_ms, last_log_write_t) > 500:
            flush_log_buffer()

        # Restore solid idle status colors
        activity_age = time.ticks_diff(time.ticks_ms(), last_activity_t)
        is_active = activity_age < 800
        if not is_active:
            set_leds(False, False, True)

        # ----------------- High-Speed Scope Sampling -----------------
        # Screen 3: Analog Oscilloscope. 
        # For 1ms/div and 10ms/div modes, we do a rapid ADC sample burst.
        # For 100ms/div, we sample once per frame to maintain responsiveness.
        if screen == 3 and scope_mode != 3 and not demo_mode:  # Not FREEZE & not Demo
            if scope_mode in (0, 1):  # 1ms/div or 10ms/div (burst capture)
                interval = scope_intervals_us[scope_mode]
                for i in range(80):
                    val = adc.read_u16()
                    osc_samples[i] = 62 - int(val * 47 / 65535)
                    time.sleep_us(interval)
            else:  # 100ms/div (read once per frame loop)
                val = adc.read_u16()
                y_pixel = 62 - int(val * 47 / 65535)
                osc_samples.pop(0)
                osc_samples.append(y_pixel)

        # ----------------- Background PWM Meter Sampling -----------------
        # Screen 5: PWM Gen/Meter. Sample external signal on D8 (GP2).
        if screen == 5 and not demo_mode:
            sample_pwm_meter()

        # ----------------- Logic Probe Sampling -----------------
        # Screen 4: Logic Probe (when pin is highlighted)
        if screen == 4 and gpio_sel_idx >= 0 and not demo_mode:
            target_pin_num = PINS_TO_MONITOR[gpio_sel_idx][0]
            val = Pin(target_pin_num).value()
            y_pixel = 24 if val == 1 else 48
            logic_samples.pop(0)
            logic_samples.append(y_pixel)

        # ----------------- Background I2C Auto-Scan -----------------
        if screen == 2 and time.ticks_diff(now_ms, last_i2c_scan) > 1500 and not demo_mode:
            last_i2c_scan = now_ms
            scan_i2c()

        # ----------------- OLED Graphics Rendering Loop -----------------
        if oled_present and time.ticks_diff(now_ms, last_render) > 80:  # ~12.5 FPS
            last_render = now_ms
            anim_tick += 1
            
            if screen == 0:
                # SCREEN 0: MASCOT / STATS
                oled.fill(0)
                draw_header(oled, "[ UART BRIDGE ]", anim_tick, demo_mode, show_rec=True)
                up = time.ticks_diff(time.ticks_ms(), boot_ms) // 1000
                up_str = f"{up // 60}m{up % 60:02d}s" if up >= 60 else f"{up}s"
                oled.text(f"Baud:{BAUDRATE}", 4, 12)
                oled.text(f"TX:{fmt_bytes(tx_bytes)}B", 4, 22)
                oled.text(f"RX:{fmt_bytes(rx_bytes)}B", 4, 32)
                oled.text(f"Up:{up_str}", 4, 42)
                if not last_log_err:
                    oled.text("USB<->UART", 4, 52)
                draw_cat(oled, is_active, anim_tick, last_type)
                # A logger fault (full/unwritable card) gets a blinking full-width banner
                # drawn last, so it stays legible even over the mascot frame.
                if last_log_err and (anim_tick // 4) % 2 == 0:
                    oled.fill_rect(0, 52, 128, 10, 0)
                    text_small(oled, "LOG STOP: " + last_log_err, 2, 53)
                oled.show()
                
            elif screen == 1:
                # SCREEN 1: SNIFFER TERMINAL
                oled.fill(0)
                title = "[ HEX SNIFFER ]" if sniffer_mode == 1 else "[ UART RX LOG ]"
                draw_header(oled, title, anim_tick, demo_mode, show_rec=True)
                if sniffer_mode == 0:
                    # 5x7 font -> 6 lines of 21 cols (was 5 lines of 16 in the 8x8 font).
                    for idx, line in enumerate(terminal_lines):
                        text_small(oled, line, 2, 11 + idx * 9)
                else:
                    # Hex dump in the 5x7 font: 6 rows x 5 bytes + ASCII gutter (was 5 x 4).
                    for idx in range(6):
                        start = idx * 5
                        chunk = hex_history[start:start + 5]
                        if not chunk:
                            break
                        hex_str = " ".join(f"{b:02X}" for b in chunk)
                        hex_str += " " * (14 - len(hex_str))
                        ascii_str = "".join(chr(b) if 32 <= b <= 126 else "." for b in chunk)
                        text_small(oled, f"{hex_str} {ascii_str}", 2, 11 + idx * 9)
                oled.show()
                
            elif screen == 2:
                # SCREEN 2: I2C SCANNER
                oled.fill(0)
                draw_header(oled, "[ I2C SCANNER ]", anim_tick, demo_mode)

                # Draw rotating radar sweep graphic on the right
                rx = 104
                ry = 38
                rad = 16
                oled.rect(rx - rad, ry - rad, rad * 2, rad * 2, 1)
                # Crosshairs
                oled.hline(rx - rad, ry, rad * 2, 1)
                oled.vline(rx, ry - rad, rad * 2, 1)
                # Sweep line rotating
                sweep_angle = (anim_tick * 0.4)
                dx = int(math.cos(sweep_angle) * rad)
                dy = int(math.sin(sweep_angle) * rad)
                oled.line(rx, ry, rx + dx, ry + dy, 1)
                
                # Glowing scan target pulses
                if (anim_tick // 2) % 2 == 0:
                    oled.pixel(rx + 6, ry - 6, 1)
                    oled.pixel(rx - 8, ry + 4, 1)

                if not i2c_devices:
                    oled.text("Scanning...", 4, 26)
                else:
                    if len(i2c_devices) <= 4:
                        for idx, addr in enumerate(i2c_devices):
                            name = KNOWN_I2C.get(addr, "Dev")
                            oled.text(f"0x{addr:02X}:{name[:7]}", 4, 12 + idx * 12)
                    else:
                        # Draw list of addresses in 2 columns
                        for idx, addr in enumerate(i2c_devices[:10]):
                            col = idx // 5
                            row = idx % 5
                            x = 4 + col * 40
                            y = 12 + row * 10
                            oled.text(f"0x{addr:02X}", x, y)
                oled.show()
                
            elif screen == 3:
                # SCREEN 3: ANALOG OSCILLOSCOPE
                oled.fill(0)
                # Compute Math stats: convert screens y-pixel values back to voltage values
                s_min = min(osc_samples)
                s_max = max(osc_samples)
                v_max = (62 - s_min) * 3.3 / 47
                v_min = (62 - s_max) * 3.3 / 47
                v_pp = max(0.0, v_max - v_min)
                
                # Estimate Frequency
                cur_interval = scope_intervals_us[scope_mode] if scope_mode < 3 else 1000
                if scope_mode == 2:
                    cur_interval = 80000  # ~80ms loop execution
                if demo_mode:
                    cur_interval = 1000  # simulate 1ms interval sine wave
                f_val = estimate_freq(osc_samples, cur_interval)
                

                
                # Render Scope waveforms
                title = f"{scope_names[scope_mode]}" if not demo_mode else "Sine Wave"
                draw_header(oled, title, anim_tick, demo_mode)
                for x in range(len(osc_samples) - 1):
                    oled.line(x, osc_samples[x], x + 1, osc_samples[x + 1], 1)
                
                # Draw sidebar separator and context
                oled.vline(82, 12, 52, 1)
                oled.text(f"Max:{v_max:.1f}V", 85, 14)
                oled.text(f"Min:{v_min:.1f}V", 85, 24)
                oled.text(f"Vpp:{v_pp:.1f}V", 85, 34)
                
                # Format Frequency string
                if f_val >= 1000.0:
                    f_str = f"{f_val/1000.0:.1f}k"
                else:
                    f_str = f"{int(f_val)}"
                oled.text(f"F:{f_str}Hz", 85, 48)
                oled.show()
                
            elif screen == 4:
                # SCREEN 4: GPIO STATE MONITOR / LOGIC ANALYZER PROBE
                oled.fill(0)
                if gpio_sel_idx == -1:
                    draw_header(oled, "[ GPIO MONITOR ]", anim_tick, demo_mode)

                    # Draw visual board map layout
                    oled.rect(36, 14, 56, 48, 1)
                    # USB Connector at top
                    oled.rect(48, 11, 32, 4, 1)
                    # Onboard chip in the center
                    oled.rect(54, 29, 20, 18, 1)
                    oled.text("RP", 60, 34, 1)

                    # List of left pins
                    left_pins = [
                        (26, "D0", 16),
                        (27, "D1", 24),
                        (28, "D2", 32),
                        (29, "D3", 40),
                        (6, "D4", 48),
                        (7, "D5", 56)
                    ]
                    for p_num, label, y in left_pins:
                        if demo_mode and p_num in (26, 28, 0, 1):
                            val = 1 if ((anim_tick // (p_num + 2)) % 2 == 0) else 0
                        else:
                            val = Pin(p_num).value()
                        
                        # Label text
                        oled.text(label, 4, y - 4, 1)
                        # Connection line to board header
                        oled.line(25, y, 36, y, 1)
                        # Status indicator circle
                        if val:
                            oled.fill_rect(20, y - 2, 5, 5, 1)
                        else:
                            oled.rect(20, y - 2, 5, 5, 1)

                    # List of right pins
                    right_pins = [
                        (None, "3V", 16, True),
                        (3, "D10", 24, False),
                        (4, "D9", 32, False),
                        (2, "D8", 40, False),
                        (1, "D7", 48, False),
                        (0, "D6", 56, False)
                    ]
                    for p_num, label, y, is_power in right_pins:
                        if is_power:
                            val = 1
                        elif demo_mode and p_num in (26, 28, 0, 1):
                            val = 1 if ((anim_tick // (p_num + 2)) % 2 == 0) else 0
                        else:
                            val = Pin(p_num).value()
                        
                        # Label text
                        x_lbl = 104 if len(label) == 3 else 110
                        oled.text(label, x_lbl, y - 4, 1)
                        # Connection line to board header
                        oled.line(92, y, 96, y, 1)
                        # Status indicator circle
                        if val:
                            oled.fill_rect(97, y - 2, 5, 5, 1)
                        else:
                            oled.rect(97, y - 2, 5, 5, 1)
                else:
                    # Individual Logic Probe Waveform screen
                    p_num, label = PINS_TO_MONITOR[gpio_sel_idx]
                    draw_header(oled, f"PROBE {label} (GP{p_num})", anim_tick, demo_mode)

                    # Draw logic level scrolling waveforms
                    for x in range(len(logic_samples) - 1):
                        y1 = logic_samples[x]
                        y2 = logic_samples[x + 1]
                        oled.line(x + 4, y1, x + 5, y2, 1)
                        if y1 != y2:  # vertical transition line
                            oled.vline(x + 4, min(y1, y2), abs(y1 - y2) + 1, 1)
                    
                    # Top/Bottom lines representing logic limits
                    oled.hline(4, 24, 76, 1)  # High line
                    oled.hline(4, 48, 76, 1)  # Low line
                    oled.text("H", 82, 21)
                    oled.text("L", 82, 45)
                    
                    # Sidebar stats in the 5x7 font (the 8x8 "State:" ran off past x=128).
                    oled.vline(94, 11, 53, 1)
                    if demo_mode:
                        cur_val = 1 if logic_samples[-1] == 24 else 0
                    else:
                        cur_val = Pin(p_num).value()
                    text_small(oled, "STATE", 97, 13)
                    text_small(oled, "HIGH" if cur_val == 1 else "LOW", 97, 23)
                    text_small(oled, "tap=", 97, 46)
                    text_small(oled, "back", 97, 55)
                oled.show()
                
            elif screen == 5:
                # SCREEN 5: PWM SIGNAL LAB (Gen + Meter)
                oled.fill(0)
                draw_header(oled, "[ PWM LAB ]", anim_tick, demo_mode)

                # Top Box: PWM Generator (GP28 / D2)
                freq = GEN_FREQS[gen_idx] if not demo_mode else 1000
                freq_str = f"{freq}Hz" if freq > 0 else "OFF"
                oled.text(f"OUT D2: {freq_str}", 4, 13)
                
                # Bottom Box: PWM Meter (GP2 / D8)
                if pwm_freq_val > 0.0:
                    if pwm_freq_val >= 1000.0:
                        meter_freq_str = f"{pwm_freq_val/1000.0:.1f}kHz"
                    else:
                        meter_freq_str = f"{pwm_freq_val:.0f}Hz"
                    meter_duty_str = f"{pwm_duty_val:.1f}%"
                else:
                    meter_freq_str = "0Hz"
                    meter_duty_str = "100%" if meter_pin.value() == 1 else "0%"
                oled.text(f"IN D8 : {meter_freq_str}", 4, 28)
                oled.text(f"Duty  : {meter_duty_str}", 4, 40)
                oled.text("D2->PWM  D8->Meter", 4, 54)
                
                # Simple generator animated block on top right
                oled.rect(98, 14, 26, 14, 1)
                if freq == 0:
                    oled.hline(100, 21, 22, 1)
                else:
                    for x in range(100, 122):
                        y = 17 if ((x + anim_tick * 2) // 3) % 2 == 0 else 25
                        oled.pixel(x, y, 1)
                        if (x + anim_tick * 2) % 3 == 0:
                            oled.vline(x, 17, 9, 1)
                oled.show()
                
            elif screen == 6:
                # SCREEN 6: COMMAND MACRO SENDER
                oled.fill(0)
                draw_header(oled, "[ MACRO SENDER ]", anim_tick, demo_mode)

                start_item = max(0, macro_idx - 4)
                if start_item + 5 > len(macro_items):
                    start_item = len(macro_items) - 5
                if start_item < 0:
                    start_item = 0

                for idx in range(start_item, min(start_item + 5, len(macro_items))):
                    y = 11 + (idx - start_item) * 10
                    prefix = "> " if idx == macro_idx else "  "
                    oled.text(prefix + macro_items[idx], 4, y)
                
                if macro_confirm_pending:
                    rem_t = max(0, time.ticks_diff(macro_confirm_t, time.ticks_ms()))
                    bar_w = int(128 * (rem_t / 2000))
                    oled.hline(0, 63, bar_w, 1)
                oled.show()
                
            elif screen == 7:
                # SCREEN 7: BAUD RATE SELECTOR
                oled.fill(0)
                draw_header(oled, "[ BAUD SELECT ]", anim_tick, demo_mode)

                start_item = max(0, menu_idx - 4)
                if start_item + 5 > len(menu_items):
                    start_item = len(menu_items) - 5
                if start_item < 0:
                    start_item = 0

                for idx in range(start_item, min(start_item + 5, len(menu_items))):
                    y = 11 + (idx - start_item) * 10
                    prefix = "> " if idx == menu_idx else "  "
                    item_text = menu_items[idx]
                    if idx > 0:
                        item_text += " bps"
                        if int(menu_items[idx]) == BAUDRATE:
                            item_text += " *"
                    oled.text(prefix + item_text, 4, y)
                
                if baud_confirm_pending:
                    rem_t = max(0, time.ticks_diff(baud_confirm_t, time.ticks_ms()))
                    bar_w = int(128 * (rem_t / 2000))
                    oled.hline(0, 63, bar_w, 1)
                oled.show()
                
            elif screen == 8:
                # SCREEN 8: DEMO TRIGGER MENU
                oled.fill(0)
                draw_header(oled, "[ DEMO TRIGGER ]", anim_tick, demo_mode)

                for idx, item in enumerate(demo_trigger_items):
                    y = 14 + idx * 14
                    prefix = "> " if idx == demo_trigger_idx else "  "
                    oled.text(prefix + item, 4, y)
                
                if demo_trigger_confirm_pending:
                    rem_t = max(0, time.ticks_diff(demo_trigger_confirm_t, time.ticks_ms()))
                    bar_w = int(128 * (rem_t / 2000))
                    oled.hline(0, 63, bar_w, 1)
                oled.show()
                
            elif screen == 9:
                # SCREEN 9: SD CARD FILE EXPLORER
                oled.fill(0)
                if sd_view_active:
                    # In the file viewer the slim header doubles as the filename bar, so the
                    # old separate "VIEW:" sub-header is gone -> more rows for file content.
                    draw_header(oled, ("/" + sd_view_file)[:20], anim_tick, demo_mode, show_rec=True)
                    lines = get_file_lines("/sd/" + sd_view_file, sd_view_offset, num_lines=5)
                    if not lines:
                        text_small(oled, "(end of file)", 2, 12)
                    else:
                        # 5x7 font: 5 rows of 21 cols (was 4 rows of 16 in the 8x8 font).
                        for idx, line in enumerate(lines):
                            text_small(oled, line[:21], 2, 11 + idx * 8)
                    text_small(oled, "tap = scroll down", 2, 55)
                else:
                    draw_header(oled, "[ SD EXPLORER ]", anim_tick, demo_mode, show_rec=True)
                    start_item = max(0, sd_menu_idx - 4)
                    if start_item + 5 > len(sd_menu_items):
                        start_item = len(sd_menu_items) - 5
                    if start_item < 0:
                        start_item = 0

                    for idx in range(start_item, min(start_item + 5, len(sd_menu_items))):
                        y = 11 + (idx - start_item) * 10
                        prefix = "> " if idx == sd_menu_idx else "  "
                        item_text = sd_menu_items[idx]
                        if len(item_text) > 14:
                            item_text = item_text[:11] + "..."
                        oled.text(prefix + item_text, 4, y)

                    if sd_confirm_pending:
                        rem_t = max(0, time.ticks_diff(sd_confirm_t, time.ticks_ms()))
                        bar_w = int(128 * (rem_t / 2000))
                        oled.hline(0, 63, bar_w, 1)
                oled.show()

            elif screen == 10:
                # SCREEN 10: WATCHDOG -- the flight-recorder status + the target's last words.
                oled.fill(0)
                draw_header(oled, "[ WATCHDOG ]", anim_tick, demo_mode, show_rec=True)
                if wedge_active:
                    blink = (anim_tick // 3) % 2 == 0
                    oled.fill_rect(0, 11, 128, 9, 1 if blink else 0)
                    text_small(oled, ("WEDGE @ " + wedge_since)[:21], 4, 12, 0 if blink else 1)
                elif ever_active:
                    sil = time.ticks_diff(time.ticks_ms(), last_rx_t) // 1000
                    text_small(oled, "Target LIVE   idle %ds" % sil, 4, 12)
                else:
                    text_small(oled, "Target: waiting...", 4, 12)
                text_small(oled, "watch %d terms  hits:%d" % (len(watch_terms), watch_hits), 4, 22)
                if watch_last:
                    text_small(oled, watch_last[:21], 4, 31)
                oled.hline(0, 40, 128, 1)
                text_small(oled, "freeze-frame (tap=ack)", 4, 42)
                ff = bytes(freeze_frame).decode("utf-8", "replace").replace("\n", " ").replace("\r", " ")
                text_small(oled, ff[-21:] if ff else "(nothing captured yet)", 4, 52)
                oled.show()

            elif screen == 11:
                # SCREEN 11: THROUGHPUT -- a live bytes/sec sparkline + now/peak/total.
                oled.fill(0)
                draw_header(oled, "[ THROUGHPUT ]", anim_tick, demo_mode, show_rec=True)
                cur = tp_hist[-1] if tp_hist else 0
                text_small(oled, "now %s/s" % fmt_bytes(cur), 4, 12)
                text_small(oled, "peak %s/s" % fmt_bytes(tp_peak), 66, 12)
                text_small(oled, "total %sB" % fmt_bytes(rx_bytes + tx_bytes), 4, 22)
                oled.rect(2, 31, 124, 30, 1)
                draw_sparkline(oled, tp_hist[-60:] if tp_hist else [0], 5, 33, 118, 26, 1, baseline=True)
                oled.show()

    except Exception as err:
        # Per-iteration recovery -- the bridge stays alive through transient faults.
        set_leds(True, False, False)
        try:
            es = str(err)
        except Exception:
            es = "?"
        last_loop_err = es[:40]
        print("loop fault:", es)
        nowf = time.ticks_ms()
        if time.ticks_diff(nowf, last_err_t) > 5000:
            loop_err_count = 0          # faults far apart -> not a storm; reset the counter
        loop_err_count += 1
        last_err_t = nowf
        # Stamp the fault into the black box (if recording) so a post-mortem sees it.
        if logging_active:
            try:
                log_uart_data("\n--- FAULT %s %s ---\n" % (log_stamp(), es))
                flush_log_buffer()
            except Exception:
                pass
        beep(700, 50)
        # A storm of back-to-back faults is a deterministic crash; a clean reboot (with a
        # visible countdown, so it never looks bricked) beats spinning on the same error.
        if loop_err_count >= 8:
            print("fault storm -> rebooting")
            for n in range(3, 0, -1):
                if oled_present:
                    try:
                        oled.fill(0)
                        oled.rect(0, 0, 128, 64, 1)
                        oled.text("BRIDGE FAULT", 18, 8)
                        oled.text(es[:18], 4, 26)
                        oled.text("Rebooting %d.." % n, 18, 46)
                        oled.show()
                    except Exception:
                        pass
                beep(500, 60)
                time.sleep_ms(700)
            reset()
        # Recoverable: a brief red flash, then carry on watching the target.
        time.sleep_ms(120)
        set_leds(False, False, True)
