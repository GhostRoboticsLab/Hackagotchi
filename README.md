# PocketTap 🛠️ — a black-box flight recorder for dev boards that go dark

**PocketTap** is custom MicroPython firmware that turns a **Seeed Studio XIAO RP2040** on its **base expansion board** into a pocket black-box recorder and debugging suite for *other* dev boards.

The pitch: a target board's own debug channel (USB-CDC, the REPL) goes dark exactly when you need it most — during an e-paper refresh, a TLS handshake, or a crash. PocketTap is a *separate* MCU with its own USB, a hardware UART tap, an OLED, a battery-backed RTC, and a microSD recorder, so it keeps **watching and driving** the target while that board is wedged — logging autonomously to SD with a wall-clock timestamp, on a screen, with no host attached. It's a flight recorder, not a tethered dumb adapter.

> Built on a Seeed XIAO RP2040; runs as a single `main.py`. Flash with `mpremote connect <port> cp pockettap/main.py :main.py` then `reset`.

---

## 🌟 Visual Layout & Features

1. **USB-to-UART Bridge (Screen 0)**:
   * Bridges USB-CDC with physical UART0.
   * **Stats panel**: Baud, TX bytes, RX bytes, and **uptime** down the left column.
   * **Sleeping/Idle Cat Mascot**: A pixel cat curls up to sleep and floats `"z Z Z"` characters if there is no data flow.
   * **Active Data**: On transfer, the cat wakes up, opens its eyes, moves its mouth, and displays a flashing `TX` or `RX` speech bubble.
   * **Short Press**: Clears current TX/RX byte statistics.
2. **Terminal Sniffer Log (Screen 1)**:
   * Displays a rolling **6-line** terminal log of incoming raw ASCII data (21 cols/line in the compact 5×7 font).
   * **Short Press**: Toggles between **ASCII Text Mode** (scrolling letters) and **Hex Dump Mode** (**6 rows × 5 bytes** with an ASCII gutter: `HH HH HH HH HH AAAAA`).
3. **I2C Bus Scanner (Screen 2)**:
   * Scans the I2C bus (GP6/GP7) in the background every 1.5 seconds. Identifies known sensors (e.g. BMP280, MPU6050, SHT30) and lists their addresses.
   * **Short Press**: Triggers an immediate re-scan.
4. **Analog Oscilloscope (Screen 3)**:
   * Plots a real-time scrolling waveform of the voltage sampled from pin **A0 (GP26)** (0V to 3.3V).
   * **Calculated Waveform Stats**: Displays **Max Voltage (Vmax)**, **Min Voltage (Vmin)**, **Peak-to-Peak (Vpp)**, and **Signal Frequency (Hz/kHz)** using mathematical zero-crossing edge calculations.
   * **Short Press**: Cycles through timebases and freeze states:
     - `1ms/div` (100us sample bursts, total sweep = 8ms)
     - `10ms/div` (1ms sample bursts, total sweep = 80ms)
     - `100ms/div` (10ms samples, background sweep = 800ms)
     - `FREEZE` (holds the last captured sweep snapshot)
5. **GPIO State Monitor (Screen 4)**:
   * Displays a real-time high/low status grid of all 11 physical pins on the XIAO header.
   * **Short Press**: Moves the cursor (`>`) to highlight a specific pin.
   * **Interactive Logic Probe**: If you let the cursor stay on a pin, it enters a dedicated **Logic Analyzer Probe screen** that draws a 1-bit scrolling waveform chart (High/Low) over time for that pin. Short-press inside the probe screen to return to the GPIO grid.
6. **PWM Signal Lab (Screen 5)**:
   * **PWM Generator (D2 / GP28)**: Outputs a 50% duty-cycle square wave on pin **D2 (GP28)**. Cycles frequencies on short-press: `OFF`, `50Hz`, `100Hz`, `500Hz`, `1kHz`, `5kHz`, `10kHz`, `20kHz`.
   * **PWM/Duty Meter (D8 / GP2)**: Uses high-speed hardware input timers (`time_pulse_us`) on pin **D8 (GP2)** to measure and display the frequency and duty cycle of any incoming PWM signal in real-time.
7. **Command Macro Sender (Screen 6)**:
   * Sends customizable serial macros (loaded from `bridge_cfg.json`) to the target device.
   * **Demo Mode Trigger**: Select **DEMO MODE** at the bottom of the list and wait 2 seconds to launch the Technical Demo.
   * **Short Press**: Cycles through options.
   * **Auto-Apply**: Leaving the cursor on a macro for **2 seconds** transmits the string (`MACRO_TEXT\r\n`) and returns to Screen 0.
