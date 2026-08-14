import { TRANSCRIPTION_CONFIDENCE_UNCERTAIN_MAX } from '@/src/db/schema'

/** GP5 payloads on `LessonJSON.sections[]` items (backend tabgen). */
export type SectionTabPayloads = {
  full?: string
  skeleton?: string
  alt?: string
}

export function readSectionTabPayloads(section: unknown): SectionTabPayloads {
  if (!section || typeof section !== 'object') return {}
  const o = section as Record<string, unknown>
  const str = (k: string) => (typeof o[k] === 'string' ? (o[k] as string) : undefined)
  return {
    full: str('tab_full_gp5_base64'),
    skeleton: str('tab_skeleton_gp5_base64'),
    alt: str('tab_alt_position_gp5_base64'),
  }
}

/** First GP5 blob on any section (full → skeleton → alt), for server export from a saved lesson. */
export function firstGp5Base64FromLessonSections(sections: unknown): string | null {
  if (!Array.isArray(sections)) return null
  for (const sec of sections) {
    const p = readSectionTabPayloads(sec)
    const gp = p.full ?? p.skeleton ?? p.alt
    if (gp) return gp
  }
  return null
}

export type TabVariant = 'full' | 'skeleton' | 'alt'

/**
 * ML Fallback Logic milestone: pick which tab variant to render.
 *
 * Automatic by default — when the lesson's transcription confidence is below
 * the "uncertain" bar, degrade to the skeleton (or alt) tab so the learner
 * never practices against a dubious full transcription. `preferFullTabs`
 * ("Always use full tabs" in Settings) overrides the auto fallback.
 */
export function pickTabVariant(
  confidence: number | null | undefined,
  tabs: SectionTabPayloads,
  preferFullTabs: boolean,
): TabVariant {
  const uncertain = typeof confidence === 'number' && confidence < TRANSCRIPTION_CONFIDENCE_UNCERTAIN_MAX
  if (!preferFullTabs && uncertain) {
    if (tabs.skeleton) return 'skeleton'
    if (tabs.alt) return 'alt'
    return tabs.full ? 'full' : 'skeleton'
  }
  return tabs.full ? 'full' : tabs.skeleton ? 'skeleton' : tabs.alt ? 'alt' : 'full'
}
