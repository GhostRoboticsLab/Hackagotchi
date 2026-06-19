// hackagotchi_case.scad — minimal pocket case for Hackagotchi (Seeed XIAO RP2040 + Expansion Board:
// 128x64 OLED, microSD, PCF8563 RTC + CR1220, buzzer, user button). A "field recorder" form:
// a soft pebble with a gently CANTED top so the OLED tilts toward you on a desk, a tapering
// PROBE SNOUT where the UART-tap leads exit, and a LANYARD eyelet for pocket carry. Snap-fit
// clamshell, no visible screws.
//
//   openscad -D 'part="base"'   -o case/pt_base.stl   case/hackagotchi_case.scad
//   openscad -D 'part="top"'    -o case/pt_top.stl    case/hackagotchi_case.scad
//   openscad -D 'part="coupon"' -o case/pt_coupon.stl case/hackagotchi_case.scad   // fit test
//   openscad -D 'part="all"'    -o case/pt_preview.stl case/hackagotchi_case.scad  // preview only
//
// v1 (2026-06-19) — authored from datasheets; board outline + component positions are [MEASURE].
// The FORM is the deliverable; confirm cutout positions with calipers and print the coupon first.

part = "all";          // "base" | "top" | "coupon" | "all"
$fn = 80;
eps = 0.02;

/* ===== board (Seeed XIAO Expansion Base) — [MEASURE] all of these ===== */
brd_l   = 72.0;        // expansion board length [MEASURE]
brd_w   = 30.0;        // expansion board width  [MEASURE]
brd_t   = 1.2;         // PCB thickness
comp_h  = 9.0;         // tallest topside component clearance (OLED module / RTC holder) [MEASURE]
under_h = 2.5;         // underside clearance (XIAO + solder) below the PCB [MEASURE]

// component positions, board-centred coords (X along length, Y along width) — [MEASURE].
// -X = OLED end = HIGH end of the cant (tall enough for the 9mm OLED module).
// +X = XIAO end = LOW end -> USB-C + UART-tap leads exit here through the snout.
oled_pos = [-17.0, 0]; // OLED active-area centre (on the high end)
oled_w   = 22.0;       // OLED active width  (window = active + frame reveal)
oled_h   = 11.5;       // OLED active height
btn_pos  = [4.0, -9.0];// user button centre
sd_edge_y= +1;         // microSD slot on the +Y long edge; -1 for -Y
sd_pos_x = -6.0;       // microSD slot centre along X
buzz_pos = [6.0, 9.0]; // buzzer (grille goes over this)

/* ===== shell / fit ===== */
wall     = 2.0;        // side wall thickness
floor_t  = 1.6;        // base floor thickness
roof_t   = 1.8;        // top roof thickness (over the OLED visor frame)
corner_r = 5.0;        // generous pebble corner radius
fit      = 0.4;        // board edge -> inner wall clearance, per side
h_front  = 14.0;       // outer height at the front (USB-C/OLED-near) edge
h_back   = 19.0;       // outer height at the back edge -> the cant that tilts the OLED up
split_z  = 7.0;        // base/top split height above the bottom (snap seam)
lip_h    = 3.0;        // snap-lip overlap depth at the seam
lip_clr  = 0.18;       // snap-lip clearance per side (raise if too tight)

/* ===== features ===== */
frame    = 1.2;        // OLED window frame reveal beyond the active area, per side
btn_bore = 4.0;        // button access hole
usbc_w   = 9.6; usbc_h = 3.6;     // USB-C cutout
sd_w     = 12.5; sd_h  = 2.2;     // microSD slot cutout
snout_w  = 12.0;       // probe-snout width (tap leads GP0/GP1/GND exit here, +X end)
snout_d  = 7.0;        // how far the snout necks out past the body
tap_slot = 5.0;        // tap-lead exit slot height/width
eyelet_d = 5.0;        // lanyard eyelet outer loop
eyelet_hole = 2.6;     // lanyard hole

/* ===== derived ===== */
cav_l   = brd_l + 2*fit;
cav_w   = brd_w + 2*fit;
outer_l = cav_l + 2*wall;
outer_w = cav_w + 2*wall;
tilt    = atan2(h_back - h_front, outer_l);   // top-face cant angle
board_z = floor_t + under_h;                   // PCB underside height in the base

module rrect(w, h, r) offset(r=r) square([max(0.1,w - 2*r), max(0.1,h - 2*r)], center=true);
module rbox(w, h, t, r) linear_extrude(height=t) rrect(w, h, r);

/* ---- the full outer pebble: a rounded prism with a canted (wedged) top ---- */
module shell_outer() {
  intersection() {
    rbox(outer_l, outer_w, h_back + 10, corner_r);
    // half-space below the cant plane (higher at -X/back, lower at +X/front)
    translate([0, 0, (h_front + h_back)/2])
      rotate([0, tilt, 0])
        translate([0, 0, -100]) cube([800, 800, 200], center=true);
  }
}

/* ---- hollow inner volume (shell_outer shrunk by wall/floor/roof) ---- */
module shell_inner() {
  intersection() {
    translate([0, 0, floor_t])
      rbox(outer_l - 2*wall, outer_w - 2*wall, h_back + 10, max(0.6, corner_r - wall));
    translate([0, 0, (h_front + h_back)/2 - roof_t/cos(tilt)])
      rotate([0, tilt, 0])
        translate([0, 0, -100]) cube([800, 800, 200], center=true);
  }
}

