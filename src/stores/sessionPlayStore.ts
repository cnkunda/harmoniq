import { create } from 'zustand'

import type { RecordedTake } from '@/src/audio/recordSession.types'

type SessionPlayState = {
  latestTake: RecordedTake | null
  /** Commit 164: stable id for the latest capture (replay-safe mastery key). */
  latestTakeId: string | null
  setLatestTake: (take: RecordedTake | null, id?: string | null) => void
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
  latestTakeId: null,
  setLatestTake: (take, id = null) => set({ latestTake: take, latestTakeId: take ? id : null }),
  clearLatestTake: () => set({ latestTake: null, latestTakeId: null }),
  lastTakeAnchorSec: null,
  setLastTakeAnchorSec: (sec) => set({ lastTakeAnchorSec: sec }),
  pendingGhostReference: false,
  setPendingGhostReference: (v) => set({ pendingGhostReference: v }),
}))
