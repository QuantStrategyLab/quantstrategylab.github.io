// Naming hygiene for the published landing: every icon reference is root-relative
// and resolves to a real Direction A file, including the implicit /favicon.ico.
import test from "node:test";
import assert from "node:assert/strict";
import { existsSync, readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const SITE = path.join(ROOT, "site");
const PACKAGE = path.join(ROOT, "site-icons", "organisation-landing");
const html = readFileSync(path.join(SITE, "index.html"), "utf8");

// Direction A USAGE.md names for the landing set, served from the site root.
const USAGE_NAMES = [
  "favicon.ico",
  "landing-light.svg",
  "landing-light-192.png",
  "landing-light-512.png",
  "landing-light-maskable-512.png",
  "landing-light-apple-touch-180.png"
];
const LEGACY_NAMES = [
  path.join("assets", "favicon.svg"),
  path.join("assets", "icons", "favicon.ico"),
  path.join("assets", "icons", "apple-touch-icon.png"),
  path.join("assets", "icons", "icon-192.png"),
  path.join("assets", "icons", "icon-512.png"),
  path.join("assets", "icons", "icon-maskable-512.png"),
  path.join("assets", "icons", "manifest.webmanifest")
];

function linkHrefs(markup) {
  return [...markup.matchAll(/<link\b[^>]*href="([^"]+)"/g)].map((match) => match[1]);
}

function icoFrameSizes(buffer) {
  assert.equal(buffer.readUInt16LE(0), 0, "ICO reserved field");
  assert.equal(buffer.readUInt16LE(2), 1, "ICO type must be icons");
  const count = buffer.readUInt16LE(4);
  const sizes = [];
  for (let index = 0; index < count; index += 1) {
    const entry = 6 + index * 16;
    const byte = buffer[entry];
    sizes.push(byte === 0 ? 256 : byte);
    assert.equal(buffer.readUInt32BE(buffer.readUInt32LE(entry + 12)), 0x89504e47, "ICO frame must be PNG");
  }
  return sizes;
}

test("every landing icon link is root-relative and points at an existing file", () => {
  const hrefs = linkHrefs(html);
  const iconHrefs = hrefs.filter(
    (href) => href.endsWith(".ico") || href.endsWith(".svg") || href.endsWith(".png") || href.endsWith(".webmanifest")
  );
  assert.deepEqual(
    iconHrefs.slice().sort(),
    ["/favicon.ico", "/landing-light-apple-touch-180.png", "/landing-light.svg", "/manifest.webmanifest"],
    "the head must link exactly the ICO, SVG master, Apple icon and manifest"
  );
  assert.equal((html.match(/rel="icon"/g) || []).length, 2, "expected the SVG and ICO icon links");
  assert.equal((html.match(/rel="manifest"/g) || []).length, 1, "expected exactly one manifest link");
  for (const href of iconHrefs) {
    assert.match(href, /^\//, `${href}: icon references must be root-relative`);
    assert.doesNotMatch(href, /^(?:https?:)?\/\//, `${href}: icon references must not be absolute URLs`);
    const file = path.join(SITE, href.replace(/^\//, ""));
    assert.ok(existsSync(file), `${href} resolves to a missing file`);
    assert.ok(readFileSync(file).length > 0, `${href} is empty`);
  }
});

test("/favicon.ico is the approved Direction A ICO with 16/32/48 frames", () => {
  const served = readFileSync(path.join(SITE, "favicon.ico"));
  assert.deepEqual(icoFrameSizes(served), [16, 32, 48], "root favicon frame sizes");
  assert.ok(
    served.equals(readFileSync(path.join(PACKAGE, "favicon.ico"))),
    "/favicon.ico must be the approved Direction A ICO asset, byte for byte"
  );
});

test("landing manifest icons are root-relative and exist", () => {
  const manifest = JSON.parse(readFileSync(path.join(SITE, "manifest.webmanifest"), "utf8"));
  assert.equal(manifest.icons.length, 3, "expected 192, 512 and maskable 512 icons");
  for (const icon of manifest.icons) {
    assert.match(icon.src, /^\//, `${icon.src}: manifest icon src must be root-relative`);
    assert.ok(icon.src.startsWith("/landing-light-"), `${icon.src}: manifest icon name must follow USAGE naming`);
    const file = path.join(SITE, icon.src.replace(/^\//, ""));
    assert.ok(existsSync(file), `manifest points at missing ${icon.src}`);
  }
  const names = manifest.icons.map((icon) => path.basename(icon.src)).sort();
  assert.deepEqual(names, [
    "landing-light-192.png",
    "landing-light-512.png",
    "landing-light-maskable-512.png"
  ]);
});

test("legacy landing asset names are gone", () => {
  for (const relative of LEGACY_NAMES) {
    assert.ok(!existsSync(path.join(SITE, relative)), `stale asset still present: site/${relative}`);
  }
  assert.doesNotMatch(html, /assets\/icons\/|assets\/favicon\.svg/, "the head still references a legacy asset path");
  for (const name of USAGE_NAMES) {
    assert.ok(existsSync(path.join(SITE, name)), `missing site root asset: ${name}`);
  }
  // A single icon family, and nothing else loose at the served root.
  assert.deepEqual(readdirSync(SITE, { withFileTypes: true }).filter((entry) => entry.isFile()).map((entry) => entry.name).sort(), [
    "favicon.ico",
    "index.html",
    "landing-light-192.png",
    "landing-light-512.png",
    "landing-light-apple-touch-180.png",
    "landing-light-maskable-512.png",
    "landing-light.svg",
    "manifest.webmanifest"
  ]);
});

test("served icon bytes match the package originals", () => {
  const pairs = [
    ["landing-light.svg", "icon.svg"],
    ["landing-light-192.png", "icon-192.png"],
    ["landing-light-512.png", "icon-512.png"],
    ["landing-light-maskable-512.png", "icon-maskable-512.png"],
    ["landing-light-apple-touch-180.png", "apple-touch-icon.png"]
  ];
  for (const [servedName, packageName] of pairs) {
    assert.ok(
      readFileSync(path.join(SITE, servedName)).equals(readFileSync(path.join(PACKAGE, packageName))),
      `site/${servedName} differs from site-icons/organisation-landing/${packageName}`
    );
  }
});
