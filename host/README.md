# Host tooling

Host-side companions for a running Hackagotchi probe. Pure Python (stdlib + `pyserial`, plus
optional `Pillow`); **nothing here touches the firmware or risks the device** — these just drive
the two USB-CDC serial ports the board exposes.

| file | what it is |
|---|---|
| `hackagotchi_ctl.py` | the CLI driver for the CDC1 JSON control channel — so you don't hand-echo `{"q":"…"}` at a port |
| `tests/ctl_selftest.py` | a no-hardware self-test of the CLI's parsing/dispatch (mock serial); falsifiable green check |

## Setup

```bash
./setup-venv.sh                 # from the repo root: creates .venv + installs requirements.txt
.venv/bin/python host/hackagotchi_ctl.py status
```

`setup-venv.sh` builds one venv at the repo root and symlinks `firmware/c/.venv` to it, so the
HIL-test convention (`.venv/bin/python tests/…` run from `firmware/c/`) resolves to the same
interpreter. Manual equivalent: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`.

## The two ports (identify by behavior, not device path)

The composite device exposes two `/dev/cu.usbmodem*` (or `/dev/ttyACM*`) ports; the numeric suffix
is **not stable across replug**. The CLI auto-detects by probing every port with `{"q":"status"}`
and matching the `"fw":"Hackagotchi"` reply — so you normally don't pass `--port` at all.

- **CDC0** — transparent target-UART bridge (the target's console; default 115200). Silent to a status probe.
- **CDC1** — newline-delimited JSON control channel (`{"q":"…"}` → one JSON line back). The one the CLI drives.

## CLI commands

```
.venv/bin/python host/hackagotchi_ctl.py <command> [args]   [--port /dev/cu.usbmodemXXXX]
```

| command | what it does |
|---|---|
| `status` | live telemetry snapshot (screen, baud, tx/rx, throughput, recorder, wedge) |
| `dump` | crash box + status in one shot |
| `lastfault` | the post-mortem crash box (HardFault / malloc-fail; survives a reboot) |
| `freeze` | the recorder's freeze-frame — the target's last words before it went silent |
| `bootsel` | reset to BOOTSEL for a hands-free reflash (the port drops; then `picotool load -x …`) |
| `baud [RATE]` | read the target-UART baud + valid options; with `RATE`, set it (validated, persisted) |
| `macro [N]` | list the configured macros; with `N`, send macro N out the target UART |
| `ls` | list the SD card's log files (shows the number to pass to `cat`) |
| `cat N [--off M] [--all]` | read SD log #N (`cat 7` → `log_007.txt`); `--all` pages to EOF |
| `sd` / `rec` / `tail` | SD mount status / recorder state / on-card log tail |
| `screen N` | jump the dashboard to screen N |
| `clear` | reset tx/rx/throughput/hits + freeze-frame |
| `watch [--seconds S]` | live-tail the relayed telemetry (Ctrl-C to stop) |
| `shot [--out f.png] [--scale K]` | screenshot the OLED over the tap → PNG (PGM fallback without Pillow) |

`ls`/`cat`/`tail` are **async by design**: the firmware services FatFs on a low-priority task off
the DAP hot path (R1), so the CLI issues each of these twice — trigger, then collect the fresh
result. The full command grammar lives in the firmware (`src/cdc1_control.c`) and the README
command table.

## Self-test (no hardware)

```bash
python3 host/tests/ctl_selftest.py                          # all checks PASS (exit 0)
HG_CTL_SELFTEST_BREAK=1 python3 host/tests/ctl_selftest.py  # verify-the-verifier: MUST FAIL (exit 1)
```

It feeds canned device replies through the CLI's parsers with a mock serial. The break mode flips
one expectation to prove the harness can actually go red — a test that cannot fail is a silent pass.

## HIL tests

The hardware-in-the-loop suites under `firmware/c/tests/**` use the same venv but need the physical
bench (a probe + a separate RP2040 target + microSD). See the project README and
`docs/release-readiness.md`.
