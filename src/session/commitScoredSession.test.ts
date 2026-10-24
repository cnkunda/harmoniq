import { beforeEach, describe, expect, it } from 'vitest'

import {
  clearAllPracticeData,
  commitScoredSession,
  getAllSkillNodes,
  getSessionCount,
} from '@/src/db/client'
import type { CommitScoredSessionInput } from '@/src/db/types'

function makeInput(id: string): CommitScoredSessionInput {
  return {
    session: {
      id,
      song_title: 'Test Song',
      artist: 'Tester',
      section_label: 'Verse',
      date: new Date().toISOString(),
      coach_review: null,
      pitch_accuracy: 0.9,
      phrasing_score: 0.8,
      nodes_targeted: ['pitch_accuracy', 'phrasing', 'timing'],
      section_index: 0,
      is_ghost_reference: false,
    },
    reviewUpdates: {
      node_scores: { pitch_accuracy: 1, phrasing: 1, timing: 1 },
      targeted_node_ids: ['pitch_accuracy', 'phrasing', 'timing'],
      session_accuracy01: 1,
      session_timing_stability01: 1,
    },
    beats: [],
    section: null,
    applyTechniqueEma: false,
  }
}

async function pitchScore(): Promise<number> {
  const nodes = await getAllSkillNodes()
  return nodes.find((n) => n.id === 'pitch_accuracy')?.score ?? 0
}

describe('commitScoredSession', () => {
  beforeEach(async () => {
    await clearAllPracticeData()
  })

  it('applies mastery once and ignores a replay with the same session id', async () => {
    const before = await pitchScore()
    const first = await commitScoredSession(makeInput('session-1'))
    expect(first.applied).toBe(true)
    const afterFirst = await pitchScore()
    expect(afterFirst).toBeGreaterThan(before)
    expect(await getSessionCount()).toBe(1)

    const replay = await commitScoredSession(makeInput('session-1'))
    expect(replay.applied).toBe(false)
    expect(await pitchScore()).toBe(afterFirst)
    expect(await getSessionCount()).toBe(1)
  })

  it('applies a different session id again', async () => {
    await commitScoredSession(makeInput('session-1'))
    const afterFirst = await pitchScore()

    const second = await commitScoredSession(makeInput('session-2'))
    expect(second.applied).toBe(true)
    expect(await pitchScore()).toBeGreaterThan(afterFirst)
    expect(await getSessionCount()).toBe(2)
  })
})
