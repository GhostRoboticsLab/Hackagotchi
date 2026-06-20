# Hackagotchi — open-core monetization, pricing & manufacturing

> Strategy analysis, 2026-06-20. Web-researched unit economics + an adversarial CFO-style
> reality-check; the numbers below are the **corrected** (haircut) figures, not the optimistic
> first-pass. Models the **niche** outcome (Hackaday front page + low-thousands of stars over a
> year), anchored to the closest real comparable — Tigard's ~$80k Crowd Supply raise — not a
> Pwnagotchi/Flipper fantasy. Pairs with [`go-to-market.md`](go-to-market.md).

## Honest headline

**Year 1 is a break-even hobby, not a business** — and that's the *realistic* case. At ~80–120
assembled units, hardware revenue (~$6–7k) is roughly erased by your own fulfilment + support time,
on top of the hundreds of unpaid hours going into v2. It becomes **modest side-income in Year 2 only
if a Crowd Supply v2 campaign lands.**

So: **sell hardware — but only one hero SKU, only in demand-proven batches, never as a standing
inventory bet.** Firmware + brand + STL alone can't fund v2 (sponsors + tips ≈ $500–1,200/yr), so the
assembled unit is the stream that pays for the part and seeds the v2 campaign.

You are not selling firmware (open) or parts (Seeed undercuts you at ~$24). You're selling the
**protection front-end Seeed doesn't make, pre-flash+test, the bespoke cat case, and the brand.**

## Pricing ladder

| SKU | Price | Notes |
|---|---|---|
| Firmware / SD image | **Free** (PWYW, $5 suggested) | Never monetize the GPL bytes |
| Pre-flashed microSD | **$9** | Captures the "don't want to flash" crowd |
| **Hero SKU** — assembled, pre-flashed, cased, **with protection front-end** | **$69** | Band $69–75. *Not $59* — at honest ~$30 COGS + ~9% fees + free-ship, $59 nets ~$0 after labor |
| Protection front-end add-on PCB/kit | **$14** | The *one* "kit" with a moat — self-builders need it, Seeed doesn't sell it, prevents brick-on-miswire RMAs |
| **v2 "Pro"** — carrier PCB, real SWD recovery | **$99** | Year-2, Crowd Supply. ~$45–50 contribution. The margin engine. |
| Faceplates/skins · premium faceplate · stickers · bundle | $9 (3/$24) · $19 · $5 · **$75 bundle** | AOV lifters only — not stocked/shipped standalone |

**Drop the generic bag-of-parts kit** — Seeed sells the same combo for $20–25; zero margin, competes
with your own supplier.

### Competitor anchors (confirmed 2026)

RPi Debug Probe **$12** · Tigard **$39** · Bus Pirate 5 **~$42–47** · Watchy kit+case **$59** ·
pre-assembled Pwnagotchi **$120** · Glasgow **$139/$189** · Flipper Zero **$169**. Defensible window
for the assembled unit: **$54–75**; floor is the bare $12 probe you can't beat, ceiling is the
narrower-pain Glasgow/Flipper you can't reach.

## Unit economics @ $69 (hand-built, honest)

- Landed COGS **~$30** (XIAO ~$5 + Expansion ~$10 + microSD ~$2.5 + CR1220 ~$0.4 + **protection
  front-end ~$3** + header/cables ~$2 + filament ~$2 + packaging ~$2).
- Tindie fees ~9% (5% + ~3.5% + $0.30); buyer pays shipping.
- **Contribution ~$26/unit before labor → ~$0–11 after** your time at small batch.
- **Labor, not BOM, is the margin killer.** Only batch size + a carrier PCB (cuts solder time) move
  it; after-labor contribution climbs toward ~$20/unit at batch-200.

## Revenue scenarios (corrected)

