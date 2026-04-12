import type { LickRow } from '@/src/db/types'
import type { LessonJSON } from '@/src/types'

/** Build in-memory lesson payload for drilling a saved lick (Library + Home “Continue”). */
export function lessonFromSavedLick(lick: LickRow, transposeSemitones = 0): LessonJSON {
  return {
    job_id: `lick-${lick.id}`,
    song_title: lick.song_title ?? 'Saved lick',
    artist: lick.artist ?? undefined,
    key: lick.key ?? undefined,
    stems: {},
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
