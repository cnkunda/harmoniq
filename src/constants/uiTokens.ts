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
