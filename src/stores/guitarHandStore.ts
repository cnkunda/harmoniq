import { create } from 'zustand'

import { getAppPref, setAppPref } from '@/src/db/client'
import { PREF_GUITAR_HAND } from '@/src/db/schema'
import {
  DEFAULT_GUITAR_HAND,
  parseGuitarHand,
  type GuitarHand,
} from '@/src/preferences/guitarHand'

/**
 * Commit 168: global playing-hand preference. Hydrated once at app start so
 * every mounted fretboard and chord diagram re-renders in the chosen mirror.
 */
export type GuitarHandState = {
  hand: GuitarHand
  hydrated: boolean
  hydrate: () => Promise<void>
  setHand: (hand: GuitarHand) => Promise<void>
}

export const useGuitarHandStore = create<GuitarHandState>((set) => ({
  hand: DEFAULT_GUITAR_HAND,
  hydrated: false,

  hydrate: async () => {
    const raw = await getAppPref(PREF_GUITAR_HAND)
    set({ hand: parseGuitarHand(raw) ?? DEFAULT_GUITAR_HAND, hydrated: true })
  },

  setHand: async (hand) => {
    await setAppPref(PREF_GUITAR_HAND, hand)
    set({ hand, hydrated: true })
  },
}))
