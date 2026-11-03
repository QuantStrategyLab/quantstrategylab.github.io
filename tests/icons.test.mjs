import test from "node:test";
import assert from "node:assert/strict";
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import zlib from "node:zlib";
import {
  CONTRAST_THRESHOLDS,
  REQUIRED_SITE_FILES,
  SITES,
  contrastForSite,
  contrastRatio,
  hexToRgb
} from "../scripts/site-icons-spec.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const PACKAGE = path.join(ROOT, "site-icons");
const LANDING = path.join(ROOT, "site", "assets");
const PNG_SIGNATURE = 0x89504e47;
const HEX = /^#[0-9A-Fa-f]{6}$/;

function pngInfo(buffer) {
  assert.equal(buffer.readUInt32BE(0), PNG_SIGNATURE, "PNG signature missing");
  return {
    width: buffer.readUInt32BE(16),
    height: buffer.readUInt32BE(20),
    bitDepth: buffer[24],
    colorType: buffer[25]
  };
}

function decodePng(buffer) {
  const { width, height } = pngInfo(buffer);
  const idat = [];
  let offset = 8;
  while (offset < buffer.length) {
    const length = buffer.readUInt32BE(offset);
    const type = buffer.toString("ascii", offset + 4, offset + 8);
    const data = buffer.subarray(offset + 8, offset + 8 + length);
    if (type === "IDAT") idat.push(data);
    offset += 12 + length;
  }
  const raw = zlib.inflateSync(Buffer.concat(idat));
  const stride = width * 4;
  assert.equal(raw.length, (stride + 1) * height, "unexpected PNG payload size");
  const pixels = Buffer.alloc(stride * height);
  for (let y = 0; y < height; y += 1) {
    const filter = raw[y * (stride + 1)];
    assert.equal(filter, 0, "verification decoder expects the builder's filter-0 rows");
    raw.copy(pixels, y * stride, y * (stride + 1) + 1, y * (stride + 1) + 1 + stride);
  }
  return { width, height, pixels };
}

function pixelAt(image, x, y) {
  const index = (y * image.width + x) * 4;
  return [...image.pixels.subarray(index, index + 4)];
}

function icoFrames(buffer) {
  assert.equal(buffer.readUInt16LE(0), 0, "ICO reserved field");
  assert.equal(buffer.readUInt16LE(2), 1, "ICO must contain icons");
  const count = buffer.readUInt16LE(4);
  const frames = [];
  for (let index = 0; index < count; index += 1) {
    const entry = 6 + index * 16;
    const size = buffer[entry] === 0 ? 256 : buffer[entry];
    const height = buffer[entry + 1] === 0 ? 256 : buffer[entry + 1];
    const bytes = buffer.readUInt32LE(entry + 8);
    const start = buffer.readUInt32LE(entry + 12);
    frames.push({ size, height, png: buffer.subarray(start, start + bytes) });
  }
  return frames;
}

function read(...parts) {
  return readFileSync(path.join(...parts));
}

function text(...parts) {
  return readFileSync(path.join(...parts), "utf8");
}

function siteFile(site, name) {
  return path.join(PACKAGE, site.dir, name);
}

