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

def trigger_transition_wipe():
    if oled_present and oled is not None:
        try:
            for x in (32, 64, 96, 128):
                oled.fill_rect(0, 0, x, 64, 0)
                if x < 128:
                    oled.vline(x, 0, 64, 1)
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
# 0: Mascot/Stats, 1: Sniffer, 2: I2C Scanner, 3: Oscilloscope,
# 4: GPIO Monitor, 5: PWM Gen/Meter, 6: Macro Sender, 7: Baud rate menu,
# 8: Demo Trigger menu
screen = 0  
tx_bytes = 0
rx_bytes = 0

# ----------------- UART Logger State -----------------
logging_active = False
log_buffer = bytearray()
last_log_write_t = 0

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
    global log_buffer, last_log_write_t, logging_active
    if len(log_buffer) == 0 or not sd_mounted:
        return
    try:
        import os
        ensure_sd_pins()
        with open("/sd/uart_log.txt", "ab") as f:
            f.write(log_buffer)
        log_buffer = bytearray()
        last_log_write_t = time.ticks_ms()
    except Exception as e:
        print("Logger write failed, stopping logger:", e)
        logging_active = False
        log_buffer = bytearray()
        beep(1000, 200)

def draw_rec_indicator(oled, anim_tick):
    if logging_active and (anim_tick // 4) % 2 == 0:
        oled.fill_rect(92, 4, 4, 4, 1)
        oled.text("REC", 98, 2)

# Demo Mode status
demo_mode = bridge_cfg.get("demo_on_boot", False)
last_demo_switch_t = time.ticks_ms() if demo_mode else 0

# Terminal sniffer history
sniffer_mode = 0  # 0: ASCII scrolling, 1: Hex dump
terminal_lines = ["", "", "", "", ""]
hex_history = []  # Last 20 bytes for hex dump

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
        terminal_lines = terminal_lines[-5:]
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
        
        if len(terminal_lines[-1]) >= 16:
            terminal_lines.append("")
            terminal_lines = terminal_lines[-5:]
        terminal_lines[-1] += c

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
    terminal_lines = ["", "", "", "", ""]
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
            sd_view_offset += 4
            lines = get_file_lines("/sd/" + sd_view_file, sd_view_offset, num_lines=4)
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
    
    # Switch screen (10 screens total)
    screen = (screen + 1) % 10
    
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
    global BAUDRATE, macro_items, bridge_cfg, demo_mode, last_demo_switch_t, screen, tx_bytes, rx_bytes, logging_active
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

            # 5. Toggle UART Logging
            if "logging" in cfg:
                logging_active = bool(cfg["logging"])
                if logging_active:
                    mount_sd()
                else:
                    flush_log_buffer()
                changed = True
            
            if changed:
                save_bridge_cfg(bridge_cfg)
                # Success notification
                beep(2500, 40)
                time.sleep_ms(40)
                beep(3000, 40)
                
                # Print response back to host
                res = {"status": "OK", "baud": BAUDRATE, "macros": bridge_cfg["macros"], "demo": demo_mode, "demo_on_boot": bridge_cfg.get("demo_on_boot", False), "logging": logging_active}
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
print("XIAO RP2040 Interactive USB-UART Multi-Tool Active!")
print("Controls:")
print("  - SHORT Press: Cycle values / Clear stats / Toggle views")
print("  - LONG Press  (>0.5s): Cycle to next tool/app")
print("================================================")

try:
    while True:
        now_ms = time.ticks_ms()
        
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
                screen = (screen + 1) % 10
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
                        if len(hex_history) > 20:
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
                logging_active = True
                beep(2400, 30)
                time.sleep_ms(50)
                beep(2800, 30)
                prepare_sd_explorer()
            elif item_text == "[STOP LOGGING]":
                flush_log_buffer()
                logging_active = False
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
                        sys.stdout.buffer.write(data)
                        rx_bytes += len(data)
                        log_uart_data(data)
                        last_activity_t = time.ticks_ms()
                        last_type = "RX"
                        for b in data:
                            add_to_terminal(b)
                            # Feed hex history
                            hex_history.append(b)
                            if len(hex_history) > 20:
                                hex_history.pop(0)
                        set_leds(False, True, False)
        
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
                oled.text("[ UART BRIDGE ]", 4, 2)
                if demo_mode:
                    oled.text("DEMO", 100, 2)
                else:
                    draw_rec_indicator(oled, anim_tick)
                oled.hline(0, 11, 128, 1)
                oled.text(f"Baud:{BAUDRATE}", 4, 16)
                oled.text(f"TX:  {fmt_bytes(tx_bytes)}B", 4, 28)
                oled.text(f"RX:  {fmt_bytes(rx_bytes)}B", 4, 40)
                oled.text("USB <-> UART", 4, 52)
                draw_cat(oled, is_active, anim_tick, last_type)
                oled.show()
                
            elif screen == 1:
                # SCREEN 1: SNIFFER TERMINAL
                oled.fill(0)
                title = "[ HEX SNIFFER ]" if sniffer_mode == 1 else "[ UART RX LOG ]"
                oled.text(title, 6, 2)
                if demo_mode:
                    oled.text("DEMO", 100, 2)
                else:
                    draw_rec_indicator(oled, anim_tick)
                oled.hline(0, 11, 128, 1)
                if sniffer_mode == 0:
                    for idx, line in enumerate(terminal_lines):
                        oled.text(line, 4, 14 + idx * 10)
                else:
                    # Formatted hex dump: 5 lines, 4 bytes each
                    for idx in range(5):
                        start = idx * 4
                        chunk = hex_history[start:start+4]
                        if not chunk:
                            break
                        hex_str = " ".join(f"{b:02X}" for b in chunk)
                        hex_str += " " * (11 - len(hex_str))
                        ascii_str = "".join(chr(b) if 32 <= b <= 126 else "." for b in chunk)
                        oled.text(f"{hex_str} {ascii_str}", 4, 14 + idx * 10)
                oled.show()
                
            elif screen == 2:
                # SCREEN 2: I2C SCANNER
                oled.fill(0)
                oled.text("[ I2C SCANNER ]", 6, 2)
                if demo_mode:
                    oled.text("DEMO", 100, 2)
                oled.hline(0, 11, 128, 1)
                
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
                    oled.text("Scanning...", 4, 28)
                else:
                    if len(i2c_devices) <= 4:
                        for idx, addr in enumerate(i2c_devices):
                            name = KNOWN_I2C.get(addr, "Dev")
                            oled.text(f"0x{addr:02X}:{name[:7]}", 4, 14 + idx * 12)
                    else:
                        # Draw list of addresses in 2 columns
                        for idx, addr in enumerate(i2c_devices[:10]):
                            col = idx // 5
                            row = idx % 5
                            x = 4 + col * 40
                            y = 14 + row * 10
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
                oled.text(title, 4, 2)
                if demo_mode:
                    oled.text("DEMO", 100, 2)
                oled.hline(0, 11, 128, 1)
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
                    oled.text("[ GPIO MONITOR ]", 4, 2)
                    if demo_mode:
                        oled.text("DEMO", 100, 2)
                    oled.hline(0, 11, 128, 1)
                    
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
                    oled.text(f"[ PROBE {label} (GP{p_num}) ]", 4, 2)
                    if demo_mode:
                        oled.text("DEMO", 100, 2)
                    oled.hline(0, 11, 128, 1)
                    
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
                    
                    # Sidebar Stats
                    oled.vline(94, 12, 52, 1)
                    if demo_mode:
                        cur_val = 1 if logic_samples[-1] == 24 else 0
                    else:
                        cur_val = Pin(p_num).value()
                    oled.text("State:", 98, 16)
                    oled.text("HIGH" if cur_val == 1 else "LOW", 98, 28)
                    oled.text("Press", 98, 44)
                    oled.text("BACK", 98, 54)
                oled.show()
                
            elif screen == 5:
                # SCREEN 5: PWM SIGNAL LAB (Gen + Meter)
                oled.fill(0)
                oled.text("[ PWM LAB ]", 6, 2)
                if demo_mode:
                    oled.text("DEMO", 100, 2)
                oled.hline(0, 11, 128, 1)
                
                # Top Box: PWM Generator (GP28 / D2)
                freq = GEN_FREQS[gen_idx] if not demo_mode else 1000
                freq_str = f"{freq}Hz" if freq > 0 else "OFF"
                oled.text(f"OUT D2: {freq_str}", 4, 16)
                
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
                oled.text(f"IN D8 : {meter_freq_str}", 4, 32)
                oled.text(f"Duty  : {meter_duty_str}", 4, 44)
                oled.text("D2->PWM  D8->Meter", 4, 55)
                
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
                oled.text("[ MACRO SENDER ]", 6, 2)
                if demo_mode:
                    oled.text("DEMO", 100, 2)
                oled.hline(0, 11, 128, 1)
                
                start_item = max(0, macro_idx - 3)
                if start_item + 4 > len(macro_items):
                    start_item = len(macro_items) - 4
                if start_item < 0:
                    start_item = 0
                
                for idx in range(start_item, min(start_item + 4, len(macro_items))):
                    y = 16 + (idx - start_item) * 12
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
                oled.text("[ BAUD SELECT ]", 6, 2)
                if demo_mode:
                    oled.text("DEMO", 100, 2)
                oled.hline(0, 11, 128, 1)
                
                start_item = max(0, menu_idx - 3)
                if start_item + 4 > len(menu_items):
                    start_item = len(menu_items) - 4
                if start_item < 0:
                    start_item = 0
                
                for idx in range(start_item, min(start_item + 4, len(menu_items))):
                    y = 16 + (idx - start_item) * 12
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
                oled.text("[ DEMO TRIGGER ]", 4, 2)
                if demo_mode:
                    oled.text("DEMO", 100, 2)
                oled.hline(0, 11, 128, 1)
                
                for idx, item in enumerate(demo_trigger_items):
                    y = 18 + idx * 14
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
                oled.text("[ SD EXPLORER ]", 4, 2)
                if demo_mode:
                    oled.text("DEMO", 100, 2)
                else:
                    draw_rec_indicator(oled, anim_tick)
                oled.hline(0, 11, 128, 1)
                
                if sd_view_active:
                    title = f"/{sd_view_file[:10]}"
                    oled.text(f"VIEW: {title}", 4, 14)
                    oled.hline(0, 23, 128, 1)
                    
                    lines = get_file_lines("/sd/" + sd_view_file, sd_view_offset, num_lines=4)
                    if not lines:
                        oled.text("(end of file)", 4, 32)
                    else:
                        for idx, line in enumerate(lines):
                            oled.text(line[:16], 4, 26 + idx * 9)
                    oled.text("ShortPress: scroll", 4, 56)
                else:
                    start_item = max(0, sd_menu_idx - 3)
                    if start_item + 4 > len(sd_menu_items):
                        start_item = len(sd_menu_items) - 4
                    if start_item < 0:
                        start_item = 0
                        
                    for idx in range(start_item, min(start_item + 4, len(sd_menu_items))):
                        y = 16 + (idx - start_item) * 12
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

except Exception as err:
    set_leds(True, False, False)
    print("Bridge crashed:", err)
    if oled_present:
        try:
            oled.fill(0)
            oled.rect(0, 0, 128, 64, 1)
            oled.text("BRIDGE ERROR!", 6, 6)
            err_str = str(err)
            oled.text(err_str[:15], 6, 22)
            oled.text(err_str[15:30], 6, 36)
            oled.text("Reconnecting...", 6, 50)
            oled.show()
        except Exception:
            pass
    while True:
        time.sleep_ms(1000)
