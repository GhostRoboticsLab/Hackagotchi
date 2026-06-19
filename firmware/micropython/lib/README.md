# Vendored MicroPython drivers

`main.py` imports two drivers that must be present on the device's filesystem (or
frozen into the firmware):

| Module | Status | Source |
|---|---|---|
| `ssd1306.py` | **vendored here** | The standard MicroPython SSD1306 framebuf driver (carried over from the PicoInky tree). |
| `sdcard.py` | **NOT yet vendored** | The canonical `sdcard.py` from [micropython/micropython-lib](https://github.com/micropython/micropython-lib/blob/master/micropython/drivers/storage/sdcard/sdcard.py). Drop it in here so the firmware is self-contained. |

Deploy both alongside `main.py`:

```bash
mpremote connect <port> cp lib/ssd1306.py :ssd1306.py
mpremote connect <port> cp lib/sdcard.py  :sdcard.py    # once vendored
mpremote connect <port> cp ../main.py     :main.py
mpremote connect <port> reset
```
