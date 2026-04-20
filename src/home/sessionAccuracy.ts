import type { SessionJournalRow } from '@/src/db/types'

/** Blend pitch + phrasing when both exist (commit 71 RecentProgress / overall trend). */
export function sessionOverallAccuracy(row: SessionJournalRow): number | null {
  const p = row.pitch_accuracy
  const ph = row.phrasing_score
  if (p != null && ph != null) return (Number(p) + Number(ph)) / 2
  if (p != null) return Number(p)
  if (ph != null) return Number(ph)
  return null
}
