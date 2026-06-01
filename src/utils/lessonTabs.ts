/** GP5 payloads on `LessonJSON.sections[]` items (backend tabgen). @deprecated Export-only — use `musicxml` for rendering. */
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

/** First GP5 blob on any section (full → skeleton → alt), for server export from a saved lesson. @deprecated Export-only (GP5→MIDI conversion). */
export function firstGp5Base64FromLessonSections(sections: unknown): string | null {
  if (!Array.isArray(sections)) return null
  for (const sec of sections) {
    const p = readSectionTabPayloads(sec)
    const gp = p.full ?? p.skeleton ?? p.alt
    if (gp) return gp
  }
  return null
}

// Commit 108: MusicXML reader utilities

/** Read MusicXML string from a section object. */
export function readSectionMusicXml(section: unknown): string | null {
  if (!section || typeof section !== 'object') return null
  const o = section as Record<string, unknown>
  if (typeof o.musicxml === 'string' && o.musicxml.trim()) return o.musicxml.trim()
  return null
}

/** First MusicXML string on any section, for fallback rendering. */
export function firstMusicXmlFromLessonSections(sections: unknown): string | null {
  if (!Array.isArray(sections)) return null
  for (const sec of sections) {
    const xml = readSectionMusicXml(sec)
    if (xml) return xml
  }
  return null
}
