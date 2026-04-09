import { create } from 'zustand'

import type { RecordedTake } from '@/src/audio/recordSession.types'

type SessionPlayState = {
  latestTake: RecordedTake | null
  setLatestTake: (take: RecordedTake | null) => void
  clearLatestTake: () => void
}

export const useSessionPlayStore = create<SessionPlayState>((set) => ({
  latestTake: null,
  setLatestTake: (take) => set({ latestTake: take }),
  clearLatestTake: () => set({ latestTake: null }),
}))
