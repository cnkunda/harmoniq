export type ConfidenceBand = 'low' | 'medium' | 'high'
export type ConfusionLevel = 'low' | 'moderate' | 'high'

/**
 * Commit 184: learner-facing copy for the heuristic confidence signals.
 *
 * The numeric score is hand-tuned, not a calibrated probability. These
 * helpers are the only place that turns it into words, so every surface
 * stays consistent and never renders a raw number or percentage.
 *
 * Thresholds mirror backend/app/confidence_thresholds.py.
 */

export const CONFIDENCE_LOW_MAX = 0.5
export const CONFIDENCE_MEDIUM_MAX = 0.75
export const HEDGE_TRIGGER = 0.3
export const STRONG_HEDGE_TRIGGER = 0.6

export const CHECK_BY_EAR_CUE =
  'The transcription here may be approximate — check this part by ear against the recording.'

const CONFIDENCE_BAND_LABELS: Record<ConfidenceBand, string> = {
  low: 'Rough transcription',
  medium: 'Some fuzziness',
  high: 'Good match',
}

const CONFUSION_LEVEL_LABELS: Record<ConfusionLevel, string> = {
  low: 'Low',
  moderate: 'Moderate',
  high: 'High',
}

const CONFUSION_BAR_WIDTHS: Record<ConfusionLevel, `${number}%`> = {
  low: '33%',
  moderate: '66%',
  high: '100%',
}

export interface SectionConfidenceInput {
  chord_confidence?: number | null
  instrument_confusion?: number | null
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value)
}

/** Map a raw heuristic score to a coarse band; missing/NaN means unknown. */
export function confidenceBandFromScore(
  value: number | null | undefined,
): ConfidenceBand | null {
  if (!isFiniteNumber(value)) return null
  if (value < CONFIDENCE_LOW_MAX) return 'low'
  if (value < CONFIDENCE_MEDIUM_MAX) return 'medium'
  return 'high'
}

/** Plain-language wording for a band; `null` renders nothing. */
export function confidenceBandLabel(
  band: ConfidenceBand | null | undefined,
): string | null {
  if (band === null || band === undefined) return null
  return CONFIDENCE_BAND_LABELS[band]
}

/** Map instrument confusion to the same three tiers the coach hedge uses. */
export function confusionLevel(value: number | null | undefined): ConfusionLevel | null {
  if (!isFiniteNumber(value)) return null
  const normalized = Math.max(0, Math.min(1, value))
  if (normalized < HEDGE_TRIGGER) return 'low'
  if (normalized < STRONG_HEDGE_TRIGGER) return 'moderate'
  return 'high'
}

/** Plain-language label for a confusion tier; `null` renders nothing. */
export function confusionLevelLabel(
  level: ConfusionLevel | null | undefined,
): string | null {
  if (level === null || level === undefined) return null
  return CONFUSION_LEVEL_LABELS[level]
}

/** Coarse bar width for a confusion tier (avoids implying numeric precision). */
export function confusionBarWidth(
  level: ConfusionLevel | null | undefined,
): `${number}%` | null {
  if (level === null || level === undefined) return null
  return CONFUSION_BAR_WIDTHS[level]
}

/** True when the current section deserves a "check this part by ear" cue. */
export function sectionNeedsCheckByEar(
  section: SectionConfidenceInput | null | undefined,
): boolean {
  if (!section) return false
  if (confidenceBandFromScore(section.chord_confidence) === 'low') return true
  const level = confusionLevel(section.instrument_confusion)
  return level === 'moderate' || level === 'high'
}
