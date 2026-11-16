import { describe, expect, it } from 'vitest'

import { coachSourceLabel } from './coachSource'

describe('coachSourceLabel', () => {
  it('labels AI and template coach copy', () => {
    expect(coachSourceLabel('ai')).toBe('AI guidance')
    expect(coachSourceLabel('template')).toBe('Template guidance')
  })

  it('returns null when the source is unknown', () => {
    expect(coachSourceLabel(null)).toBeNull()
    expect(coachSourceLabel(undefined)).toBeNull()
  })
})
