import { create } from 'zustand'

import type { ScoreResult } from '@/src/types'

type OnboardingPlacementState = {
  results: [ScoreResult | null, ScoreResult | null, ScoreResult | null]
  setPhraseResult: (index: number, result: ScoreResult) => void
  reset: () => void
}

const tripleNull = (): [ScoreResult | null, ScoreResult | null, ScoreResult | null] => [null, null, null]

export const useOnboardingPlacementStore = create<OnboardingPlacementState>((set) => ({
  results: tripleNull(),
  setPhraseResult: (index, result) =>
    set((s) => {
      if (index < 0 || index > 2) return s
      const next: [ScoreResult | null, ScoreResult | null, ScoreResult | null] = [
        s.results[0],
        s.results[1],
        s.results[2],
      ]
      next[index] = result
      return { results: next }
    }),
  reset: () => set({ results: tripleNull() }),
}))
