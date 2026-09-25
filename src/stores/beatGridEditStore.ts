/** Commit 109: Beat grid edit history with undo/redo. */

import { create } from 'zustand'

import type { BeatGridRecomputeResponse } from '@/src/types'

export interface BeatGridOverride {
  time_signature?: string
  bpm_override?: number
}

interface BeatGridEditState {
  /** Stack of overrides applied during this session. */
  history: BeatGridOverride[]
  /** Pointer into history (-1 = no edits yet). */
  currentIndex: number
  /** Whether a recompute is currently in-flight. */
  isRecomputing: boolean
  /** Latest recompute response from the backend. */
  recomputeResult: BeatGridRecomputeResponse | null

  /** Push a new override onto the history stack (discards any redo states). */
  pushOverride: (override: BeatGridOverride) => void
  /** Undo: move pointer back one step. Returns the override to re-apply, or null. */
  undo: () => BeatGridOverride | null
  /** Redo: move pointer forward one step. Returns the override to re-apply, or null. */
  redo: () => BeatGridOverride | null
  /** Whether undo is available (pointer > 0). */
  canUndo: () => boolean
  /** Whether redo is available (pointer < history.length - 1). */
  canRedo: () => boolean
  /** Set recomputing state. */
  setRecomputing: (recomputing: boolean) => void
  /** Set recompute result from backend. */
  setRecomputeResult: (result: BeatGridRecomputeResponse | null) => void
  /** Reset to initial state (e.g. when lesson changes). */
  reset: () => void
}

export const useBeatGridEditStore = create<BeatGridEditState>((set, get) => ({
  history: [],
  currentIndex: -1,
  isRecomputing: false,
  recomputeResult: null,

  pushOverride: (override) => {
    const { history, currentIndex } = get()
    // Discard any redo states after current pointer
    const trimmed = history.slice(0, currentIndex + 1)
    set({
      history: [...trimmed, override],
      currentIndex: trimmed.length,
    })
  },

  undo: () => {
    const { history, currentIndex } = get()
    if (currentIndex <= 0) return null
    const newIndex = currentIndex - 1
    set({ currentIndex: newIndex })
    return history[newIndex]
  },

  redo: () => {
    const { history, currentIndex } = get()
    if (currentIndex >= history.length - 1) return null
    const newIndex = currentIndex + 1
    set({ currentIndex: newIndex })
    return history[newIndex]
  },

  canUndo: () => get().currentIndex > 0,
  canRedo: () => get().currentIndex < get().history.length - 1,

  setRecomputing: (recomputing) => set({ isRecomputing: recomputing }),
  setRecomputeResult: (result) => set({ recomputeResult: result }),

  reset: () =>
    set({
      history: [],
      currentIndex: -1,
      isRecomputing: false,
      recomputeResult: null,
    }),
}))
