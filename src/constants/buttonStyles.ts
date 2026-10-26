/**
 * Shared button tokens.
 *
 * One visual language for the app: solid amber primary, bordered wood
 * secondary, transparent ghost, terracotta danger. All buttons share the same
 * radius, height, padding, and type scale.
 */

/** Layout + type shared by every button. */
export const BTN_BASE =
  'min-h-[44px] flex-row items-center justify-center gap-2 rounded-xl px-5 py-3'

export const BTN_PRIMARY = 'bg-amber-accent active:bg-amber-light'

export const BTN_SECONDARY = 'border border-wood-600/55 bg-wood-700/40 active:bg-wood-700/60'

export const BTN_GHOST = 'border border-wood-600/35 bg-transparent active:bg-wood-800/50'

export const BTN_DANGER = 'border border-danger/50 bg-danger/10 active:bg-danger/20'

/** Compact size for inline action rows (review exports, modal actions). */
export const BTN_SM_BASE =
  'min-h-[36px] flex-row items-center justify-center gap-1.5 rounded-lg px-3.5 py-2'
