import { DEFAULT_SKILL_NODES } from '@/src/db/schema'
import type { ReviewSkillUpdateInput, SessionInsertInput, SkillNodeRow } from '@/src/db/types'
import { deriveSkillNodeAfterSession } from '@/src/spaced/sm2'

let sessionCount = 0
const skillNodes = new Map<string, SkillNodeRow>()

function seedWebSkillNodes(): void {
  if (skillNodes.size > 0) return
  for (const n of DEFAULT_SKILL_NODES) {
    skillNodes.set(n.id, {
      id: n.id,
      label: n.label,
      score: 0,
      sessions_count: 0,
      last_session_date: null,
      easiness_factor: 2.5,
      interval_days: 1,
      next_review_date: null,
      sm2_repetitions: 0,
    })
  }
}

/** Commit 29/30: web has no SQLite; session counter + in-memory skill nodes keep APIs aligned. */
export async function initDb(): Promise<void> {
  seedWebSkillNodes()
}

export async function insertSessionRow(_input: SessionInsertInput): Promise<void> {
  sessionCount += 1
}

export async function getSessionCount(): Promise<number> {
  return sessionCount
}

export async function getAllSkillNodes(): Promise<SkillNodeRow[]> {
  seedWebSkillNodes()
  return Array.from(skillNodes.values()).sort((a, b) => a.id.localeCompare(b.id))
}

export async function applyReviewSkillUpdates(input: ReviewSkillUpdateInput): Promise<void> {
  seedWebSkillNodes()
  for (const id of input.targeted_node_ids) {
    const row = skillNodes.get(id)
    if (!row) continue
    const sessionScore = input.node_scores[id]
    if (typeof sessionScore !== 'number' || !Number.isFinite(sessionScore)) continue
    const u = deriveSkillNodeAfterSession(
      {
        score: row.score,
        easiness_factor: row.easiness_factor,
        interval_days: row.interval_days,
        sm2_repetitions: row.sm2_repetitions,
        sessions_count: row.sessions_count,
      },
      sessionScore,
    )
    skillNodes.set(id, {
      ...row,
      score: u.score,
      easiness_factor: u.easiness_factor,
      interval_days: u.interval_days,
      sm2_repetitions: u.sm2_repetitions,
      next_review_date: u.next_review_date,
      sessions_count: u.sessions_count,
      last_session_date: u.last_session_date,
    })
  }
}
