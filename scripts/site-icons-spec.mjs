// Direction A "Chart series" icon specification shared by the generator and tests.
// Every site uses the same chart vocabulary: rx14 plate, 5 px round strokes, end dot, baseline.

export const DIRECTION = "A";
export const DIRECTION_TITLE = "Chart series";

export const REQUIRED_SITE_FILES = [
  "icon.svg",
  "icon-16.svg",
  "icon-maskable.svg",
  "favicon.ico",
  "icon-16.png",
  "icon-32.png",
  "apple-touch-icon.png",
  "icon-192.png",
  "icon-512.png",
  "icon-maskable-512.png",
  "manifest.webmanifest.json",
  "head-snippet.html",
  "CONCEPT.txt"
];

export const PACKAGE_TEXT_FILES = [
  "README.md",
  "INSTALL.md",
  "contrast.json",
  "preview.png"
];

export const NORMAL_PLATE = { x: 1, y: 1, w: 62, h: 62, rx: 14 };
export const SMALL_PLATE = { x: 0.75, y: 0.75, w: 14.5, h: 14.5, rx: 3.5 };

export const SITES = [
  {
    key: "meridian-console",
    dir: "meridian-console",
    label: "CONSOLE",
    title: "Meridian console",
    englishName: "QuantStrategyLab Console",
    chineseName: "量化策略实验室 · 控制台",
    name: "QuantStrategyLab Console / 控制台",
    shortName: "QSL Console",
    assetBase: "assets/icons",
    concept:
      "The console keeps the QuantStrategyLab brand chart mark: a blue plate, a white chart line that steps up to an end dot, and a pale blue baseline.",
    palette: {
      light: {
        plate: "#2563EB",
        glyph: "#FFFFFF",
        accent: "#E6E4DE",
        accent2: "#93C5FD",
        baseline: "#93C5FD",
        line: "#FFFFFF",
        rim: { color: "#E6E4DE", alpha: 0 }
      },
      dark: {
        plate: "#2563EB",
        glyph: "#FFFFFF",
        accent: "#E6E4DE",
        accent2: "#93C5FD",
        baseline: "#93C5FD",
        line: "#FFFFFF",
        rim: { color: "#E6E4DE", alpha: 0 }
      },
      staticRimAlpha: 0,
      tabLight: "#F3F4F6",
      tabDark: "#16181D",
      themeLight: "#F3F4F6",
      themeDark: "#2563EB",
      themeColor: "#2563EB",
      backgroundColor: "#F3F4F6"
    },
    normal: {
      baseline: { points: [[14, 49], [50, 49]], width: 3, role: "baseline" },
      strokes: [
        { points: [[14, 44], [24, 34], [33, 39], [46, 20]], width: 5, role: "glyph" }
      ],
      dot: { x: 46, y: 20, r: 4.5, role: "accent" }
    },
    small: {
      baseline: { points: [[3, 13], [13, 13]], width: 1.1, role: "baseline" },
      strokes: [
        { points: [[3.5, 11], [6, 8.6], [8.5, 9.8], [12.5, 4.5]], width: 1.8, role: "glyph" }
      ],
      dot: { x: 12.5, y: 4.5, r: 1.5, role: "accent" }
    },
    caveats: "The white stroke and bone end dot hold up on both tab colours; the pale baseline is decorative."
  },
  {
    key: "qar-research",
    dir: "qar-research",
    label: "RESEARCH",
    title: "Research desk",
    englishName: "QuantStrategyLab Research",
    chineseName: "量化策略实验室 · 研究",
    name: "QuantStrategyLab Research / 研究",
    shortName: "QSL Research",
    assetBase: "assets/icons",
    concept:
      "Approved direction A: two white horizontal research bars, a shorter teal bar, and a pale blue baseline on navy.",
    palette: {
      light: {
        plate: "#1D3F66",
        glyph: "#FFFFFF",
        accent: "#4FB3A7",
        accent2: "#4FB3A7",
        baseline: "#9DBBE0",
        line: "#FFFFFF",
        rim: { color: "#1D3F66", alpha: 0 }
      },
      dark: {
        plate: "#1D3F66",
        glyph: "#FFFFFF",
        accent: "#4FB3A7",
        accent2: "#4FB3A7",
        baseline: "#9DBBE0",
        line: "#FFFFFF",
        rim: { color: "#1D3F66", alpha: 0 }
      },
      staticRimAlpha: 0,
      tabLight: "#F3F4F6",
      tabDark: "#16181D",
      themeLight: "#F3F4F6",
      themeDark: "#1D3F66",
      themeColor: "#1D3F66",
      backgroundColor: "#F3F4F6"
    },
    plate: { x: 0, y: 0, w: 64, h: 64, rx: 14 },
    borderWidth: 0,
    normal: {
      baseline: { points: [[15, 52], [49, 52]], width: 3, role: "baseline" },
      strokes: [
        { points: [[15, 20], [49, 20]], width: 5, role: "glyph" },
        { points: [[15, 32], [40, 32]], width: 5, role: "glyph" },
        { points: [[15, 44], [28, 44]], width: 5, role: "accent2" }
      ],
      dot: null
    },
    small: {
      baseline: { points: [[3.75, 13], [12.25, 13]], width: 0.75, role: "baseline" },
      strokes: [
        { points: [[3.75, 5], [12.25, 5]], width: 1.25, role: "glyph" },
        { points: [[3.75, 8], [10, 8]], width: 1.25, role: "glyph" },
        { points: [[3.75, 11], [7, 11]], width: 1.25, role: "accent2" }
      ],
      dot: null
    },
    caveats: "The approved original is fixed in both colour schemes. Contrast measurements are reported without adding unapproved rims."
  },
  {
    key: "qas-gateway",
    dir: "qas-gateway",
    label: "GATEWAY",
    title: "AI gateway",
    englishName: "QuantStrategyLab Gateway",
    chineseName: "量化策略实验室 · 网关",
    name: "QuantStrategyLab Gateway / 网关",
    shortName: "QSL Gateway",
    assetBase: "assets/icons",
    concept:
      "Approved direction A: an orange plate, near-black gate posts and request line, and a light-orange baseline.",
    palette: {
      light: {
        plate: "#FF7A1A",
        glyph: "#0E0F10",
        accent: "#0E0F10",
        accent2: "#211E19",
        baseline: "#FFD2AE",
        line: "#0E0F10",
        rim: { color: "#FF7A1A", alpha: 0 }
      },
      dark: {
        plate: "#FF7A1A",
        glyph: "#0E0F10",
        accent: "#0E0F10",
        accent2: "#211E19",
        baseline: "#FFD2AE",
        line: "#0E0F10",
        rim: { color: "#FF7A1A", alpha: 0 }
      },
      staticRimAlpha: 0,
      tabLight: "#F3F4F6",
      tabDark: "#16181D",
      themeLight: "#F3F4F6",
      themeDark: "#0E0F10",
      themeColor: "#0E0F10",
      backgroundColor: "#0E0F10"
    },
    plate: { x: 0, y: 0, w: 64, h: 64, rx: 14 },
    borderWidth: 0,
    normal: {
      baseline: { points: [[14, 50], [50, 50]], width: 4, role: "baseline" },
      strokes: [
        { points: [[22, 14], [22, 40]], width: 4, role: "glyph" },
        { points: [[42, 14], [42, 40]], width: 4, role: "glyph" },
        { points: [[12, 27], [48, 27]], width: 5, role: "glyph" }
      ],
      dot: { x: 51, y: 27, r: 4.5, role: "accent" }
    },
    small: {
      baseline: { points: [[3.5, 12.5], [12.5, 12.5]], width: 1, role: "baseline" },
      strokes: [
        { points: [[5.5, 3.5], [5.5, 10]], width: 1, role: "glyph" },
        { points: [[10.5, 3.5], [10.5, 10]], width: 1, role: "glyph" },
        { points: [[3, 6.75], [12, 6.75]], width: 1.25, role: "glyph" }
      ],
      dot: { x: 12.75, y: 6.75, r: 1.125, role: "accent" }
    },
    caveats: "The approved original is fixed in both colour schemes. Contrast measurements are reported without adding unapproved rims."
  },
  {
    key: "qrs-reconciliation",
    dir: "qrs-reconciliation",
    label: "RECON",
    title: "Reconciliation ledger",
    englishName: "QuantStrategyLab Reconciliation",
    chineseName: "量化策略实验室 · 对账",
    name: "QuantStrategyLab Reconciliation / 对账",
    shortName: "QSL Recon",
    assetBase: "assets/icons",
    concept:
      "Approved direction A: a paper plate with its original ink border, symmetric ink chevron, green endpoint, and amber baseline.",
    palette: {
      light: {
        plate: "#EDE5D3",
        glyph: "#211E19",
        accent: "#2C5A39",
        accent2: "#211E19",
        baseline: "#9A6410",
        line: "#211E19",
        rim: { color: "#211E19", alpha: 1 }
      },
      dark: {
        plate: "#EDE5D3",
        glyph: "#211E19",
        accent: "#2C5A39",
        accent2: "#211E19",
        baseline: "#9A6410",
        line: "#211E19",
        rim: { color: "#211E19", alpha: 1 }
      },
      staticRimAlpha: 1,
      tabLight: "#F3F4F6",
      tabDark: "#16181D",
      themeLight: "#F4EEE1",
      themeDark: "#211E19",
      themeColor: "#211E19",
      backgroundColor: "#F4EEE1"
    },
    plate: { x: 1.5, y: 1.5, w: 61, h: 61, rx: 13 },
    borderWidth: 3,
    normal: {
      baseline: { points: [[14, 52], [50, 52]], width: 3, role: "baseline" },
      strokes: [
        { points: [[14, 20], [32, 32], [48, 32]], width: 5, role: "glyph" },
        { points: [[14, 44], [32, 32]], width: 5, role: "glyph" }
      ],
      dot: { x: 50, y: 32, r: 5, role: "accent" }
    },
    small: {
      baseline: { points: [[3.5, 13], [12.5, 13]], width: 0.75, role: "baseline" },
      strokes: [
        { points: [[3.5, 5], [8, 8], [12, 8]], width: 1.25, role: "glyph" },
        { points: [[3.5, 11], [8, 8]], width: 1.25, role: "glyph" }
      ],
      dot: { x: 12.5, y: 8, r: 1.25, role: "accent" }
    },
    caveats: "The approved original is fixed in both colour schemes. Contrast measurements are reported without adding unapproved rims."
  },
  {
    key: "organisation-landing",
    dir: "organisation-landing",
    label: "LANDING",
    title: "Organisation landing",
    englishName: "QuantStrategyLab",
    chineseName: "量化策略实验室",
    name: "QuantStrategyLab / 量化策略实验室",
    shortName: "QSL",
    assetBase: "assets/icons",
    concept:
      "Approved direction A: a green plate, bone stepped line and endpoint, and mint baseline.",
    palette: {
      light: {
        plate: "#22483E",
        glyph: "#F5F4EF",
        accent: "#F5F4EF",
        accent2: "#211E19",
        baseline: "#8EB8A8",
        line: "#F5F4EF",
        rim: { color: "#22483E", alpha: 0 }
      },
      dark: {
        plate: "#22483E",
        glyph: "#F5F4EF",
        accent: "#F5F4EF",
        accent2: "#211E19",
        baseline: "#8EB8A8",
        line: "#F5F4EF",
        rim: { color: "#22483E", alpha: 0 }
      },
      staticRimAlpha: 0,
      tabLight: "#F3F4F6",
      tabDark: "#16181D",
      themeLight: "#E6E4DE",
      themeDark: "#15181D",
      themeColor: "#15181D",
      backgroundColor: "#E6E4DE"
    },
    plate: { x: 0, y: 0, w: 64, h: 64, rx: 14 },
    borderWidth: 0,
    normal: {
      baseline: { points: [[14, 50], [50, 50]], width: 4, role: "baseline" },
      strokes: [
        { points: [[14, 42], [24, 42], [24, 33], [35, 33], [35, 24], [50, 24]], width: 5, role: "glyph" }
      ],
      dot: { x: 50, y: 24, r: 4, role: "accent" }
    },
    small: {
      baseline: { points: [[3.5, 12.5], [12.5, 12.5]], width: 1, role: "baseline" },
      strokes: [
        { points: [[3.5, 10.5], [6, 10.5], [6, 8.25], [8.75, 8.25], [8.75, 6], [12.5, 6]], width: 1.25, role: "glyph" }
      ],
      dot: { x: 12.5, y: 6, r: 1, role: "accent" }
    },
    caveats: "The approved original is fixed in both colour schemes. Contrast measurements are reported without adding unapproved rims."
  }
];

