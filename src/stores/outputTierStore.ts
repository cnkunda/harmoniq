import { create } from 'zustand'

import { getAppPref, setAppPref } from '@/src/db/client'
import { PREF_EXPERIENCE_LEVEL, PREF_OUTPUT_TIER } from '@/src/db/schema'
import {
  DEFAULT_OUTPUT_TIER,
  parseOutputTier,
  tierForExperienceLevel,
  type OutputTier,
} from '@/src/preferences/outputTier'

export type OutputTierState = {
  tier: OutputTier
  hydrated: boolean
  /** Load `output_tier`; if unset, derive from `experience_level` (and persist that derivation). */
  hydrate: () => Promise<void>
  setTier: (tier: OutputTier) => Promise<void>
}

export const useOutputTierStore = create<OutputTierState>((set) => ({
  tier: DEFAULT_OUTPUT_TIER,
  hydrated: false,

  hydrate: async () => {
    const [storedRaw, experienceRaw] = await Promise.all([
      getAppPref(PREF_OUTPUT_TIER),
      getAppPref(PREF_EXPERIENCE_LEVEL),
    ])

    const stored = parseOutputTier(storedRaw)
    if (stored) {
      set({ tier: stored, hydrated: true })
      return
    }

    const derived = tierForExperienceLevel(experienceRaw)
    if (!derived) {
      // No experience level yet (pre-onboarding): keep the in-memory default without
      // persisting, so the taste quiz can still auto-detect on its first completion.
      set({ tier: DEFAULT_OUTPUT_TIER, hydrated: true })
      return
    }

    await setAppPref(PREF_OUTPUT_TIER, derived)
    set({ tier: derived, hydrated: true })
  },

  setTier: async (tier) => {
    await setAppPref(PREF_OUTPUT_TIER, tier)
    set({ tier, hydrated: true })
  },
}))