8. **Baud Rate Selector (Screen 7)**:
   * Selects the active bridge speed (`9600`, `19200`, `38400`, `57600`, `115200`).
   * **Short Press**: Cycles through options.
   * **Auto-Apply**: Leaving the cursor on an option for **2 seconds** re-initializes the UART and returns to Screen 0.
9. **Demo Trigger App (Screen 8)**:
   * Instantly starts the technical demo or sets up boot configuration settings.
   * **Short Press**: Cycles through options:
     - `START NOW`: Starts the Demo Mode immediately.
     - `BOOT & RUN`: Persistently configures the board to boot directly into Demo Mode, then soft-resets the board.
     - `< CANCEL`: Cancels and returns to Screen 0.
   * **Auto-Apply**: Leaving the cursor on an option for **2 seconds** executes the action.
10. **SD Explorer & Black Box (Screen 9)**:
    * Mounts a microSD (SPI0: CS **D2/GP28**, SCK **D8/GP2**, MOSI **D9/GP3**, MISO **D10/GP4**) and browses files; the **file viewer** shows 5 lines × 21 cols in the 5×7 font (short-press scrolls).
    * **Black-box recorder**: `[START LOGGING]` opens an auto-incrementing session file (`log_NNN.txt`) and streams the raw UART telemetry to it, buffered (flush at 64 B / 500 ms). Each session writes a timestamped header and a **60 s heartbeat** marker — so if the target goes silent (a wedge) the last heartbeat bounds when it died. A write error stops the logger and buzzes.
    * **Autonomous start**: set `{"cfg":{"log_on_boot":true}}` and the board records from power-on — an untethered/overnight capture with nobody to press START.
    * **Timestamps**: headers/heartbeats use real wall-clock time when the expansion board's **PCF8563 RTC (I2C 0x51)** has a good **CR1220** coin cell; with no/dead cell it falls back to uptime (`+Ns`). The target's own `dbg.log` markers already carry relative-ms times, so the session header is the absolute anchor.
    * ⚠️ The SD shares pins with the **PWM Lab** (D2/GP28, D8/GP2) — don't run that screen while logging. The UART tap (GP0/GP1) is unaffected, so logging + bridging coexist fine.
