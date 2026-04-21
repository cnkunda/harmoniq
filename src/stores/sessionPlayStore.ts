import { create } from 'zustand'

import type { RecordedTake } from '@/src/audio/recordSession.types'

type SessionPlayState = {
  latestTake: RecordedTake | null
  setLatestTake: (take: RecordedTake | null) => void
  clearLatestTake: () => void
  /** Commit 75: song-timeline position (sec) when the most recent take’s capture started. */
  lastTakeAnchorSec: number | null
  setLastTakeAnchorSec: (sec: number | null) => void
  /** User asked to save the last take as a ghost reference (cleared after Review persist). */
  pendingGhostReference: boolean
  setPendingGhostReference: (v: boolean) => void
}

export const useSessionPlayStore = create<SessionPlayState>((set) => ({
  latestTake: null,
  setLatestTake: (take) => set({ latestTake: take }),
  clearLatestTake: () => set({ latestTake: null }),
  lastTakeAnchorSec: null,
  setLastTakeAnchorSec: (sec) => set({ lastTakeAnchorSec: sec }),
  pendingGhostReference: false,
  setPendingGhostReference: (v) => set({ pendingGhostReference: v }),
}))
