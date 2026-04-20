import { create } from 'zustand'

export type VoiceGenderPref = 'default' | 'female' | 'male'

export interface VoiceCoachPrefsState {
  enabled: boolean
  rate: number
  gender: VoiceGenderPref
  setAll: (patch: Partial<Pick<VoiceCoachPrefsState, 'enabled' | 'rate' | 'gender'>>) => void
}

export const useVoiceCoachPrefsStore = create<VoiceCoachPrefsState>((set) => ({
  enabled: true,
  rate: 1,
  gender: 'default',
  setAll: (patch) => set((s) => ({ ...s, ...patch })),
}))
