// Deterministic, dependency-free builder for the Direction A "Chart series" icon package.
// Run with `node scripts/build-site-icons.mjs` (also wired as npm pretest).

import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import zlib from "node:zlib";
import {
  CONTRAST_THRESHOLDS,
  NORMAL_PLATE,
  SITES,
  SMALL_PLATE,
  contrastForSite,
  hexToRgb
} from "./site-icons-spec.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const APPROVED_ART = JSON.parse(readFileSync(new URL("./approved-direction-a.json", import.meta.url), "utf8"));
for (const site of SITES.filter((site) => site.key !== "meridian-console")) {
  if (typeof APPROVED_ART[site.key] !== "string" || !APPROVED_ART[site.key].startsWith('<svg ') || !APPROVED_ART[site.key].endsWith('</svg>')) {
    throw new Error(`Missing approved Direction A original: ${site.key}`);
  }
}
const PACKAGE_ROOT = path.join(ROOT, "site-icons");
const LANDING_ICON_DIR = path.join(ROOT, "site", "assets", "icons");
const LANDING_SVG = path.join(ROOT, "site", "assets", "favicon.svg");

// ---------------------------------------------------------------------------
// PNG / ICO encoders (no native dependencies)

const CRC_TABLE = (() => {
  const table = new Uint32Array(256);
  for (let n = 0; n < 256; n += 1) {
    let c = n;
    for (let k = 0; k < 8; k += 1) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    table[n] = c >>> 0;
  }
  return table;
})();

function crc32(buffer) {
  let crc = 0xffffffff;
  for (const byte of buffer) crc = CRC_TABLE[(crc ^ byte) & 0xff] ^ (crc >>> 8);
  return (crc ^ 0xffffffff) >>> 0;
}

function pngChunk(type, data) {
  const typeBuffer = Buffer.from(type, "ascii");
  const body = Buffer.concat([typeBuffer, data]);
  const length = Buffer.alloc(4);
  length.writeUInt32BE(data.length, 0);
  const checksum = Buffer.alloc(4);
  checksum.writeUInt32BE(crc32(body), 0);
  return Buffer.concat([length, body, checksum]);
}

function encodePng(width, height, rgba) {
  if (rgba.length !== width * height * 4) throw new Error("RGBA buffer size mismatch");
  const stride = width * 4;
  const raw = Buffer.alloc((stride + 1) * height);
  for (let y = 0; y < height; y += 1) {
    raw[y * (stride + 1)] = 0;
    Buffer.from(rgba.buffer, rgba.byteOffset + y * stride, stride).copy(raw, y * (stride + 1) + 1);
  }
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(width, 0);
  ihdr.writeUInt32BE(height, 4);
  ihdr[8] = 8;
  ihdr[9] = 6;
  ihdr[10] = 0;
  ihdr[11] = 0;
  ihdr[12] = 0;
  const signature = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
  return Buffer.concat([
    signature,
    pngChunk("IHDR", ihdr),
    pngChunk("IDAT", zlib.deflateSync(raw, { level: 9 })),
    pngChunk("IEND", Buffer.alloc(0))
  ]);
}

function encodeIco(frames) {
  const header = Buffer.alloc(6);
  header.writeUInt16LE(0, 0);
  header.writeUInt16LE(1, 2);
  header.writeUInt16LE(frames.length, 4);
  const directory = Buffer.alloc(16 * frames.length);
  let offset = 6 + directory.length;
  frames.forEach((frame, index) => {
    const entry = index * 16;
    directory[entry] = frame.size >= 256 ? 0 : frame.size;
    directory[entry + 1] = frame.size >= 256 ? 0 : frame.size;
    directory[entry + 2] = 0;
    directory[entry + 3] = 0;
    directory.writeUInt16LE(1, entry + 4);
    directory.writeUInt16LE(32, entry + 6);
    directory.writeUInt32LE(frame.png.length, entry + 8);
    directory.writeUInt32LE(offset, entry + 12);
    offset += frame.png.length;
  });
  return Buffer.concat([header, directory, ...frames.map((frame) => frame.png)]);
}

function readPngSize(buffer) {
  if (buffer.length < 24) throw new Error("PNG too short");
  if (buffer.readUInt32BE(0) !== 0x89504e47) throw new Error("PNG signature missing");
  return { width: buffer.readUInt32BE(16), height: buffer.readUInt32BE(20), colorType: buffer[25] };
}

function readIcoFrames(buffer) {
  if (buffer.readUInt16LE(0) !== 0 || buffer.readUInt16LE(2) !== 1) throw new Error("ICO header invalid");
  const count = buffer.readUInt16LE(4);
  const frames = [];
  for (let index = 0; index < count; index += 1) {
    const entry = 6 + index * 16;
    const size = buffer[entry] === 0 ? 256 : buffer[entry];
    const height = buffer[entry + 1] === 0 ? 256 : buffer[entry + 1];
    const bytes = buffer.readUInt32LE(entry + 8);
    const offset = buffer.readUInt32LE(entry + 12);
    const png = buffer.subarray(offset, offset + bytes);
    if (png.readUInt32BE(0) !== 0x89504e47) throw new Error("ICO frame is not PNG");
    frames.push({ size, height, bytes, png });
  }
  return frames;
}

