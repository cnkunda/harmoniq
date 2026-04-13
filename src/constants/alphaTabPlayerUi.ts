import colors from '@/src/constants/colors'

/**
 * Player overlay styles — https://alphatab.net/docs/guides/styling-player
 * Beat cursor must have explicit width. Palette matches wood/amber tab harness.
 *
 * Keep `assets/alphatab-harness/index.html` `<style>` player rules in sync with this file.
 */
const AMBER_LIGHT = colors.amber.light // #E8B86D
/** Theme success — notehead, stem, flag, and tab digits during playback (Listen / stem sync). */
const HIGHLIGHT = colors.success // #7A9B6D
/** Bar wash: amber accent @ ~22% on dark score */
const BAR_WASH = 'rgba(212, 165, 116, 0.22)'

const WOOD_TRACK = 'rgba(61, 35, 23, 0.92)'
const SCROLL_THUMB = colors.amber.accent
const SCROLL_THUMB_HOVER = colors.amber.light

/**
 * Horizontal scrollbar for the tab strip — wood track + amber thumb (WebKit + Firefox).
 * Apply class `harmoniq-alphatab-scroll` on the same element that scrolls horizontally.
 *
 * Keep `assets/alphatab-harness/index.html` in sync.
 */
export const ALPHATAB_SCROLLBAR_CSS = `
.harmoniq-alphatab-scroll {
  scrollbar-width: thin;
  scrollbar-color: ${SCROLL_THUMB} ${WOOD_TRACK};
}
.harmoniq-alphatab-scroll::-webkit-scrollbar {
  height: 10px;
}
.harmoniq-alphatab-scroll::-webkit-scrollbar-track {
  background: ${WOOD_TRACK};
  border-radius: 5px;
}
.harmoniq-alphatab-scroll::-webkit-scrollbar-thumb {
  background: ${SCROLL_THUMB};
  border-radius: 5px;
  border: 2px solid ${WOOD_TRACK};
}
.harmoniq-alphatab-scroll::-webkit-scrollbar-thumb:hover {
  background: ${SCROLL_THUMB_HOVER};
}
`

export const ALPHATAB_PLAYER_CURSOR_CSS = `
.at-cursor-bar { background: ${BAR_WASH}; }
.at-cursor-beat {
  background: ${AMBER_LIGHT};
  width: 3px;
  box-shadow: 0 0 2px rgba(44, 24, 16, 0.45);
}
/* Per-note playback tint — same color for heads, stems, flags, SMuFL <use>, etc. */
path.at-highlight,
polygon.at-highlight,
circle.at-highlight,
ellipse.at-highlight,
rect.at-highlight,
use.at-highlight,
text.at-highlight,
tspan.at-highlight,
.at-highlight path,
.at-highlight polygon,
.at-highlight circle,
.at-highlight ellipse,
.at-highlight rect,
.at-highlight use,
.at-highlight text,
.at-highlight tspan {
  fill: ${HIGHLIGHT};
  stroke: ${HIGHLIGHT};
  stroke-width: 1.8px;
}
line.at-highlight,
polyline.at-highlight,
.at-highlight line,
.at-highlight polyline {
  stroke: ${HIGHLIGHT};
}
/*
 * AlphaTab adds class at-highlight only to nodes with the beat group class (e.g. b + beat id). Stems/flags/beams
 * are often sibling g content under the same beat wrapper — use :has() so those shapes tint too.
 * !important beats SVG presentation attributes on paths/stems (runtime evidence: no line elements in host).
 */
svg g:has(> .at-highlight) :is(path, line, polyline, use, text, tspan) {
  fill: ${HIGHLIGHT} !important;
  stroke: ${HIGHLIGHT} !important;
  stroke-width: 1.8px;
}
svg g:has(> .at-highlight) line,
svg g:has(> .at-highlight) polyline {
  fill: none !important;
}
`

/** Combined skin injected once on web (player overlays + scrollbar). */
export const ALPHATAB_WEB_SURFACE_CSS = `${ALPHATAB_PLAYER_CURSOR_CSS}\n${ALPHATAB_SCROLLBAR_CSS}`