| Scenario | Units (Y1) | Revenue | Reality |
|---|---|---|---|
| Low | ~40–70 | ~$2–4k | A hobby |
| **Base (plan for this)** | **~80–120** | **~$6–7k** | Break-even after your time |
| Year-2 upside (v2 campaign) | ~200–350 | ~$15–30k | First run that actually pays you |
| Lottery (10–20%, Pwnagotchi-tier) | 1k–2k | $60–120k | **Never** in the P&L or any spend decision |

## The two cardinal financial rules

1. **Never spend carrier-PCB tooling (~$2k NRE) + batch inventory ($4–12k) outside a pre-funded
   crowdfunding campaign.** A debug "gotchi" is illiquid inventory — at 0.2% conversion you sit on
   ~200 unsold units and $4–6k of dead cash. *Inventory-before-demand is the biggest dollar risk.*
2. **Never ship a unit without the protection front-end.** A 5V target TX or reversed probe *silently
   bricks* a bare-GPIO unit; a 5–10% RMA rate erases all contribution + the brand. Product safety —
   do it before the first sale. *Skipped-protection is the quickest way to lose money.*

## Manufacturing roadmap (staged thresholds)

| Part | ≤100 units | ~100–500 | 500–2,000+ |
|---|---|---|---|
| **Enclosure** | FDM in-house (print *time* is the bottleneck, not filament) | Print-on-demand MJF/resin ~$8–15/case | Injection-mold only at 2,000+ (tool $2–8k) — **never at niche volume** |
| **Electronics** | COTS XIAO+Expansion **+ ~$3–5 protection board** (series-R + BAT54S clamps + TXS0108E level translator) | — | **Custom carrier PCB** via JLCPCB PCBA (NRE ~$1.5–2.5k; COGS ~$20@300 → ~$15@1k; fixes the SD-vs-PWM pin collision in copper) — only after a funded campaign |
| **Certification** | No radio → **self-declare FCC + CE** (saves ~$3–10k lab bill). Ship **battery-less to skip UN38.3** (LiPo-only trigger). RoHS/REACH from parts. | | |
| **Assembly** | Build a solder/test/flash jig. Flash + OLED functional test (~20–40 min/order) is the real time sink. | | |

## Channel sequence

1. **Stage 1 — validate (v1 done, 10–50 hand-built):** Tindie @ $69 + a **Lectronz EU mirror** (both
   collect tax for you — Tindie US facilitator, Lectronz EU IOSS). ~9% fees, ~$0 tooling. **Capture a
   v2 waitlist email on every page.**
2. **Decision gate:** proceed to carrier/v2 **only if v1 clears ~100 units AND the waitlist >300.**
3. **Stage 2 — Year 2:** crowdfund v2 on **Crowd Supply, not Kickstarter** (hardware-hacker audience;
   they do manufacturing guidance + Mouser fulfilment + customs + VAT). Their ~15% + ~$10/item nets
   ~$30/unit *and buys out 150–250 hrs of solo labor*. Pre-orders fund the MOQ; break-even ~100–140
   units; target $15–30k.
4. **Stage 3 — steady state:** Crowd Supply store (Mouser long-tail) + Tindie/Lectronz (discovery) +
   own Shopify (brand hub for bundles/named editions). Printed cat cases on **Etsy** ($25–35, taps
   Pwnagotchi-case traffic); STL free or Lemon Squeezy ($5–9, merchant-of-record handles global tax).

## Pre-revenue gate (do before any sale)

- [ ] Finish + **bundle the protection front-end** into every unit
- [ ] Register the **"Hackagotchi" trademark** (~$300 — the real moat under open-core)
- [ ] Switch on **GitHub Sponsors** (5 min, compounds)
- [ ] Keep firmware **and** STL free

## Cut list

- Generic parts/kit SKU; paid firmware; standalone merch/paid-STL managed as products.
- Any carrier-PCB or large batch run outside a pre-funded campaign.
- Kickstarter for v2 (you'd eat all fulfilment/customs/VAT solo).
- LiPo/charger in v1 (UN38.3 shipping burden) unless the campaign funds it.
- Injection-molding at niche volume; launching the hero SKU at $59; planning around 300 units / the
  1k–2k lottery.
