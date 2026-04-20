import { JAM_REFERENCE_TAB_GP5_BASE64 } from '@/src/jam/jamReferenceTabGp5Base64'
import type { LessonJSON } from '@/src/types'

import { DEMO_LESSON_JOB_ID } from './constants'

/** GP5-backed practice lesson using bundled stems only (offline). */
export function getDemoLesson(): LessonJSON {
  return {
    job_id: DEMO_LESSON_JOB_ID,
    song_title: 'Reggae pocket (demo)',
    artist: 'Harmoniq',
    style_label: 'reggae',
    key: 'G major',
    tempo: 90,
    transcription_confidence: 0.85,
    bar_timestamps: [0],
    beat_grid: [],
    stems: {
      guitar: 'bundled://demo/reggae',
    },
    sections: [
      {
        label: 'Groove',
        start_time_seconds: 0,
        coach_note: 'This demo plays a short bundled WAV — no backend required.',
        coach_explanation: '',
        tab_full_gp5_base64: JAM_REFERENCE_TAB_GP5_BASE64,
      },
    ],
  }
}