function assertSelfContainedSvg(svg, label) {
  assert.doesNotMatch(svg, /<text\b/i, `${label} must not contain text`);
  assert.doesNotMatch(svg, /\b(?:href|src)\s*=\s*["'](?:https?:)?\/\//i, `${label} has an external reference`);
  assert.doesNotMatch(svg, /url\(\s*["']?(?:https?:)?\/\//i, `${label} has an external url()`);
  assert.doesNotMatch(svg, /@import\b/i, `${label} imports external CSS`);
  assert.match(svg, /role="img"/, `${label} needs role="img"`);
  assert.match(svg, /aria-label="[^"]+"/, `${label} needs an aria-label`);
  assert.match(svg, /prefers-color-scheme:\s*dark/, `${label} needs a dark-media branch`);
  assert.match(svg, /stroke-linecap="round"/, `${label} needs round stroke caps`);
  assert.match(svg, /stroke-linejoin="round"/, `${label} needs round stroke joins`);
}

test("package lives outside the served site tree and declares five complete sets", () => {
  assert.ok(existsSync(PACKAGE), "site-icons/ package is missing");
  assert.ok(!existsSync(path.join(ROOT, "site", "site-icons")), "package must not be inside site/");
  assert.equal(REQUIRED_SITE_FILES.length, 13);
  assert.deepEqual(SITES.map((site) => site.dir), [
    "meridian-console",
    "qar-research",
    "qas-gateway",
    "qrs-reconciliation",
    "organisation-landing"
  ]);
  assert.doesNotMatch(text(ROOT, "site", "index.html"), /site-icons/, "landing must not expose the asset package");
});

test("every site ships all 13 required files with sensible sizes", () => {
  const caps = {
    "icon.svg": 24 * 1024,
    "icon-16.svg": 24 * 1024,
    "icon-maskable.svg": 24 * 1024,
    "favicon.ico": 200 * 1024,
    "icon-16.png": 40 * 1024,
    "icon-32.png": 40 * 1024,
    "apple-touch-icon.png": 200 * 1024,
    "icon-192.png": 200 * 1024,
    "icon-512.png": 400 * 1024,
    "icon-maskable-512.png": 400 * 1024,
    "manifest.webmanifest.json": 8 * 1024,
    "head-snippet.html": 8 * 1024,
    "CONCEPT.txt": 16 * 1024
  };
  for (const site of SITES) {
    for (const name of REQUIRED_SITE_FILES) {
      const file = siteFile(site, name);
      assert.ok(existsSync(file), `${site.key}: missing ${name}`);
      const size = statSync(file).size;
      assert.ok(size > 0, `${site.key}: ${name} is empty`);
      assert.ok(size <= caps[name], `${site.key}: ${name} is unexpectedly large (${size} bytes)`);
    }
  }
  assert.ok(statSync(path.join(PACKAGE, "preview.png")).size < 4 * 1024 * 1024, "preview.png is too large");
  assert.ok(statSync(path.join(PACKAGE, "README.md")).size > 0, "README.md is missing");
  assert.ok(statSync(path.join(PACKAGE, "install.md")).size > 0, "install.md is missing");
});

test("raster sets have the required dimensions, alpha and safe-zone bleed", () => {
  const sizes = {
    "icon-16.png": 16,
    "icon-32.png": 32,
    "apple-touch-icon.png": 180,
    "icon-192.png": 192,
    "icon-512.png": 512,
    "icon-maskable-512.png": 512
  };
  for (const site of SITES) {
    for (const [name, size] of Object.entries(sizes)) {
      const image = decodePng(read(siteFile(site, name)));
      assert.equal(image.width, size, `${site.key}: ${name} width`);
      assert.equal(image.height, size, `${site.key}: ${name} height`);
      const info = pngInfo(read(siteFile(site, name)));
      assert.equal(info.bitDepth, 8, `${site.key}: ${name} bit depth`);
      assert.equal(info.colorType, 6, `${site.key}: ${name} must be RGBA`);
    }
    const normal = decodePng(read(siteFile(site, "icon-512.png")));
    const maskable = decodePng(read(siteFile(site, "icon-maskable-512.png")));
    const apple = decodePng(read(siteFile(site, "apple-touch-icon.png")));
    assert.equal(pixelAt(normal, 0, 0)[3], 0, `${site.key}: normal icon must keep rounded transparent corners`);
    assert.equal(pixelAt(maskable, 0, 0)[3], 255, `${site.key}: maskable icon must be full bleed`);
    assert.equal(pixelAt(apple, 0, 0)[3], 255, `${site.key}: apple icon must be full bleed`);
    const plate = hexToRgb(site.palette.light.plate);
    assert.deepEqual(pixelAt(maskable, 0, 0).slice(0, 3), [plate.r, plate.g, plate.b], `${site.key}: maskable corner must be plate colour`);
    const dot = site.normal.dot;
    if (!dot) continue; // The approved research original has horizontal bars, no endpoint.
    const point = [
      Math.round(((32 + (dot.x - 32) * 0.8) / 64) * 512),
      Math.round(((32 + (dot.y - 32) * 0.8) / 64) * 512)
    ];
    const accent = hexToRgb(site.palette.light[dot.role]);
    const actual = pixelAt(maskable, point[0], point[1]);
    assert.ok(
      Math.abs(actual[0] - accent.r) <= 2 && Math.abs(actual[1] - accent.g) <= 2 && Math.abs(actual[2] - accent.b) <= 2,
      `${site.key}: maskable end dot is missing at ${point.join(",")} (got ${actual.slice(0, 3).join(",")})`
    );
  }
});

test("favicons carry 16, 32 and 48 PNG frames with matching 16/32 files", () => {
  for (const site of SITES) {
    const frames = icoFrames(read(siteFile(site, "favicon.ico")));
    assert.deepEqual(frames.map((frame) => frame.size), [16, 32, 48], `${site.key}: ICO frame sizes`);
    assert.deepEqual(frames.map((frame) => frame.height), [16, 32, 48], `${site.key}: ICO frame heights`);
    for (const frame of frames) {
      const info = pngInfo(frame.png);
      assert.equal(info.width, frame.size, `${site.key}: ICO ${frame.size} width`);
      assert.equal(info.colorType, 6, `${site.key}: ICO frame must be RGBA PNG`);
    }
    assert.ok(frames[0].png.equals(read(siteFile(site, "icon-16.png"))), `${site.key}: ICO 16 frame must match icon-16.png`);
    assert.ok(frames[1].png.equals(read(siteFile(site, "icon-32.png"))), `${site.key}: ICO 32 frame must match icon-32.png`);
  }
});

test("manifests are bilingual, relative and resolve to shipped icons", () => {
  for (const site of SITES) {
    const manifest = JSON.parse(text(siteFile(site, "manifest.webmanifest.json")));
    assert.equal(typeof manifest.name, "string");
    assert.match(manifest.name, /[\u4e00-\u9fff]/, `${site.key}: manifest name needs Chinese copy`);
    assert.ok(manifest.name.toLowerCase().includes("quantstrategylab"), `${site.key}: manifest name needs English copy`);
    assert.equal(manifest.short_name, site.shortName);
    assert.match(manifest.theme_color, HEX, `${site.key}: theme_color`);
    assert.match(manifest.background_color, HEX, `${site.key}: background_color`);
    assert.equal(manifest.icons.length, 3, `${site.key}: expected 192, 512 and maskable 512 icons`);
    const purposes = manifest.icons.map((icon) => `${icon.sizes}/${icon.purpose}`).sort();
    assert.deepEqual(purposes, ["192x192/any", "512x512/any", "512x512/maskable"]);
    for (const icon of manifest.icons) {
      assert.equal(icon.type, "image/png");
      assert.doesNotMatch(icon.src, /^(?:https?:)?\/\//, `${site.key}: manifest icon must be local`);
      assert.ok(existsSync(path.join(PACKAGE, site.dir, icon.src)), `${site.key}: manifest points at missing ${icon.src}`);
    }
    assert.doesNotMatch(JSON.stringify(manifest), /(?:start_url|scope)":\s*"\//, `${site.key}: manifest must not assume a root deployment`);
  }
});

test("SVG masters carry light and dark palettes with the chart geometry", () => {
  for (const site of SITES) {
    const master = text(siteFile(site, "icon.svg"));
    const small = text(siteFile(site, "icon-16.svg"));
    const maskable = text(siteFile(site, "icon-maskable.svg"));

    if (site.key !== "meridian-console") {
      // Fixed approved art is shared by light/dark rather than recoloured by media CSS.
      for (const [label, svg] of [["master", master], ["small", small], ["maskable", maskable]]) {
        assert.doesNotMatch(svg, /<text\b|@import|https?:\/\/(?!www.w3.org)/i, label);
        assert.match(svg, /role="img"/);
        assert.match(svg, /aria-label="[^"]+"/);
        assert.doesNotMatch(svg, /class="rim"|@media/);
      }
      assert.match(master, /viewBox="0 0 64 64"/);
      assert.match(small, /viewBox="0 0 16 16"/);
      assert.match(small, /scale\(\.25\)/);
      assert.match(maskable, /scale\(\.8\)/);
      continue;
    }
    assert.match(master, /viewBox="0 0 64 64"/);
    assert.match(master, /<rect class="plate"[^>]*rx="14"/);
    assert.match(master, /stroke-width="5",?/);
    assert.match(master, /<circle class="accent"/);
    assertSelfContainedSvg(master, `${site.key} icon.svg`);

    assert.match(small, /viewBox="0 0 16 16"/);
    assert.match(small, /<rect class="plate"[^>]*rx="3.5"/);
    assertSelfContainedSvg(small, `${site.key} icon-16.svg`);

    assert.match(maskable, /viewBox="0 0 64 64"/);
    assert.match(maskable, /<rect class="plate" x="0" y="0" width="64" height="64"\/>/);
    assertSelfContainedSvg(maskable, `${site.key} icon-maskable.svg`);

    for (const [label, svg] of [["icon.svg", master], ["icon-16.svg", small], ["icon-maskable.svg", maskable]]) {
      const split = svg.indexOf("@media");
      assert.ok(split > 0, `${site.key}: ${label} lacks a media split`);
      assert.match(svg.slice(0, split), new RegExp(site.palette.light.plate, "i"), `${site.key}: ${label} lacks the light plate`);
      assert.match(svg.slice(split), new RegExp(site.palette.dark.plate, "i"), `${site.key}: ${label} lacks the dark plate`);
    }
  }
});

test("head snippets use relative links, one manifest and measured theme colours", () => {
  for (const site of SITES) {
    const snippet = text(siteFile(site, "head-snippet.html"));
    assert.equal((snippet.match(/<link rel="icon"/g) || []).length, 2, `${site.key}: expected SVG + ICO icon links`);
    assert.equal((snippet.match(/<link rel="manifest"/g) || []).length, 1, `${site.key}: exactly one manifest link`);
    assert.match(snippet, /<link rel="apple-touch-icon" href="assets\/icons\/apple-touch-icon\.png">/);
    assert.match(snippet, new RegExp(`content="${site.palette.themeLight}" media="\\(prefers-color-scheme: light\\)"`));
    assert.match(snippet, new RegExp(`content="${site.palette.themeDark}" media="\\(prefers-color-scheme: dark\\)"`));
    assert.match(snippet, new RegExp(site.englishName));
    assert.match(snippet, /[\u4e00-\u9fff]/, `${site.key}: snippet needs Chinese copy`);
    for (const match of snippet.matchAll(/href="([^"]+)"/g)) {
      assert.doesNotMatch(match[1], /^(?:https?:)?\/\//, `${site.key}: snippet must not use external links`);
      assert.doesNotMatch(match[1], /^\//, `${site.key}: snippet must use relative paths`);
    }
    const svgHref = site.key === "organisation-landing" ? "assets/favicon.svg" : "assets/icons/icon.svg";
    assert.match(snippet, new RegExp(`href="${svgHref.replace(/\./g, "\\.")}"`));
  }
});

test("contrast measurements stay current; approved art retains its measured limitations", () => {
  const contrast = JSON.parse(text(PACKAGE, "contrast.json"));
  assert.equal(contrast.direction, "A");
  assert.deepEqual(contrast.thresholds, CONTRAST_THRESHOLDS);
  for (const site of SITES) {
    const measured = contrast.sites[site.key];
    assert.deepEqual(measured, contrastForSite(site), `${site.key}: contrast.json is stale`);
    // The owner explicitly chose the original art. Do not silently redraw it to
    // satisfy the former variant's thresholds. Keep reporting all actual ratios.
    if (site.key !== "meridian-console") {
      assert.deepEqual(site.palette.light, site.palette.dark);
      assert.equal(site.palette.staticRimAlpha, site.key === "qrs-reconciliation" ? 1 : 0);
      for (const mode of ["light", "dark"]) {
        for (const value of Object.values(measured[mode])) assert.ok(Number.isFinite(value) && value >= 1);
      }
      continue;
    }
    for (const mode of ["light", "dark"]) {
      const values = measured[mode];
      assert.ok(values.glyphOnPlate >= CONTRAST_THRESHOLDS.glyphOnPlate, `${site.key} ${mode}: glyph ${values.glyphOnPlate}`);
      assert.ok(values.dotOnPlate >= CONTRAST_THRESHOLDS.dotOnPlate, `${site.key} ${mode}: dot ${values.dotOnPlate}`);
      assert.ok(values.baselineOnPlate >= CONTRAST_THRESHOLDS.baselineOnPlate, `${site.key} ${mode}: baseline ${values.baselineOnPlate}`);
      assert.ok(
        Math.max(values.plateOnTabLight, values.rimOnTabLight) >= CONTRAST_THRESHOLDS.plateOrRimOnTab,
        `${site.key} ${mode}: plate or rim is invisible on a light tab`
      );
      assert.ok(
        Math.max(values.plateOnTabDark, values.rimOnTabDark) >= CONTRAST_THRESHOLDS.plateOrRimOnTab,
        `${site.key} ${mode}: plate or rim is invisible on a dark tab`
      );
    }
    const lightPlate = site.palette.light.plate;
    assert.ok(
      Math.max(contrastRatio(lightPlate, site.palette.tabLight), measured.static.rimOnTabLight) >= CONTRAST_THRESHOLDS.plateOrRimOnTab,
      `${site.key}: static PNG disappears on a light tab`
    );
    assert.ok(
      Math.max(contrastRatio(lightPlate, site.palette.tabDark), measured.static.rimOnTabDark) >= CONTRAST_THRESHOLDS.plateOrRimOnTab,
      `${site.key}: static PNG disappears on a dark tab`
    );
    const concept = text(siteFile(site, "CONCEPT.txt"));
    assert.match(concept, /DIRECTION A/);
    assert.match(concept, new RegExp(`${measured.light.glyphOnPlate}:1`));
    assert.match(concept, new RegExp(`${measured.dark.glyphOnPlate}:1`));
  }
});

test("preview sheet shows both media modes at the required sizes", () => {
  const preview = decodePng(read(PACKAGE, "preview.png"));
  assert.equal(preview.width, 3000, "preview width");
  assert.ok(preview.height >= 2000, "preview must fit two full sections");
  assert.deepEqual(pixelAt(preview, 5, 5).slice(0, 3), [0xf3, 0xf4, 0xf6], "light section background");
  assert.deepEqual(pixelAt(preview, 10, preview.height - 20).slice(0, 3), [0x16, 0x18, 0x1d], "dark section background");
});

test("landing applies the organisation set and keeps a single icon family", () => {
  const landing = SITES.find((site) => site.key === "organisation-landing");
  assert.ok(read(LANDING, "favicon.svg").equals(read(siteFile(landing, "icon.svg"))), "landing favicon must be the package master");
  for (const name of ["favicon.ico", "apple-touch-icon.png", "icon-192.png", "icon-512.png", "icon-maskable-512.png"]) {
    assert.ok(read(LANDING, "icons", name).equals(read(siteFile(landing, name))), `landing ${name} differs from the package`);
  }
  assert.deepEqual(
    JSON.parse(text(LANDING, "icons", "manifest.webmanifest")),
    JSON.parse(text(siteFile(landing, "manifest.webmanifest.json"))),
    "landing manifest differs from the package"
  );

  const html = text(ROOT, "site", "index.html");
  assert.equal((html.match(/rel="icon"/g) || []).length, 2, "landing must link exactly the SVG and ICO");
  assert.equal((html.match(/rel="manifest"/g) || []).length, 1, "landing must link exactly one manifest");
  assert.match(html, /<link rel="icon" href="assets\/favicon\.svg" type="image\/svg\+xml">/);
  assert.match(html, /<link rel="icon" href="assets\/icons\/favicon\.ico" sizes="any">/);
  assert.match(html, /<link rel="apple-touch-icon" href="assets\/icons\/apple-touch-icon\.png">/);
  assert.match(html, /<link rel="manifest" href="assets\/icons\/manifest\.webmanifest">/);
  assert.match(html, /<meta name="theme-color" content="#E6E4DE" media="\(prefers-color-scheme: light\)">/);
  assert.match(html, /<meta name="theme-color" content="#15181D" media="\(prefers-color-scheme: dark\)">/);
  assert.doesNotMatch(html, /#2F6FED|>QSL<\/text>/, "old favicon identity must be gone");

  const assets = readdirSync(LANDING);
  assert.ok(!assets.includes("favicon.ico"), "legacy favicon.ico must not remain at the assets root");
  assert.ok(!assets.some((name) => /^icon-\d+\.png$/.test(name)), "landing raster icons belong in assets/icons/");
  assert.ok(existsSync(path.join(LANDING, "icons", "manifest.webmanifest")));
});

test("install guide covers every surface, target and cleanup step", () => {
  const install = text(PACKAGE, "install.md");
  for (const site of SITES) assert.ok(install.includes(site.dir), `install.md omits ${site.dir}`);
  for (const repo of ["quantstrategylab.github.io", "QuantAdvisorResearch", "QuantAIService"]) {
    assert.ok(install.includes(repo), `install.md omits ${repo}`);
  }
  for (const phrase of ["head-snippet.html", "manifest", "Delete", "assets/icons/"]) {
    assert.ok(install.includes(phrase), `install.md omits ${phrase}`);
  }
  assert.match(install, /owner to confirm/i, "unconfirmed repositories must be labelled");
});

test("package text carries no identifiers, emails or tokens", () => {
  const files = [path.join(PACKAGE, "README.md"), path.join(PACKAGE, "install.md"), path.join(PACKAGE, "contrast.json")];
  for (const site of SITES) {
    for (const name of REQUIRED_SITE_FILES) {
      if (/\.(?:svg|json|html|txt)$/.test(name)) files.push(siteFile(site, name));
    }
  }
  files.push(path.join(LANDING, "favicon.svg"), path.join(LANDING, "icons", "manifest.webmanifest"));
  const all = files.map((file) => readFileSync(file, "utf8")).join("\n");
  assert.doesNotMatch(all, /[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/i, "email address");
  assert.doesNotMatch(all, /\b(?:acct|account)[-_]?\d{3,}\b/i, "account-like identifier");
  assert.doesNotMatch(all, /\b(?:sk|pk|ghp)_[A-Za-z0-9]{10,}\b/, "token-like value");
  assert.doesNotMatch(all, /\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b/, "card-like number");
});
