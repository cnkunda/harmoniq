import type { SkillNodeRow } from '@/src/db/types'

/** Commit 71: surface pulse when a node has enough history and remains under 50% accuracy. */
export function pickWeakAreaPulseNode(nodes: readonly SkillNodeRow[]): SkillNodeRow | null {
  const candidates = nodes.filter((n) => n.sessions_count > 2 && n.score < 0.5)
  if (candidates.length === 0) return null
  return [...candidates].sort((a, b) => a.score - b.score || a.sessions_count - b.sessions_count)[0] ?? null
}