// ---------------------------------------------------------------------------
// Rasteriser

function insideRoundedRect(px, py, x0, y0, x1, y1, r) {
  if (px < x0 || px > x1 || py < y0 || py > y1) return false;
  const cx = Math.min(Math.max(px, x0 + r), x1 - r);
  const cy = Math.min(Math.max(py, y0 + r), y1 - r);
  const dx = px - cx;
  const dy = py - cy;
  return dx * dx + dy * dy <= r * r;
}

function distanceToSegment(px, py, x1, y1, x2, y2) {
  const dx = x2 - x1;
  const dy = y2 - y1;
  const lengthSquared = dx * dx + dy * dy;
  if (lengthSquared === 0) return Math.hypot(px - x1, py - y1);
  const t = Math.max(0, Math.min(1, ((px - x1) * dx + (py - y1) * dy) / lengthSquared));
  return Math.hypot(px - (x1 + t * dx), py - (y1 + t * dy));
}

class Raster {
  constructor(size) {
    this.size = size;
    this.data = new Uint8ClampedArray(size * size * 4);
  }

  blend(x, y, colorHex, alpha) {
    if (x < 0 || y < 0 || x >= this.size || y >= this.size || alpha <= 0) return;
    const { r, g, b } = hexToRgb(colorHex);
    const index = (y * this.size + x) * 4;
    const destinationAlpha = this.data[index + 3] / 255;
    const outputAlpha = alpha + destinationAlpha * (1 - alpha);
    if (outputAlpha <= 0) return;
    this.data[index] = Math.round((r / 255) * alpha * 255 + this.data[index] * (1 - alpha));
    this.data[index + 1] = Math.round((g / 255) * alpha * 255 + this.data[index + 1] * (1 - alpha));
    this.data[index + 2] = Math.round((b / 255) * alpha * 255 + this.data[index + 2] * (1 - alpha));
    this.data[index + 3] = Math.round(outputAlpha * 255);
  }

  fillRect(x0, y0, x1, y1, color, alpha = 1) {
    const left = Math.max(0, Math.floor(x0));
    const top = Math.max(0, Math.floor(y0));
    const right = Math.min(this.size, Math.ceil(x1));
    const bottom = Math.min(this.size, Math.ceil(y1));
    for (let y = top; y < bottom; y += 1) {
      for (let x = left; x < right; x += 1) this.blend(x, y, color, alpha);
    }
  }

  fillRoundedRect(x0, y0, x1, y1, r, color, alpha = 1) {
    const left = Math.max(0, Math.floor(x0));
    const top = Math.max(0, Math.floor(y0));
    const right = Math.min(this.size, Math.ceil(x1));
    const bottom = Math.min(this.size, Math.ceil(y1));
    for (let y = top; y < bottom; y += 1) {
      for (let x = left; x < right; x += 1) {
        if (insideRoundedRect(x + 0.5, y + 0.5, x0, y0, x1, y1, r)) this.blend(x, y, color, alpha);
      }
    }
  }

  fillRoundedRing(x0, y0, x1, y1, r, width, color, alpha) {
    const inner = {
      x0: x0 + width,
      y0: y0 + width,
      x1: x1 - width,
      y1: y1 - width,
      r: Math.max(0, r - width)
    };
    const left = Math.max(0, Math.floor(x0));
    const top = Math.max(0, Math.floor(y0));
    const right = Math.min(this.size, Math.ceil(x1));
    const bottom = Math.min(this.size, Math.ceil(y1));
    for (let y = top; y < bottom; y += 1) {
      for (let x = left; x < right; x += 1) {
        const px = x + 0.5;
        const py = y + 0.5;
        const outer = insideRoundedRect(px, py, x0, y0, x1, y1, r);
        const hole = insideRoundedRect(px, py, inner.x0, inner.y0, inner.x1, inner.y1, inner.r);
        if (outer && !hole) this.blend(x, y, color, alpha);
      }
    }
  }

  fillCircle(cx, cy, radius, color) {
    const left = Math.max(0, Math.floor(cx - radius));
    const top = Math.max(0, Math.floor(cy - radius));
    const right = Math.min(this.size, Math.ceil(cx + radius));
    const bottom = Math.min(this.size, Math.ceil(cy + radius));
    const radiusSquared = radius * radius;
    for (let y = top; y < bottom; y += 1) {
      for (let x = left; x < right; x += 1) {
        const dx = x + 0.5 - cx;
        const dy = y + 0.5 - cy;
        if (dx * dx + dy * dy <= radiusSquared) this.blend(x, y, color, 1);
      }
    }
  }

