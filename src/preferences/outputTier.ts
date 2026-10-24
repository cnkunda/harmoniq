/** Commit 166: notation presentation tiers derived from the same LessonJSON. */
export const OUTPUT_TIERS = ['learner', 'intermediate', 'transcriber'] as const

export type OutputTier = (typeof OUTPUT_TIERS)[number]

/** Intermediate is the non-regression default when no preference exists. */
export const DEFAULT_OUTPUT_TIER: OutputTier = 'intermediate'

/** Parse a stored `output_tier` value; unknown values are rejected. */
export function parseOutputTier(raw: string | null | undefined): OutputTier | null {
  if (raw == null) return null
  const normalized = raw.trim().toLowerCase()
  return (OUTPUT_TIERS as readonly string[]).includes(normalized) ? (normalized as OutputTier) : null
}

/** Map the onboarding experience level to a tier for first-launch auto-detect. */
export function tierForExperienceLevel(
  level: 'beginner' | 'intermediate' | 'advanced' | string | null | undefined,
): OutputTier | null {
  if (level == null) return null
  switch (level.trim().toLowerCase()) {
    case 'beginner':
      return 'learner'
    case 'intermediate':
      return 'intermediate'
    case 'advanced':
      return 'transcriber'
    default:
      return null
  }
}
