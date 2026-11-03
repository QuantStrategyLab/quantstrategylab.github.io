# INSTALL — Direction A "Chart series" icons

This package is the single source of truth for the five QuantStrategyLab icon
sets. Copy one folder per site; do not hand-edit the generated files. Rebuild
with `npm run build:icons`.

## Targets and destinations

| Package folder | Surface | Target repository | Destination in that repo | Status |
| --- | --- | --- | --- | --- |
| `organisation-landing/` | Organisation landing | `quantstrategylab.github.io` | `site/assets/favicon.svg` + `site/assets/icons/` | **Applied in this PR** |
| `meridian-console/` | Meridian console | Console web repo — owner to confirm slug | Served static directory + `assets/icons/` | Copy pending |
| `qar-research/` | QAR research desk | `QuantAdvisorResearch` | The site's served static dir + `assets/icons/` | Copy pending |
| `qas-gateway/` | AI gateway | `QuantAIService` | Frontend static dir + `assets/icons/` | Copy pending; static route TBC |
| `qrs-reconciliation/` | Reconciliation ledger | Reconciliation web repo — owner to confirm slug | Served static directory + `assets/icons/` | Copy pending |

Do not guess a repository or route that is not listed above. The two "owner to
confirm" rows are deliberate: the slug and asset root must be read from the
target deployment, not inferred from a role name.

## Copy procedure (non-landing sites)

1. Create `assets/icons/` in the target site's served static directory.
2. Copy all 13 files from the site folder into it.
3. Rename `manifest.webmanifest.json` to `manifest.webmanifest` (the landing
   copy and the head snippets use the `.webmanifest` extension).
4. Put the SVG master at `assets/icons/icon.svg`. Do **not** also keep a
   second master at `assets/favicon.svg`; the master is `icon.svg` for these
   four sites, and `favicon.svg` only on the landing repo.
5. Add the links from `head-snippet.html` to the site `<head>`, adjusting the
   relative prefix if the page is not served from the site root.
6. If the site already has a web-app manifest, merge instead of replacing:
   keep the target's own `start_url` / `scope` / `id`, copy `name`,
   `short_name`, `description`, `theme_color`, `background_color`, and append
   the three icon entries (`192x192/any`, `512x512/any`,
   `512x512/maskable`). Keep exactly one `<link rel="manifest">`.
7. Delete the previous favicon family and any old icon links (see below).

All heads should end with this shape, using the paths that match the host:

```html
<link rel="icon" href="assets/icons/icon.svg" type="image/svg+xml">
<link rel="icon" href="assets/icons/favicon.ico" sizes="any">
<link rel="apple-touch-icon" href="assets/icons/apple-touch-icon.png">
<link rel="manifest" href="assets/icons/manifest.webmanifest">
<meta name="theme-color" content="#…" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#…" media="(prefers-color-scheme: dark)">
```

The exact colours for each site are already written in its
`head-snippet.html`; do not hand-transcribe them.

### Relative paths and subpaths

The snippets and manifests use relative paths on purpose. They work at a domain
root and under a project-page prefix such as `/<repo>/`. If a page uses
client-side routing and is not served from the site root, resolve the hrefs
through the application's base-path helper instead of copying them verbatim.
The manifests intentionally omit `start_url` and `scope` so a project page is
not pinned to `/`; keep the target app's own values when merging.

## Organisation landing — already applied

This PR changed the landing in place:

- replaced `site/assets/favicon.svg` with the Direction A stepped equity master
  (light/dark media branches, no text);
- added `site/assets/icons/favicon.ico`, `apple-touch-icon.png`,
  `icon-192.png`, `icon-512.png`, `icon-maskable-512.png` and
  `manifest.webmanifest`;
- added the SVG + ICO + Apple + manifest links and the two `theme-color` metas
  to `site/index.html`;
- kept exactly one icon family: there is no legacy `site/assets/favicon.ico`
  and no raster icons at the assets root.

No other landing file, copy string or layout was changed.

## Per-site notes

### Meridian console

- Palette: blue plate `#2563EB`, white line, bone dot, pale-blue baseline.
- Repo slug and static root are **not** proven in this checkout. Confirm before
  copying; do not add a backend route just to serve icons.
- If the console build fingerprints assets, place the folder in the public
  static directory so the filenames in the manifest remain stable.

### QAR research desk (`QuantAdvisorResearch`)

- Palette: navy `#1D3F66`, two white horizontal bars, a shorter teal bar `#4FB3A7`, and pale-blue baseline.
- This replaces any earlier r1 `icon.svg` / `icon-16.svg` /
  `icon-maskable.svg` in the same destination. Delete the old trio so only one
  master remains.
- The teal glyph is **4.26:1** on navy. That clears the 3:1 non-text threshold
  but not 4.5:1 text contrast; do not set small text in this teal on navy.
- If the site already ships a manifest, merge per the procedure above.

### AI gateway (`QuantAIService`)

- Palette: signal-orange `#FF7A1A` plate, near-black `#0E0F10` gate posts, request line and endpoint, light-orange baseline.
- The approved original has no added rim; its palette is fixed in both schemes.
- **Static-asset route is TBC.** If the gateway service does not serve static
  files, the frontend host (not this PR) must expose `/assets/icons/`. Do not
  add backend handlers, mounts or proxy rules as part of an icon change.
- Theme colours: light `#F3F4F6`, dark `#0E0F10`; background `#0E0F10`.

### Reconciliation ledger

- Palette: paper `#EDE5D3`, ink `#211E19`, matched green `#2C5A39`, amber
  `#9A6410`. The symmetric chevron and original ink border remain fixed in both schemes.
- The paper plate is the visible surface on light chrome; the ink rim is what
  keeps it legible where the surface is light. Do not strip the rim from the
  static PNGs.
- Repo slug and asset root are **not** proven here. Confirm before copying.
- If reconciliation and console are separate frontends, use the same set in
  both; the folder is the canonical copy.

## What to delete after integration

- old `favicon.ico`, `favicon.png`, `favicon.svg` (except the landing's
  replaced `favicon.svg`), old `apple-touch-icon*.png`, old
  `icon-*.png` / `icon-*.svg` masters;
- old `<link rel="icon">`, `<link rel="apple-touch-icon">` and duplicate
  `<link rel="manifest">` entries;
- duplicate `theme-color` metas that point at the previous palette;
- any earlier r1 icon trio in the same folder.

Keep exactly **two icon links** (SVG + ICO), one Apple link, and one manifest
link per page.

## Verification

Offline, from the organisation landing repo:

```sh
npm run build:icons
npm test
```

`tests/icons.test.mjs` fails closed on: missing files, wrong PNG dimensions,
ICO frames other than 16/32/48, ICO frames that differ from the shipped PNGs,
malformed or non-bilingual manifests, manifest icons that do not exist, SVG
text or external references, changed approved masters, incomplete original inventory,
console contrast below its thresholds, stale `contrast.json`, a preview that is not 3000 px wide
with both media sections, and a landing copy that differs from the package.

Manual checks after deployment:

1. Browser tab in light and dark mode — the mark stays legible;
2. DevTools → Application → Manifest — name, colours and all three icons;
3. iOS "Add to Home Screen" — full-bleed Apple icon, no clipped glyph;
4. Android install prompt — maskable icon is not cropped;
5. Network panel — no icon, font or manifest request leaves the origin.

## Rollback

Restore the previous favicon/manifest files from the target repo's history and
remove the added head block. Nothing in this package is referenced by runtime
code, so rollback is a file-and-head-only change.
