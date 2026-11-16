export type CoachSource = 'ai' | 'template'

/** Quiet byline-style provenance label for coach copy. */
export function coachSourceLabel(source: CoachSource | null | undefined): string | null {
  if (source === 'ai') return 'AI guidance'
  if (source === 'template') return 'Template guidance'
  return null
}
