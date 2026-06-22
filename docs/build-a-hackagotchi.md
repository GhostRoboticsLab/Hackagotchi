# Build a Hackagotchi

How to assemble, wire, flash, and first-boot a Hackagotchi from parts. This is the **physical
reproducibility** guide; the toolchain-level firmware build lives in
[`c-firmware-build.md`](c-firmware-build.md) and [`../firmware/c/README.md`](../firmware/c/README.md),
and the host tooling in [`../host/README.md`](../host/README.md).

> Hackagotchi runs three roles from one image on a single XIAO RP2040: a CMSIS-DAP SWD debug probe,
> a UART-to-microSD black-box recorder, and a reactive OLED dashboard. The hardware is almost
> entirely a stock **Seeed XIAO RP2040 + XIAO Expansion Board** — the expansion board already carries
> the OLED, microSD slot, and buzzer, so the BOM is short.

## Bill of materials

Approximate costs are USD, ballpark as of 2026 — check the store for current pricing. Quantities are
per unit.

| # | Part | Qty | ~Cost | Where | Notes |
|---|------|-----|-------|-------|-------|
| 1 | **Seeed XIAO RP2040** | 1 | ~$5–6 | [wiki.seeedstudio.com/XIAO-RP2040](https://wiki.seeedstudio.com/XIAO-RP2040/) | the MCU. Has an **onboard WS2812 NeoPixel** (GP12 data / GP11 power) + onboard LED (GP25) the firmware uses |
| 2 | **Seeed Studio XIAO Expansion Board Base** | 1 | ~$11–14 | [wiki.seeedstudio.com/Seeeduino-XIAO-Expansion-Board](https://wiki.seeedstudio.com/Seeeduino-XIAO-Expansion-Board/) | carries the **0.96″ 128×64 SSD1306 OLED** (I2C @ 0x3C), **microSD slot** (SPI), **passive buzzer** (GP29), a user button (GP27 — **unusable**, see reconciliation), and a PCF8563 RTC + CR1220 holder (**unused**, see reconciliation) |
| 3 | **microSD card**, FAT32 | 1 | ~$5–8 | any | the black-box log store. Tested on a 16 GB FAT32 card; format FAT32 before first use |
| 4 | **Dupont / jumper leads** | ~5 | ~$2 | any | to a target board: SWCLK/SWDIO + GND (debug) and the UART tap GP0/GP1 + GND |
| 5 | **USB-C cable** | 1 | ~$3 | any | data-capable (powers + enumerates the composite USB device) |
| 6 | **Filament**, PETG or PLA | ~10 g | ~$1 | any | for the printed case ([`../case/`](../case/)) — 0.4 mm nozzle, 0.2 mm layers |
| 7 | *(for testing)* a separate **RP2040 target** | 1 | ~$4–5 | any | e.g. a Pico/Pico W to debug + record. Not part of the shipped unit |

**Rough total (the unit itself, parts 1–6): ~$27–34.**

The expansion board is the lever that keeps this cheap: OLED + microSD + buzzer come pre-mounted and
pre-wired to the XIAO's pads, so there is no peripheral soldering for the core build — just stack,
insert the card, and wire the two taps to whatever you're debugging.

## Consolidated pin map (as-built)

Every pin is fixed in firmware — `firmware/c/boards/board_hackagotchi_config.h` (probe/UART),
`firmware/c/src/sd/hw_config.c` (SD), `firmware/c/src/i2c1_bus.h` (OLED), and
`firmware/c/src/feedback.c` (buzzer/NeoPixel). The XIAO pad name (D0…D10) is what's silk-screened.

| Signal | GPIO | XIAO pad | Bus / role | Notes |
|--------|------|----------|------------|-------|
| **SWCLK** | GP26 | D0 | PIO0 SWD (probe out) | reclaims the D0 green-LED/ADC pad |
| **SWDIO** | GP27 | D1 | PIO0 SWD (probe I/O) | reclaims the user-button pad. **SWDIO must equal SWCLK+1** (PIO side-set adjacency) — that's why GP26/GP27 |
| **UART0 TX** | GP0 | D6 | target-UART tap → target RX | the recorder/bridge's view of the target console |
| **UART0 RX** | GP1 | D7 | target-UART tap ← target TX | |
| **SD SCK** | GP2 | D8 | SPI0 (FatFs) | 12 MHz |
| **SD MOSI** | GP3 | D10 | SPI0 | |
| **SD MISO** | GP4 | D9 | SPI0 | |
| **SD CS** | GP28 | D2 | SPI0, software SS | GP28 isn't an SPI0 HW pin, but CS is a plain GPIO so it's fine |
| **I2C1 SDA** | GP6 | D4 | OLED SSD1306 @ 0x3C | **OLED is the sole device** (RTC dropped); FM+ **1 MHz**, single-owner, no mutex |
| **I2C1 SCL** | GP7 | D5 | OLED SSD1306 | |
| **Buzzer** | GP29 | D3 | PWM | passive piezo |
| **NeoPixel data** | GP12 | onboard | WS2812 via **pio1** | the color status indicator (wedge = red, recovery = green). pio1 deliberately — pio0 is the SWD probe |
| **NeoPixel power** | GP11 | onboard | power-enable (drive HIGH) | the XIAO gates NeoPixel power on this pin |
| **Onboard LED** | GP25 | onboard | USB heartbeat | active-low; no pad |
| ~~Onboard RGB~~ | ~~GP16/17~~ | onboard | **unused** | abandoned as an unreliable status channel (firmware Finding M3-1) — the WS2812 is the status LED |

**Do not press the user button during a flash.** GP27 is now SWDIO; a debounce cap on that line can
break SWD at 1 MHz. The Gate-1 pre-soak check `probe-rs info --chip RP2040 --protocol swd` is the
arbiter that the soldered/stacked SWD path is sound before you trust a soak.

## As-shipped vs. the case docs — reconciliation

⚠️ The enclosure docs ([`../case/HACKAGOTCHI_CASE.md`](../case/HACKAGOTCHI_CASE.md),
[`../case/CAT_ENCLOSURE_SPEC.md`](../case/CAT_ENCLOSURE_SPEC.md)) and `hackagotchi_case.scad` were
written against an **earlier hardware intent** and have drifted from the as-built firmware. Until the
case is revised, reconcile as follows:

| Case docs say… | As-built firmware | What to do |
|---|---|---|
| Enclose a **PCF8563 RTC + CR1220 coin cell** | RTC **dropped** (commit `eca0f03`): `rtc_read = NULL`, logs carry **uptime `+Ns`** stamps, no `time`/`settime` verbs, I2C1 runs OLED-only at FM+ 1 MHz | No coin cell needed for operation. The RTC chip is still on the expansion board but the firmware never reads it — don't design the case around coin-cell access. There is **no wall-clock**; log timestamps are uptime-relative |
| A **recessed user button** as a "cheek" tap-target | GP27 is **SWDIO** — the button is electrically sacrificed and **unusable** (pressing it can break SWD) | Treat the button as decorative-only, or blank the cutout. All interaction is over USB (CDC1) — there is no physical button. `pet`/`summon`/`exorcise` etc. are CDC1 verbs |
| (no mention of a status light) | Firmware drives the **onboard WS2812 NeoPixel** (GP12/GP11) as the primary color-status channel | The `.scad` has **no light-pipe / cutout** for the NeoPixel, so the status color is invisible in an opaque case. Add a diffuser/cutout over the XIAO's onboard NeoPixel, or accept a blind status LED |
| OLED "face", buzzer "muzzle" grille, canted top | Consistent — OLED on GP6/7 @ 0x3C, buzzer on GP29 | No change. The cat-face/OLED and buzzer-grille mappings still hold |

The case files are also explicitly **v1 "form, not fit"** — every board outline and component
position is a `[MEASURE]` placeholder. Measure your stacked board with calipers and set the `.scad`
parameters before a full print; print the `coupon` first.

## Assembly

1. **Stack** the XIAO RP2040 onto the XIAO Expansion Board (USB-C end matching the board's USB-C
   cutout). This connects the OLED, microSD, and buzzer to the pads in the map above — no soldering.
2. **Format and insert** a FAT32 microSD card into the expansion board's slot (this is the black-box
   log store; with no card the recorder degrades gracefully and the SD glyph shows unmounted).
3. **Wire the debug + tap leads** to your target board:
   - SWD: XIAO **GP26 → target SWCLK**, **GP27 → target SWDIO**, **GND → GND**.
   - UART tap (optional but it's the recorder's whole point): XIAO **GP0 (TX) → target RX**,
     **GP1 (RX) → target TX**, **GND → GND**.
4. **Print the case** from [`../case/`](../case/) — render the STLs with the OpenSCAD commands in
   `HACKAGOTCHI_CASE.md`, print the `coupon` first to check the snap-fit seam and cable opening, then
   the base + top. Apply the reconciliation notes above (button cutout, NeoPixel diffuser).
5. **USB-C** from the XIAO to your host. The device enumerates as a composite USB device: two CDC
   serial ports (bridge + control) and the CMSIS-DAP probe.

## Build & flash the firmware

Full toolchain detail is in [`c-firmware-build.md`](c-firmware-build.md); the short path (all from
`firmware/c/`, pinned Arm GCC 13.3 + pico-sdk 2.2.0):

```bash
cd firmware/c
./setup.sh                                          # fetch pinned upstream (gitignored)
VERSION=$(git describe --tags --always) ./build_fork.sh   # -> build/hackagotchi_probe.uf2
./analyze.sh                                         # static-analysis gate (must pass)
```

Flash it:

- **First time / recovery:** hold nothing — there is no BOOTSEL button (GP27 is SWDIO). Put a *bare*
  XIAO into BOOTSEL via its onboard reset before first flash, then:
  `picotool load -x build/hackagotchi_probe.uf2`.
- **Reflash a running unit, hands-free:** send `{"q":"bootsel"}` on the control port (CDC1) — the
  firmware resets to BOOTSEL with no button — then `picotool load -x …`. The host CLI wraps this:
  `.venv/bin/python host/hackagotchi_ctl.py bootsel`. See [`recovery-model.md`](recovery-model.md).

## First-contact verification

Set up the host tooling once (`./setup-venv.sh` from the repo root — see
[`../host/README.md`](../host/README.md)), then:

```bash
.venv/bin/python host/hackagotchi_ctl.py status     # should answer fw=Hackagotchi, ver=…
.venv/bin/python host/hackagotchi_ctl.py sd          # SD mount/bring-up status
.venv/bin/python host/hackagotchi_ctl.py screen 0    # the OLED should show the cat / home screen
```

If `status` answers with `"fw":"Hackagotchi"`, the composite USB device, the control channel, and
the firmware are all alive. The OLED lighting up and `sd` reporting a mounted card confirm the two
expansion-board peripherals are seated. To prove the **probe** path, point `probe-rs` or `openocd` at
a wired target (`probe-rs info --chip RP2040 --protocol swd`).

## References

- [`c-firmware-build.md`](c-firmware-build.md) — toolchain, pinned versions, build flags
- [`../firmware/c/README.md`](../firmware/c/README.md) — firmware overview + CDC1 command table
- [`../host/README.md`](../host/README.md) — host CLI + the two-CDC port model
- [`recovery-model.md`](recovery-model.md) — bootsel / recovery guarantees
- [`release-readiness.md`](release-readiness.md) — what's HIL-attested on the release image
- [`../case/`](../case/) — enclosure source + print instructions
