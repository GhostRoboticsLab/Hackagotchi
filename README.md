# Hackagotchi 🛠️🐾

**A black-box flight recorder for dev boards that go dark — that also debugs them, and keeps you company while it works.**

[![Firmware CI](https://github.com/GhostRoboticsLab/Hackagotchi/actions/workflows/firmware-c.yml/badge.svg)](https://github.com/GhostRoboticsLab/Hackagotchi/actions/workflows/firmware-c.yml)
[![Firmware: MIT](https://img.shields.io/badge/firmware%2Fc-MIT-blue.svg)](firmware/c/LICENSE)
[![Project: GPL-3.0-or-later](https://img.shields.io/badge/project-GPL--3.0--or--later-blue.svg)](LICENSE)
[![Release](https://img.shields.io/badge/firmware-v1.0.0-green.svg)](https://github.com/GhostRoboticsLab/Hackagotchi/releases)

One **Seeed XIAO RP2040**, one firmware image, **three tools running at the same time** — without ever corrupting a flash in progress:

- 🔌 **A real SWD debug probe** — a fork of [`debugprobe`](https://github.com/raspberrypi/debugprobe): halt, erase, and reflash a wedged target with OpenOCD / probe-rs, *whatever state its firmware is in*.
- 📼 **A UART black-box recorder** — continuously logs the target's serial to microSD (session headers, heartbeats, a freeze-frame on a wedge), so a board that goes dark still has its **last words**.
- 🐾 **A reactive OLED dashboard** — a Tamagotchi-style cat that reacts to your target: live logs, throughput, a watchdog freeze-frame. The probe is *alive*, not a dongle.

> 🎯 **The whole point** is doing all three on one **single-core** RP2040 with **0 DAP transfer stalls under load** — the dashboard and SD writer never steal a cycle from a flash in progress. That invariant (**R1**) is *proven on hardware, not asserted*: see [`docs/release-readiness.md`](docs/release-readiness.md).

## ⚡ Flash it in 30 seconds

No toolchain needed — just `picotool` (`brew install picotool`). Grab `hackagotchi_probe.uf2` from the **[latest release](https://github.com/GhostRoboticsLab/Hackagotchi/releases)**, then:

```bash
# BOOTSEL the XIAO: hold B, tap R, release B  ->  an RPI-RP2 drive mounts
picotool load -x hackagotchi_probe.uf2          # -x = run after loading

# alive check: send this to the control serial port (the one that answers as "Hackagotchi")
printf '{"q":"status"}\n' > /dev/cu.usbmodemXXXX  # -> {"fw":"Hackagotchi","ver":"1.0.0",...}
```

> Already running an older build? You don't even need the button — send `{"q":"bootsel"}` to the control port and it drops to BOOTSEL on its own. Building from source instead? → [`docs/c-firmware-build.md`](docs/c-firmware-build.md).

<sub>**Two firmwares live here.** The shipping product is the **C firmware** in [`firmware/c/`](firmware/c) (everything below). [`firmware/micropython/`](firmware/micropython) is the original MicroPython v1 prototype, kept for reference.</sub>

---

<details>
<summary><b>🔧 Wiring &amp; pin map</b> — it's a XIAO on a Seeed expansion board; you only wire SWD + GND to your target</summary>

| Function | Pins |
|---|---|
| **SWD → target** (the probe) | SWCLK **GP26**, SWDIO **GP27**, + GND |
| **Target UART tap** → CDC0 bridge | TX **GP0**, RX **GP1** (uart0) |
| **microSD** — SPI0 (black box) | SCK **GP2**, MOSI **GP3**, MISO **GP4**, CS **GP28** |
| **OLED** — I2C1 @ 1 MHz (addr 0x3C) | SDA **GP6**, SCL **GP7** |
| **Buzzer** (PWM) | **GP29** |
| **WS2812 NeoPixel** (status LED) | data **GP12**, power **GP11** |

**No physical button** — GP27 became SWDIO, so navigation and tools are driven over USB (CDC1, below). A deliberate trade: an extra debug pin is worth more than a menu button when the device *is* a debugger.

</details>

<details>
<summary><b>🎛️ Using it</b> — two USB serial ports: a transparent UART bridge + a JSON control channel</summary>

| Port | Role |
|---|---|
| **CDC0** | Transparent **UART bridge** — your target's serial console, passed straight through (115200 default; runtime-changeable). |
| **CDC1** | **JSON control channel** — newline-delimited `{"q":"..."}` requests, JSON replies. |

The numeric `/dev/cu.usbmodemXXXX` suffix is **not stable** across replug — identify the control port by *behavior*: it's the one that answers `{"q":"status"}` with `"fw":"Hackagotchi"`. The other is the bridge.

**Debugging a target (SWD)** — it's a standard CMSIS-DAP probe, so point your usual tools at it:

```bash
probe-rs list                                   # -> "Hackagotchi Probe (CMSIS-DAP)"
probe-rs download --verify firmware.elf --chip RP2040
openocd -f interface/cmsis-dap.cfg -f target/rp2040.cfg
```

</details>

<details>
<summary><b>📡 Control channel (CDC1) — full command reference</b></summary>

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
| **Companion** | `{"q":"pet"}` | a happy cat beat (heart + chirp) |
| | `{"q":"summon"}` / `{"q":"banish"}` | force the ghost present / absent (also lets tests drive it) |
| | `{"q":"exorcise"}` | the exorcism dissolve — a host flasher fires it after a clean reflash |
| | `{"q":"ghost","on":0/1}` / `{"q":"theme","n":0/1}` | mute the character layer (pure-instrument) / motion density |
| **Maintenance** | `{"q":"bootsel"}` | reset to BOOTSEL for a hands-free reflash |
| | `{"q":"wd_arm"}` / `{"q":"wd_reset"}` | software watchdog control |

There are also test/diagnostic hooks used by the HIL suite (`uloop_on/off`, `recgen_on/off`, `crash`, `oom_test`, `wd_test`) — see [`firmware/c/src/cdc1_control.c`](firmware/c/src/cdc1_control.c).

</details>

<details>
<summary><b>🐾 The dashboard</b> — a cat + a ghost, 6 auto-cycling monitor screens, 3 summonable tool screens</summary>

```
HOME         SNIFFER        RECORDER     THROUGHPUT    WATCHDOG       UPTIME
 /\_/\  .-.  UART RX LOG    BLACK BOX     ▁▂▄▆█▆▄▂      last freeze    + heap
( o.o )(o o) live tail      log NNN       bytes/s       frame          rev/flt
```

Two characters, and **every flicker of personality is a literal readout of a real signal**:

- **The cat** is your bench familiar. Its mood is the bench at a glance — **sleeping** (idle), **content** (target chatting), **hunting** (data really flowing; particles + tail speed up with throughput), **alert** (target wedged or SD fault). Pet it with `{"q":"pet"}`.
- **Spectre, the ghost**, *is the target board's soul* — **absent** (no target), **solid** (alive), **hollow/pale** (wedged), **torn** (recorder fault), and **exorcised** (dissolves when the host reflashes). A status pip rides the top-right corner of every screen.

The six **monitor** screens auto-cycle (a ghostly dither wipe between them); three **tool** screens (MACRO / BAUD / SD-EXPLORER) are summoned over CDC1 and stay put. The buzzer + NeoPixel add event feedback (summon chirp, wedge alarm + red, recovery gasp + green) — all driven off the DAP hot path. Prefer a pure instrument cluster? `{"q":"ghost","on":0}`.

</details>

<details>
<summary><b>🧠 How it works — the R1 invariant</b> (single-core coexistence bought with priority, not a 2nd core)</summary>

The RP2040 in `debugprobe-v2.2.3` is **single-core** (no SMP), so coexistence is bought with **task priority**:

```
priority  high ─────────────────────────────────────────────► low
          UART bridge / watchdog  >  USB (TUD)  >  DAP  >  dashboard + SD writer
```

The DAP path is never blocked by anything below it, and nothing above it takes a DAP-needed lock. Cross-task data moves through **single-writer published snapshots** (a seqlock) and **lock-free SPSC rings** — never shared mutable structs. Each resource has exactly one owning task (FatFs ↔ SD task, OLED/I2C1 ↔ dashboard task, uart0 TX ↔ bridge task). The firmware runs from **flash XIP** (not `copy_to_ram`), buying +139 KB of SRAM at identical DAP throughput.

The measured payoff: **0 DAP transfer stalls** in every soak — while the SD writer hammers the card and the dashboard renders. Rationale: [`docs/engineering-plan.md`](docs/engineering-plan.md) · evidence: [`docs/release-readiness.md`](docs/release-readiness.md).

</details>

<details>
<summary><b>📁 Repository layout</b></summary>

```
firmware/c/          the shipping C firmware (this README)
  src/               our overlay: probe + bridge + control + recorder + dashboard + reliability
  boards/            the locked XIAO pin map (board config shim over upstream)
  tests/             gates/ (Gate 0/1/2) + m1..m4 (HIL + host unit tests)
  build_fork.sh setup.sh analyze.sh   build / fetch-upstream / static-analysis gate
firmware/micropython/  legacy v1 prototype (MicroPython)
docs/                engineering-plan · release-readiness · c-firmware-build · recovery-model · firmware-conventions
.github/workflows/   firmware-c.yml — manual-dispatch build + static-analysis gate + Release
case/                3D-printable enclosure
```

</details>

<details>
<summary><b>🛡️ Reliability &amp; evidence</b> — this project is gates-first</summary>

The risky architectural claims — *does the dashboard starve the probe? does the SD writer corrupt a flash? does the 2nd CDC keep DAP enumerating?* — were proven on real hardware as falsifiable **gates** *before* any feature work. See [`docs/release-readiness.md`](docs/release-readiness.md) for the full CI-automated-vs-HIL-attested evidence table, and `firmware/c/tests/gates/GATE_RESULTS.md`.

> ⚠️ A green CI badge means "builds + passes static analysis," **not** "the gates ran" — the HIL gates need the physical bench and are attested by hand on each release image.

</details>

<details>
<summary><b>📜 License &amp; open-core model</b></summary>

- **Project: GPL-3.0-or-later** ([`LICENSE`](LICENSE)) — © 2026 GhostRoboticsLab and the Hackagotchi authors. Same copyleft lineage as Pwnagotchi / Flipper Zero / Meshtastic: use, study, modify, redistribute; derivatives stay GPL.
- **`firmware/c/` subtree: MIT** ([`firmware/c/LICENSE`](firmware/c/LICENSE)) — kept MIT so fixes stay rebasable onto upstream `debugprobe`.
- Third-party components are all permissive (MIT / BSD-3 / Apache-2.0), attributed in [`THIRD-PARTY-NOTICES.md`](THIRD-PARTY-NOTICES.md) (+ [`firmware/c/THIRD-PARTY-NOTICES.md`](firmware/c/THIRD-PARTY-NOTICES.md)).

**Open-core:** the firmware is free and forkable; the project is sustained by selling assembled, pre-flashed units and the enclosure — not by closing the code.

</details>

<details>
<summary><b>🙏 Acknowledgements</b></summary>

Built on the shoulders of [`raspberrypi/debugprobe`](https://github.com/raspberrypi/debugprobe), the [Raspberry Pi Pico SDK](https://github.com/raspberrypi/pico-sdk), [TinyUSB](https://github.com/hathach/tinyusb), [FreeRTOS](https://www.freertos.org/), [carlk3's no-OS-FatFS](https://github.com/carlk3/no-OS-FatFS-SD-SDIO-SPI-RPi-Pico), ChaN's [FatFs](http://elm-chan.org/fsw/ff/), [daschr/pico-ssd1306](https://github.com/daschr/pico-ssd1306), and [zserge/jsmn](https://github.com/zserge/jsmn). 🐾

</details>

---

**Contributing?** Start with **[`CONTRIBUTING.md`](CONTRIBUTING.md)** — the fork-overlay model (don't edit upstream), the R1 concurrency rules, the gates-first discipline, and the build/test loop. 🐾
