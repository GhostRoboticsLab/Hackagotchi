# Media assets

Drop README / launch media here.

## `hero.png` — the README hero render (placeholder slot)

The top of [`../../README.md`](../../README.md) has a **commented-out** `<img>` waiting for this file:

```html
<!-- HERO RENDER: export the Blender hero to docs/media/hero.png ... and uncomment the <img> below.
<img src="docs/media/hero.png" width="640" alt="Hackagotchi — XIAO RP2040: CMSIS-DAP debug probe + UART black-box recorder + reactive OLED companion" />
-->
```

When the Blender render is ready:

1. Export it to `docs/media/hero.png` (recommend ~1280 px wide; transparent or dark background so it reads on both GitHub themes).
2. **Uncomment** the `<img>` block in `README.md` (delete the `<!--` and `-->` lines around it).

Until then the slot renders nothing — no broken-image icon.

## Other assets to add here later

- `hero.gif` — the looping cat + ghost reaction loop (the launch centerpiece): idle → throughput → wedge → exorcise-on-reflash. Keep it under ~5 MB so it inlines on GitHub.
- `social-preview.png` — 1280×640, set via **Settings → Social preview** (controls the link unfurl card on HN / Reddit / Mastodon / Slack / Discord).
