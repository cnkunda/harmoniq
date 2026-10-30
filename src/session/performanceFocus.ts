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

/** Resolve the effective fretboard mode. Manual choice always wins. */
export function resolveFretboardMode(
  override: FretboardMode,
  profile: PerformanceProfile | null | undefined,
): Exclude<FretboardMode, 'auto'> {
  if (override !== 'auto') return override
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
