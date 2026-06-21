# Cat-as-object enclosure — spec & CAD-agent prompt

> Design spec, 2026-06-20. Evolves the existing "Field Recorder" pebble
> ([`HACKAGOTCHI_CASE.md`](HACKAGOTCHI_CASE.md) / `hackagotchi_case.scad`) into **Hackagotchi** — a
> desk-cat enclosure whose **face is the OLED**. The single ignition lever: a still
> photo of the powered-off object must read unmistakably as a cat.

## Design thesis

Fuse mascot + object. The on-screen `draw_cat` sprite (a 28×20 head with pointed ears, nose,
whiskers, wagging tail) should rhyme with the physical form. **#1 acceptance criterion:** one still
photo of the powered-OFF printed unit reads as a cat. The team's in-house 3D printing makes this the
highest-leverage, lowest-cost viral asset.

## Hardware to enclose

Seeed XIAO RP2040 stacked on the Seeed XIAO Expansion Board — **every dimension stays a parametric
`[MEASURE]` placeholder**, matching the current file's discipline:

- 0.96″ 128×64 SSD1306 OLED · microSD slot (edge access) · PCF8563 RTC + CR1220 coin cell ·
  passive buzzer · user button · USB-C (on the XIAO) · UART-tap leads GP0/GP1/GND exiting as a
  bundle · optional future LiPo volume.

## Cat-feature → physical mapping

| Cat feature | Physical realization |
|---|---|
| **Face** | the flush OLED visor — the screen shows the cat mascot, so the object frames the screen *as* the face |
| **Ears** | two pointed 3D ears at the OLED end, flanking the canted top corners (echo the sprite's ear angle) |
| **Nose / mouth** | the buzzer grille, recentred directly below the screen as a muzzle motif |
| **Whiskers** | shallow debossed lines on the front face flanking the screen |
| **Cheek / paw** | the recessed user button as a tap-target "cheek" |
| **Tail / rump** | the probe-snout cable boot at the XIAO end where USB-C + tap leads exit — sculpt a curled-tail relief |
| **Collar loop** | the lanyard eyelet, relocated between/behind the ears |

## Carry over from v1

Canted top (tilts screen to a desk viewer) · snap-fit seam + **no visible screws** · corner-post
board cradle · flush visor. **Print:** FDM, 0.4 mm nozzle / 0.2 mm layers, PETG or PLA; base
flat-down, top visor-window-down → no supports; ears self-support **or** are separate snap/glue
parts; ship a `coupon` (one ear + seam + cable opening) to print first.

## The CAD-agent prompt

Hand the block below to a CAD agent (OpenSCAD-fluent) to refactor `case/hackagotchi_case.scad`:

```
ROLE: You are a parametric CAD engineer fluent in OpenSCAD and FDM design-for-manufacture.

GOAL: Refactor the existing enclosure `case/hackagotchi_case.scad` from a plain "Field Recorder"
pebble into "Hackagotchi" — a desk-cat enclosure whose FACE is the OLED screen. THE #1 ACCEPTANCE
CRITERION: a single still photo of the powered-OFF printed object must read unmistakably as a cat.
This is a marketing-critical hero object, not just a box.

START FROM: the current `case/hackagotchi_case.scad` and `case/HACKAGOTCHI_CASE.md`. Preserve its
parametric structure, its `[MEASURE]`-placeholder discipline (DO NOT invent precise hardware
dimensions — keep every unknown as a clearly-commented variable with a provisional default), its
snap-fit seam, corner-post board cradle, canted top, and no-visible-screws constraint.

HARDWARE TO HOUSE (Seeed XIAO RP2040 stacked on the Seeed XIAO Expansion Board; all dims = [MEASURE]):
- 0.96" 128x64 SSD1306 OLED (the "face")     - microSD slot, edge-accessible
- PCF8563 RTC + CR1220 coin-cell holder       - passive buzzer        - user button
- USB-C port on the XIAO                       - UART-tap leads GP0/GP1/GND exit as a bundle
- leave an optional parametric volume for a future LiPo (default off)

CAT FORM (map features onto function — the printed silhouette must persist when unpowered):
- FACE  = flush OLED visor with a thin frame reveal (the on-screen mascot aligns to it)
- EARS  = two pointed 3D ears at the OLED end flanking the canted top corners
- NOSE/MOUTH = the buzzer grille, recentred directly below the screen as a muzzle
- WHISKERS   = shallow debossed lines on the front face beside the screen
- CHEEK = the recessed user button                - TAIL/RUMP = the probe-snout cable boot at
  the XIAO end (USB-C + tap leads exit here); add a curled-tail relief
- COLLAR LOOP = lanyard eyelet relocated between/behind the ears

HARD CONSTRAINTS:
- FDM, 0.4 mm nozzle, 0.2 mm layers, PETG/PLA. Base prints flat-down, top prints visor-down →
  NO support material. Ears must EITHER self-support at their radii OR be separate snap/glue parts
  (your call — justify it in a comment). Keep wall thickness, snap-fit lip clearance (`lip_clr`),
  and all tolerances as named parameters.
- Everything parametric. Anything you cannot know (board outline, component positions, OLED active
  area, USB-C cutout, tap-lead slot) stays a `[MEASURE]` variable with a sane default + a comment.

DELIVERABLES:
1. Refactored `case/hackagotchi_case.scad` with a `part=` switch: "base" | "top" | "ears"
   (if separate) | "coupon" | "all" (preview only).
2. Every part renders MANIFOLD / NoError via the OpenSCAD CLI. Provide the exact render commands.
3. A "[MEASURE] checklist": list every variable a human must set with calipers before a full print,
   grouped by part, each with units and what to measure against.
4. A 3-line print plan (orientation per part, which to print first, support=none confirmation).

STYLE: minimal but unmistakably feline; soft radii; the cat should look intentional and cute, not
a literal toy cat — think "instrument with a face." Comment your geometry. Do not add electronics,
firmware, or BOM commentary — enclosure only. If a requirement is physically impossible to print
without supports, say so and propose the nearest printable alternative rather than silently changing intent.
```
