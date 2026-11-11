import type { PerformancePartRole, PerformanceProfile } from '@/src/types'

export type FretboardMode = 'auto' | 'chords' | 'solo' | 'both'

const ROLE_TO_MODE: Record<PerformancePartRole, Exclude<FretboardMode, 'auto'>> = {
  rhythm: 'chords',
  lead_solo: 'solo',
  riff: 'solo',
  chord_melody: 'both',
  mixed: 'both',
  unknown: 'both',
}

export type NotePartRoleLike = {
  part_role?: 'lead' | 'rhythm' | null
  string?: number | null
  fret?: number | null
  midi?: number | null
  technique?: string[] | null
}

/**
 * Resolve the effective fretboard mode. Manual choice always wins.
 *
 * When per-note roles are available (T3), they take precedence over the
 * section-level profile: all-lead sections show solo notes, all-rhythm sections
 * show chords, and genuinely mixed material shows both.
 */
export function resolveFretboardMode(
  override: FretboardMode,
  profile: PerformanceProfile | null | undefined,
  soloNotes?: ReadonlyArray<NotePartRoleLike> | null,
): Exclude<FretboardMode, 'auto'> {
  if (override !== 'auto') return override

  let lead = 0
  let rhythm = 0
  for (const note of soloNotes ?? []) {
    if (note.part_role === 'lead') lead += 1
    else if (note.part_role === 'rhythm') rhythm += 1
  }
  if (lead > 0 || rhythm > 0) {
    if (rhythm === 0) return 'solo'
    if (lead === 0) return 'chords'
    if (lead >= rhythm * 3) return 'solo'
    if (rhythm >= lead * 3) return 'chords'
    return 'both'
  }

  if (!profile || profile.part_role === 'unknown') return 'both'
  return ROLE_TO_MODE[profile.part_role] ?? 'both'
}

export function performanceRoleLabel(profile: PerformanceProfile | null | undefined): string | null {
  if (!profile || profile.part_role === 'unknown') return null
  switch (profile.part_role) {
    case 'rhythm':
      return 'Rhythm'
    case 'lead_solo':
      return 'Lead'
    case 'riff':
      return 'Riff'
    case 'chord_melody':
      return 'Chord melody'
    case 'mixed':
      return 'Mixed'
    default:
      return null
  }
}

export function performanceStyleLabel(profile: PerformanceProfile | null | undefined): string | null {
  if (!profile || profile.playing_style === 'unknown') return null
  switch (profile.playing_style) {
    case 'strummed':
      return 'Strummed'
    case 'fingerpicked_arpeggiated':
      return 'Fingerpicked'
    case 'picked':
      return 'Picked'
    case 'muted':
      return 'Muted'
    case 'mixed':
      return 'Mixed'
    default:
      return null
  }
}


/** Read per-note roles from a section payload, falling back to lesson notes. */
export function sectionSoloNotesForMode(
  section: unknown,
  lessonNotes?: ReadonlyArray<NotePartRoleLike> | null,
): ReadonlyArray<NotePartRoleLike> | null {
  if (section && typeof section === 'object') {
    const notes = (section as { solo_notes?: { notes?: unknown } }).solo_notes?.notes
    if (Array.isArray(notes) && notes.length > 0) {
      return notes as ReadonlyArray<NotePartRoleLike>
    }
  }
  return lessonNotes ?? null
}
