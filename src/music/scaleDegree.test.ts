import { describe, expect, it } from 'vitest'

import { midiToNoteName, scaleDegreeLabel } from './scaleDegree'

describe('scaleDegreeLabel — major', () => {
  it('tonic and common degrees in C major', () => {
    expect(scaleDegreeLabel('C major', 60)).toContain('tonic')
    expect(scaleDegreeLabel('C major', 64)).toContain('3')
    expect(scaleDegreeLabel('C major', 67)).toContain('5')
  })

  it('flat-seven blues colour in major', () => {
    const bb = 58
    expect(scaleDegreeLabel('C major', bb)).toMatch(/b7|flat seventh|blues/i)
  })
})

describe('scaleDegreeLabel — minor / blues b7', () => {
  it('A minor: G is flat-seven colour', () => {
    expect(scaleDegreeLabel('A minor', 55)).toMatch(/b7|flat-seven|blues/i)
  })
})

describe('midiToNoteName', () => {
  it('names middle C', () => {
    expect(midiToNoteName(60)).toBe('C4')
  })
})