  strokeSegment(x1, y1, x2, y2, width, color) {
    const radius = width / 2;
    const left = Math.max(0, Math.floor(Math.min(x1, x2) - radius));
    const top = Math.max(0, Math.floor(Math.min(y1, y2) - radius));
    const right = Math.min(this.size, Math.ceil(Math.max(x1, x2) + radius));
    const bottom = Math.min(this.size, Math.ceil(Math.max(y1, y2) + radius));
    for (let y = top; y < bottom; y += 1) {
      for (let x = left; x < right; x += 1) {
        if (distanceToSegment(x + 0.5, y + 0.5, x1, y1, x2, y2) <= radius) this.blend(x, y, color, 1);
      }
    }
  }

  strokePolyline(points, width, color) {
    for (let index = 1; index < points.length; index += 1) {
      this.strokeSegment(points[index - 1][0], points[index - 1][1], points[index][0], points[index][1], width, color);
    }
    for (let index = 1; index < points.length - 1; index += 1) {
      this.fillCircle(points[index][0], points[index][1], width / 2, color);
    }
  }

  downsample(size) {
    const factor = this.size / size;
    const output = new Uint8ClampedArray(size * size * 4);
    const samples = factor * factor;
    for (let y = 0; y < size; y += 1) {
      for (let x = 0; x < size; x += 1) {
        let r = 0;
        let g = 0;
        let b = 0;
        let a = 0;
        for (let sy = 0; sy < factor; sy += 1) {
          for (let sx = 0; sx < factor; sx += 1) {
            const source = ((y * factor + sy) * this.size + (x * factor + sx)) * 4;
            r += this.data[source];
            g += this.data[source + 1];
            b += this.data[source + 2];
            a += this.data[source + 3];
          }
        }
        const target = (y * size + x) * 4;
        const alpha = a / samples / 255;
        if (alpha > 0) {
          output[target] = Math.round(r / samples / alpha);
          output[target + 1] = Math.round(g / samples / alpha);
          output[target + 2] = Math.round(b / samples / alpha);
        }
        output[target + 3] = Math.round(a / samples);
      }
    }
    return output;
  }
}

function renderRgba(site, size, options = {}) {
  const variant = options.variant ?? "normal";
  const mode = options.mode ?? "light";
  const staticRaster = options.staticRaster ?? false;
  const small = variant === "small";
  const maskable = variant === "maskable";
  const unit = small ? 16 : 64;
  const supersample = size >= 512 ? 3 : size >= 192 ? 4 : 8;
  const hi = size * supersample;
  const raster = new Raster(hi);
  let palette = site.palette[mode];
  if (staticRaster) {
    palette = {
      ...palette,
      rim: { color: site.palette.light.rim.color, alpha: site.palette.staticRimAlpha }
    };
  }
  const shapes = small ? site.small : site.normal;
  const scaleCoordinate = (value) => (value / unit) * hi;
  const mapPoint = (point) =>
    maskable ? [32 + (point[0] - 32) * 0.8, 32 + (point[1] - 32) * 0.8] : point;
  const mapWidth = (value) => (maskable ? value * 0.8 : value);

  if (maskable) {
    raster.fillRect(0, 0, hi, hi, palette.plate);
  } else {
    const plate = site.plate
      ? Object.fromEntries(Object.entries(site.plate).map(([key, value]) => [key, small ? value / 4 : value]))
      : small ? SMALL_PLATE : NORMAL_PLATE;
    raster.fillRoundedRect(
      scaleCoordinate(plate.x),
      scaleCoordinate(plate.y),
      scaleCoordinate(plate.x + plate.w),
      scaleCoordinate(plate.y + plate.h),
      scaleCoordinate(plate.rx),
      palette.plate
    );
  }

  const rim = palette.rim;
  if (!maskable && rim.alpha > 0) {
    const plate = site.plate
      ? Object.fromEntries(Object.entries(site.plate).map(([key, value]) => [key, small ? value / 4 : value]))
      : small ? SMALL_PLATE : NORMAL_PLATE;
    const rimWidth = site.borderWidth ? site.borderWidth / (small ? 4 : 1) : 1.5;
    const inset = site.borderWidth ? -rimWidth / 2 : rimWidth / 2;
    raster.fillRoundedRing(
      scaleCoordinate(plate.x + inset),
      scaleCoordinate(plate.y + inset),
      scaleCoordinate(plate.x + plate.w - inset),
      scaleCoordinate(plate.y + plate.h - inset),
      scaleCoordinate(Math.max(0, plate.rx - inset)),
      scaleCoordinate(rimWidth),
      rim.color,
      rim.alpha
    );
  }

  const baseline = shapes.baseline;
  const baselinePoints = baseline.points.map(mapPoint).map((point) => [scaleCoordinate(point[0]), scaleCoordinate(point[1])]);
  raster.strokePolyline(baselinePoints, scaleCoordinate(mapWidth(baseline.width)), palette[baseline.role]);

  for (const stroke of shapes.strokes) {
    const points = stroke.points.map(mapPoint).map((point) => [scaleCoordinate(point[0]), scaleCoordinate(point[1])]);
    raster.strokePolyline(points, scaleCoordinate(mapWidth(stroke.width)), palette[stroke.role]);
  }

  if (shapes.dot) {
    const [x, y] = mapPoint([shapes.dot.x, shapes.dot.y]);
    raster.fillCircle(
      scaleCoordinate(x),
      scaleCoordinate(y),
      scaleCoordinate(mapWidth(shapes.dot.r)),
      palette[shapes.dot.role]
    );
  }

  return raster.downsample(size);
}

