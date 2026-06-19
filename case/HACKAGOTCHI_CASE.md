# Hackagotchi case — "Field Recorder"

A minimal pocket enclosure for **Hackagotchi** (Seeed XIAO RP2040 + Expansion Board: 128×64
OLED, microSD, PCF8563 RTC + CR1220, buzzer, user button). Source: `case/hackagotchi_case.scad`.

## The form

A soft pebble with a few deliberate, functional gestures — minimal but not anonymous:

- **Canted top** — the lid slopes up toward the OLED end so the screen tilts toward you on a
  desk. Hackagotchi is a *glanceable* black-box recorder; the cant makes it readable without
  picking it up. (It also gives the OLED end the extra height the 9 mm OLED module needs.)
- **Probe snout** — a rounded cable-boot on the XIAO end where the USB-C and the UART-tap
  leads (GP0/GP1/GND) exit together. It reads as the "business end" of an instrument and
  gives the leads strain relief.
- **Lanyard eyelet** — a loop at the tall OLED corner (away from the cables) so it rides on a
  keyring or bag zip — it's a *pocket* tool.
- **Flush OLED visor** with a thin frame reveal, a recessed **button**, and a small **buzzer
  grille** (3×3 holes). Soft radii throughout, snap-fit seam, **no visible screws**.

## Render to STL

```bash
openscad -D 'part="base"'   -o case/pt_base.stl   case/hackagotchi_case.scad
openscad -D 'part="top"'    -o case/pt_top.stl    case/hackagotchi_case.scad
openscad -D 'part="coupon"' -o case/pt_coupon.stl case/hackagotchi_case.scad   # print FIRST: seam/fit test
openscad -D 'part="all"'    -o case/pt_preview.stl case/hackagotchi_case.scad  # preview only — do NOT print
```

All three parts render manifold / `NoError`.

## Mounting & assembly

- The board is cradled by four **corner posts** (rest pillar + edge-capture lip) in the base.
- **Snap-fit**: the top's inward lip drops into a recess in the base rim (`lip_h`, `lip_clr`).
- **Print**: PETG or PLA, 0.4 mm nozzle / 0.2 mm layers. Base flat-down, top OLED-window-down
  → no supports. The eyelet and snout self-support at these radii.

## ⚠️ Confirm with calipers before printing

This is **v1 — the *form* is the deliverable, not the fit.** Every board outline and component
position is marked `[MEASURE]` in the `.scad` because this machine has no Hackagotchi hardware to
measure. Before a full print, measure and set:

- `brd_l/brd_w/brd_t`, `comp_h` (OLED module height), `under_h` (XIAO underside clearance)
- `oled_pos/oled_w/oled_h`, `btn_pos`, `buzz_pos`, `sd_pos_x/sd_edge_y` (component positions)
- the USB-C opening (`usbc_w/usbc_h`) and tap-lead slot (`tap_slot`)

Print the **`coupon`** (the snout end) first to check the seam snap and the cable opening, then
commit to the full base + top.
