# quantstrategylab.github.io

English | [简体中文](README.zh-CN.md)

Static organization landing site for QuantStrategyLab, served from `site/` via GitHub Pages.

## Status

Active. This repository publishes the static organization landing page and icon assets. It is informational only, provides no financial or investment advice, and does not execute trades or connect to any broker.

## What this is

A dependency-free HTML and CSS landing page introducing QuantStrategyLab and its open-source repositories, together with the source icon specifications and local verification scripts used to build and check the published `site/` directory.

## What this is not

This repository does not contain trading strategies, market-data pipelines, execution engines, or user accounts. It has no backend service, server-side rendering, or third-party runtime dependencies.

## Quick start

Requirements: Node.js 20+ and Python 3.12+.

```bash
# Rebuild site icons and run the Node test suite
npm test

# Run the Python site checker tests and publication guard
python3 -m unittest discover -s scripts -p "test_*.py"
python3 scripts/check_site.py --phase 2
```

To preview the static site locally, serve the `site/` directory with any static HTTP server:

```bash
python3 -m http.server --directory site 8080
```

## Configuration

The site has no runtime environment variables or configuration files. GitHub Pages deployment is configured in `.github/workflows/pages.yml` and publishes only the `site/` directory.

| Item | Required | Default | Purpose |
|---|---|---|---|
| `site/` | Yes | Repository root `site/` | Static HTML, CSS, icons, and manifest uploaded to GitHub Pages |
| `PORT` (local preview) | No | `8080` | Local HTTP server port when previewing `site/` |

## Architecture

The published site is pure static HTML and CSS in `site/` with zero external network requests at runtime. Icon masters and specifications live outside `site/` under `site-icons/` and are compiled into `site/` by `scripts/build-site-icons.mjs`. Publication checks verify icon integrity, contrast, i18n key parity, and public content boundaries before deployment.

## Repository layout

```text
site/           Published static site (index.html, assets/, icons, manifest)
site-icons/     Icon source assets, contrast measurements, and specifications
scripts/        Icon build script (build-site-icons.mjs) and site checks
tests/          Node test suite covering icons and landing page invariants
.github/        GitHub Actions workflows, CODEOWNERS, and Dependabot config
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) and [AGENTS.md](AGENTS.md) for contribution workflow, commit conventions, and public content boundaries.

## Security

See [SECURITY.md](SECURITY.md). Do not open a public issue for a vulnerability.

## License

Released under the [MIT License](LICENSE).
