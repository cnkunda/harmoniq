import { describe, it, expect } from 'vitest'
import {
  SCALE_DB,
  getScale,
  getScalesByFamily,
  getScalePitchClasses,
  getScalePitchClassesFromKey,
  matchScaleToPitchClasses,
} from './scales'

describe('SCALE_DB structural integrity', () => {
  it('contains 33 scales', () => {
    const keys = Object.keys(SCALE_DB)
    expect(keys.length).toBe(33)
  })

  it('every scale has valid intervals (starts with 0, strictly increasing, all < 12)', () => {
    for (const [key, entry] of Object.entries(SCALE_DB)) {
      expect(entry.intervals[0]).toBe(0)
      for (let i = 1; i < entry.intervals.length; i++) {
        expect(entry.intervals[i]).toBeGreaterThan(entry.intervals[i - 1])
        expect(entry.intervals[i]).toBeLessThan(12)
      }
    }
  })

  it('every scale has pitchClasses matching intervals for root=0', () => {
    for (const [key, entry] of Object.entries(SCALE_DB)) {
      expect(entry.pitchClasses).toEqual(entry.intervals)
    }
  })

  it('every scale has a valid family', () => {
    const validFamilies = ['diatonic', 'harmonic_minor', 'melodic_minor', 'pentatonic', 'blues', 'symmetrical', 'other']
    for (const entry of Object.values(SCALE_DB)) {
      expect(validFamilies).toContain(entry.family)
    }
  })
})

describe('getScale', () => {
  it('returns correct entry for known scale', () => {
    const s = getScale('ionian')
    expect(s).toBeDefined()
    expect(s!.name).toBe('Ionian')
    expect(s!.intervals).toEqual([0, 2, 4, 5, 7, 9, 11])
  })

  it('returns undefined for unknown scale', () => {
    expect(getScale('nonexistent')).toBeUndefined()
  })
})

describe('getScalesByFamily', () => {
  it('returns 7 diatonic modes', () => {
    expect(getScalesByFamily('diatonic').length).toBe(7)
  })

  it('returns 7 harmonic minor modes', () => {
    expect(getScalesByFamily('harmonic_minor').length).toBe(7)
  })

  it('returns 7 melodic minor modes', () => {
    expect(getScalesByFamily('melodic_minor').length).toBe(7)
  })

  it('returns 3 pentatonic scales', () => {
    expect(getScalesByFamily('pentatonic').length).toBe(3)
  })

  it('returns 2 blues scales', () => {
    expect(getScalesByFamily('blues').length).toBe(2)
  })

  it('returns 4 symmetrical scales', () => {
    expect(getScalesByFamily('symmetrical').length).toBe(4)
  })

  it('returns 3 other scales', () => {
    expect(getScalesByFamily('other').length).toBe(3)
  })
})

describe('getScalePitchClasses', () => {
  it('returns correct pitch classes for C Ionian (C major)', () => {
    const pcs = getScalePitchClasses(0, 'ionian')
    expect(pcs).toEqual([0, 2, 4, 5, 7, 9, 11])
  })

  it('transposes correctly for D Dorian', () => {
    const pcs = getScalePitchClasses(2, 'dorian')
    expect(pcs).toEqual([2, 4, 5, 7, 9, 11, 0])
  })

  it('returns null for unknown scale', () => {
    expect(getScalePitchClasses(0, 'nonexistent')).toBeNull()
  })
})

describe('getScalePitchClassesFromKey', () => {
  it('returns Ionian pitch classes for C major', () => {
    const pcs = getScalePitchClassesFromKey('C major')
    expect(pcs).toEqual([0, 2, 4, 5, 7, 9, 11])
  })

  it('returns Aeolian pitch classes for A minor', () => {
    const pcs = getScalePitchClassesFromKey('A minor')
    expect(pcs).toEqual([9, 11, 0, 2, 4, 5, 7])
  })

  it('transposes correctly for G major', () => {
    const pcs = getScalePitchClassesFromKey('G major')
    expect(pcs).toEqual([7, 9, 11, 0, 2, 4, 6])
  })

  it('returns null for invalid key', () => {
    expect(getScalePitchClassesFromKey('invalid')).toBeNull()
  })

  it('returns null for empty key', () => {
    expect(getScalePitchClassesFromKey('')).toBeNull()
  })
})

describe('matchScaleToPitchClasses', () => {
  it('returns top-3 candidates sorted by score', () => {
    const result = matchScaleToPitchClasses([0, 2, 4, 5, 7, 9, 11])
    expect(result.length).toBe(3)
    expect(result[0].score).toBeGreaterThanOrEqual(result[1].score)
    expect(result[1].score).toBeGreaterThanOrEqual(result[2].score)
  })

  it('returns ionian as top match for C major pitch classes', () => {
    const result = matchScaleToPitchClasses([0, 2, 4, 5, 7, 9, 11])
    expect(result[0].name).toBe('ionian')
  })

  it('returns empty array for empty input', () => {
    expect(matchScaleToPitchClasses([])).toEqual([])
  })

  it('returns empty array for all-invalid pitch classes', () => {
    expect(matchScaleToPitchClasses([-1, 99])).toEqual([])
  })

  it('with rootPitchClass, ranks D dorian higher than C ionian for D-centered PCs', () => {
    // D dorian intervals transposed to D = full C major PC set
    // With rootPitchClass=2 (D), dorian should beat ionian because its pattern aligns
    const result = matchScaleToPitchClasses([0, 2, 4, 5, 7, 9, 11], 2)
    expect(result[0].name).toBe('dorian')
  })
})

