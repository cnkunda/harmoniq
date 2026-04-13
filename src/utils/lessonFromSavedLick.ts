import type { LickRow } from '@/src/db/types'
import type { LessonJSON } from '@/src/types'

function stemsRecordFromLick(lick: LickRow): Record<string, string> {
  const raw = lick.stems_json?.trim()
  if (raw) {
    try {
      const o = JSON.parse(raw) as unknown
      if (o && typeof o === 'object' && !Array.isArray(o)) {
        const out: Record<string, string> = {}
        for (const [k, v] of Object.entries(o as Record<string, unknown>)) {
          if (typeof v === 'string' && v.trim()) out[k] = v.trim()
        }
        if (Object.keys(out).length > 0) return out
      }
    } catch {
      /* fall through to legacy */
    }
  }
  const trimmed = lick.audio_segment_path?.trim() ?? ''
  return trimmed ? { guitar: trimmed } : {}
}

/** Build in-memory lesson payload for drilling a saved lick (Library + Home “Continue”). */
export function lessonFromSavedLick(lick: LickRow, transposeSemitones = 0): LessonJSON {
  const stems = stemsRecordFromLick(lick)

  return {
    job_id: `lick-${lick.id}`,
    song_title: lick.song_title ?? 'Saved lick',
    artist: lick.artist ?? undefined,
    key: lick.key ?? undefined,
    stems,
    beat_grid: [],
    bar_timestamps: [],
    lyrics_aligned: [],
    sections: [
      {
        label: lick.position ?? 'Lick',
        primary_position: lick.position ?? undefined,
        tab_full_gp5_base64: lick.tab_gp5_base64,
        transposition_semitones: transposeSemitones,
      },
    ],
  }
}
