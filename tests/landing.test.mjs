import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const I18N = require("../site/assets/i18n.js");
const html = readFileSync(new URL("../site/index.html", import.meta.url), "utf8");
const css = readFileSync(new URL("../site/assets/styles.css", import.meta.url), "utf8");
const appJs = readFileSync(new URL("../site/assets/app.js", import.meta.url), "utf8");
const i18nJs = readFileSync(new URL("../site/assets/i18n.js", import.meta.url), "utf8");
const favicon = readFileSync(new URL("../site/assets/favicon.svg", import.meta.url), "utf8");

const LOCALES = ["en", "zh-CN"];
const THEMES = ["light", "dark"];
const TOKENS = ["bg", "surf", "ink", "ink2", "ink3", "rule", "rule2", "acc", "acc2", "onacc"];
const ALLOWED_LINKS = new Set([
  "https://github.com/QuantStrategyLab",
  "https://github.com/QuantStrategyLab/QuantPlatformKit",
  "https://github.com/QuantStrategyLab/UsEquityStrategies",
  "https://github.com/QuantStrategyLab/QuantAdvisorResearch"
]);

function themeTokens(theme) {
  const block = css.match(new RegExp(`\\[data-theme=${theme}\\]\\s*\\{([^}]*)\\}`));
  assert.ok(block, `missing [data-theme=${theme}] token block`);
  const tokens = {};
  for (const match of block[1].matchAll(/(--[a-z0-9-]+)\s*:\s*([^;]+);/gi)) {
    tokens[match[1]] = match[2].trim();
  }
  return tokens;
}

function channel(value) {
  const c = value / 255;
  return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
}

function luminance(hex) {
  const value = hex.replace("#", "");
  assert.equal(value.length, 6, `expected a 6-digit hex colour, got ${hex}`);
  const [r, g, b] = [0, 2, 4].map((offset) => channel(parseInt(value.slice(offset, offset + 2), 16)));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(fg, bg) {
  const a = luminance(fg);
  const b = luminance(bg);
  return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
}

test("i18n locales have identical key sets and non-empty values", () => {
  assert.deepEqual(Object.keys(I18N).sort(), LOCALES.slice().sort());
  assert.deepEqual(Object.keys(I18N["zh-CN"]).sort(), Object.keys(I18N.en).sort());
  for (const locale of LOCALES) {
    for (const [key, value] of Object.entries(I18N[locale])) {
      assert.equal(typeof value, "string", `${locale}.${key} must be a string`);
      assert.ok(value.trim().length > 0, `${locale}.${key} must not be empty`);
    }
  }
});

test("every referenced i18n key exists in both locales", () => {
  const referenced = new Set();
  for (const match of html.matchAll(/data-i18n(?:-html|-aria)?="([^"]+)"/g)) {
    referenced.add(match[1]);
  }
  for (const match of appJs.matchAll(/\btext\("([^"]+)"\)/g)) {
    referenced.add(match[1]);
  }
  assert.ok(referenced.size >= 60, "expected the full landing copy to be referenced");
  for (const key of referenced) {
    for (const locale of LOCALES) {
      assert.ok(
        Object.prototype.hasOwnProperty.call(I18N[locale], key),
        `${locale} is missing the key ${key}`
      );
    }
  }
});

test("HTML-valued copy uses only em and br markup", () => {
  for (const locale of LOCALES) {
    const stripped = I18N[locale].h_title.replace(/<\/?(?:em|br)\s*\/?>/g, "");
    assert.doesNotMatch(stripped, /[<>]/, `${locale}.h_title contains unexpected markup`);
  }
});

