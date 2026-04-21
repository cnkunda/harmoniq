import type { JamSnapshotRow, PracticePlanCompletionRow, SessionJournalRow } from '@/src/db/types'

export type ProgressTimelineItem =
  | { kind: 'review_score'; sortKey: string; tie: string; session: SessionJournalRow }
  | { kind: 'jam_snapshot'; sortKey: string; tie: string; jam: JamSnapshotRow }
  | { kind: 'plan_complete'; sortKey: string; tie: string; completion: PracticePlanCompletionRow }

function compareTimeline(a: ProgressTimelineItem, b: ProgressTimelineItem): number {
  if (a.sortKey !== b.sortKey) return a.sortKey < b.sortKey ? 1 : -1
  return a.tie < b.tie ? 1 : a.tie > b.tie ? -1 : 0
}

/** Newest-first merged history for Progress (review sessions, saved jams, plan completions). */
export function mergeProgressTimeline(
  sessions: SessionJournalRow[],
  jams: JamSnapshotRow[],
  completions: PracticePlanCompletionRow[],
): ProgressTimelineItem[] {
  const items: ProgressTimelineItem[] = [
    ...sessions.map((session) => ({
      kind: 'review_score' as const,
      sortKey: session.date,
      tie: session.id,
      session,
    })),
    ...jams.map((jam) => ({
      kind: 'jam_snapshot' as const,
      sortKey: jam.date,
      tie: jam.id,
      jam,
    })),
    ...completions.map((completion) => ({
      kind: 'plan_complete' as const,
      sortKey: completion.completed_at,
      tie: completion.id,
      completion,
    })),
  ]
  return items.sort(compareTimeline)
}
