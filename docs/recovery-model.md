# Hackagotchi — recovery model ("can it brick?")

What actually recovers the probe and a target it's attached to, in what order, and the residual cases
that genuinely *can* brick. Written to be honest about guarantees — the enemy is an over-claim that
gets trusted (the same silent-pass discipline as `mcu-bringup-playbook.md`). Two separate stories that
are easy to conflate: **the XIAO (the probe)** and **the attached target** recover by different means.

> TL;DR: **"unbrickable" is too strong.** But the XIAO is *practically* unrecoverable-proof thanks to
> the RP2040's mask-ROM bootrom (a chip property, not our firmware), and the M1 reliability core makes
> it self-healing + usually reflashable without touching it. A target is recoverable by the probe over
> SWD in the common case — but **not** if its debug port is physically dead or permanently locked.

---

## 1. The real source of resilience: the RP2040 bootrom (not our code)

On every reset the RP2040 runs its **bootrom**, which lives in **mask ROM and cannot be overwritten**.
The bootrom checks the **BOOTSEL** condition *before it branches to any code in flash* — it does first
read + checksum the flash's boot-stage-2 candidate into SRAM (trying the QSPI modes), but BOOTSEL,
sensed on the **QSPI_SS / flash chip-select strap pin**, is evaluated before that second stage is
*executed*:

- BOOTSEL asserted at reset → enter the USB bootloader (USB MSC + PICOBOOT), **regardless of what is
  in flash** — even if flash is blank, corrupt, or full of garbage (flash is read/probed, never run).
- BOOTSEL not asserted → validate + run the flash second-stage; if that's invalid, fall back to USB.

Consequences that matter here:

- **No software — including a bug of ours — can disable the BOOTSEL escape hatch on RP2040.** There is
  no secure-boot / OTP lockout that removes it. (RP2350 adds optional secure boot; RP2040 does not.)
- Holding BOOTSEL while powering up / resetting **always** wins over whatever is in flash. So even a
  tight reboot-loop is recoverable: a reboot-loop is *annoying*, not a brick.
- Flash content can always be mass-erased + rewritten over PICOBOOT, so corrupt flash is recoverable
  as long as the QSPI flash chip is electrically alive.

On the XIAO RP2040 the BOOTSEL gesture is: **hold B, tap R, release B**. (macOS sometimes does not
auto-mount the `RPI-RP2` volume; that's cosmetic — `picotool` still reaches the device over PICOBOOT,
which is all a reflash needs.)

## 2. What the M1 reliability core adds on top

These reduce how often a human or the physical button is needed; they do **not** replace the bootrom
guarantee in §1.

| Tier | Mechanism | Recovers without… | Requires |
|------|-----------|-------------------|----------|
| **T1 — self-heal** | Crash box + SW watchdog: a HardFault / stack-overflow / malloc-fail / wedged monitored task auto-reboots into the working image and records a post-mortem | host **and** human | a valid image in flash |
| **T2 — remote reflash** | `{"q":"bootsel"}` over CDC1 → `reset_usb_boot` → BOOTSEL → `picotool load` | the physical button | firmware alive enough to service USB/CDC1 |
| **T3 — physical button** | bootrom honors BOOTSEL at reset (§1) | — (always works) | a hand on the device |

- **Crash box** (`src/crash_box.{c,h}`): an `isr_hardfault` override captures the M0+ exception frame
  into `.uninitialized_data` + the watchdog scratch registers; surfaced next boot via CDC1
  `{"q":"lastfault"}` and the stdio log. The FreeRTOS stack-overflow + malloc hooks feed the same box;
  a fault firing *before* `crash_box_init()` runs is still captured (the recorder re-inits the region
  on the spot). HIL-proven (`tests/m1/crashbox_hil.py`).
  - **Survival boundary (important):** the record + the `crashes` counter live in RAM, so they survive
    only a **warm reset** — a watchdog reboot, the R/RUN button, `reset_usb_boot` (the bootsel command),
    or a `picotool load -x` reflash all preserve them (empirically confirmed this session: the counter
    rode `0→1→2→3` across multiple reflashes). A **cold power cycle** (USB unplug / VDD loss) leaves
    `.uninitialized_data` as garbage → `crash_box_init` re-zeroes it and the `crashes` total resets to
    0. So treat `crashes` as "faults since the last power-up," not lifetime, and don't expect a
    post-mortem to outlive a unplug.
- **SW watchdog** (`src/watchdog_task.c`): monitors the **high-priority** TUD task — deliberately not a
  low-priority task, which would false-positive under legitimate flash load and reset the probe
  mid-flash. A stalled TUD task is caught after the **~4 s SW stall window**, recorded as `kind=watchdog`
  + the task name, and rebooted; the **8 s HW WDT** is a second-layer backstop for the watchdog task
  *itself* dying. **Disarmed by default** (HW WDT not enabled until `wd_arm`), so a fresh flash cannot
  reboot-loop; arming is **one-way for the session** — there is no software disarm, only a reboot
  returns to the disarmed default. HIL-proven (`tests/m1/watchdog_hil.py`).

