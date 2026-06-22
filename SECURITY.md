# Security Policy

Hackagotchi is a **bench tool**: a CMSIS-DAP debug probe, a UART black-box
recorder, and an OLED companion, all running from one firmware image on a Seeed
XIAO RP2040. This policy frames what a "vulnerability" means for a device whose
entire job is to have privileged physical access to *another* board.

## Trust model

- **Physical and USB access is trusted.** The probe is designed to be plugged
  into a host you control and wired to a target you own. That a debug probe can
  halt, erase, and flash its SWD target — or reset itself to the bootloader over
  `{"q":"bootsel"}` — is the **intended function**, not a vulnerability.
- **The host driving the USB-CDC ports is trusted.** Anyone who can open the
  control port can already drive the probe.

## In scope

Bugs where *untrusted or malformed input* causes memory corruption, a hang, or a
crash on the device — i.e. failures of the firmware's own safety invariants:

- Malformed `{"q":...}` JSON on the CDC1 control channel (parser/overflow bugs).
- Path/argument handling in the SD-backed commands (`{"q":"ls"}`, `{"q":"cat"}`,
  config save) reachable from CDC1.
- Buffer/ISR-stack safety in USB and IRQ callbacks.
- Anything that **stalls the DAP path** through input alone (the probe must
  never stall — see `docs/firmware-conventions.md` R1).
- Vulnerabilities in the host tooling (`host/hackagotchi_ctl.py`) that a
  malicious *device* could exploit against the host.

## Out of scope

- "A debug probe can flash arbitrary firmware to its target" — that's the product.
- Attacks requiring physical modification of the board or a malicious host.
- The original v1 MicroPython prototype in `firmware/micropython/` (reference only).

## Reporting

Please report privately via GitHub's **[private vulnerability reporting](https://github.com/GhostRoboticsLab/Hackagotchi/security/advisories/new)**
(Security tab → "Report a vulnerability"). Include the firmware `"ver"` from
`{"q":"status"}` and a reproduction. This is a small open-source project — there
is no formal SLA, but reports in scope will be acknowledged and addressed on a
best-effort basis.

## Supported versions

Only the latest published [release](https://github.com/GhostRoboticsLab/Hackagotchi/releases)
is supported. Fixes land on `main` and ship in the next release.