// ---------------------------------------------------------------------------
// SVG

const ROLE_ORDER = ["plate", "glyph", "accent", "accent2", "baseline", "line"];

function styleRule(role, palette) {
  switch (role) {
    case "plate":
      return `.${role}{fill:${palette.plate}}`;
    case "glyph":
      return `.${role}{stroke:${palette.glyph}}`;
    case "accent":
      return `.${role}{fill:${palette.accent}}`;
    case "accent2":
      return `.${role}{stroke:${palette.accent2}}`;
    case "baseline":
      return `.${role}{stroke:${palette.baseline}}`;
    case "line":
      return `.${role}{stroke:${palette.line}}`;
    default:
      throw new Error(`unknown role ${role}`);
  }
}

function svgFor(site, variant) {
  const approved = APPROVED_ART[site.key];
  if (approved) {
    const accessible = approved.replace('<svg ', `<svg role="img" aria-label="${site.englishName}" `);
    if (variant === "normal") return `${accessible}\n`;
    const body = approved.slice(approved.indexOf(">") + 1, -6);
    if (variant === "small") {
      return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" role="img" aria-label="${site.englishName}"><g transform="scale(.25)">${body}</g></svg>\n`;
    }
    const glyph = body.replace(/^<rect[^>]+\/>/, "");
    return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" role="img" aria-label="${site.englishName}"><rect class="plate" x="0" y="0" width="64" height="64" fill="${site.palette.light.plate}"/><g transform="translate(6.4 6.4) scale(.8)">${glyph}</g></svg>\n`;
  }
  const small = variant === "small";
  const maskable = variant === "maskable";
  const unit = small ? 16 : 64;
  const plate = small ? SMALL_PLATE : NORMAL_PLATE;
  const shapes = small ? site.small : site.normal;
  const mapPoint = (point) =>
    maskable ? [32 + (point[0] - 32) * 0.8, 32 + (point[1] - 32) * 0.8] : point;
  const mapWidth = (value) => (maskable ? value * 0.8 : value);
  const fmt = (value) => Number(value.toFixed(3));
  const light = site.palette.light;
  const dark = site.palette.dark;
  const lightRules = ROLE_ORDER.map((role) => styleRule(role, light)).join("\n      ");
  const darkRules = ROLE_ORDER.map((role) => styleRule(role, dark)).join("\n      ");
  const lightRim = light.rim.alpha > 0
    ? `.rim{stroke:${light.rim.color};stroke-opacity:${light.rim.alpha}}`
    : ".rim{stroke:none}";
  const darkRim = dark.rim.alpha > 0
    ? `.rim{stroke:${dark.rim.color};stroke-opacity:${dark.rim.alpha}}`
    : ".rim{stroke:none}";
  const viewBox = small ? "0 0 16 16" : "0 0 64 64";

  const plateMarkup = maskable
    ? '<rect class="plate" x="0" y="0" width="64" height="64"/>'
    : `<rect class="plate" x="${fmt(plate.x)}" y="${fmt(plate.y)}" width="${fmt(plate.w)}" height="${fmt(plate.h)}" rx="${fmt(plate.rx)}"/>`;
  const rimMarkup = maskable
    ? ""
    : `<rect class="rim" x="${fmt(plate.x + 0.75)}" y="${fmt(plate.y + 0.75)}" width="${fmt(plate.w - 1.5)}" height="${fmt(plate.h - 1.5)}" rx="${fmt(Math.max(0, plate.rx - 0.75))}" fill="none" stroke-width="1.5"/>`;

  const baseline = shapes.baseline;
  const baselinePoints = baseline.points.map(mapPoint);
  const baselineMarkup = `<line class="${baseline.role}" x1="${fmt(baselinePoints[0][0])}" y1="${fmt(baselinePoints[0][1])}" x2="${fmt(baselinePoints[1][0])}" y2="${fmt(baselinePoints[1][1])}" stroke-width="${fmt(mapWidth(baseline.width))}" stroke-linecap="round"/>`;

  const strokeMarkup = shapes.strokes
    .map((stroke) => {
      const points = stroke.points.map(mapPoint);
      const data = points.map((point, index) => `${index === 0 ? "M" : "L"}${fmt(point[0])} ${fmt(point[1])}`).join(" ");
      return `<path class="${stroke.role}" d="${data}" fill="none" stroke-width="${fmt(mapWidth(stroke.width))}" stroke-linecap="round" stroke-linejoin="round"/>`;
    })
    .join("\n  ");

  const dot = shapes.dot;
  const dotPoint = dot ? mapPoint([dot.x, dot.y]) : null;
  const dotMarkup = dot
    ? `<circle class="${dot.role}" cx="${fmt(dotPoint[0])}" cy="${fmt(dotPoint[1])}" r="${fmt(mapWidth(dot.r))}"/>`
    : "";

  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${viewBox}" role="img" aria-label="${site.englishName}">
  <style>
      ${lightRules}
      ${lightRim}
      @media (prefers-color-scheme: dark) {
      ${darkRules}
      ${darkRim}
      }
  </style>
  ${plateMarkup}
${rimMarkup ? `  ${rimMarkup}\n` : ""}  ${baselineMarkup}
  ${strokeMarkup}
  ${dotMarkup}
</svg>
`;
}

// ---------------------------------------------------------------------------
// Text deliverables

function manifestFor(site) {
  const palette = site.palette;
  return {
    name: site.name,
    short_name: site.shortName,
    description: `${site.englishName} — ${site.chineseName}. Direction A chart-series icon set.`,
    lang: "en",
    dir: "ltr",
    display: "standalone",
    background_color: palette.backgroundColor,
    theme_color: palette.themeColor,
    icons: [
      { src: "icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      { src: "icon-maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" }
    ]
  };
}

function snippetFor(site) {
  const base = site.assetBase;
  const svgPath = site.key === "organisation-landing" ? "assets/favicon.svg" : `${base}/icon.svg`;
  const rasterBase = site.key === "organisation-landing" ? "assets/icons" : base;
  return `<!-- ${site.englishName} — Direction A "Chart series" icons.
     en: ${site.englishName}
     zh-CN: ${site.chineseName}
     Replace the existing favicon and manifest links with this block; keep exactly one manifest link. -->
<link rel="icon" href="${svgPath}" type="image/svg+xml">
<link rel="icon" href="${rasterBase}/favicon.ico" sizes="any">
<link rel="apple-touch-icon" href="${rasterBase}/apple-touch-icon.png">
<link rel="manifest" href="${rasterBase}/manifest.webmanifest">
<meta name="theme-color" content="${site.palette.themeLight}" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="${site.palette.themeDark}" media="(prefers-color-scheme: dark)">
`;
}

function conceptFor(site) {
  const contrast = contrastForSite(site);
  const palette = site.palette.light;
  const dark = site.palette.dark;
  return `DIRECTION A — CHART SERIES
Site: ${site.title}
English name: ${site.englishName}
Chinese name: ${site.chineseName}

Palette (light media): plate ${palette.plate}; glyph ${palette.glyph}; accent ${palette.accent}; secondary ${palette.accent2}; baseline ${palette.baseline}; rim ${palette.rim.color} @ ${palette.rim.alpha}
Palette (dark media):  plate ${dark.plate}; glyph ${dark.glyph}; accent ${dark.accent}; secondary ${dark.accent2}; baseline ${dark.baseline}; rim ${dark.rim.color} @ ${dark.rim.alpha}

Geometry: rx14 plate in a 64-unit box, 5 px round strokes, one end dot, one baseline. The 16 px file uses a simplified rx3.5 plate and a 1.4–1.8 px stroke.

Contrast (WCAG 2.1, measured by scripts/build-site-icons.mjs):
  light: glyph/plate ${contrast.light.glyphOnPlate}:1; dot/plate ${contrast.light.dotOnPlate}:1; baseline/plate ${contrast.light.baselineOnPlate}:1; plate vs light tab ${contrast.light.plateOnTabLight}:1; rim vs light tab ${contrast.light.rimOnTabLight}:1
  dark:  glyph/plate ${contrast.dark.glyphOnPlate}:1; dot/plate ${contrast.dark.dotOnPlate}:1; baseline/plate ${contrast.dark.baselineOnPlate}:1; plate vs dark tab ${contrast.dark.plateOnTabDark}:1; rim vs dark tab ${contrast.dark.rimOnTabDark}:1
  static PNG: plate vs light tab ${contrast.light.plateOnTabLight}:1; plate vs dark tab ${contrast.light.plateOnTabDark}:1; rim alpha ${contrast.static.rimAlpha}; rim vs light tab ${contrast.static.rimOnTabLight}:1; rim vs dark tab ${contrast.static.rimOnTabDark}:1

Caveat: ${site.caveats}
`;
}

// ---------------------------------------------------------------------------
// Preview sheet

const FONT = {
  A: ["010", "101", "111", "101", "101"],
  B: ["110", "101", "110", "101", "110"],
  C: ["011", "100", "100", "100", "011"],
  D: ["110", "101", "101", "101", "110"],
  E: ["111", "100", "110", "100", "111"],
  F: ["111", "100", "110", "100", "100"],
  G: ["011", "100", "101", "101", "011"],
  H: ["101", "101", "111", "101", "101"],
  I: ["111", "010", "010", "010", "111"],
  J: ["001", "001", "001", "101", "010"],
  K: ["101", "101", "110", "101", "101"],
  L: ["100", "100", "100", "100", "111"],
  M: ["101", "111", "111", "101", "101"],
  N: ["101", "111", "111", "111", "101"],
  O: ["010", "101", "101", "101", "010"],
  P: ["110", "101", "110", "100", "100"],
  Q: ["010", "101", "101", "111", "011"],
  R: ["110", "101", "110", "101", "101"],
  S: ["011", "100", "010", "001", "110"],
  T: ["111", "010", "010", "010", "010"],
  U: ["101", "101", "101", "101", "111"],
  V: ["101", "101", "101", "101", "010"],
  W: ["101", "101", "111", "111", "101"],
  X: ["101", "101", "010", "101", "101"],
  Y: ["101", "101", "010", "010", "010"],
  Z: ["111", "001", "010", "100", "111"],
  0: ["111", "101", "101", "101", "111"],
  1: ["010", "110", "010", "010", "111"],
  2: ["110", "001", "010", "100", "111"],
  3: ["110", "001", "010", "001", "110"],
  4: ["101", "101", "111", "001", "001"],
  5: ["111", "100", "110", "001", "110"],
  6: ["011", "100", "111", "101", "111"],
  7: ["111", "001", "010", "010", "010"],
  8: ["111", "101", "111", "101", "111"],
  9: ["111", "101", "111", "001", "110"],
  " ": ["000", "000", "000", "000", "000"],
  "-": ["000", "000", "111", "000", "000"],
  "/": ["001", "001", "010", "100", "100"],
  ":": ["000", "010", "000", "010", "000"],
  ".": ["000", "000", "000", "000", "010"]
};

class Sheet {
  constructor(width, height) {
    this.width = width;
    this.height = height;
    this.data = new Uint8ClampedArray(width * height * 4);
  }

  fill(colorHex) {
    const { r, g, b } = hexToRgb(colorHex);
    for (let index = 0; index < this.data.length; index += 4) {
      this.data[index] = r;
      this.data[index + 1] = g;
      this.data[index + 2] = b;
      this.data[index + 3] = 255;
    }
  }

  fillRect(x0, y0, x1, y1, colorHex) {
    const { r, g, b } = hexToRgb(colorHex);
    const left = Math.max(0, Math.floor(x0));
    const top = Math.max(0, Math.floor(y0));
    const right = Math.min(this.width, Math.ceil(x1));
    const bottom = Math.min(this.height, Math.ceil(y1));
    for (let y = top; y < bottom; y += 1) {
      for (let x = left; x < right; x += 1) {
        const index = (y * this.width + x) * 4;
        this.data[index] = r;
        this.data[index + 1] = g;
        this.data[index + 2] = b;
        this.data[index + 3] = 255;
      }
    }
  }

  fillRoundedRect(x0, y0, x1, y1, radius, colorHex) {
    const { r, g, b } = hexToRgb(colorHex);
    for (let y = Math.max(0, Math.floor(y0)); y < Math.min(this.height, Math.ceil(y1)); y += 1) {
      for (let x = Math.max(0, Math.floor(x0)); x < Math.min(this.width, Math.ceil(x1)); x += 1) {
        if (insideRoundedRect(x + 0.5, y + 0.5, x0, y0, x1, y1, radius)) {
          const index = (y * this.width + x) * 4;
          this.data[index] = r;
          this.data[index + 1] = g;
          this.data[index + 2] = b;
          this.data[index + 3] = 255;
        }
      }
    }
  }

  blit(rgba, size, x, y) {
    const left = Math.max(0, x);
    const top = Math.max(0, y);
    const right = Math.min(this.width, x + size);
    const bottom = Math.min(this.height, y + size);
    for (let sy = top - y; sy < bottom - y; sy += 1) {
      for (let sx = left - x; sx < right - x; sx += 1) {
        const source = (sy * size + sx) * 4;
        const target = ((top + sy) * this.width + (left + sx)) * 4;
        const alpha = rgba[source + 3] / 255;
        if (alpha <= 0) continue;
        this.data[target] = Math.round(rgba[source] * alpha + this.data[target] * (1 - alpha));
        this.data[target + 1] = Math.round(rgba[source + 1] * alpha + this.data[target + 1] * (1 - alpha));
        this.data[target + 2] = Math.round(rgba[source + 2] * alpha + this.data[target + 2] * (1 - alpha));
        this.data[target + 3] = 255;
      }
    }
  }

  text(value, x, y, scale, colorHex) {
    const { r, g, b } = hexToRgb(colorHex);
    let cursor = x;
    for (const character of String(value).toUpperCase()) {
      const glyph = FONT[character] ?? FONT[" "];
      glyph.forEach((row, rowIndex) => {
        [...row].forEach((bit, columnIndex) => {
          if (bit !== "1") return;
          const left = cursor + columnIndex * scale;
          const top = y + rowIndex * scale;
          for (let dy = 0; dy < scale; dy += 1) {
            for (let dx = 0; dx < scale; dx += 1) {
              const px = left + dx;
              const py = top + dy;
              if (px < 0 || py < 0 || px >= this.width || py >= this.height) continue;
              const index = (py * this.width + px) * 4;
              this.data[index] = r;
              this.data[index + 1] = g;
              this.data[index + 2] = b;
              this.data[index + 3] = 255;
            }
          }
        });
      });
      cursor += 4 * scale;
    }
    return cursor;
  }
}

function makePreview() {
  const width = 3000;
  const margin = 64;
  const gap = 24;
  const column = Math.floor((width - margin * 2 - gap * 4) / 5);
  const header = 110;
  const sectionLabel = 52;
  const tabStrip = 96;
  const bigRow = 512 + 58;
  const midRow = 192 + 44;
  const smallRow = 100;
  const sectionGap = 36;
  const sectionHeight = sectionLabel + tabStrip + bigRow + midRow + smallRow;
  const height = margin + header + sectionHeight * 2 + sectionGap + 56;
  const sheet = new Sheet(width, height);
  sheet.fill("#F3F4F6");

  const darkTop = margin + header + sectionHeight + sectionGap;
  sheet.fillRect(0, darkTop - 18, width, height, "#16181D");

  sheet.text("QUANTSTRATEGYLAB - DIRECTION A CHART SERIES", margin, margin - 10, 4, "#15181D");
  sheet.text("FIVE SITES / 512 / 192 / 64 / 32 / 16 / LIGHT AND DARK MOCK TAB STRIPS", margin, margin + 42, 2, "#4B5563");

  const sections = [
    { mode: "light", label: "LIGHT TAB STRIP", top: margin + header, bg: "#F3F4F6", strip: "#E9EBEF", stripActive: "#FFFFFF", labelColor: "#15181D" },
    { mode: "dark", label: "DARK TAB STRIP", top: darkTop, bg: "#16181D", strip: "#0F1115", stripActive: "#1E222A", labelColor: "#E6E4DE" }
  ];

  for (const section of sections) {
    let y = section.top;
    sheet.text(section.label, margin, y, 3, section.labelColor);
    y += sectionLabel;

    sheet.fillRoundedRect(margin, y, width - margin, y + tabStrip - 12, 10, section.strip);
    SITES.forEach((site, index) => {
      const tabX = margin + index * (column + gap) + 10;
      if (index === 0) {
        sheet.fillRoundedRect(tabX - 6, y + 4, tabX + column - 2, y + tabStrip - 12, 8, section.stripActive);
      }
      sheet.blit(renderRgba(site, 16, { variant: "small", mode: section.mode }), 16, tabX + 8, y + 30);
      sheet.blit(renderRgba(site, 32, { variant: "normal", mode: section.mode }), 32, tabX + 34, y + 22);
      sheet.text(site.label, tabX + 78, y + 40, 2, section.labelColor);
    });
    y += tabStrip;

    SITES.forEach((site, index) => {
      const x = margin + index * (column + gap);
      sheet.blit(renderRgba(site, 512, { mode: section.mode }), 512, x, y);
      sheet.text(site.label, x + 4, y + 526, 2, section.labelColor);
    });
    y += bigRow;

    SITES.forEach((site, index) => {
      const x = margin + index * (column + gap);
      sheet.blit(renderRgba(site, 192, { mode: section.mode }), 192, x, y);
    });
    y += midRow;

    SITES.forEach((site, index) => {
      const x = margin + index * (column + gap);
      sheet.blit(renderRgba(site, 64, { mode: section.mode }), 64, x, y);
      sheet.blit(renderRgba(site, 32, { mode: section.mode }), 32, x + 82, y + 16);
      sheet.blit(renderRgba(site, 16, { variant: "small", mode: section.mode }), 16, x + 130, y + 24);
      sheet.text("64 / 32 / 16", x + 4, y + 78, 2, section.labelColor);
    });
  }

  sheet.text("STATIC PNG SETS PRESERVE THE APPROVED DIRECTION A PALETTES AND BORDERS.", margin, height - 38, 2, "#6B7280");
  return { width, height, rgba: sheet.data };
}

// ---------------------------------------------------------------------------
// File output

function writeText(relative, contents) {
  const target = path.join(PACKAGE_ROOT, relative);
  mkdirSync(path.dirname(target), { recursive: true });
  writeFileSync(target, contents, "utf8");
}

function writeBinary(relative, buffer) {
  const target = path.join(PACKAGE_ROOT, relative);
  mkdirSync(path.dirname(target), { recursive: true });
  writeFileSync(target, buffer);
}

function assertPng(buffer, width, height, label) {
  const size = readPngSize(buffer);
  if (size.width !== width || size.height !== height) {
    throw new Error(`${label}: expected ${width}x${height}, got ${size.width}x${size.height}`);
  }
  if (size.colorType !== 6) throw new Error(`${label}: expected RGBA PNG`);
}

function main() {
  const contrast = {
    direction: "A",
    directionTitle: "Chart series",
    thresholds: CONTRAST_THRESHOLDS,
    sites: {}
  };

  for (const site of SITES) {
    const siteDir = site.dir;
    const master = svgFor(site, "normal");
    const small = svgFor(site, "small");
    const maskable = svgFor(site, "maskable");
    const png16 = encodePng(16, 16, renderRgba(site, 16, { variant: "small", staticRaster: true }));
    const png32 = encodePng(32, 32, renderRgba(site, 32, { staticRaster: true }));
    const png48 = encodePng(48, 48, renderRgba(site, 48, { staticRaster: true }));
    const apple = encodePng(180, 180, renderRgba(site, 180, { variant: "maskable", staticRaster: true }));
    const png192 = encodePng(192, 192, renderRgba(site, 192, { staticRaster: true }));
    const png512 = encodePng(512, 512, renderRgba(site, 512, { staticRaster: true }));
    const maskable512 = encodePng(512, 512, renderRgba(site, 512, { variant: "maskable", staticRaster: true }));
    const ico = encodeIco([
      { size: 16, png: png16 },
      { size: 32, png: png32 },
      { size: 48, png: png48 }
    ]);

    assertPng(png16, 16, 16, `${site.key} icon-16.png`);
    assertPng(png32, 32, 32, `${site.key} icon-32.png`);
    assertPng(apple, 180, 180, `${site.key} apple-touch-icon.png`);
    assertPng(png192, 192, 192, `${site.key} icon-192.png`);
    assertPng(png512, 512, 512, `${site.key} icon-512.png`);
    assertPng(maskable512, 512, 512, `${site.key} icon-maskable-512.png`);
    const frames = readIcoFrames(ico);
    if (frames.map((frame) => frame.size).join(",") !== "16,32,48") throw new Error(`${site.key}: ICO frame sizes invalid`);
    if (!frames[0].png.equals(png16)) throw new Error(`${site.key}: ICO 16 frame must equal icon-16.png`);
    if (!frames[1].png.equals(png32)) throw new Error(`${site.key}: ICO 32 frame must equal icon-32.png`);

    writeText(path.join(siteDir, "icon.svg"), master);
    writeText(path.join(siteDir, "icon-16.svg"), small);
    writeText(path.join(siteDir, "icon-maskable.svg"), maskable);
    writeBinary(path.join(siteDir, "favicon.ico"), ico);
    writeBinary(path.join(siteDir, "icon-16.png"), png16);
    writeBinary(path.join(siteDir, "icon-32.png"), png32);
    writeBinary(path.join(siteDir, "apple-touch-icon.png"), apple);
    writeBinary(path.join(siteDir, "icon-192.png"), png192);
    writeBinary(path.join(siteDir, "icon-512.png"), png512);
    writeBinary(path.join(siteDir, "icon-maskable-512.png"), maskable512);
    writeText(path.join(siteDir, "manifest.webmanifest.json"), `${JSON.stringify(manifestFor(site), null, 2)}\n`);
    writeText(path.join(siteDir, "head-snippet.html"), snippetFor(site));
    writeText(path.join(siteDir, "CONCEPT.txt"), conceptFor(site));
    contrast.sites[site.key] = contrastForSite(site);
  }

  writeText("contrast.json", `${JSON.stringify(contrast, null, 2)}\n`);

  const preview = makePreview();
  const previewPng = encodePng(preview.width, preview.height, preview.rgba);
  assertPng(previewPng, preview.width, preview.height, "preview.png");
  writeBinary("preview.png", previewPng);

  const landing = SITES.find((site) => site.key === "organisation-landing");
  const landingMaster = svgFor(landing, "normal");
  mkdirSync(path.dirname(LANDING_SVG), { recursive: true });
  writeFileSync(LANDING_SVG, landingMaster, "utf8");
  mkdirSync(LANDING_ICON_DIR, { recursive: true });
  for (const name of ["favicon.ico", "apple-touch-icon.png", "icon-192.png", "icon-512.png", "icon-maskable-512.png"]) {
    writeFileSync(path.join(LANDING_ICON_DIR, name), readFileSync(path.join(PACKAGE_ROOT, landing.dir, name)));
  }
  writeFileSync(
    path.join(LANDING_ICON_DIR, "manifest.webmanifest"),
    readFileSync(path.join(PACKAGE_ROOT, landing.dir, "manifest.webmanifest.json"))
  );

  console.log(`Built ${SITES.length} Direction A icon sets under site-icons/`);
  console.log(`Preview: ${preview.width}x${preview.height}px`);
  console.log("Landing assets: site/assets/favicon.svg + site/assets/icons/*");
}

main();