## 3. What can still brick the XIAO (the honest residual)

- **Physical / electrical death** — fried GPIO, ESD, reverse polarity / over-voltage, a dead USB
  connector, broken solder joints, or a damaged BOOTSEL button / QSPI_SS strap line (T3's bootrom
  guarantee is unconditional only as long as that wiring is alive). No firmware recovers dead silicon.
  (Cold/again-dead SWD joints are exactly what killed the *original* Gate-0 target board.)
- **The one case T2 can't cover:** an image flashed that faults *before USB enumerates* never receives
  `{"q":"bootsel"}` → fall back to T3 (the physical button). This is why the button stays in the loop
  and why we artifact-verify every image before flashing.
- **Worst case our own code can cause is a reboot-loop**, which T3 always recovers — so a Hackagotchi
  firmware bug cannot produce a *true* brick on RP2040.

The QSPI flash chip itself being physically damaged would be unrecoverable, but BOOTSEL/PICOBOOT can
always re-erase + rewrite it, so this effectively only happens with hardware failure of the flash part.

## 4. The attached target is a *different* guarantee

The probe's whole purpose is recovering a wedged target over **SWD**: halt → mass-erase → reflash.
SWD is independent of the target CPU's running state (dedicated debug pins), so a target whose firmware
has wedged its own CPU is still reachable. Recovery works **when**:

- **the SWD wiring is physically intact** — dead joints / a broken trace = no reach (the Gate-0 lesson);
- **the target has not permanently locked its debug port.**

This is **chip-family dependent** — there are four meaningfully different classes:

- **(A) Lockout-free, dedicated SWD pins — RP2040:** SWCLK/SWDIO are dedicated debug pins, reachable
  regardless of target firmware state, with no permanent SWD lockout → **very recoverable** (a
  bootrom/openocd mass-erase always works). Note **RP2350 is *not* in this class**: it adds a
  secure-boot OTP `DEBUG_DISABLE` that, once provisioned, permanently kills debug (class D below).
- **(B) Firmware re-muxes SWD pins to GPIO — some STM32** (e.g. PA13/PA14 reconfigured by firmware):
  debug is lost while running, but usually recoverable with **connect-under-reset** — assert reset and
  attach during the bootrom window before the firmware remaps the pins. (nRF52 is *not* here: its
  SWDIO/SWDCLK are dedicated and cannot be muxed to GPIO.)
- **(C) Recoverable debug-lock via destructive mass-erase:** the debug port is disconnected by a
  protection bit, but a full chip-erase re-enables it — **at the cost of wiping the target**. Examples:
  **nRF52 APPROTECT** (recover via CTRL-AP `ERASEALL` / `nrfjprog --recover`, wipes flash+UICR+RAM) and
  **STM32 RDP Level 1** (regressing L1→L0 triggers a mass-erase that re-enables debug). The probe *can*
  recover these — just not non-destructively.
- **(D) Permanent / irreversible debug-disable:** **STM32 RDP Level 2** (irreversible) and **RP2350
  with secure-boot OTP `DEBUG_DISABLE`** provisioned. If the target set this, **no debugger, including
  this probe, can recover it** — a true brick.

### Erase path caveat for target recovery (Finding F0-1)

Use the **openocd / bootrom** mass-erase path, **not** `probe-rs erase --chip RP2040`: on RP2040 the
latter is pathologically slow (observed >150 s, never completing — it skips the bootrom block-erase),
while openocd erases all 2 MB in ~7.7 s. Our recovery flows must use the openocd/bootrom path.

## 5. Quick reference

| Situation | Recovery |
|-----------|----------|
| Probe firmware faulted (HardFault / stack / malloc) | T1 — auto-reboots, `{"q":"lastfault"}` shows it |
| A monitored probe task wedged (watchdog armed) | T1 — auto-reboots, `kind=watchdog` |
| Want to reflash the probe, firmware alive | T2 — `{"q":"bootsel"}` then `picotool load` (no button) |
| Probe firmware faults before USB enumerates / tight reboot-loop | T3 — hold B, tap R, release B |
| Probe hardware electrically dead | unrecoverable (replace) |
| Target firmware wedged, SWD wired, lockout-free (RP2040) | probe halt → openocd erase → reflash (class A) |
| Target SWD pins remapped to GPIO at runtime (some STM32) | connect-under-reset (class B) |
| Target debug-locked but mass-erasable (nRF52 APPROTECT / STM32 RDP L1) | recoverable by full chip-erase — re-enables SWD but **wipes the target** (class C) |
| Target debug port permanently locked (STM32 RDP2 / RP2350 OTP DEBUG_DISABLE) | unrecoverable by any probe (class D) |
| Target SWD joints/wiring dead | fix the wiring first (no reach otherwise) |
