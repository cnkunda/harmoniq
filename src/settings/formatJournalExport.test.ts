import { describe, expect, it } from 'vitest'

import { formatJournalPlainText } from '@/src/settings/formatJournalExport'

describe('formatJournalPlainText', () => {
  it('includes header and sections', () => {
    const text = formatJournalPlainText({
      exportedAt: '2026-01-01T00:00:00Z',
      sessions: [
        {
          id: '1',
          song_title: 'Test',
          artist: null,
          section_label: 'Verse',
          date: '2026-01-02',
          coach_review: null,
          pitch_accuracy: 0.8,
          phrasing_score: 0.7,
          nodes_targeted: [],
          has_review_snapshot: false,
          waveform_user_path: null,
          waveform_ref_path: null,
        },
      ],
      licks: [],
      jams: [],
      skills: [
        {
          id: 'pitch_accuracy',
          label: 'Pitch',
          score: 0.5,
          sessions_count: 1,
          last_session_date: null,
          easiness_factor: 2.5,
          interval_days: 1,
          next_review_date: null,
          sm2_repetitions: 0,
        },
      ],
    })
    expect(text).toContain('Harmoniq')
    expect(text).toContain('Test')
    expect(text).toContain('Pitch')
    expect(text).toContain('End of export.')
  })
})
