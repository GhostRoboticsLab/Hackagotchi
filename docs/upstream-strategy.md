# Hackagotchi — Upstream Strategy

How we relate to the two upstream projects: **debugprobe** (our base) and **yapicoprobe**
(a feature donor we also intend to contribute to). Companion to `c-firmware-analysis.md` §2 and
`engineering-plan.md` §2.

---

## 1. debugprobe — our base: track official stable, diverge minimally

**Policy: base on the official `raspberrypi/debugprobe`, track STABLE TAGS only (never `master`),
and keep our delta small enough that rebasing onto a new stable tag is cheap.**

- **Start point:** `debugprobe-v2.2.3` (the last tag before the #189 SMP flash regression).
- **Update cadence:** when a newer stable tag lands (e.g. `v2.3.1`), **spike it through the
  Gate-1 soak** (`gate1_soak.sh` + the openocd twin). If it passes — especially if it carries the
  #189 fix — **rebase our overlay onto it**. Goal: ride upstream maintenance, don't fossilize on an
  old tag. (This is risk R10 in the engineering plan.)
- **Keep OUR DELTA MINIMAL — a thin overlay, not a hard fork:**
  - `boards/board_hackagotchi_config.h` (the XIAO pin map),
  - one low-priority core-0 dashboard FreeRTOS task,
  - the 2nd CDC (control channel) + USB interface-name descriptors,
  - the SD/OLED/recorder subsystems, isolated behind their own files.
  Everything else stays **stock**, so a rebase touches few files.
- **Push fixes UPSTREAM.** Any bug we hit in the probe/DAP/USB core goes back as a PR to
  `raspberrypi/debugprobe` rather than living as a private patch. Carrying private patches in the
  hot path is exactly what makes a fork rot.

---

## 2. yapicoprobe — feature donor + contribution target (NOT a base)

We do **not** fork yapicoprobe as our base (bus-factor ≈ 1; `master` currently fails to build on
modern `arm-none-eabi-gcc`, issue #197; no umbrella `LICENSE`). But it is a rich, MIT/Apache-ish
**source of features to cherry-pick** into our debugprobe-based fork — and a project we intend to
**contribute to**.

### 2a. Cherry-pick candidates (verified-status; re-confirm at adoption time)

| Feature | What it gives Hackagotchi | Verified | License | Priority | Notes |
|---|---|---|---|---|---|
| **MSC drag-n-drop UF2 flash** (DAPLink "drive") | Flash a target by copying a `.uf2` onto a mounted drive — zero host tooling | ✅ exists | MIT/Apache (`daplink-pico`) | **HIGH** (post-Gate 2) | Add an MSC interface to our composite; pairs with the CDC1 control channel. Endpoint budget check needed. |
| **RTT terminal → CDC** | Live target logging with **no UART pins**; our probe becomes the RTT host | ✅ | SEGGER-RTT BSD (attribution) | **HIGH** | Feeds a great dashboard "telemetry" screen. Keep RTT data **separate** from the recorded target-UART stream. |
| **sigrok logic-analyzer mode** | Turns the probe into a basic LA (PulseView) | ✅ | verify per-file | MED | Uses spare PIO; **pin-budget conflict** on the XIAO — verify feasibility. |
| **connect-under-reset / attach niceties** | More robust attach to a wedged target | ⚠️ to verify | — | MED | Confirm what's debugprobe-stock vs yapicoprobe-added before porting. |
| **FreeRTOS SMP priority table** | Proven task-priority template | ✅ (design ref) | — | **DONE** | Already folded into `engineering-plan.md` §4.1. |
| **SystemView streaming** | Bring-up task visualization | ✅ | ⚠️ **non-commercial** | **SKIP in product** | Bring-up tool only; never ship in the product image. |
| **NCM USB networking** | Probe-over-network | ✅ exists | — | SKIP | Not needed. |

**Cherry-pick discipline:** for each adopted feature — confirm the source file's license header,
vendor it with a NOTICE entry, and add a host-side + on-hardware test **before** merge. Re-verify
the feature is present and working against a *stable* yapicoprobe state at adoption time (its
`master` is build-broken as of #197).

### 2b. Contribution intent → toward maintainer

We intend to **support yapicoprobe with substantial fixes and PRs**, and over time possibly become
a **co-maintainer**. Concrete, well-scoped first contributions:

1. **Fix issue #197** — `master` fails to build on current `arm-none-eabi-gcc`
   ("cannot read spec file `nosys.specs`"). A clean build fix is high-value and unblocks everyone
   (including us). **Best first PR.**
2. **License hygiene** — there is **no umbrella `LICENSE` file** (the GitHub license API returns
   null). Proposing/adding one (reconciling the MIT + Apache-2.0 + SEGGER-BSD + FreeRTOS-MIT
   headers) is small, valuable, and also unblocks our ability to vendor its code for a product.
3. **RTT regressions** (#198 / #183) — investigate + fix once we're using the RTT path ourselves.
4. After a few landed PRs of this quality, **offer ongoing maintenance** to `rgrr`.

> Tracking upstream stable + contributing fixes (rather than diverging) is the cheapest long-term
> path to a reliable product **and** earns the standing to upstream the features we want.
