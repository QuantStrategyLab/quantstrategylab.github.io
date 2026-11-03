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
      "The research desk uses the existing three-bar QAR geometry, stroked in teal on Research Desk navy, with a bone end dot on the tallest bar and a muted baseline.",
    palette: {
      light: {
        plate: "#1D3F66",
        glyph: "#4FB3A7",
        accent: "#E6E4DE",
        accent2: "#4FB3A7",
        baseline: "#7FA2B8",
        line: "#4FB3A7",
        rim: { color: "#E6E4DE", alpha: 0.45 }
      },
      dark: {
        plate: "#1D3F66",
        glyph: "#4FB3A7",
        accent: "#E6E4DE",
        accent2: "#4FB3A7",
        baseline: "#7FA2B8",
        line: "#4FB3A7",
        rim: { color: "#E6E4DE", alpha: 0.45 }
      },
      staticRimAlpha: 0.45,
      tabLight: "#F3F4F6",
      tabDark: "#16181D",
      themeLight: "#F3F4F6",
      themeDark: "#1D3F66",
      themeColor: "#1D3F66",
      backgroundColor: "#F3F4F6"
    },
    normal: {
      baseline: { points: [[14, 49], [50, 49]], width: 3, role: "baseline" },
      strokes: [
        { points: [[19, 36], [19, 48]], width: 5, role: "glyph" },
        { points: [[31, 27], [31, 48]], width: 5, role: "glyph" },
        { points: [[43, 18], [43, 48]], width: 5, role: "glyph" }
      ],
      dot: { x: 43, y: 18, r: 4.5, role: "accent" }
    },
    small: {
      baseline: { points: [[3, 13], [13, 13]], width: 1, role: "baseline" },
      strokes: [
        { points: [[4.5, 9.5], [4.5, 12.5]], width: 1.6, role: "glyph" },
        { points: [[8, 7.5], [8, 12.5]], width: 1.6, role: "glyph" },
        { points: [[11.5, 5], [11.5, 12.5]], width: 1.6, role: "glyph" }
      ],
      dot: { x: 11.5, y: 5, r: 1.4, role: "accent" }
    },
    caveats: "Three bars remain separable at 16 px because the simplified glyph uses two gaps and a 1.6 px stroke. The static PNG carries a bone rim so the navy plate separates from a dark tab strip."
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
      "The AI gateway is a signal-orange gate on near-black: two rounded gate posts, a bone request line passing through them, an orange end dot, and a dark amber baseline.",
    palette: {
      light: {
        plate: "#0E0F10",
        glyph: "#FF7A1A",
        accent: "#FF7A1A",
        accent2: "#FFB27A",
        baseline: "#B25A12",
        line: "#E6E4DE",
        rim: { color: "#E6E4DE", alpha: 0.55 }
      },
      dark: {
        plate: "#0E0F10",
        glyph: "#FF7A1A",
        accent: "#FF7A1A",
        accent2: "#FFB27A",
        baseline: "#B25A12",
        line: "#E6E4DE",
        rim: { color: "#E6E4DE", alpha: 0.55 }
      },
      staticRimAlpha: 0.55,
      tabLight: "#F3F4F6",
      tabDark: "#16181D",
      themeLight: "#F3F4F6",
      themeDark: "#0E0F10",
      themeColor: "#0E0F10",
      backgroundColor: "#0E0F10"
    },
    normal: {
      baseline: { points: [[14, 49], [50, 49]], width: 3, role: "baseline" },
      strokes: [
        { points: [[24, 18], [24, 46]], width: 5, role: "glyph" },
        { points: [[42, 18], [42, 46]], width: 5, role: "glyph" },
        { points: [[14, 32], [50, 32]], width: 5, role: "line" }
      ],
      dot: { x: 50, y: 32, r: 4.5, role: "accent" }
    },
    small: {
      baseline: { points: [[3, 13], [13, 13]], width: 1, role: "baseline" },
      strokes: [
        { points: [[6, 4.5], [6, 12.5]], width: 1.6, role: "glyph" },
        { points: [[11, 4.5], [11, 12.5]], width: 1.6, role: "glyph" },
        { points: [[3, 8], [13, 8]], width: 1.5, role: "line" }
      ],
      dot: { x: 13, y: 8, r: 1.4, role: "accent" }
    },
    caveats: "The bone request line separates from the orange posts at 16 px; the static PNG carries a bone rim for dark tab strips."
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
      "Reconciliation reads as a paper ledger: two entries in ink and amber converge on one matched green point, with a muted baseline. The dark-media branch flips to an ink plate with paper strokes.",
    palette: {
      light: {
        plate: "#F4EEE1",
        glyph: "#211E19",
        accent: "#2C5A39",
        accent2: "#9A6410",
        baseline: "#8A8378",
        line: "#211E19",
        rim: { color: "#211E19", alpha: 0.55 }
      },
      dark: {
        plate: "#211E19",
        glyph: "#F4EEE1",
        accent: "#6FAE7C",
        accent2: "#C98A2E",
        baseline: "#8A8378",
        line: "#F4EEE1",
        rim: { color: "#F4EEE1", alpha: 0.5 }
      },
      staticRimAlpha: 0.55,
      tabLight: "#F3F4F6",
      tabDark: "#16181D",
      themeLight: "#F4EEE1",
      themeDark: "#211E19",
      themeColor: "#211E19",
      backgroundColor: "#F4EEE1"
    },
    normal: {
      baseline: { points: [[14, 49], [50, 49]], width: 3, role: "baseline" },
      strokes: [
        { points: [[14, 23], [29, 23], [42, 28]], width: 5, role: "glyph" },
        { points: [[14, 42], [29, 42], [42, 28]], width: 5, role: "accent2" }
      ],
      dot: { x: 42, y: 28, r: 4.5, role: "accent" }
    },
    small: {
      baseline: { points: [[3, 13], [13, 13]], width: 1, role: "baseline" },
      strokes: [
        { points: [[3.5, 5.5], [7, 5.5], [11.5, 7.5]], width: 1.5, role: "glyph" },
        { points: [[3.5, 10.5], [7, 10.5], [11.5, 7.5]], width: 1.5, role: "accent2" }
      ],
      dot: { x: 11.5, y: 7.5, r: 1.4, role: "accent" }
    },
    caveats: "The paper plate carries an ink rim on light chrome; the dark-media branch replaces it with ink and a paper rim so the plate never disappears."
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
      "The organisation landing icon is a stepped equity line in bone on ink, with a mint end dot and a deep green baseline. It is the most restrained set in the family.",
    palette: {
      light: {
        plate: "#15181D",
        glyph: "#E6E4DE",
        accent: "#8EB8A8",
        accent2: "#22483E",
        baseline: "#5C7C71",
        line: "#E6E4DE",
        rim: { color: "#E6E4DE", alpha: 0.55 }
      },
      dark: {
        plate: "#15181D",
        glyph: "#E6E4DE",
        accent: "#8EB8A8",
        accent2: "#22483E",
        baseline: "#5C7C71",
        line: "#E6E4DE",
        rim: { color: "#E6E4DE", alpha: 0.55 }
      },
      staticRimAlpha: 0.55,
      tabLight: "#F3F4F6",
      tabDark: "#16181D",
      themeLight: "#E6E4DE",
      themeDark: "#15181D",
      themeColor: "#15181D",
      backgroundColor: "#E6E4DE"
    },
    normal: {
      baseline: { points: [[14, 49], [50, 49]], width: 3, role: "baseline" },
      strokes: [
        {
          points: [[14, 44], [22, 44], [22, 37], [31, 37], [31, 29], [40, 29], [40, 21], [48, 21]],
          width: 5,
          role: "glyph"
        }
      ],
      dot: { x: 48, y: 21, r: 4.5, role: "accent" }
    },
    small: {
      baseline: { points: [[3, 13], [13, 13]], width: 1.1, role: "baseline" },
      strokes: [
        {
          points: [[3.5, 11], [5.5, 11], [5.5, 9], [8.2, 9], [8.2, 6.8], [10.8, 6.8], [10.8, 4.8], [12.5, 4.8]],
          width: 1.8,
          role: "glyph"
        }
      ],
      dot: { x: 12.5, y: 4.8, r: 1.5, role: "accent" }
    },
    caveats: "The ink plate is given a subtle bone rim in dark chrome and in the static PNGs; the mint dot is the only saturated accent."
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