/* ---- probe snout: a rounded cable-boot on the +X end, centred on the USB-C/tap exit ---- */
module snout() {
  translate([outer_l/2 - 1, 0, board_z + 1.0])
    hull() {
      rotate([90, 0, 0]) cylinder(h = snout_w, d = usbc_h + 5, center = true, $fn = 48);
      translate([snout_d, 0, 0])
        rotate([90, 0, 0]) cylinder(h = snout_w * 0.7, d = usbc_h + 2.5, center = true, $fn = 48);
    }
}

/* ---- lanyard eyelet: a loop off the -X/back top corner ---- */
module eyelet() {
  translate([-outer_l/2 - eyelet_d*0.4, outer_w/2 - eyelet_d, h_back - eyelet_d/2 - 1])
    rotate([90, 0, 0])
      difference() {
        cylinder(h = 3.2, d = eyelet_d + 3, center = true);
        cylinder(h = 4, d = eyelet_hole, center = true);
      }
}

/* ---- board-locating posts in the base (corner cradles) ---- */
module board_posts() {
  for (sx = [-1, 1]) for (sy = [-1, 1])
    translate([sx*(cav_l/2 - 1.6), sy*(cav_w/2 - 1.6), floor_t]) {
      linear_extrude(under_h) square([3.2, 3.2], center=true);      // PCB rest pillar
      translate([0,0,under_h]) linear_extrude(brd_t + 1.2)          // edge-capture lip
        square([3.2, 3.2], center=true);
    }
}

/* ---- top cutouts: OLED window, button, buzzer grille (cut through the roof) ---- */
module top_cuts() {
  // OLED window — projected straight up through the canted roof
  translate([oled_pos[0], oled_pos[1], 0])
    rbox(oled_w + 2*frame, oled_h + 2*frame, h_back + 5, 1.6);
  // button bore
  translate([btn_pos[0], btn_pos[1], 0]) cylinder(h = h_back + 5, d = btn_bore);
  // buzzer grille — a small 3x3 hole array
  for (i = [-1:1]) for (j = [-1:1])
    translate([buzz_pos[0] + i*3.2, buzz_pos[1] + j*3.2, 0]) cylinder(h = h_back + 5, d = 1.4);
}

/* ---- edge cutouts: combined USB-C + tap exit through the +X snout, microSD on a long edge ---- */
module edge_cuts() {
  // One generous opening through the +X snout for the XIAO USB-C AND the UART-tap leads
  // (both originate at the XIAO end). A single cable boot rather than two fragile slots.
  translate([outer_l/2 + snout_d/2, 0, board_z + 1.5])
    hull() {
      cube([snout_d + wall + 2, usbc_w, usbc_h], center=true);                 // USB-C window
      translate([0, 0, -1.5]) cube([snout_d + wall + 2, usbc_w + 4, tap_slot], center=true); // lead exit
    }
  // microSD on a long edge
  translate([sd_pos_x, sd_edge_y*(outer_w/2), board_z + 0.5])
    rotate([90,0,0]) cube([sd_w, sd_h, 3*wall], center=true);
}

/* ---- assemblies ---- */
module body_solid() { union() { shell_outer(); snout(); eyelet(); } }

module base() {
  difference() {
    union() {
      intersection() { body_solid(); translate([0,0,-eps]) rbox(outer_l+40, outer_w+40, split_z+eps, 0.1); }
      board_posts();
    }
    // hollow + seam recess for the top's lip + edge cuts
    shell_inner();
    translate([0,0,split_z - lip_h])
      difference() {
        rbox(outer_l - 2*wall + 2*lip_clr + 2, outer_w - 2*wall + 2*lip_clr + 2, lip_h + eps, corner_r);
        rbox(outer_l - 2*wall - 2*lip_clr, outer_w - 2*wall - 2*lip_clr, lip_h + 4*eps, max(0.6,corner_r-wall));
      }
    edge_cuts();
  }
}

module top() {
  difference() {
    union() {
      intersection() { body_solid(); translate([0,0,split_z]) rbox(outer_l+40, outer_w+40, h_back+10, 0.1); }
      // inward snap lip that drops into the base recess
      translate([0,0,split_z - lip_h])
        difference() {
          rbox(outer_l - 2*wall + 2*lip_clr, outer_w - 2*wall + 2*lip_clr, lip_h, max(0.6,corner_r-wall));
          translate([0,0,-eps]) rbox(outer_l - 2*wall - 2*lip_clr - 2, outer_w - 2*wall - 2*lip_clr - 2, lip_h+2*eps, max(0.6,corner_r-wall));
        }
    }
    shell_inner();
    top_cuts();
    edge_cuts();
  }
}

/* ---- coupon: the snout end of the base+top for a fast seam/fit test ---- */
module coupon() {
  intersection() {
    union() { base(); top(); }
    translate([outer_l/2 - 8, 0, (h_back)/2]) cube([24, outer_w+2, h_back+10], center=true);
  }
}

/* ---- dispatch ---- */
if (part == "base") base();
else if (part == "top") top();
else if (part == "coupon") coupon();
else {                                   // "all": exploded preview
  base();
  color("white") translate([0, 0, h_back + 8]) top();
}
