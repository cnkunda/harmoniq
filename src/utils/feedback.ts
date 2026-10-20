import type { FeedbackType, UserFeedbackRow, UserFeedbackStats } from '@/src/db/types'

export const FEEDBACK_TYPE_LABELS: Record<FeedbackType, string> = {
  chord_correction: 'Chord correction',
  note_correction: 'Note correction',
  wrong_chord: 'Wrong chord',
}

export type FeedbackValues = Record<string, unknown>

export type FeedbackCounts = {
  total: number
  chord_corrections: number
  note_corrections: number
  wrong_chords: number
}

export type LocalFeedbackExport = {
  exported_at: string
  user_id: string
  records: Array<{
    job_id: string
    song_id: string
    feedback_type: FeedbackType
    event_index: number
    original: FeedbackValues
    corrected: FeedbackValues | null
    reason: string | null
    timestamp: string
  }>
}

export function parseFeedbackValues(raw: string | null): FeedbackValues | null {
  if (!raw?.trim()) return null
  try {
    const parsed = JSON.parse(raw) as unknown
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return null
    return parsed as FeedbackValues
  } catch {
    return null
  }
}

function feedbackKey(row: UserFeedbackRow): string {
  return `${row.job_id}\u0000${row.feedback_type}\u0000${row.event_index}`
}

/** Latest record per (job, type, event), newest first. */
export function dedupeFeedbackRows(rows: UserFeedbackRow[]): UserFeedbackRow[] {
  const latest = new Map<string, UserFeedbackRow>()
  for (const row of rows) {
    const key = feedbackKey(row)
    const previous = latest.get(key)
    if (!previous || row.timestamp >= previous.timestamp) latest.set(key, row)
  }
  return [...latest.values()].sort((a, b) =>
    a.timestamp < b.timestamp ? 1 : a.timestamp > b.timestamp ? -1 : 0,
  )
}

export function summarizeFeedbackRows(rows: UserFeedbackRow[]): FeedbackCounts {
  let chord_corrections = 0
  let note_corrections = 0
  let wrong_chords = 0
  for (const row of rows) {
    if (row.feedback_type === 'chord_correction') chord_corrections += 1
    else if (row.feedback_type === 'note_correction') note_corrections += 1
    else wrong_chords += 1
  }
  return {
    total: rows.length,
    chord_corrections,
    note_corrections,
    wrong_chords,
  }
}

export function buildFeedbackStats(rows: UserFeedbackRow[]): UserFeedbackStats {
  const counts = summarizeFeedbackRows(rows)
  const chordCounts = new Map<string, number>()
  for (const row of rows) {
    if (row.feedback_type !== 'chord_correction') continue
    const corrected = parseFeedbackValues(row.corrected_value)
    const chord = corrected?.chord
    if (typeof chord !== 'string' || !chord.trim()) continue
    const key = chord.trim()
    chordCounts.set(key, (chordCounts.get(key) ?? 0) + 1)
  }
  const most_corrected_chords = [...chordCounts.entries()]
    .map(([chord, count]) => ({ chord, count }))
    .sort((a, b) => (b.count - a.count) || a.chord.localeCompare(b.chord))
    .slice(0, 3)
  return { ...counts, most_corrected_chords }
}

export function buildLocalFeedbackExport(
  rows: UserFeedbackRow[],
  userId: string,
  exportedAt: string = new Date().toISOString(),
): LocalFeedbackExport {
  return {
    exported_at: exportedAt,
    user_id: userId,
    records: dedupeFeedbackRows(rows).map((row) => ({
      job_id: row.job_id,
      song_id: row.song_id,
      feedback_type: row.feedback_type,
      event_index: row.event_index,
      original: parseFeedbackValues(row.original_value) ?? {},
      corrected: parseFeedbackValues(row.corrected_value),
      reason: row.reason,
      timestamp: row.timestamp,
    })),
  }
}

/** Match a tapped fretboard note to the closest transcribed solo note. */
export function findSoloNoteIndexForSelection(
  notes: ReadonlyArray<{ pitch: number; start_time: number }>,
  selection: { midi?: number | null; timeSec?: number | null },
): number {
  const midi = typeof selection.midi === 'number' && Number.isFinite(selection.midi) ? Math.round(selection.midi) : null
  if (midi == null) return -1
  const candidates = notes
    .map((note, index) => ({ note, index }))
    .filter(({ note }) => note.pitch === midi)
  if (candidates.length === 0) return -1

  const timeSec = typeof selection.timeSec === 'number' && Number.isFinite(selection.timeSec) ? selection.timeSec : null
  if (timeSec == null) return candidates[0]!.index

  let best = candidates[0]!
  let bestDistance = Math.abs(best.note.start_time - timeSec)
  for (const candidate of candidates.slice(1)) {
    const distance = Math.abs(candidate.note.start_time - timeSec)
    if (distance < bestDistance) {
      best = candidate
      bestDistance = distance
    }
  }
  return best.index
}
