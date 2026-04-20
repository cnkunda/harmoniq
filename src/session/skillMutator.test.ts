import { describe, expect, it } from 'vitest'

import {
  applySkillEma,
  appendRollingSessionScores,
  computeSkillMutations,
  extractTechniqueTagsFromSection,
  parseTechniqueRollJson,
  rollingSessionsWeak,
  sessionAccuracyFromBeats,
  SKILL_MUTATION_EMA_OLD,
  SKILL_MUTATION_EMA_SESSION,
  techniqueMarkerToSkillNodeId,
} from '@/src/session/skillMutator'

describe('techniqueMarkerToSkillNodeId', () => {
  it('maps bend variants to bend_accuracy', () => {
    expect(techniqueMarkerToSkillNodeId('bend')).toBe('bend_accuracy')
    expect(techniqueMarkerToSkillNodeId('bending')).toBe('bend_accuracy')
    expect(techniqueMarkerToSkillNodeId('alternate-picking')).toBe('timing')
    expect(techniqueMarkerToSkillNodeId('vibrato')).toBe('vibrato_control')
  })
})

describe('sessionAccuracyFromBeats', () => {
  it('computes miss-heavy sessions', () => {
    const beats = Array.from({ length: 10 }, () => 'miss' as const)
    expect(sessionAccuracyFromBeats(beats)).toBe(0)
    const mix = ['miss', 'miss', 'miss', 'miss', 'miss', 'miss', 'miss', 'hit', 'hit', 'hit'] as const
    expect(sessionAccuracyFromBeats([...mix])).toBeCloseTo(0.3, 5)
  })

  it('ignores ignored beats', () => {
    expect(sessionAccuracyFromBeats(['ignored', 'hit'])).toBe(1)
    expect(sessionAccuracyFromBeats(['ignored'])).toBeNull()
  })
})

describe('applySkillEma', () => {
  it('keeps strong nodes above 0.40 after one zero session', () => {
    const strong = 0.95
    const next = applySkillEma(strong, 0)
    expect(next).toBe(SKILL_MUTATION_EMA_OLD * strong + SKILL_MUTATION_EMA_SESSION * 0)
    expect(next).toBeGreaterThanOrEqual(0.4)
  })
})

describe('rolling weak flag', () => {
  it('requires three sessions below threshold mean', () => {
    expect(rollingSessionsWeak([0.4])).toBe(false)
    expect(rollingSessionsWeak([0.49, 0.49])).toBe(false)
    expect(rollingSessionsWeak([0.49, 0.49, 0.49])).toBe(true)
    expect(rollingSessionsWeak([0.6, 0.6, 0.6])).toBe(false)
  })
})

describe('computeSkillMutations', () => {
  it('updates bend_accuracy from bend-tagged section', () => {
    const nodes = new Map([
      ['bend_accuracy', { score: 0.9, technique_roll_json: null }],
      ['timing', { score: 0.8, technique_roll_json: null }],
    ])
    const beats = [...Array.from({ length: 7 }, () => 'miss' as const), ...Array.from({ length: 3 }, () => 'hit' as const)]
    const section = { technique_tags: ['bend'] }
    const updates = computeSkillMutations({ nodesById: nodes, beats, section })
    expect(updates).toHaveLength(1)
    expect(updates[0]!.id).toBe('bend_accuracy')
    expect(updates[0]!.score).toBeGreaterThan(0)
    expect(updates[0]!.score).toBeLessThan(0.9)
    expect(parseTechniqueRollJson(updates[0]!.technique_roll_json)).toHaveLength(1)
  })

  it('returns empty when section has no technique tags', () => {
    const nodes = new Map([['bend_accuracy', { score: 0.5, technique_roll_json: null }]])
    const updates = computeSkillMutations({
      nodesById: nodes,
      beats: ['hit'],
      section: {},
    })
    expect(updates).toEqual([])
  })
})

describe('appendRollingSessionScores', () => {
  it('retains last three scores', () => {
    const j = JSON.stringify([0.2, 0.3])
    const next = appendRollingSessionScores(j, 0.25)
    expect(next).toEqual([0.2, 0.3, 0.25])
    const next2 = appendRollingSessionScores(JSON.stringify(next), 0.1)
    expect(next2).toEqual([0.3, 0.25, 0.1])
  })
})

describe('extractTechniqueTagsFromSection', () => {
  it('reads technique_tags array', () => {
    expect(extractTechniqueTagsFromSection({ technique_tags: ['bend', 'slide'] })).toEqual(['bend', 'slide'])
  })
})
