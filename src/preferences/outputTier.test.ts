import { describe, expect, it } from 'vitest'

import {
  DEFAULT_OUTPUT_TIER,
  OUTPUT_TIERS,
  parseOutputTier,
  tierForExperienceLevel,
} from '@/src/preferences/outputTier'

describe('outputTier preferences', () => {
  it('exposes the three personas with Intermediate as the default', () => {
    expect(OUTPUT_TIERS).toEqual(['learner', 'intermediate', 'transcriber'])
    expect(DEFAULT_OUTPUT_TIER).toBe('intermediate')
  })

  it('parses stored values case-insensitively and rejects unknown values', () => {
    expect(parseOutputTier('learner')).toBe('learner')
    expect(parseOutputTier(' Transcriber ')).toBe('transcriber')
    expect(parseOutputTier('expert')).toBeNull()
    expect(parseOutputTier(null)).toBeNull()
  })

  it('maps experience levels to tiers', () => {
    expect(tierForExperienceLevel('beginner')).toBe('learner')
    expect(tierForExperienceLevel('intermediate')).toBe('intermediate')
    expect(tierForExperienceLevel('advanced')).toBe('transcriber')
    expect(tierForExperienceLevel('unknown')).toBeNull()
    expect(tierForExperienceLevel(null)).toBeNull()
  })
})
