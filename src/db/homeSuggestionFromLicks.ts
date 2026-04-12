import type { HomeSuggestion, LickRow } from '@/src/db/types'

/** When there is no session-based suggestion, promote saved Review licks on Home. */
export function tryLibraryHomeSuggestion(licks: LickRow[]): Extract<HomeSuggestion, { kind: 'library_saved' }> | null {
  if (licks.length === 0) return null
  const latest = licks.reduce((a, b) => (a.date_saved >= b.date_saved ? a : b))
  return {
    kind: 'library_saved',
    lickCount: licks.length,
    latest: {
      id: latest.id,
      song_title: latest.song_title,
      artist: latest.artist,
      position: latest.position,
      coach_oneliner: latest.coach_oneliner,
      date_saved: latest.date_saved,
    },
  }
}
