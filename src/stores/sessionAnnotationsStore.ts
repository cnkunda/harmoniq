import { create } from 'zustand'

export type SessionAnnotation = {
  barIndex: number
  text: string
  updatedAt: number
}

type SessionAnnotationsState = {
  notesBySection: Record<string, Record<number, SessionAnnotation>>
  setNote: (sectionKey: string, barIndex: number, text: string) => void
  clearSection: (sectionKey: string) => void
}

export const useSessionAnnotationsStore = create<SessionAnnotationsState>((set) => ({
  notesBySection: {},

  setNote: (sectionKey, barIndex, text) =>
    set((state) => {
      const current = state.notesBySection[sectionKey] ?? {}
      return {
        notesBySection: {
          ...state.notesBySection,
          [sectionKey]: {
            ...current,
            [barIndex]: { barIndex, text, updatedAt: Date.now() },
          },
        },
      }
    }),

  clearSection: (sectionKey) =>
    set((state) => {
      const next = { ...state.notesBySection }
      delete next[sectionKey]
      return { notesBySection: next }
    }),
}))
