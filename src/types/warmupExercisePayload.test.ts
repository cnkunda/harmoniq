import { describe, expect, it } from 'vitest'

import type { WarmupExercisePayload } from '@/src/types'

describe('WarmupExercisePayload fretboard_guide', () => {
  it('accepts pool-shaped fretboard_guide for API hydration', () => {
    const ex: WarmupExercisePayload = {
      name: 'Single-string chromatic pairs',
      description: 'On one string…',
      duration_seconds: 56,
      technique_tag: 'timing',
      bpm: 72,
      fretboard_guide: {
        cells: [
          { string: 3, fret: 5, variant: 'primary' },
          { string: 3, fret: 6, variant: 'secondary' },
        ],
        caption: 'First chromatic pair on the G string.',
      },
    }
    expect(ex.fretboard_guide?.cells).toHaveLength(2)
    expect(ex.fretboard_guide?.cells[1]?.variant).toBe('secondary')
    expect(ex.fretboard_guide?.caption).toContain('G string')
  })
})
