# Hackagotchi 🛠️🐾

**A black-box flight recorder for dev boards that go dark — that also debugs them, and keeps you company while it works.**

[![Firmware CI](https://github.com/GhostRoboticsLab/Hackagotchi/actions/workflows/firmware-c.yml/badge.svg)](https://github.com/GhostRoboticsLab/Hackagotchi/actions/workflows/firmware-c.yml)
[![Firmware: MIT](https://img.shields.io/badge/firmware%2Fc-MIT-blue.svg)](firmware/c/LICENSE)
[![Project: GPL-3.0-or-later](https://img.shields.io/badge/project-GPL--3.0--or--later-blue.svg)](LICENSE)
[![Release](https://img.shields.io/badge/firmware-v1.0.0-green.svg)](https://github.com/GhostRoboticsLab/Hackagotchi/releases)

Hackagotchi turns a **Seeed XIAO RP2040** into three tools in one image — and does all three *at the
same time* without ever corrupting a flash:

1. 🔌 **A real SWD debug probe.** A fork of Raspberry Pi's [`debugprobe`](https://github.com/raspberrypi/debugprobe):
   halt, erase, and reflash a wedged target chip with OpenOCD / probe-rs, *regardless of the target's
   firmware state*.
2. 📼 **A UART black-box recorder.** It continuously logs the target's serial output to a microSD card —
   with session headers, heartbeats, and freeze-frames on a wedge — so when a board goes dark you still
   have its **last words**.
3. 🐾 **A reactive, Tamagotchi-style dashboard.** A little OLED cat that reacts to what your target is
   doing — streaming logs, throughput, a watchdog freeze-frame — so the probe is *alive*, not a dongle.

The hard part isn't any one of those; it's doing all three on one RP2040 **without the dashboard or the
SD writer ever stealing a cycle from a flash in progress.** That guarantee — *0 DAP transfer stalls
under load* — is the project's central invariant (we call it **R1**), and it's proven on hardware, not
asserted. See [`docs/release-readiness.md`](docs/release-readiness.md).

> **Two firmwares in this repo.** The shipping product is the **C firmware** in [`firmware/c/`](firmware/c)
> (this README). [`firmware/micropython/`](firmware/micropython) is the original MicroPython v1 prototype,
> kept for reference.

---

## Quick start — flash a release build

You don't need a toolchain to *use* Hackagotchi, just `picotool` (`brew install picotool`).

1. **Download** `hackagotchi_probe.uf2` from the [latest release](https://github.com/GhostRoboticsLab/Hackagotchi/releases).
2. **Enter BOOTSEL** on the XIAO: hold **B**, tap **R**, release **B** → an `RPI-RP2` drive mounts.
3. **Flash** it — either drag the `.uf2` onto `RPI-RP2`, or:
   ```bash
   picotool load -x hackagotchi_probe.uf2     # -x = run after loading
   ```
4. **Verify** it's alive (two USB serial ports appear — `CDC1` is the control channel):
   ```bash
   # find the control port (the one that answers as "Hackagotchi"), then:
   printf '{"q":"status"}\n' > /dev/cu.usbmodemXXXX     # -> {"fw":"Hackagotchi","ver":"1.0.0",...}
   ```

Already running an older build? You don't even need the button: send `{"q":"bootsel"}` to the control
port and it drops to BOOTSEL on its own, then `picotool load -x` the new image.

To build from source instead, see **[`docs/c-firmware-build.md`](docs/c-firmware-build.md)**.

---

## Wiring

Hackagotchi is a XIAO RP2040 on a Seeed expansion board. Wire SWD/GND to your target; everything else
is on-board.

| Function | Pins |
|---|---|
| **SWD → target** (the probe) | SWCLK **GP26**, SWDIO **GP27**, + GND |
| **Target UART tap** → CDC0 bridge | TX **GP0**, RX **GP1** (uart0) |
| **microSD** — SPI0 (black box) | SCK **GP2**, MOSI **GP3**, MISO **GP4**, CS **GP28** |
| **OLED** — I2C1 @ 1 MHz (addr 0x3C) | SDA **GP6**, SCL **GP7** |
| **Buzzer** (PWM) | **GP29** |
| **WS2812 NeoPixel** (status LED) | data **GP12**, power **GP11** |

> **No physical button.** GP27 became SWDIO, so there are no on-device buttons — navigation and tools
> are driven over USB (CDC1, below). This was a deliberate trade: an extra debug pin is worth more than
> a menu button when the device is, itself, a debugger.

---

## Using it

Hackagotchi enumerates as **two USB serial (CDC) ports**:

| Port | Role |
|---|---|
| **CDC0** | Transparent **UART bridge** — your target's serial console, passed straight through (115200 default; runtime-changeable). |
| **CDC1** | **JSON control channel** — newline-delimited `{"q":"..."}` requests, JSON replies. |

The numeric `/dev/cu.usbmodemXXXX` suffix is **not stable** across replug — identify the control port by
behavior: it's the one that answers `{"q":"status"}` with `"fw":"Hackagotchi"`. The other is the bridge.

### Debugging a target (SWD)

It's a standard CMSIS-DAP probe — point your usual tools at it:

```bash
probe-rs list                                   # -> "Hackagotchi Probe (CMSIS-DAP)"
probe-rs download --verify firmware.elf --chip RP2040
openocd -f interface/cmsis-dap.cfg -f target/rp2040.cfg
```

### Control channel (CDC1) commands

Send `{"q":"<cmd>", ...}\n`; you get one JSON line back.

| Group | Command | Does |
|---|---|---|
| **Status** | `{"q":"status"}` | live telemetry: `fw, ver, heap, up, n, crashes, wd_armed, page, urx_drop, frag, …` |
| | `{"q":"dump"}` | status + last crash report |
| | `{"q":"lastfault"}` | the post-mortem crash box (HardFault / malloc-fail, survives reboot) |
| **Recorder / SD** | `{"q":"rec"}` / `{"q":"tail"}` | recorder state / the on-card log tail |
| | `{"q":"ls"}` / `{"q":"cat","i":N,"off":M}` | list logs / read log #N (by index — no path traversal) |
| | `{"q":"sd"}` | SD mount + bring-up status |
| **Dashboard** | `{"q":"next"}` / `{"q":"prev"}` / `{"q":"screen","n":N}` | navigate screens |
| | `{"q":"hex"}` | toggle the SNIFFER between ASCII and hex |
| **Tools** | `{"q":"macros"}` / `{"q":"macro","i":N}` | list / send a predefined string out the target UART |
| | `{"q":"setmacro","i":N,"s":"..."}` | set macro N (persisted to SD) |
| | `{"q":"baud","v":N}` | change the target-UART baud (validated set; persisted) |
| **Feedback** | `{"q":"beep"}` / `{"q":"led",...}` / `{"q":"pixel",...}` | buzzer / status LEDs / NeoPixel |
| **Maintenance** | `{"q":"bootsel"}` | reset to BOOTSEL for a hands-free reflash |
| | `{"q":"wd_arm"}` / `{"q":"wd_reset"}` | software watchdog control |

There are also test/diagnostic hooks used by the HIL suite (`uloop_on/off`, `recgen_on/off`, `crash`,
`oom_test`, `wd_test`) — see [`firmware/c/src/cdc1_control.c`](firmware/c/src/cdc1_control.c).

### The dashboard

A cat mascot plus screens that react to your target. Six auto-cycling **monitor** screens:

```
HOME (cat)   SNIFFER        RECORDER     THROUGHPUT    WATCHDOG       UPTIME
 /\_/\       UART RX LOG    BLACK BOX     ▁▂▄▆█▆▄▂      last freeze    + heap
( o.o )      live tail      log NNN       bytes/s       frame          uptime
```

…and three **tool** screens (MACRO / BAUD / SD-EXPLORER) summoned over CDC1 — these stay put (excluded
from auto-cycle) so the panel never parks on a menu. The buzzer + NeoPixel give event feedback (wedge =
alarm + red, recovery = chirp + green, etc.), all driven off the DAP hot path.

---

## How it works (the R1 invariant)

The RP2040 in `debugprobe-v2.2.3` is **single-core** (no SMP), so coexistence is bought with **task
priority**, not a second core:

```
priority  high ─────────────────────────────────────────────► low
          UART bridge / watchdog  >  USB (TUD)  >  DAP  >  dashboard + SD writer
```

The DAP path is never blocked by anything below it, and nothing above it blocks or takes a DAP-needed
lock. Cross-task data moves through **single-writer published snapshots** (a seqlock) and **lock-free
SPSC rings** — never shared mutable structs. Each resource has exactly one owning task (FatFs ↔ SD task,
OLED/I2C1 ↔ dashboard task, uart0 TX ↔ bridge task). The firmware runs from **flash XIP** (not
`copy_to_ram`), buying +139 KB of SRAM at identical DAP throughput.

The payoff, measured on hardware: **0 DAP transfer stalls** in every soak — while the SD writer hammers
the card and the dashboard renders. Full rationale: [`docs/engineering-plan.md`](docs/engineering-plan.md);
evidence: [`docs/release-readiness.md`](docs/release-readiness.md).

---

## Repository layout

```
firmware/c/          the shipping C firmware (this README)
  src/               our overlay: probe + bridge + control + recorder + dashboard + reliability
  boards/            the locked XIAO pin map (board config shim over upstream)
  tests/             gates/ (Gate 0/1/2) + m1..m4 (HIL + host unit tests)
  build_fork.sh setup.sh analyze.sh   build / fetch-upstream / static-analysis gate
firmware/micropython/  legacy v1 prototype (MicroPython)
docs/                engineering-plan · release-readiness · c-firmware-build · recovery-model · conventions
.github/workflows/   firmware-c.yml — manual-dispatch build + static-analysis gate + Release
case/                3D-printable enclosure
```

## Reliability & evidence

This project is **gates-first**: the risky architectural claims (does the dashboard starve the probe?
does the SD writer corrupt a flash? does the 2nd CDC keep DAP enumerating?) were proven on real hardware
as falsifiable gates *before* any feature work. See [`docs/release-readiness.md`](docs/release-readiness.md)
for the full CI-automated-vs-HIL-attested evidence table, and `firmware/c/tests/gates/GATE_RESULTS.md`.

## Contributing

PRs welcome — please read **[`CONTRIBUTING.md`](CONTRIBUTING.md)** first. It covers the fork-overlay
model (don't edit upstream), the R1 concurrency rules, the gates-first / HIL discipline, and the
build/test loop.

## License & project model

- **Project: GPL-3.0-or-later** (see [`LICENSE`](LICENSE)) — Copyright © 2026 GhostRoboticsLab and the
  Hackagotchi authors. Same copyleft lineage as Pwnagotchi / Flipper Zero / Meshtastic: use, study,
  modify, redistribute; derivatives stay GPL.
- **`firmware/c/` subtree: MIT** (see [`firmware/c/LICENSE`](firmware/c/LICENSE)) — kept MIT so fixes
  stay rebasable onto upstream `debugprobe`.
- Third-party components are all permissive (MIT / BSD-3 / Apache-2.0) and attributed in
  [`THIRD-PARTY-NOTICES.md`](THIRD-PARTY-NOTICES.md) (+ [`firmware/c/THIRD-PARTY-NOTICES.md`](firmware/c/THIRD-PARTY-NOTICES.md)).

**Open-core:** the firmware is free and forkable; the project is sustained by selling assembled,
pre-flashed units, the 3D-printed enclosure, and the brand — not by closing the code.

## Acknowledgements

Built on the shoulders of [`raspberrypi/debugprobe`](https://github.com/raspberrypi/debugprobe), the
[Raspberry Pi Pico SDK](https://github.com/raspberrypi/pico-sdk), [TinyUSB](https://github.com/hathach/tinyusb),
[FreeRTOS](https://www.freertos.org/), [carlk3's no-OS-FatFS](https://github.com/carlk3/no-OS-FatFS-SD-SDIO-SPI-RPi-Pico),
ChaN's [FatFs](http://elm-chan.org/fsw/ff/), [daschr/pico-ssd1306](https://github.com/daschr/pico-ssd1306),
and [zserge/jsmn](https://github.com/zserge/jsmn). 🐾
