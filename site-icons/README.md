# Direction A — Chart series icon set

Production icon package for the five QuantStrategyLab surfaces. This folder is
**not** served by the organisation landing build: the Pages workflow uploads
`site/` only, so nothing here can leak into the public site by accident.

Owner-approved direction: **A "Chart series"**, 2026-11-03 12:40 SGT.

## Shared vocabulary

Every mark uses the same chart grammar:

- 64-unit box, rounded plate `rx14` (16 px file: `rx3.5`);
- round `5 px` strokes (`stroke-linecap` / `stroke-linejoin` = `round`);
- exactly one end dot;
- one baseline stroke;
- light/dark branches inside the SVG via `prefers-color-scheme`;
- no text, no external references, no runtime network calls.

## Sites

| Folder | Surface | Plate | Line / glyph | Accent |
| --- | --- | --- | --- | --- |
| `meridian-console/` | Meridian console | `#2563EB` | `#FFFFFF` | bone dot `#E6E4DE`, pale baseline `#93C5FD` |
| `qar-research/` | QAR research desk | `#1D3F66` | teal bars `#4FB3A7` | bone dot `#E6E4DE` |
| `qas-gateway/` | AI gateway | `#0E0F10` | orange posts `#FF7A1A`, bone request line | orange dot |
| `qrs-reconciliation/` | Reconciliation ledger | paper `#F4EEE1` | ink/amber entries | matched green dot `#2C5A39` |
| `organisation-landing/` | Org landing | ink `#15181D` | bone stepped equity line `#E6E4DE` | mint dot `#8EB8A8` |

`contrast.json` records every measured WCAG ratio. Thresholds follow WCAG 1.4.11
non-text contrast: glyph and dot ≥ 3:1, decorative baseline ≥ 2:1, and the plate
or rim must clear 3:1 against both light and dark mock tab strips. The Research
teal is the tightest glyph pair at **4.26:1** on its navy plate.

## Files per site

Thirteen files, all local and deterministic:

- `icon.svg` — master with light/dark media branches;
- `icon-16.svg` — simplified 16 px geometry (`viewBox="0 0 16 16"`);
- `icon-maskable.svg` — full-bleed plate, glyph inside the 80% safe zone;
- `favicon.ico` — 16 (simplified), 32 and 48 PNG frames;
- `icon-16.png`, `icon-32.png`, `icon-192.png`, `icon-512.png`;
- `apple-touch-icon.png` — 180 px, full bleed, 80% safe zone;
- `icon-maskable-512.png`;
- `manifest.webmanifest.json` — bilingual name, 192/512/maskable icons;
- `head-snippet.html` — copy-ready head block;
- `CONCEPT.txt` — palette, geometry and measured contrast.

`preview.png` shows all five sets at 512, 192, 64, 32 and 16 px in light and
dark mock tab strips.

## Regeneration

The builder is pure Node with no dependencies:

```sh
npm run build:icons
```

`npm test` runs the same builder through `pretest` before the offline
verification suite. Output is deterministic for a given Node runtime, so a
clean rebuild reproduces the same assets (including the compressed PNG bytes);
ICOs are written from those same PNG buffers. The organisation-landing set is
also copied to `site/assets/` (`favicon.svg` plus `site/assets/icons/`) by the
builder; that copy is the live landing favicon.

See `INSTALL.md` for per-site integration and cleanup.