export const SITE_BY_KEY = Object.fromEntries(SITES.map((site) => [site.key, site]));

// WCAG 1.4.11 non-text contrast: icon shapes need 3:1, decorative baselines 2:1.
export const CONTRAST_THRESHOLDS = {
  glyphOnPlate: 3,
  dotOnPlate: 3,
  baselineOnPlate: 2,
  plateOrRimOnTab: 3
};

export function hexToRgb(hex) {
  const value = String(hex).replace("#", "");
  if (!/^[0-9a-fA-F]{6}$/.test(value)) throw new Error(`invalid hex colour: ${hex}`);
  return {
    r: parseInt(value.slice(0, 2), 16),
    g: parseInt(value.slice(2, 4), 16),
    b: parseInt(value.slice(4, 6), 16)
  };
}

export function rgbToHex({ r, g, b }) {
  const clamp = (n) => Math.max(0, Math.min(255, Math.round(n)));
  return `#${[r, g, b].map((n) => clamp(n).toString(16).padStart(2, "0")).join("").toUpperCase()}`;
}

export function composite(hex, alpha, backgroundHex) {
  const fg = hexToRgb(hex);
  const bg = hexToRgb(backgroundHex);
  return rgbToHex({
    r: fg.r * alpha + bg.r * (1 - alpha),
    g: fg.g * alpha + bg.g * (1 - alpha),
    b: fg.b * alpha + bg.b * (1 - alpha)
  });
}

