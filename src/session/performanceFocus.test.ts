import { describe, expect, it } from 'vitest'

import type { PerformanceProfile } from '@/src/types'
import {
  performanceRoleLabel,
  performanceStyleLabel,
  resolveFretboardMode,
} from './performanceFocus'

function profile(overrides: Partial<PerformanceProfile> = {}): PerformanceProfile {
  return {
    playing_style: 'unknown',
    part_role: 'unknown',
    technique_tags: [],
    confidence: 0.5,
    source: 'heuristic',
    ...overrides,
  }
}

describe('resolveFretboardMode', () => {
  it('keeps a manual override', () => {
    expect(resolveFretboardMode('solo', profile({ part_role: 'rhythm' }))).toBe('solo')
    expect(resolveFretboardMode('both', profile({ part_role: 'lead_solo' }))).toBe('both')
  })

  it('maps rhythm sections to chords in auto mode', () => {
    expect(resolveFretboardMode('auto', profile({ part_role: 'rhythm' }))).toBe('chords')
  })

  it('maps lead sections to solo in auto mode', () => {
    expect(resolveFretboardMode('auto', profile({ part_role: 'lead_solo' }))).toBe('solo')
    expect(resolveFretboardMode('auto', profile({ part_role: 'riff' }))).toBe('solo')
  })

  it('falls back to both for chord melody, mixed, or missing profiles', () => {
    expect(resolveFretboardMode('auto', profile({ part_role: 'chord_melody' }))).toBe('both')
    expect(resolveFretboardMode('auto', profile({ part_role: 'mixed' }))).toBe('both')
    expect(resolveFretboardMode('auto', undefined)).toBe('both')
  })
})

describe('performance labels', () => {
  it('formats role and style labels', () => {
    expect(performanceRoleLabel(profile({ part_role: 'rhythm' }))).toBe('Rhythm')
    expect(performanceStyleLabel(profile({ playing_style: 'fingerpicked_arpeggiated' }))).toBe(
      'Fingerpicked',
    )
    expect(performanceRoleLabel(null)).toBeNull()
  })
})
