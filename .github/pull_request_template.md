<!--
Thanks for contributing to Hackagotchi! 🐾
This template maps to CONTRIBUTING.md §7. Fill in what applies; delete what doesn't.
The one rule that governs most reviews: the probe must never stall (R1). See §2.
-->

## What & why

<!-- What does this change do, and why? Link any issue: "Closes #123". -->

## Type of change

<!-- Tick all that apply. -->

- [ ] `feat` — new functionality
- [ ] `fix` — bug fix
- [ ] `docs` — documentation only
- [ ] `test` — a gate / HIL / host test
- [ ] `chore` / `ci` / `refactor`

## ⛔ R1 — does anything run on or above the DAP path?

<!--
Reviewers look here FIRST. The priority order is:
  UART bridge / watchdog  >  USB (TUD)  >  DAP  >  dashboard + SD writer
"On or above the DAP path" = the bridge cdc_task, any TUD callback, or DAP priority itself.
If your change is host-only / docs-only / lands entirely on the +0 dashboard/SD task, say so and tick "No".
-->

- [ ] **No** — this change is host-only, docs-only, or lands entirely on the **+0** dashboard/SD task.
- [ ] **Yes** — and here is how it stays non-blocking (no `sleep` / busy-wait / blocking I/O / DAP-needed lock on the hot path; slow work is posted to the owning task):

> _…explain…_

## Checklist

- [ ] **Did not edit `upstream/`** — customization is by overlay (new file in `src/`, or a shadowed copy added to `CMakeLists.txt` and documented in its header).
- [ ] **One owner per resource** — FatFs↔SD task, OLED/I2C1↔dashboard task, uart0 TX↔bridge task; no cross-task reach (post an async request instead).
- [ ] **No new silent drop / silent pass** — every bounded buffer has a counted overflow surfaced in `{"q":"status"}`; every new test can actually fail.
- [ ] Commits are **small, atomic, conventional-commit** (`feat(scope): …`), and each builds + passes the gate on its own.
- [ ] Every commit is **signed off** (`git commit -s` — [DCO](https://developercertificate.org/)).
- [ ] Shared hooks enabled (`git config core.hooksPath .githooks`) so personal AI-assistant context files stay out of the repo.
- [ ] New first-party files under `firmware/c/` carry an `SPDX-License-Identifier: MIT` header; no copyleft/non-commercial dep added to the shipping image.
- [ ] README / docs updated if a CDC1 command, dashboard screen, or build flag changed.

## Test evidence

<!--
CI proves "builds + analyze.sh passes" — NOT that the gates ran. HIL gates are attested by hand.
Paste host-test output and/or the HIL *_hil.py PASS lines. If you can't run a HIL test, say "needs bench: <which>".
Never report a HIL claim as proven unless you (or a recorded *_RESULTS.md entry) ran it on hardware.
-->

- [ ] **CI green** — `Firmware (C probe fork)` (build + `analyze.sh` gate) and `Host unit tests` (portable logic).
- [ ] **Host tests** run locally:

```
$ cc -I src tests/... && ./a.out
…paste output…
```

- [ ] **HIL** — attested on the candidate image, or noted as `needs bench: <which>`:

```
…paste the *_hil.py PASS lines, or the GATE_RESULTS.md / *_RESULTS.md entry…
```
