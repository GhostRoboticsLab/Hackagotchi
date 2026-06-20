# Hackagotchi UI Upgrade — v1.1 (grounded)

**Status:** planning doc for the *later* graphics/UI rewrite (after M3 ships the faithful port).
**Supersedes:** `hackagotchiUI_upgradev1.0.md` (a Ghost Labs spec written by an agent with **no context of
our hardware bring-up** — Gates 0–2, M1, M2, M3.0–M3.2). This doc keeps v1.0's good UI/aesthetic ideas and
**rejects its architectural prescriptions that contradict what we proved on hardware.**

---

## 0. Ground truth the v1.0 spec didn't have

These are *established by HIL evidence* in this repo (see `tests/{gates,m1,m2,m3}/*_RESULTS.md`,
`docs/engineering-plan.md`, the product-focus memory). The upgrade must respect them:

- **F1-1 — SINGLE-CORE FreeRTOS.** The base is debugprobe **v2.2.3**, `configNUM_CORES=1`. SMP (and the
  #189 flash regression) came later; we deliberately stay on the stable single-core tag. **There is no
  "Core 1" to give the UI.** Coexistence is by **priority/preemption**, proven across 5000+ flash cycles.
- **XIP, no flash-pinning.** We dropped `copy_to_ram` → run from flash XIP (**+139 KB SRAM**, free 35→174 KB).
  The soak proved the DAP hot path stays warm in the 16 KB XIP cache **without** `__not_in_flash_func`
  pinning (SWCLK is PIO-generated; the SWD servicing code is tiny). Pinning code into RAM would spend back
  the RAM win for no measured benefit.
- **No user button.** GP27 (the only expansion button) became **SWDIO** at Gate 1; GP26 → SWCLK. Input is
  **auto-cycle + CDC1** (`next`/`prev`/`{"q":"screen","n":N}`). External buttons/switches are a future
  soldering option (broken-out Dx pads only — GP16/17 aren't pads).
- **Hard-dropped screens.** Oscilloscope (ADC on GP26=SWCLK), PWM Lab (GP28=SD-CS + GP2=SD-SCK), Logic
  Analyzer (monitors the whole locked bus) **cannot exist** — they need runtime pin re-mux, which wedges
  SD/SWD/UART. I2C-scanner is pointless (only our own OLED+RTC on I2C1) and contends the bus.
- **Status LED = onboard WS2812 NeoPixel** (GP12 data + GP11 power), driven via **PIO on pio1** (SWD owns
  pio0). The tiny onboard RGB (GP16/17) proved unreliable (color ≠ spec + competes with the GP25 USB-LED).
- **i2c1 is SHARED** (OLED 0x3C + PCF8563 RTC 0x51), GP6/GP7, behind a FreeRTOS mutex. Any OLED change
  must keep the RTC working on the same bus.
- **Concurrency idiom = single-writer published snapshots / SPSC rings**, never shared mutable structs.
  The dashboard already reads recorder/RTC state via a seqlock `rec_snapshot_t` and touches i2c1 only for
  `ssd1306_show()`. The M2 "two-ring" rule is load-bearing.
- **R1 (make-or-break):** nothing on the DAP/USB hot path may block. The OLED `ssd1306_show()` (~23 ms at
  400 kHz) is proven-safe **only** because it runs at the lowest priority + fully preemptible; the M2/M3
  coexist soaks pass at the **250 ms** redraw cadence.

---

## 1. Adversarial verdict on v1.0, claim by claim

| v1.0 claim | Verdict | Why (grounded) |
| --- | --- | --- |
| **Dual-core split**: Core 0 diagnostic, Core 1 UI; communicate via `multicore_fifo` | **REJECT** | Single-core FreeRTOS (F1-1). There is no spare core without enabling the #189-regressed SMP path we avoided, or bare-metal core1 fighting FreeRTOS. Our priority model already gives the UI "free" time. |
| **"No shared volatile flags; use multicore FIFO"** | **REJECT** | Moot (single core) and counter to our *proven* single-writer-snapshot idiom. Keep snapshots/SPSC. |
| **`__not_in_flash_func()` the UI loop + ISRs to protect the XIP cache** | **REJECT** | We empirically disproved the cache-thrash fear; pinning re-spends the XIP RAM win. The UI is lowest-prio + preempted, so its cache footprint can't threaten DAP timing. |
| **Framebuffer in an isolated SRAM bank (`.sram4`)** | **DEFER / measure-first** | A real RP2040 technique for DMA-vs-USB AHB contention, but M2 already showed the OLED coexists at ~1% retryable. Only worth it *if* a DMA flush (below) shows measurable contention. Don't pre-optimize. |
| **DMA-push the 1025-byte framebuffer to I2C, CPU-free** | **ADOPT** | Genuine win: frees the CPU during the flush and (with FM+) shrinks the bus-hold. Our ssd1306 lib **already** uses the 1025-byte / `[0]=0x40` layout, so only the transfer path changes. Must still hold the i2c1 mutex for the DMA's duration (RTC shares the bus). |
| **`frame_dirty` — only flush on change** | **ADOPT** | We currently redraw every 250 ms. A dirty-flag cuts i2c1 traffic hugely (most frames are identical), freeing the bus for the RTC and lowering coexistence pressure. High value, low risk. |
| **I2C1 @ 1000 kHz (Fast Mode Plus)** | **ADAPT — with care** | FM+ shrinks the flush ~23 ms→~9 ms (good for R1). **But the PCF8563 RTC shares this bus and is typically rated 400 kHz.** Options: (a) verify the specific RTC tolerates FM+; (b) keep 400 kHz; (c) clock-switch around RTC transactions. Do **not** blindly set 1 MHz — it risks the clock. |
| **Reactive state machine (IDLE / UART_RX / ERROR), cat animation scales with packet rate** | **ADOPT** | Already feasible from the snapshot (`rx_total` delta, `wedge`, `alert`). This is the heart of the "alive" feel. Map states to snapshot fields, not FIFO messages. |
| **`STATE_OSC` / `STATE_PWM` (cat interacting with waveforms/wheels)** | **REJECT** | Those screens are hard-dropped (pin conflicts). No scope/PWM to react to. |
| **Sprite system (1-bit bitmap blit, lightweight struct)** | **ADOPT** | Needed for richer graphics than line-art. Sprites are `const` → live in flash/XIP, blit directly (no SRAM copy needed; cache-thrash disproven). This is the right primitive for the cat rewrite. |
| **Ghost Labs "Phantom" mascot + day/night variants (RTC)** | **ADOPT (aesthetic)** | Pure identity/polish; RTC day/night is trivial (we cache the clock). Good for the rewrite the user wants. |
| **Buzzer soundscapes (boot jingle, error buzz), non-blocking** | **ADOPT** | We have the buzzer HAL (GP29 PWM, non-blocking, serviced off the hot path). Jingles/alerts fit M3.3. |
| **MicroSD FatFs blackbox logging, non-blocking** | **ALREADY DONE** | That's M2 (the recorder). The UI just reads its snapshot. |
| **User-button HW interrupt → Core 1 for UI toggle/ack** | **REJECT** | No button (GP27=SWDIO). Use CDC1 nav; if external buttons get soldered later, route them to a free Dx pad + the existing nav intents. |
| **Battery voltage via onboard divider → "hunger" level** | **DEFER — needs HW** | The XIAO RP2040 has **no** battery divider (not a Pico LiPo). All ADC-capable pins (GP26-29) are taken (SWCLK/SWDIO/SD-CS/buzzer). Needs external sense HW on a future board rev. Cute idea, park it. |
| **SSD1306 Horizontal Addressing Mode for linear DMA** | **ADOPT (with DMA)** | Correct prerequisite for a single-shot full-frame DMA. Fold in when we do the DMA flush. |

**Net:** v1.0's *UI vision* (reactive sprite-based mascot ecosystem, DMA/dirty rendering, soundscapes) is
good and worth building. v1.0's *system architecture* (dual-core, flash-pinning, button, battery sense,
scope/PWM states, 1 MHz bus) is mostly wrong for our proven hardware/firmware and must not be copied.

---

## 2. The grounded v1.1 upgrade plan (for after M3)

**Keep the M3 spine** (lowest-prio render task, snapshot-only reads, i2c1-mutex'd show, CDC1 nav,
self-attestation with the show-success counter). Layer the upgrade on top:

**Phase A — render pipeline (perf + headroom).**
1. **Dirty-flag rendering** — hash/compare the framebuffer (or track a dirty bool per screen); only
   `ssd1306_show()` when it changed. Biggest, safest win; cuts i2c1 traffic → more RTC headroom + lower R1
   pressure. (Lets a faster animation cadence be cheap.)
2. **DMA framebuffer flush** — push the existing 1025-byte buffer via a DMA channel to I2C1 TX, holding the
   i2c1 mutex for the transfer; switch the SSD1306 to Horizontal Addressing. Frees the CPU during the flush.
3. **Conditional FM+** — only after confirming the PCF8563 tolerates it (else keep 400 kHz, or clock-switch
   around RTC reads). Re-run the coexist soak at the new cadence — *the soak is the gate, not the spec.*

**Phase B — graphics rewrite (the part the user wants).**
4. **Sprite engine** — a tiny `sprite_t { w,h, const uint8_t *bits }` + blit (XOR/OR/clear) into the
   framebuffer. Sprites are `const` (flash/XIP). Replace the line-art cat with sprite frames.
5. **Reactive mascot state machine** — `IDLE / RX / WEDGE / FAULT` derived from the snapshot (rx-rate,
   wedge, alert, SD error). Animation speed scales with `tp_now`. Add the Ghost Labs phantom + RTC
   day/night variants. The NeoPixel mirrors state (idle=dim, RX=green pulse, wedge/fault=red).
6. **Soundscape** — boot jingle + per-state buzzer motifs via the existing non-blocking HAL (M3.3 wires
   wedge/fault/trigger; the rewrite adds the jingle + RX blips).

**Phase C — input & expansion (optional, HW-gated).**
7. If external buttons get soldered (free Dx pad), route them to the existing `dash_nav_step`/`dash_nav_to`
   intents + a "select/ack" intent — zero architecture change.
8. Battery/hunger only on a board rev that adds a real divider on a free ADC pin.

**Non-negotiables for every phase:** stay single-core + priority-preemptive; keep the render task lowest-
prio; read state only via published snapshots; keep i2c1's only writers the OLED show + RTC (mutex'd);
**gate every change on the probe-rs coexist soak (0 stalls, rec_drop=0)** — not on the spec's assertions.

---

## 3. One-line summary
Take v1.0's *look* (reactive sprite mascot + ghost, DMA/dirty rendering, soundscapes, day/night); throw out
its *architecture* (dual-core, flash-pinning, a button, battery sense, scope/PWM, 1 MHz bus) — all of which
assume a device we don't have. Build the upgrade on the proven M3 spine, soak-gated.
