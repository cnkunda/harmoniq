/**
 * Shared typography and UI token constants for session steps.
 * Eliminates inline duplication across FretboardDiagram, ListenStemPanel,
 * PlayCaptureCard, GhostPlayerControl, and session screens.
 */

/** Eyebrow / section label — used above cards, panels, and controls. */
export const SECTION_EYEBROW_CLASS =
  'font-sans-medium text-xs uppercase tracking-wide text-amber-accent'

/** Compact eyebrow for tight spaces (e.g. GhostPlayerControl, PlayCaptureCard). */
export const SECTION_EYEBROW_COMPACT_CLASS =
  'font-sans-medium text-[10px] uppercase tracking-wider text-amber-accent'

/**
 * Choice chip base system — used for speed presets, metronome subdivisions,
 * fretboard mode toggles, overlay modes, section chips, etc.
 */
export const CHOICE_CHIP_BASE =
  'min-w-0 items-center justify-center rounded-full border px-3 py-1.5'
export const CHOICE_CHIP_OFF = 'border-wood-600/40 bg-wood-900/10'
export const CHOICE_CHIP_ON = 'border-amber-accent bg-amber-accent'

/** Mono labels inside chips (speed %, subdivision). */
export const CHOICE_LABEL_MONO_OFF = 'font-mono text-[11px] font-medium text-muted-brown'
export const CHOICE_LABEL_MONO_ON = 'font-mono text-[11px] font-medium text-wood-900'

/** Sans labels inside chips (section names, overlay labels). */
export const CHOICE_LABEL_SANS_OFF = 'font-sans text-xs text-muted-brown'
export const CHOICE_LABEL_SANS_ON = 'font-sans-medium text-xs text-wood-900'

/** Standard disabled opacity for all pressables. */
export const DISABLED_OPACITY = 'opacity-50'

/** Standard card shell for session playback surfaces. */
export const SESSION_CARD_CLASS =
  'rounded-xl border border-wood-600/40 bg-cream-dark/45 px-3.5 py-3'

/**
 * Non-interactive pill tokens (status labels, tags, metadata).
 * Interactive choice chips live above as `CHOICE_CHIP_*`.
 */
export const PILL_BASE = 'flex-row items-center gap-1.5 rounded-full border px-2.5 py-1'
export const PILL_NEUTRAL = 'border-hairline bg-wood-800/55'
export const PILL_ACCENT = 'border-amber-accent/45 bg-amber-accent/15'
export const PILL_SUCCESS = 'border-success/45 bg-success/15'
export const PILL_DANGER = 'border-danger/45 bg-danger/10'
export const PILL_LIGHT = 'border-wood-600/30 bg-cream-dark/50'

export const PILL_LABEL = 'font-sans-medium text-[11px]'
export const PILL_LABEL_XS = 'font-sans-medium text-[10px]'
export const PILL_TEXT_NEUTRAL = 'text-muted-brown'
export const PILL_TEXT_ACCENT = 'text-amber-light'
export const PILL_TEXT_SUCCESS = 'text-success'
export const PILL_TEXT_DANGER = 'text-danger'
export const PILL_TEXT_LIGHT = 'text-wood-900'