test("light and dark themes define the same complete token set", () => {
  const light = themeTokens("light");
  const dark = themeTokens("dark");
  assert.deepEqual(Object.keys(dark).sort(), Object.keys(light).sort());
  for (const token of TOKENS) {
    assert.ok(light[`--${token}`], `light theme is missing --${token}`);
    assert.ok(dark[`--${token}`], `dark theme is missing --${token}`);
    assert.match(light[`--${token}`], /^#[0-9A-Fa-f]{6}$/, `light --${token} must be a hex colour`);
    assert.match(dark[`--${token}`], /^#[0-9A-Fa-f]{6}$/, `dark --${token} must be a hex colour`);
  }
});

test("text token pairs meet WCAG AA contrast in both themes", () => {
  const pairs = [
    ["ink", "bg"],
    ["ink2", "bg"],
    ["ink3", "bg"],
    ["ink", "surf"],
    ["ink2", "surf"],
    ["ink3", "surf"],
    ["ink2", "acc2"],
    ["ink3", "acc2"],
    ["acc", "bg"],
    ["acc", "surf"],
    ["acc", "acc2"],
    ["onacc", "acc"],
    ["bg", "ink"]
  ];
  for (const theme of THEMES) {
    const tokens = themeTokens(theme);
    for (const [fg, bg] of pairs) {
      const ratio = contrast(tokens[`--${fg}`], tokens[`--${bg}`]);
      assert.ok(
        ratio >= 4.5,
        `${theme}: --${fg} on --${bg} is ${ratio.toFixed(2)}:1, expected at least 4.5:1`
      );
    }
  }
});

test("theme and language preferences persist and follow browser defaults", () => {
  assert.match(appJs, /var STORAGE_LANG = "qsl-lang"/);
  assert.match(appJs, /var STORAGE_THEME = "qsl-theme"/);
  assert.match(appJs, /localStorage\.getItem\(key\)/);
  assert.match(appJs, /localStorage\.setItem\(key, value\)/);
  assert.match(appJs, /prefers-color-scheme: dark/);
  assert.match(appJs, /navigator\.language/);
  assert.match(appJs, /root\.lang = lang/);
  assert.match(appJs, /setAttribute\("data-theme", theme\)/);
  assert.match(html, /<html lang="en" data-theme="light">/);
  assert.match(html, /localStorage\.getItem\(key\)/);
  assert.match(html, /read\("qsl-lang"\)/);
  assert.match(html, /read\("qsl-theme"\)/);
  assert.match(html, /prefers-color-scheme: dark/);
  assert.match(html, /navigator\.language/);
  assert.match(css, /:lang\(zh-CN\) body/);
});

test("document has one h1 and no skipped heading levels", () => {
  const levels = [...html.matchAll(/<h([1-6])\b/g)].map((match) => Number(match[1]));
  assert.equal(levels.filter((level) => level === 1).length, 1, "expected exactly one h1");
  assert.equal(levels[0], 1, "h1 must come first");
  for (let index = 1; index < levels.length; index += 1) {
    assert.ok(
      levels[index] <= levels[index - 1] + 1,
      `heading level jumps from h${levels[index - 1]} to h${levels[index]}`
    );
  }
  assert.ok(levels.includes(2) && levels.includes(3), "expected section and item headings");
});

test("all anchors target existing ids or allow-listed public pages", () => {
  const ids = [...html.matchAll(/\bid="([^"]+)"/g)].map((match) => match[1]);
  assert.equal(new Set(ids).size, ids.length, "duplicate element ids");
  const hrefs = [...html.matchAll(/<a\b[^>]*\shref="([^"]+)"/g)].map((match) => match[1]);
  assert.ok(hrefs.length >= 7, "expected navigation, CTA and publication links");
  for (const href of hrefs) {
    if (href.startsWith("#")) {
      assert.ok(href.length > 1, "empty fragment link");
      assert.ok(ids.includes(href.slice(1)), `missing internal target ${href}`);
    } else {
      assert.ok(ALLOWED_LINKS.has(href), `disallowed outbound link ${href}`);
    }
  }
  assert.ok(hrefs.includes("https://github.com/QuantStrategyLab"));
  assert.ok(hrefs.includes("https://github.com/QuantStrategyLab/QuantAdvisorResearch"));
  assert.ok(hrefs.includes("https://github.com/QuantStrategyLab/QuantPlatformKit"));
  assert.ok(!hrefs.some((href) => /console|login|gateway/i.test(href)), "console/login links must not be published");
  assert.match(html, /<div class="row"><h3 data-i18n="i2"/, "reconciliation ledger must be unlinked text");
  assert.match(html, /<div class="row"><h3 data-i18n="i4"/, "gateway console must be unlinked text");
});

test("page has no third-party requests or runtime network calls", () => {
  let stripped = html;
  for (const url of ALLOWED_LINKS) stripped = stripped.split(url).join("");
  assert.doesNotMatch(stripped, /https?:\/\//i, "unexpected absolute URL in HTML");
  assert.doesNotMatch(css, /@import\b/i, "CSS must not import remote styles");
  assert.doesNotMatch(css, /url\(\s*["']?https?:/i, "CSS must not fetch remote resources");
  for (const api of ["fetch(", "XMLHttpRequest", "WebSocket", "EventSource", "sendBeacon"]) {
    assert.ok(!appJs.includes(api), `app.js must not use ${api}`);
    assert.ok(!i18nJs.includes(api), `i18n.js must not use ${api}`);
  }
  assert.match(html, /<link rel="stylesheet" href="assets\/styles\.css">/);
  assert.match(html, /<link rel="icon" href="assets\/favicon\.svg"/);
  assert.match(html, /<script src="assets\/i18n\.js" defer><\/script>/);
  assert.match(html, /<script src="assets\/app\.js" defer><\/script>/);
});

test("controls expose accessible names and state", () => {
  assert.match(html, /<button[^>]*class="tg js-lang"[^>]*aria-label="[^"]+"/);
  assert.match(html, /<button[^>]*class="tg js-theme"[^>]*aria-label="[^"]+"[^>]*aria-pressed="false"/);
  assert.match(html, /<button[^>]*class="tg menu js-menu"[^>]*aria-controls="primary-nav"[^>]*aria-expanded="false"/);
  assert.match(html, /<nav[^>]*aria-label="Primary"/);
  assert.match(appJs, /aria-pressed/);
  assert.match(appJs, /aria-expanded/);
  assert.match(appJs, /langButton\.lang = lang === "zh-CN" \? "en" : "zh-CN"/);
  assert.match(appJs, /menu_close/);
});

test("favicon is a local blue line-chart SVG", () => {
  assert.match(favicon, /<svg[^>]*xmlns="http:\/\/www\.w3\.org\/2000\/svg"/);
  assert.match(favicon, /stroke="#2F6FED"/);
  assert.match(favicon, />QSL<\/text>/);
});

test("copy makes no performance, return or guarantee claims", () => {
  const copy = LOCALES.map((locale) => Object.values(I18N[locale]).join("\n")).join("\n");
  assert.doesNotMatch(copy, /\b\d+(?:\.\d+)?\s?%/, "percentage claim");
  assert.doesNotMatch(copy, /\b(?:returns?|yield|profit|alpha|sharpe)\s*(?:of|:)?\s*\d/i, "numeric return claim");
  assert.doesNotMatch(copy, /\b(?:guarantee|guaranteed|risk[- ]free)\b/i, "guarantee language");
  assert.doesNotMatch(copy, /保证|稳赚|无风险|收益率\s*\d/, "guarantee or return language (zh)");
});

test("site files contain no account identifiers, emails or tokens", () => {
  const all = [html, css, appJs, i18nJs, favicon].join("\n");
  assert.doesNotMatch(all, /[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/i, "email address");
  assert.doesNotMatch(all, /\b(?:acct|account)[-_]?\d{3,}\b/i, "account-like identifier");
  assert.doesNotMatch(all, /\b(?:sk|pk|ghp)_[A-Za-z0-9]{10,}\b/, "token-like value");
  assert.doesNotMatch(all, /\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b/, "card-like number");
});
