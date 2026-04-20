import colors from '@/src/constants/colors'
import { TAB_HARNESS_THEME } from '@/src/constants/tabHarnessTheme'
import type { TabThemeColors } from '@/types/tabMessage'

/**
 * Named AlphaTab display presets for session steps (Commit 56).
 * Unknown names fall back to `study` in `normalizeTabRenderPresetName`.
 */
export type TabRenderPresetName = 'listen' | 'study' | 'slow' | 'play'

export const DEFAULT_TAB_RENDER_PRESET: TabRenderPresetName = 'study'

export type TabRenderPreset = {
  name: TabRenderPresetName
  colors: TabThemeColors
  /** AlphaTab `display.scale` */
  scale: number
  /** AlphaTab `display.stretchForce` */
  stretchForce: number
}

/** Baseline matches harness defaults / `TAB_HARNESS_THEME`. */
const BASE: TabThemeColors = { ...TAB_HARNESS_THEME }

export const TAB_RENDER_PRESETS: Record<TabRenderPresetName, TabRenderPreset> = {
  listen: {
    name: 'listen',
    colors: { ...BASE },
    scale: 1.1,
    stretchForce: 1,
  },
  study: {
    name: 'study',
    colors: { ...BASE },
    scale: 1.1,
    stretchForce: 1,
  },
  slow: {
    name: 'slow',
    colors: {
      ...BASE,
      /** Slightly brighter bar lines for loop boundary readability. */
      barSeparatorColor: '#6E5644',
      mainGlyphColor: '#F7ECD4',
      secondaryGlyphColor: BASE.secondaryGlyphColor,
    },
    scale: 1.12,
    stretchForce: 1.02,
  },
  play: {
    name: 'play',
    colors: {
      ...BASE,
      /** Stronger glyph contrast while following tab under stems. */
      mainGlyphColor: '#FFF6E0',
      secondaryGlyphColor: colors.amber.light ?? '#E8B86D',
      barNumberColor: colors.muted.brown,
    },
    scale: 1.08,
    stretchForce: 1,
  },
}

export function normalizeTabRenderPresetName(raw: string | null | undefined): TabRenderPresetName {
  const s = String(raw ?? '').trim().toLowerCase()
  if (s === 'listen' || s === 'study' || s === 'slow' || s === 'play') return s
  return DEFAULT_TAB_RENDER_PRESET
}

export function getTabRenderPreset(name: string | null | undefined): TabRenderPreset {
  const key = normalizeTabRenderPresetName(name)
  return TAB_RENDER_PRESETS[key]
}
