# Brand assets

Source of truth: [ADR-0001](../adr/0001-brand-identity-klopot.md).

The mark **is** the two `o`s in the wordmark: a solid amber **source disc** and
an **open amber ring with a detached satellite** at its upper-right opening — a
declared event leaving the system for delivery. The word is set in JetBrains
Mono Bold (700), lowercase, optically kerned. Both `o`s are amber `#FFB31A` on
every background; the open ring + satellite also stand alone as the app icon.

| File | Purpose |
|------|---------|
| `klopot-mark.svg` | App icon: open ring + satellite on an ink tile (≥ 24 px) |
| `klopot-favicon.svg` | Favicon variant (< 24 px): ring + satellite, thickened/simplified |
| `klopot-symbol.svg` | Ring + satellite alone, amber on transparent |
| `klopot-mark-mono.svg` | Ring + satellite in `currentColor`, no tile (README/docs headers, print) |
| `klopot-wordmark.svg` / `klopot-wordmark-dark.svg` | Full `klopot` wordmark — light / dark |
| `klopot-lockup.svg` / `klopot-lockup-dark.svg` | Wordmark + `.dev` suffix, light / dark |
| `social-preview.svg` | 1280×640 social card (lockup + tagline on ink); rasterise to PNG for GitHub |
| `concepts.html` | Historical exploration sheet (Threshold, then disc + locator), kept for the record |

The letters are **outlined paths** cut from JetBrains Mono 700, so the SVGs carry
no font dependency. The admin UI embeds the same outlined wordmark as inline
SVG (letters `currentColor`, the two `o` marks amber) — see ADR-0001 Typography.

## Palette

Amber `#FFB31A` · ink `#0C1016` · paper `#F5F6F8` · secondary `#ADB4BF` (on dark)
/ `#46505C` (on light). Letters off-white on dark, near-black on light; the whole
`.dev` suffix stays the **neutral secondary** colour, never amber.

## Themes

The wordmark ships light and dark variants because the ink letterforms have no
contrast on a dark background. In a README, swap them by scheme:

```html
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/brand/klopot-wordmark-dark.svg">
  <img src="docs/brand/klopot-wordmark.svg" alt="klopot" height="40">
</picture>
```

## Contrast

Text clears AA comfortably: letters ~17.6:1 on their ground; `.dev` secondary
9.1:1 (dark) / 7.6:1 (light). The amber `o` marks are a **logo signature, not
text** — amber on the light ground is ~1.7:1 by design and is not held to the
text contrast bar.

## Rasterising

No rasteriser is bundled. Generate the social PNG with any SVG tool, e.g.
`rsvg-convert -w 1280 social-preview.svg > social-preview.png`, and upload it as
the repository's social preview. (The tagline uses Inter; install it or convert
to outlines first.)

Applied to the admin UI (favicon, tokens, wordmark) 2026-11-08; the wordmark was
reworked to the disc + open-ring + satellite signal mark on 2026-11-09.
