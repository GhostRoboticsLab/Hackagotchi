# Hackagotchi — go-to-market & virality strategy

> Strategy analysis, 2026-06-20. Evidence-based synthesis (real viral cases: Pwnagotchi,
> Flipper Zero, the ESP8266 deauther, Meshtastic) with an adversarial reality-check. Audience
> is **hobbyist makers** (beginner→advanced), explicitly **not** enterprise. Pairs with
> [`monetization.md`](monetization.md) (the money/manufacturing plan) and the open-core
> licensing decision (`LICENSE`, GPL-3.0).

## Thesis

This is an **attention-and-credibility play**, not a paid-acquisition play. The two real assets
are (1) a one-sentence, universally-felt pain — *your board's own debug channel dies exactly when
you need it* — and (2) a shareable pixel-cat mascot riffing on **Pwnagotchi**. Lead with the cat +
the wedge story in the maker tribe, convert that to Hackaday/Reddit/HN reach and GitHub stars; the
v2 SWD-recovery probe is the thing you eventually sell.

## Audience

- **Primary = hobbyist makers** (Pico / MicroPython / ESP32 / e-paper / cyberdeck crowd). For this
  audience the cat/pet personality is the **primary viral lever**, not a credibility risk.
- **Amplifiers** = the Pwnagotchi / Flipper / hardware-hacker scene (the `-gotchi` name gives
  instant context).
- **Not** a launch target: enterprise / QA-manufacturing, and the security/CTF crowd (Flipper owns
  it — you'd be out-ecosystemed).

## Positioning

- **One-liner (use everywhere):** *"A Pwnagotchi for debugging — it watches your board's heartbeat
  and screams when it flatlines, then black-boxes its dying words."*
- **The cat is the brand hero.** Pwnagotchi's creator: *"just adding a simple ASCII face was the
  best way to get emotionally overly attached."* Hackagotchi's cat is a *better* version — its moods
  map to a **real external event** (another board living/dying), not a self-referential score.
- **Lineage = free comprehension.** Flipper literally shipped as "Tamagochi for Hackers" and
  credited Pwnagotchi. The `Hackagotchi` name already does this and is under-exploited.
  - ⚠️ Never literally call it a "Tamagotchi" or copy the egg shape (Bandai trademark in 56
    countries). The `-gotchi` suffix itself is safe (Pwnagotchi precedent).
- Keep the credibility ballast one layer down (autonomous SD black box, freeze-frame "dying words",
  v2 recovery) so it never reads as *only* a toy.

## The single ignition move

**Make the OBJECT the cat, then fire one earned-media drop around it.**

The hero "money moment" lives on a tiny 0.96″ mono OLED — the drama is *conceptual*, not *visual*.
Fix it with the asset the team already has (in-house 3D printing): **redesign the enclosure as the
cat, with the OLED as its face** (see [`../case/CAT_ENCLOSURE_SPEC.md`](../case/CAT_ENCLOSURE_SPEC.md)),
so a single still photo of the powered-off object reads unmistakably as a cat. **Name the cat.**
Then shoot **one** clean, sound-on, seamless ~15 s loop: cat asleep → wakes on UART data → SCREAMS
the instant a recognizable board (Pi Pico / ESP32) wedges → freeze-frames its dying words.

Tailwind: the **2026 "anti-AI cyberdeck" wave** (personalized, character-driven, owned hardware) is
peaking — a printable cat that records and "saves" dev boards sits dead-center in that aesthetic.

## Channel sequence (don't blast all at once)

1. **Reddit first** (warm-up/proof): post the GIF as "I built a black-box recorder that screams when
   your dev board dies" → r/embedded + r/somethingimade, Tue/Wed ~9–10am ET, reply in the first 60 min.
2. **Hackaday 24–48 h later** (the amplifier): personal tip to `tips@hackaday.com`, war-story subject,
   link a media-rich Hackaday.io page, cite the Reddit numbers. Hackaday's bar is *"the only thing
   that needs to be complete is your description of the hack"* — ideal for a still-in-development
   project; it runs a dedicated Pwnagotchi tag.
3. **Hold Show HN** as a separate, later beat for the v2 C / debugprobe-fork / "recover a wedged
   board over SWD" *engineering* story (the HN-grade hook). Don't burn it on day one.
4. **Printables / MakerWorld** get the free enclosure STL (real algorithmic discovery + remix trees
   that link back). **Tindie is a cash register, not a megaphone** (near-zero organic discovery).

## The honest ceiling

| Tier | Looks like | Odds |
|---|---|---|
| Flipper-tier breakout | 5–6-figure crowdfund, TikTok, mainstream press | **≈ 0** |
| Pwnagotchi-tier | one maker-YouTuber pickup → thousands of stars, self-organizing community + skin economy | **~10–20%** (only if open-source + a photogenic cat-object + a clean first-flash) |
| **Tier 1 (the plan)** | Hackaday front page, top-of-sub on r/embedded, a few hundred stars week one → low-thousands over a year, a modest Tindie/Crowd Supply business | **Realistic target** |

**The hard ceiling is the narrowness of the pain.** "My board went silent on UART" is a real but
intermediate/intermittent problem — not the *fantasy* Pwnagotchi ("be a WiFi hacker") or Flipper
("open stuff you shouldn't") sold to millions. Target **"beloved niche maker tool with a cult
following"** as success; treat actual virality as a cheap upside lottery ticket you buy by nailing
the artifact.

## What kills virality (avoid)

- **Closed-source firmware** in a militantly-open lineage — disables the fork/plugin/skin flywheel
  that drove 100% of the comparables. (Resolved: project is GPL-3.0 open-core.)
- **A visually weak hero artifact** — if it reads as "a tiny screen beeping," nothing ignites. The
  cat-as-object redesign is the whole game.
- **Launching before the readiness gate** — a spike that converts to "I flashed it and it bricked" is
  worse than no spike.
- **Gating on v2** — real "resurrect the dead board" SWD recovery is months out (M1 of M5). Tease it
  as the sequel; never delay the cheap v1 spike for it.
- **Leading with the spec sheet, the 12-screen grid, or the toy-grade scope/logic/PWM "instruments"**
  — a reviewer with a Saleae benchmarks them and discounts the whole product.

## Readiness gate (pre-launch minimum, ~2–4 weeks)

1. Open-source license committed (done — GPL-3.0).
2. **Name the cat**; redesign + **actually print one** cat-object case for the hero shot.
3. Harden first-run: **watchdog/auto-reboot** instead of crash-spin, **SD-full + "logging stopped"**
   states, **vendor `sdcard.py`**, a **5-minute flash-and-first-capture** quickstart.
4. **Open the cosmetic layer** — a documented face/skin format + configurable trigger words — so the
   "show me my gotchi" UGC loop can exist. Ship 3–4 starter skins.

## Cut list

- Don't headline the universal "reboots/reflashes any wedged board" recovery — v1's reverse channel
  is RP2040-only and needs a live cooperating target. Caveat it or hold for v2.
- Don't sell hardware before the protection front-end exists (see `monetization.md`).
- Cat = thumbnail/sticker/avatar; never in the HN title, spec sheet, or any capability claim.
- Skip (premature) conferences, cold creator pitches, guest-post asks, a Discord, and the weekly
  build-in-public wheel — all assume reach/reputation you don't have yet. Earn them after launch 1.