11. **Watchdog — Flight Recorder (Screen 10)**: *the black-box differentiator.* Three always-on background monitors (they run no matter which screen you're viewing) surfaced on one status page:
    * **Wedge detector**: once the target has been seen alive, going silent for **>8 s** is flagged as a *wedge* — the screen shows `WEDGE @ <time>`, a blinking `!` badge appears on every screen, the buzzer drops a low alarm, and the moment is stamped into the black-box log.
    * **Freeze-frame**: the target's **last ~96 bytes** before it went dark are kept and shown — its dying words. Captured into the log alongside the wedge stamp.
    * **Trigger watch**: each completed RX line is scanned for armed substrings (default `ERROR`, `FATAL`, `Traceback`, `panic`, `BUSY-TIMEOUT`). A match chirps, flashes, marks the log (`--- ALERT … ---`), and increments the on-screen hit counter. Set terms with `{"cfg":{"watch":["ERROR","oops"]}}` (≤ 8 terms).
    * **Short press** = acknowledge (clears the hit count + the wedge flag).
12. **Throughput Meter (Screen 11)**: a live **bytes/sec** sparkline (auto-scaled, 60 s window) with `now` / `peak` rates and a running `total`. **Short press** resets the meter.

---

## 🕹️ System Controls

*   **SHORT PRESS (< 400ms)**: Cycles options, clears stats, toggles views, enters logic probes, or acknowledges alerts.
*   **LONG PRESS (>= 500ms)**: Cycles to the **next tool** through all 12 screens (0 → 1 → … → 11 → 0), each with a distinct animated transition.
*   **Buzzer Feedback**: 
    *   *Click*: Plays on button press.
    *   *Rising pitch slide*: Plays when switching screens.
    *   *Success chime*: Plays when a Baud rate is applied, a Macro is sent, or config is updated.
    *   *Flat click*: Plays on cancellations.

---

## 🔌 Pin Configuration & Wiring

Connect the bridge to your target microcontroller (e.g. Raspberry Pi Pico W):

| Expansion Shield Pin | Direction | Target Pin | Function |
| :--- | :--- | :--- | :--- |
| **D6** (XIAO TX / GP0) | $\rightarrow$ | Target **RX** | UART Transmit |
| **D7** (XIAO RX / GP1) | $\leftarrow$ | Target **TX** | UART Receive |
| **GND** | $\leftrightarrow$ | Target **GND** | Common Ground Reference |
| **A0** (GP26) | $\leftarrow$ | Test Signal | Oscilloscope Probe Input (0V–3.3V) |
| **D2** (GP28) | $\rightarrow$ | Test Input | PWM Signal Generator Output |
| **D8** (GP2) | $\leftarrow$ | Test Signal | PWM & Duty Cycle Meter Input |

---

## 💻 Host JSON Configuration Mode

You can configure and **drive** the bridge on-the-fly from your host machine over USB. Any JSON line (`{...}`) is intercepted as a host command; anything else falls through to the target unchanged. `{"cfg": ...}` is saved persistently to `bridge_cfg.json`; two non-persistent commands let a companion app/script control and monitor the bridge over the same port — the cheapest fix for the single-button UX:

- **Jump to any screen** — `{"screen": 4}` (0…11) switches the bridge screen and replies `{"status":"OK","screen":4}`. So you don't have to long-press through every tool to reach one.
- **Query status** — `{"q":"status"}` replies with a one-line snapshot (no state change): `screen`, `baud`, `tx`/`rx` byte counts, `logging`, `log_file`, `sd`, throughput `tp_peak`, `demo`. Lets a host script watch the recorder without reading the OLED.

```bash
echo '{"screen": 3}'    > /dev/cu.usbmodem21201   # jump to the Oscilloscope screen
echo '{"q":"status"}'   > /dev/cu.usbmodem21201   # -> {"status":"OK","screen":3,"rx":...,"sd":true,...}
```

#### Examples:
1.  **Configure Custom Macros**:
    ```bash
    echo '{"cfg": {"macros": ["AT", "AT+GMR", "PING", "RESET"]}}' > /dev/cu.usbmodem21201
    ```
2.  **Adjust Baudrate**:
    ```bash
    echo '{"cfg": {"baud": 9600}}' > /dev/cu.usbmodem21201
    ```
3.  **Toggle Demo Mode**:
    ```bash
    # Enable Technical Demo Mode:
    echo '{"cfg": {"demo": true}}' > /dev/cu.usbmodem21201
    
    # Disable Technical Demo Mode:
    echo '{"cfg": {"demo": false}}' > /dev/cu.usbmodem21201
    ```
4.  **Configure Reboot to Demo**:
    ```bash
    # Configure board to reboot directly into Demo Mode:
    echo '{"cfg": {"demo_on_boot": true}}' > /dev/cu.usbmodem21201
    
    # Disable Demo Mode on boot:
    echo '{"cfg": {"demo_on_boot": false}}' > /dev/cu.usbmodem21201
    ```
5.  **Black box — start/stop recording, and auto-start on boot**:
    ```bash
    # Start a new session log now (log_NNN.txt on the SD):
    echo '{"cfg": {"logging": true}}'  > /dev/cu.usbmodem21201
    echo '{"cfg": {"logging": false}}' > /dev/cu.usbmodem21201

    # Record automatically from power-on (untethered black box):
    echo '{"cfg": {"log_on_boot": true}}'  > /dev/cu.usbmodem21201
    echo '{"cfg": {"log_on_boot": false}}' > /dev/cu.usbmodem21201
    ```
6.  **Trigger watch — beep/flag when the target says something**:
    ```bash
    # Up to 8 substrings; each completed RX line is scanned for them.
    echo '{"cfg": {"watch": ["ERROR", "FATAL", "Guru Meditation"]}}' > /dev/cu.usbmodem21201
    echo '{"cfg": {"watch": []}}' > /dev/cu.usbmodem21201   # disable
    ```
7.  **Hardware watchdog — auto-reboot on a true CPU hang (untethered)**:
    ```bash
    # Armed at the NEXT boot (kept off by default so it can't trip a slow reflash).
    echo '{"cfg": {"wdt": true}}'  > /dev/cu.usbmodem21201
    echo '{"cfg": {"wdt": false}}' > /dev/cu.usbmodem21201
    ```
The board will chime and return a JSON status line confirming the updated config
(it includes `logging`, `log_on_boot`, `log_file`, `watch`, and `wdt`).

---

## 🎮 Driving the PicoInky (reverse channel)

The bridge transmits to the target's RX (**D6 / GP0 → Pico GP1**), and PicoInky firmware
(≥ the stock-MicroPython base) listens there for **single-character control commands** —
a refresh-immune control plane that works *during* an e-paper refresh or TLS fetch, when a
USB raw-REPL break-in would fail. Bytes are dispatched by `App._drain_uart_cmds`; acks come
back as `cmd ...` lines on the telemetry stream (visible in the Sniffer screen):

| Key | Action |
| :-- | :--- |
| `n` / `p` | Next / previous page |
| `r` | Mark all feeds due → refetch on the next poll |
| `g` | `gc.collect()` then report free / allocated RAM |
| `d` | Dump a compact state snapshot (page, key list, free RAM) |
| `R` | Reboot the Pico |
| `B` | Drop the Pico into **BOOTSEL** (UF2 bootloader) for a remote flash — works when USB-CDC is wedged and no one can press the button; the host then runs `picotool load` over the resulting BOOTSEL USB |

Send them either from the host (`echo -n n > /dev/cu.usbmodem21201`) or straight from the
bridge by loading them as **macros** (Screen 6): `{"cfg": {"macros": ["n", "p", "r", "g", "d"]}}`.

### Host-side telemetry tools (in the PicoInky repo's `tools/`)

Two Mac-side helpers turn the raw tap stream into something you can actually read. Run them
with the project venv (they need `pyserial`):

```bash
# Flash the Pico, then live-watch its DECODED boot/telemetry through the tap.
# Auto-detects which port is the XIAO bridge (by its marker traffic) and which is the target.
.venv/bin/python tools/flash_and_watch.py                 # detect → deploy → watch
.venv/bin/python tools/flash_and_watch.py --no-flash      # just watch the tap
.venv/bin/python tools/flash_and_watch.py --no-flash --reboot   # reboot via tap, then watch

# The decoder on its own: live (port/stdin/--tail) or a post-mortem of a black-box log.
.venv/bin/python tools/markerdecode.py --port /dev/cu.usbmodem21201   # live, colourised
.venv/bin/python tools/markerdecode.py /sd/log_007.txt               # post-mortem summary
```

`markerdecode.py` understands the `dbg.log` grammar (`<ms> <body>`): it pairs each `uc>` e-ink
refresh with its `uc<` (an unmatched one before a reboot = the canonical standalone wedge),
tracks the `free=` RAM floor, and flags `FATAL` / `BUSY-TIMEOUT` / `EXC` / `ENOMEM`. Point it at
a `log_NNN.txt` off this bridge's SD card and it prints "where did it die and why" in one shot.

---

## 🎬 Technical Demo Mode

Demo Mode is a comprehensive visual demonstration designed to show off all of the bridge's capabilities under a simulated full load. 

*   **Activation**: Triggered by waiting 2 seconds on the **DEMO MODE** macro item, using the **Demo Trigger App (Screen 8)** (`START NOW` or `BOOT & RUN`), or by sending `{"cfg": {"demo": true}}` or `{"cfg": {"demo_on_boot": true}}` over USB CDC.
*   **Behavior**: It automatically cycles through all 9 screens, displaying each state for **7 seconds**.
*   **Simulated Loads**:
    *   **Screen 0 (Mascot/Stats)**: Shows simulated byte transfers, updating the RX/TX statistics while the mascot wakes up and flashes speech bubbles.
    *   **Screen 1 (Sniffer)**: Automatically alternates between ASCII RX logging and Hex Sniffer modes on each cycle, displaying a simulated stream of incoming telemetry and command responses.
    *   **Screen 2 (I2C Scanner)**: Lists a mockup of active I2C addresses on the bus.
    *   **Screen 3 (Oscilloscope)**: Displays a smooth math-generated sine wave, calculating frequency and voltage stats in real-time.
    *   **Screen 4 (GPIO Monitor)**: Simulates active logic level states across headers, alternating between the grid view and a pulsing 1-bit scrolling Logic Probe view on pin D0.
    *   **Screen 5 (PWM Lab)**: Illustrates a stable PWM wave input (1.0kHz @ 50.0% duty) alongside generator animation.
    *   **Screen 6/7 (Menus)**: Animates the selection cursor cycling through options to demonstrate navigation.
    *   **Screen 8 (Demo Trigger)**: Cycles the selection highlight between trigger commands.
*   **Interaction**: Pressing the physical button (short or long press) at any point during the demo **instantly exits** Demo Mode and resets the device.
