import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import type { Page } from "@playwright/test";

export type DeterministicFinding = {
  check: string;
  issue: string;
  severity: "error" | "warning";
  detail: string;
};

type Rgba = [number, number, number, number];
type Group = { count: number; examples: string[] };
type ContrastGroup = Group & { ratio: number; threshold: number };

const COLOR_SOURCES = ["src/constants/colors.ts", "tailwind.config.js"] as const;

const COLOR_LITERAL_RE =
  /['"](#[0-9a-fA-F]{3,8}|rgba?\(\s*\d+\s*,\s*\d+\s*,\s*\d+(?:\s*,\s*(?:0|1|0?\.\d+))?\s*\))['"]/g;

const CHANNEL_TOLERANCE = 2;
const MAX_UNIQUE_VALUES_PER_CHECK = 10;

function hexToRgba(hex: string): Rgba | null {
  let h = hex.slice(1);
  if (h.length === 3 || h.length === 4) {
    h = h
      .split("")
      .map((c) => c + c)
      .join("");
  }
  if (h.length !== 6 && h.length !== 8) return null;
  const r = parseInt(h.slice(0, 2), 16);
  const g = parseInt(h.slice(2, 4), 16);
  const b = parseInt(h.slice(4, 6), 16);
  const a = h.length === 8 ? parseInt(h.slice(6, 8), 16) / 255 : 1;
  if ([r, g, b].some(Number.isNaN)) return null;
  return [r, g, b, a];
}

function colorLiteralToRgba(literal: string): Rgba | null {
  if (literal.startsWith("#")) return hexToRgba(literal);
  const m = literal.match(/rgba?\(([^)]+)\)/);
  if (!m) return null;
  const parts = m[1]
    .split(/[,/\s]+/)
    .filter(Boolean)
    .map(Number);
  if (parts.length < 3 || parts.slice(0, 3).some(Number.isNaN)) return null;
  return [parts[0], parts[1], parts[2], parts.length > 3 ? parts[3] : 1];
}

/**
 * Allowed-color palette parsed live from the design token sources so the
 * check always matches the current theme (single source of truth). Returns
 * opaque RGB channels; alpha variants of palette colors match by proximity.
 */
export function loadAllowedPalette(): number[][] {
  const channels: number[][] = [];
  const seen = new Set<string>();
  for (const relPath of COLOR_SOURCES) {
    const abs = path.resolve(process.cwd(), relPath);
    if (!existsSync(abs)) continue;
    const source = readFileSync(abs, "utf-8");
    for (const match of source.matchAll(COLOR_LITERAL_RE)) {
      const rgba = colorLiteralToRgba(match[1]);
      if (!rgba) continue;
      const key = rgba.slice(0, 3).join(",");
      if (seen.has(key)) continue;
      seen.add(key);
      channels.push(rgba.slice(0, 3));
    }
  }
  return channels;
}

/**
 * Deterministic (DOM-measured) visual checks: overflow, broken images,
 * blank screens, off-palette colors, wrong font families, WCAG contrast.
 * Authoritative — unlike vision-model prose, these produce no false positives.
 */
