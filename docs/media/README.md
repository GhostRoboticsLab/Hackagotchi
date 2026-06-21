# Media assets

Drop README / launch media here.

## `social-preview.jpg` — the GitHub social card ✅ (in repo)

The Open Graph card GitHub serves as the link-unfurl image (on GitHub itself, plus HN /
Reddit / Mastodon / Slack / Discord).

- **1280×640** (2:1), JPEG, **under 1 MB** — GitHub rejects social-preview uploads over 1 MB.
- Generated with Nano Banana 2 from `repository-open-graph-template.png`; the AI sparkle
  watermark was painted out and the image cropped/resized to spec.
- **To apply it:** repo **Settings → General → Social preview → Edit → Upload an image** →
  pick `docs/media/social-preview.jpg`. This is a **one-time manual upload** — GitHub does
  *not* read the file from the repo automatically.
- The full-res source generations (and the de-watermarked master) are kept local under
  `img_assets/` (gitignored), not committed, to keep the repo lean.

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