describe('Diatonic mode correctness', () => {
  it('Ionian (C major): C D E F G A B', () => {
    const s = getScale('ionian')
    expect(s!.intervals).toEqual([0, 2, 4, 5, 7, 9, 11])
  })

  it('Dorian: C D Eb F G A Bb', () => {
    const s = getScale('dorian')
    expect(s!.intervals).toEqual([0, 2, 3, 5, 7, 9, 10])
  })

  it('Phrygian: C Db Eb F G Ab Bb', () => {
    const s = getScale('phrygian')
    expect(s!.intervals).toEqual([0, 1, 3, 5, 7, 8, 10])
  })

  it('Lydian: C D E F# G A B', () => {
    const s = getScale('lydian')
    expect(s!.intervals).toEqual([0, 2, 4, 6, 7, 9, 11])
  })

  it('Mixolydian: C D E F G A Bb', () => {
    const s = getScale('mixolydian')
    expect(s!.intervals).toEqual([0, 2, 4, 5, 7, 9, 10])
  })

  it('Aeolian: C D Eb F G Ab Bb', () => {
    const s = getScale('aeolian')
    expect(s!.intervals).toEqual([0, 2, 3, 5, 7, 8, 10])
  })

  it('Locrian: C Db Eb F Gb Ab Bb', () => {
    const s = getScale('locrian')
    expect(s!.intervals).toEqual([0, 1, 3, 5, 6, 8, 10])
  })
})

describe('Harmonic minor mode correctness', () => {
  it('Harmonic Minor: C D Eb F G Ab B', () => {
    const s = getScale('harmonic_minor')
    expect(s!.intervals).toEqual([0, 2, 3, 5, 7, 8, 11])
  })

  it('Phrygian Dominant: C Db E F G Ab Bb', () => {
    const s = getScale('phrygian_dominant')
    expect(s!.intervals).toEqual([0, 1, 4, 5, 7, 8, 10])
  })
})

describe('Melodic minor mode correctness', () => {
  it('Melodic Minor: C D Eb F G A B', () => {
    const s = getScale('melodic_minor')
    expect(s!.intervals).toEqual([0, 2, 3, 5, 7, 9, 11])
  })

  it('Altered: C Db Eb E Gb Ab Bb', () => {
    const s = getScale('altered')
    expect(s!.intervals).toEqual([0, 1, 3, 4, 6, 8, 10])
  })
})

describe('Pentatonic and blues correctness', () => {
  it('Major Pentatonic: C D E G A', () => {
    const s = getScale('major_pentatonic')
    expect(s!.intervals).toEqual([0, 2, 4, 7, 9])
  })

  it('Minor Pentatonic: C Eb F G Bb', () => {
    const s = getScale('minor_pentatonic')
    expect(s!.intervals).toEqual([0, 3, 5, 7, 10])
  })

  it('Blues (Major): C D Eb E G A', () => {
    const s = getScale('blues_major')
    expect(s!.intervals).toEqual([0, 2, 3, 4, 7, 9])
  })

  it('Blues (Minor): C Eb F F# G Bb', () => {
    const s = getScale('blues_minor')
    expect(s!.intervals).toEqual([0, 3, 5, 6, 7, 10])
  })

  it('Egyptian: C D F G A', () => {
    const s = getScale('egyptian')
    expect(s!.intervals).toEqual([0, 2, 5, 7, 9])
  })
})

describe('Symmetrical scale correctness', () => {
  it('Whole Tone: C D E F# G# A#', () => {
    const s = getScale('whole_tone')
    expect(s!.intervals).toEqual([0, 2, 4, 6, 8, 10])
  })

  it('Diminished (Half-Whole): 8 notes', () => {
    const s = getScale('diminished_half_whole')
    expect(s!.intervals).toEqual([0, 1, 3, 4, 6, 7, 9, 10])
  })

  it('Diminished (Whole-Half): 8 notes', () => {
    const s = getScale('diminished_whole_half')
    expect(s!.intervals).toEqual([0, 2, 3, 5, 6, 8, 9, 11])
  })

  it('Augmented: C Eb E G G# B', () => {
    const s = getScale('augmented_scale')
    expect(s!.intervals).toEqual([0, 3, 4, 7, 8, 11])
  })
})

describe('Other scale correctness', () => {
  it('Chromatic: all 12 pitch classes', () => {
    const s = getScale('chromatic')
    expect(s!.intervals).toEqual([0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11])
  })

  it('Bebop Dominant: C D E F G A Bb B', () => {
    const s = getScale('bebop_dominant')
    expect(s!.intervals).toEqual([0, 2, 4, 5, 7, 9, 10, 11])
  })

  it('Bebop Major: C D E F G G# A B', () => {
    const s = getScale('bebop_major')
    expect(s!.intervals).toEqual([0, 2, 4, 5, 7, 8, 9, 11])
  })
})