export function relativeLuminance(hex) {
  const { r, g, b } = hexToRgb(hex);
  const channel = (value) => {
    const c = value / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

export function contrastRatio(a, b) {
  const la = relativeLuminance(a);
  const lb = relativeLuminance(b);
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
}

export function round2(value) {
  return Math.round(value * 100) / 100;
}

export function contrastForSite(site) {
  const result = { light: {}, dark: {}, static: {} };
  for (const mode of ["light", "dark"]) {
    const palette = site.palette[mode];
    result[mode] = {
      glyphOnPlate: round2(contrastRatio(palette.glyph, palette.plate)),
      dotOnPlate: round2(contrastRatio(palette.accent, palette.plate)),
      baselineOnPlate: round2(contrastRatio(palette.baseline, palette.plate)),
      plateOnTab: round2(contrastRatio(palette.plate, site.palette.tabLight)),
      plateOnTabLight: round2(contrastRatio(palette.plate, site.palette.tabLight)),
      plateOnTabDark: round2(contrastRatio(palette.plate, site.palette.tabDark)),
      rimOnTabLight: round2(
        contrastRatio(
          palette.rim.alpha > 0 ? composite(palette.rim.color, palette.rim.alpha, site.palette.tabLight) : palette.plate,
          site.palette.tabLight
        )
      ),
      rimOnTabDark: round2(
        contrastRatio(
          palette.rim.alpha > 0 ? composite(palette.rim.color, palette.rim.alpha, site.palette.tabDark) : palette.plate,
          site.palette.tabDark
        )
      )
    };
  }
  const staticRim = site.palette.staticRimAlpha;
  const rimColor = site.palette.light.rim.color;
  result.static = {
    rimAlpha: staticRim,
    rimOnTabLight: round2(
      contrastRatio(staticRim > 0 ? composite(rimColor, staticRim, site.palette.tabLight) : site.palette.light.plate, site.palette.tabLight)
    ),
    rimOnTabDark: round2(
      contrastRatio(staticRim > 0 ? composite(rimColor, staticRim, site.palette.tabDark) : site.palette.light.plate, site.palette.tabDark)
    )
  };
  return result;
}
