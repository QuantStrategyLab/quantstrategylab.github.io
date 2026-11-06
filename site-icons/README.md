# Direction A — Chart series icon set

Production icon package for the five QuantStrategyLab surfaces. This folder is
**not** served by the organisation landing build: the Pages workflow uploads
`site/` only, so nothing here can leak into the public site by accident.

The set follows direction A, "Chart series".

## Shared vocabulary

Every mark uses the same chart grammar:

- 64-unit box, rounded plate `rx14` (the reconciliation original uses its own ink-bordered plate);
- round `5 px` strokes (`stroke-linecap` / `stroke-linejoin` = `round`);
- an end dot except on the approved horizontal research bars;
- one baseline stroke;
- fixed approved colours in both schemes for research, gateway, reconciliation and landing; the console keeps its existing media branches;
- no text, no external references, no runtime network calls.

## Sites

| Folder | Surface | Plate | Line / glyph | Accent |
| --- | --- | --- | --- | --- |
| `meridian-console/` | Meridian console | `#2563EB` | `#FFFFFF` | bone dot `#E6E4DE`, pale baseline `#93C5FD` |
| `qar-research/` | QAR research desk | `#1D3F66` | white horizontal bars | short teal bar `#4FB3A7` |
| `qas-gateway/` | AI gateway | `#FF7A1A` | near-black posts and request line | near-black dot |
| `qrs-reconciliation/` | Reconciliation ledger | paper `#EDE5D3` | symmetric ink chevron | matched green dot `#2C5A39` |
| `organisation-landing/` | Org landing | green `#22483E` | bone stepped line and dot `#F5F4EF` | mint baseline `#8EB8A8` |

`contrast.json` records every measured ratio, including limitations of the approved
originals. The former variant's 3:1 plate/rim threshold is not met by every original
on every tab background. The approved art is preserved without added rims or palette
changes. Console contrast thresholds remain unchanged.

The four originals in `scripts/approved-direction-a.json` are copied from the
owner-approved direction A thumbnail source. Master SVGs add accessibility metadata
only. Small icons scale the same art; maskable and Apple icons retain the existing
full-bleed, 80% safe-zone adaptation.

## Files per site

Thirteen files, all local and deterministic:

- `icon.svg` — master preserving approved art;
- `icon-16.svg` — 16 px geometry (scaled original for the four restored icons) (`viewBox="0 0 16 16"`);
- `icon-maskable.svg` — full-bleed plate, glyph inside the 80% safe zone;
- `favicon.ico` — 16, 32 and 48 PNG frames;
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
also published to the served root, `site/`, under the `.design` USAGE.md names
(`/favicon.ico`, `/landing-light.*`, `/manifest.webmanifest`); that copy is the
live landing icon family.

See `install.md` for per-site integration and cleanup.