export async function runVisualChecks(page: Page): Promise<DeterministicFinding[]> {
  const palette = loadAllowedPalette();
  return page.evaluate((allowed: number[][]) => {
    // Everything the browser context needs must live inside this callback —
    // module-scope constants are not serialized across.
    const allowedFontRe = /playfairdisplay|playfair display|dmsans|dm sans|jetbrainsmono|jetbrains mono/i;
    const channelTolerance = 2;
    const maxUniquePerCheck = 10;

    type Rgba = [number, number, number, number];
    type Group = { count: number; examples: string[] };
    type ContrastGroup = Group & { ratio: number; threshold: number };

    const out: {
      check: string;
      issue: string;
      severity: "error" | "warning";
      detail: string;
    }[] = [];
    const offPalette = new Map<string, Group>();
    const fontIssues = new Map<string, Group>();
    const contrastIssues = new Map<string, ContrastGroup>();

    const add = (
      check: string,
      issue: string,
      severity: "error" | "warning",
      detail: string,
    ) => {
      out.push({ check, issue, severity, detail });
    };

    const parseCssColor = (value: string): Rgba | null => {
      const v = value.trim().toLowerCase();
      if (!v || v === "transparent") return null;
      const fnMatch = v.match(/^rgba?\(([^)]+)\)$/);
      if (fnMatch) {
        const parts = fnMatch[1]
          .split(/[,/\s]+/)
          .filter(Boolean)
          .map(Number);
        if (parts.length >= 3 && parts.slice(0, 3).every((n) => !Number.isNaN(n))) {
          return [parts[0], parts[1], parts[2], parts.length > 3 ? parts[3] : 1];
        }
        return null;
      }
      if (v.startsWith("#")) {
        let h = v.slice(1);
        if (h.length === 3 || h.length === 4) {
          h = h
            .split("")
            .map((c) => c + c)
            .join("");
        }
        if (h.length !== 6 && h.length !== 8) return null;
        const r = parseInt(h.slice(0, 2), 16);
        const g = parseInt(h.slice(2, 4), 16);
        const b = parseInt(h.slice(4, 6), 16);
        const a = h.length === 8 ? parseInt(h.slice(6, 8), 16) / 255 : 1;
        if ([r, g, b].some(Number.isNaN)) return null;
        return [r, g, b, a];
      }
      return null;
    };

    // Named colors and gradients stay unflagged — only parseable values are judged.
    const inPalette = (c: Rgba | null): boolean => {
      if (!c) return true;
      if (c[3] === 0) return true;
      return allowed.some(
        (p) =>
          Math.abs(c[0] - p[0]) <= channelTolerance &&
          Math.abs(c[1] - p[1]) <= channelTolerance &&
          Math.abs(c[2] - p[2]) <= channelTolerance,
      );
    };

    // react-native-web internals (r-* runtime classes, css-* View bases) and
    // Expo dev overlays are framework chrome, not design surface. Elements
    // carrying an explicit background class stay checkable.
    const isFrameworkChrome = (el: Element): boolean => {
      const raw = el.getAttribute("class") || "";
      const classes = raw.trim().split(/\s+/).filter(Boolean);
      if (classes.length === 0) return false;
      if (classes.some((c) => c.startsWith("__expo"))) return true;
      return (
        classes.every((c) => c.startsWith("r-") || c.startsWith("css-")) &&
        !classes.some((c) => c.includes("background"))
      );
    };

    const label = (el: Element): string => {
      const tag = el.tagName.toLowerCase();
      const raw = el.getAttribute("class") || "";
      const cls = raw
        .trim()
        .split(/\s+/)
        .filter((c) => c && !c.startsWith("css-"))
        .slice(0, 3)
        .map((c) => "." + c)
        .join("");
      const text = (el.textContent || "")
        .trim()
        .replace(/\s+/g, " ")
        .slice(0, 24);
      return `<${tag}${cls}>${text ? ` "${text}"` : ""}`;
    };

    const directTextOf = (el: Element): string =>
      Array.from(el.childNodes)
        .filter((n) => n.nodeType === 3)
        .map((n) => (n.textContent || "").trim())
        .filter(Boolean)
        .join(" ");

    // scrollWidth counts absolutely-positioned decorative children (ambient
    // glows, animated ripples) that are meant to bleed. Only flag when a
    // non-absolute child actually spills past the border box — that is real
    // layout overflow (text/rows sticking out or clipped by overflow-hidden).
    const hasFlowOverflow = (el: Element): boolean => {
      const rect = el.getBoundingClientRect();
      return Array.from(el.children).some((child) => {
        if (window.getComputedStyle(child).position === "absolute") return false;
        const r = child.getBoundingClientRect();
        return r.right > rect.right + 4 || r.left < rect.left - 4;
      });
    };

    const luminance = (c: [number, number, number]): number => {
      const f = (x: number): number => {
        const v = x / 255;
        return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
      };
      return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]);
    };

    const blend = (fg: Rgba, bg: Rgba): Rgba => {
      const a = fg[3] + bg[3] * (1 - fg[3]);
      if (a === 0) return [0, 0, 0, 0];
      return [
        (fg[0] * fg[3] + bg[0] * bg[3] * (1 - fg[3])) / a,
        (fg[1] * fg[3] + bg[1] * bg[3] * (1 - fg[3])) / a,
        (fg[2] * fg[3] + bg[2] * bg[3] * (1 - fg[3])) / a,
        a,
      ];
    };

    // A gradient's stops are blended to one representative color — close
    // enough for WCAG estimation on the app's dark wood gradients.
    const bgFromImage = (image: string): Rgba | null => {
      if (!image || image === "none") return null;
      const stops: Rgba[] = [];
      for (const m of image.matchAll(/#[0-9a-fA-F]{3,8}|rgba?\([^)]+\)/g)) {
        const c = parseCssColor(m[0]);
        if (c) stops.push(c);
      }
      if (stops.length === 0) return null;
      const avg: Rgba = [0, 0, 0, 0];
      for (const s of stops) {
        avg[0] += s[0] / stops.length;
        avg[1] += s[1] / stops.length;
        avg[2] += s[2] / stops.length;
        avg[3] += s[3] / stops.length;
      }
      return avg;
    };

    // True visual background = full ancestor composite: every semi-transparent
    // layer between the element and an opaque base must be composited (skipping
    // alpha<0.95 layers reported false "invisible text" positives on buttons
    // like bg-amber-accent/90). Wood gradients average their stops — good
    // enough for WCAG estimation on the app's dark wood gradients.
    const opaqueBg = (el: Element): Rgba => {
      const layers: Rgba[] = [];
      let node: Element | null = el;
      while (node) {
        if (!isFrameworkChrome(node)) {
          const cs = window.getComputedStyle(node);
          const fromImage = bgFromImage(cs.backgroundImage);
          if (fromImage) layers.push(fromImage);
          const c = parseCssColor(cs.backgroundColor);
          if (c && c[3] > 0) layers.push(c);
        }
        node = node.parentElement;
      }
      // layers are leaf→root; fold root-first so each layer composites over
      // everything below it. wood.900 is the app-wide fallback base.
      let acc: Rgba = [27, 18, 14, 1];
      for (let i = layers.length - 1; i >= 0; i -= 1) {
        acc = blend(layers[i], acc);
      }
      return acc;
    };

    const bump = (map: Map<string, Group>, key: string, example: string) => {
      const g = map.get(key) || { count: 0, examples: [] };
      g.count += 1;
      if (g.examples.length < 3 && !g.examples.includes(example)) g.examples.push(example);
      map.set(key, g);
    };

    const docEl = document.documentElement;
    const docOverflow = docEl.scrollWidth - docEl.clientWidth;
    if (docOverflow > 4) {
      add(
        "document-overflow",
        "Layout overflow / clipping",
        "error",
        `Page scrolls horizontally by ${docOverflow}px (scrollWidth ${docEl.scrollWidth} > viewport ${docEl.clientWidth})`,
      );
    }

    let visibleTextLength = 0;
    let visibleImageCount = 0;

    for (const el of Array.from(document.querySelectorAll("*"))) {
      const cs = window.getComputedStyle(el);
      if (cs.display === "none" || cs.visibility === "hidden" || cs.opacity === "0") continue;
      const rect = el.getBoundingClientRect();
      if (rect.width < 2 || rect.height < 2) continue;

      // SVG rendering uses fill attributes and glyph fonts (alphaTab music
      // glyphs, fretboard diagrams) — CSS color/font semantics don't apply.
      if (el instanceof SVGElement) {
        if (el.tagName.toLowerCase() === "svg") visibleImageCount += 1;
        continue;
      }

      // Framework chrome (RNW internals, Expo dev overlay) is not design surface.
      if (isFrameworkChrome(el)) continue;

      if (el.tagName === "IMG") {
        const img = el as HTMLImageElement;
        if (img.complete && img.naturalWidth === 0) {
          add("broken-image", "Broken image", "error", `${label(el)} failed to load (naturalWidth 0)`);
        } else {
          visibleImageCount += 1;
        }
        continue;
      }

      if (
        el.scrollWidth > el.clientWidth + 4 &&
        el.clientWidth > 0 &&
        cs.overflowX !== "auto" &&
        cs.overflowX !== "scroll" &&
        hasFlowOverflow(el)
      ) {
        add(
          "element-overflow",
          "Layout overflow / clipping",
          "warning",
          `${label(el)} overflows horizontally (scrollWidth ${el.scrollWidth} > clientWidth ${el.clientWidth}, overflow-x ${cs.overflowX})`,
        );
      }

      const directText = directTextOf(el);
      if (directText) {
        visibleTextLength += directText.length;

        if (!allowedFontRe.test(cs.fontFamily)) {
          bump(fontIssues, cs.fontFamily, label(el));
        }

        const textColor = parseCssColor(cs.color);
        if (textColor && textColor[3] > 0 && !inPalette(textColor)) {
          bump(offPalette, `text color ${textColor.slice(0, 3).join(", ")}`, label(el));
        }

        if (textColor) {
          const bg = opaqueBg(el);
          const effective = blend(textColor, bg);
          const l1 = luminance([effective[0], effective[1], effective[2]]);
          const l2 = luminance([bg[0], bg[1], bg[2]]);
          const ratio = (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
          const fontSize = parseFloat(cs.fontSize) || 16;
          const bold = parseInt(cs.fontWeight, 10) >= 700 || cs.fontWeight === "bold";
          const large = fontSize >= 24 || (fontSize >= 18.66 && bold);
          const threshold = large ? 3.0 : 4.5;
          if (ratio < threshold - 0.01) {
            const key = `${textColor.slice(0, 3).join(", ")} on ${bg.slice(0, 3).join(", ")}`;
            const g = contrastIssues.get(key) || { count: 0, examples: [], ratio, threshold };
            g.count += 1;
            if (g.examples.length < 3 && !g.examples.includes(label(el))) {
              g.examples.push(label(el));
            }
            contrastIssues.set(key, g);
          }
        }
      }

      const bgColor = parseCssColor(cs.backgroundColor);
      if (bgColor && bgColor[3] > 0 && !inPalette(bgColor)) {
        bump(offPalette, `background ${bgColor.slice(0, 3).join(", ")}`, label(el));
      }

      if (parseFloat(cs.borderTopWidth) > 0) {
        const borderColor = parseCssColor(cs.borderTopColor);
        if (borderColor && borderColor[3] > 0 && !inPalette(borderColor)) {
          bump(offPalette, `border ${borderColor.slice(0, 3).join(", ")}`, label(el));
        }
      }
    }

    if (visibleTextLength === 0 && visibleImageCount === 0) {
      add(
        "blank-screen",
        "Broken / blank screen",
        "error",
        "No visible text or images in the DOM — possible runtime error or blank render",
      );
    }

    const flush = (
      map: Map<string, Group | ContrastGroup>,
      check: string,
      issue: string,
      format: (key: string, g: Group | ContrastGroup) => string,
    ) => {
      const entries = Array.from(map.entries());
      for (const [key, g] of entries.slice(0, maxUniquePerCheck)) {
        const more = g.count > g.examples.length ? ` (+${g.count - g.examples.length} more)` : "";
        add(check, issue, "warning", `${format(key, g)} — e.g. ${g.examples.join(", ")}${more}`);
      }
      if (entries.length > maxUniquePerCheck) {
        add(
          check,
          issue,
          "warning",
          `...and ${entries.length - maxUniquePerCheck} more unique values for this check`,
        );
      }
    };

    flush(offPalette, "off-palette-color", "Color mismatch", (key, g) =>
      `Off-palette ${key} on ${g.count} element(s)`,
    );
    flush(fontIssues, "font-family", "Typography", (key, g) =>
      `Font family "${key}" on ${g.count} element(s)`,
    );
    flush(contrastIssues, "contrast", "Contrast / readability", (key, g) =>
      `Text rgb(${key}) — ratio ${(g as ContrastGroup).ratio.toFixed(2)}:1, needs ${(g as ContrastGroup).threshold}:1 — ${g.count} element(s)`,
    );

    return out;
  }, palette);
}
