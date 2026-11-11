/** Derive jam-bed settings from a saved lesson/section (J5). */

export type LessonBed = {
  musicalKey: string
  keyRoot: string
  keyMode: 'major' | 'minor'
  bpm: number | null
  progression: string[]
  sectionLabel: string | null
  songTitle: string
}

type ChordEventLike = { timestamp?: number | null; chord?: string | null }
type SectionLike = {
  label?: string | null
  start_time_seconds?: number | null
  end_time_seconds?: number | null
}
export type LessonLike = {
  key?: string | null
  tempo?: number | null
  song_title?: string | null
  chord_timeline?: { events?: ChordEventLike[] | null } | null
  sections?: SectionLike[] | null
}

const QUALITY_SUFFIX: Record<string, string> = {
  maj: '',
  major: '',
  min: 'm',
  minor: 'm',
  m: 'm',
  maj7: 'maj7',
  min7: 'm7',
  m7: 'm7',
  '7': '7',
  dim: 'dim',
  dim7: 'dim7',
  aug: 'aug',
  sus2: 'sus2',
  sus4: 'sus4',
  '6': '6',
  min6: 'm6',
  m6: 'm6',
  '9': '9',
  maj9: 'maj9',
  min9: 'm9',
  m9: 'm9',
  '11': '11',
  '13': '13',
}

/** Convert lesson chord ids (`C:maj`, `A:min7`) to jam chord symbols (`C`, `Am7`). */
export function lessonChordToSymbol(chord: string | null | undefined): string | null {
  if (!chord) return null
  const trimmed = chord.trim()
  if (!trimmed || trimmed === 'N') return null
  const [rootRaw, qualityRaw = 'maj'] = trimmed.split(':')
  const root = rootRaw.trim()
  if (!/^[A-G][#b]?$/.test(root)) return null
  const suffix = QUALITY_SUFFIX[qualityRaw.trim().toLowerCase()]
  return suffix === undefined ? null : `${root}${suffix}`
}

/** Split a lesson key literal (`A minor`, `G major`) into root + mode. */
export function splitLessonKey(key: string | null | undefined): { root: string; mode: 'major' | 'minor' } {
  const match = /^\s*([A-G][#b]?)\s*(major|minor)?/i.exec(key ?? '')
  const root = match?.[1] ? match[1].charAt(0).toUpperCase() + match[1].slice(1) : 'A'
  const mode = (match?.[2] ?? '').toLowerCase() === 'minor' ? 'minor' : 'major'
  return { root, mode }
}

/** Build a section-aware chord progression (consecutive duplicates collapsed). */
export function deriveLessonBed(lesson: LessonLike, sectionIndex: number): LessonBed {
  const sections = lesson.sections ?? []
  const section = sections[sectionIndex] ?? null
  const start = typeof section?.start_time_seconds === 'number' ? section.start_time_seconds : null
  const end = typeof section?.end_time_seconds === 'number' ? section.end_time_seconds : null
  const events = lesson.chord_timeline?.events ?? []

  const progression: string[] = []
  for (const event of events) {
    const ts = typeof event.timestamp === 'number' ? event.timestamp : null
    if (start != null && ts != null && ts < start) continue
    if (end != null && ts != null && ts >= end) continue
    const symbol = lessonChordToSymbol(event.chord)
    if (!symbol) continue
    if (progression[progression.length - 1] === symbol) continue
    progression.push(symbol)
    if (progression.length >= 16) break
  }

  const { root, mode } = splitLessonKey(lesson.key)
  return {
    musicalKey: `${root} ${mode}`,
    keyRoot: root,
    keyMode: mode,
    bpm: typeof lesson.tempo === 'number' && lesson.tempo > 0 ? Math.round(lesson.tempo) : null,
    progression,
    sectionLabel: typeof section?.label === 'string' && section.label.trim() ? section.label.trim() : null,
    songTitle: lesson.song_title?.trim() || 'Current song',
  }
}
