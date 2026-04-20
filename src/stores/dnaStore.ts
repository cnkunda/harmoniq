import { create } from 'zustand'

import { computePlayerDNA, type PlayerDNA } from '@/src/music/dnaComputer'
import { getLicks, listJamSnapshots, listSessionsArchive } from '@/src/db/client'

type DnaState = {
  dna: PlayerDNA | null
  loaded: boolean
  refresh: () => Promise<void>
}

export const useDnaStore = create<DnaState>((set) => ({
  dna: null,
  loaded: false,
  refresh: async () => {
    const [sessions, jams, licks] = await Promise.all([listSessionsArchive(), listJamSnapshots(), getLicks()])
    const dna = computePlayerDNA({
      sessions: sessions.map((s) => ({
        date: s.date,
        review_snapshot: s.review_snapshot ?? null,
        nodes_targeted: s.nodes_targeted,
      })),
      jams: jams.map((j) => ({
        date: j.date,
        pitch_class_weight_map: j.pitch_class_weight_map,
        position_weight_map: j.position_weight_map,
        recurring_gestures: j.recurring_gestures,
      })),
      licks: licks.map((l) => ({
        date_saved: l.date_saved,
        position: l.position,
        technique_tags: l.technique_tags,
      })),
    })
    set({ dna, loaded: true })
  },
}))
