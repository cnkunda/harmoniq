import type { JamSnapshotRow, LickRow, SessionJournalRow, SkillNodeRow } from '@/src/db/types'

export function formatJournalPlainText(input: {
  exportedAt: string
  sessions: SessionJournalRow[]
  licks: LickRow[]
  jams: JamSnapshotRow[]
  skills: SkillNodeRow[]
}): string {
  const lines: string[] = []
  lines.push('Harmoniq — local practice journal export')
  lines.push(`Exported: ${input.exportedAt}`)
  lines.push('')
  lines.push('=== Skill nodes ===')
  for (const n of input.skills) {
    lines.push(
      `- ${n.label ?? n.id}: score ${(n.score * 100).toFixed(0)}% · sessions ${n.sessions_count} · next review ${n.next_review_date ?? '—'}`,
    )
  }
  lines.push('')
  lines.push('=== Sessions (newest first) ===')
  if (input.sessions.length === 0) lines.push('(none)')
  else {
    for (const s of input.sessions) {
      const title = [s.song_title, s.artist].filter(Boolean).join(' · ') || 'Practice'
      lines.push(`- ${s.date} · ${title}`)
      if (s.section_label) lines.push(`  section: ${s.section_label}`)
      if (s.coach_review) lines.push(`  coach: ${s.coach_review}`)
      if (s.pitch_accuracy != null) lines.push(`  pitch: ${(s.pitch_accuracy * 100).toFixed(0)}%`)
      if (s.phrasing_score != null) lines.push(`  phrasing: ${(s.phrasing_score * 100).toFixed(0)}%`)
    }
  }
  lines.push('')
  lines.push('=== Library licks ===')
  if (input.licks.length === 0) lines.push('(none)')
  else {
    for (const l of input.licks) {
      lines.push(`- ${l.date_saved} · ${l.song_title ?? 'Lick'} · ${l.key ?? ''} · ${l.position ?? ''}`)
      if (l.coach_oneliner) lines.push(`  note: ${l.coach_oneliner}`)
    }
  }
  lines.push('')
  lines.push('=== Jam snapshots ===')
  if (input.jams.length === 0) lines.push('(none)')
  else {
    for (const j of input.jams) {
      lines.push(`- ${j.date} · ${j.duration_seconds}s`)
      lines.push(`  ${j.coach_summary.replace(/\s+/g, ' ').trim()}`)
      const keys = Object.keys(j.scale_position_map)
      if (keys.length > 0) {
        lines.push(`  map: ${keys.slice(0, 8).join(', ')}${keys.length > 8 ? '…' : ''}`)
      }
    }
  }
  lines.push('')
  lines.push('End of export.')
  return lines.join('\n')
}
