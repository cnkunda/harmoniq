import colors from '@/src/constants/colors'
import type { TabThemeColors } from '@/types/tabMessage'

/**
 * AlphaTab display resources — aligned with `docs/DESIGN_SYSTEM.md` (theme white glyphs / amber on wood).
 * Keep `assets/alphatab-harness/index.html` initial `display.resources` + `HARMONIQ_TAB_PRESETS` in sync.
 */
export const TAB_HARNESS_THEME: TabThemeColors = {
  mainGlyphColor: colors.white,
  secondaryGlyphColor: colors.amber.light,
  /** Lighter warm brown for better visibility on `#2B1D0E` score chrome. */
  barSeparatorColor: '#9B8D7B',
  scoreInfoColor: colors.muted.brown,
  staffLineColor: '#9B8D7B',
  barNumberColor: colors.muted.brown,
}
