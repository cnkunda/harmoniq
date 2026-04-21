import colors from '@/src/constants/colors'
import type { TabThemeColors } from '@/types/tabMessage'

/**
 * AlphaTab display resources — aligned with `docs/DESIGN_SYSTEM.md` (theme white glyphs / amber on wood).
 * Keep `assets/alphatab-harness/index.html` initial `display.resources` + `HARMONIQ_TAB_PRESETS` in sync.
 */
export const TAB_HARNESS_THEME: TabThemeColors = {
  mainGlyphColor: colors.white,
  secondaryGlyphColor: colors.amber.light,
  /** Slightly lighter than `wood.500` for staff/separators on `#2B1D0E` score chrome. */
  barSeparatorColor: '#6E5644',
  scoreInfoColor: colors.muted.brown,
  staffLineColor: '#6E5644',
  barNumberColor: colors.muted.brown,
}
