import { create } from 'zustand'

import type { ChordDetection, ChordDetectorState, ChordDetectorStatus } from '@/src/chord/chordModelTypes'
import { MAX_HISTORY } from '@/src/chord/chordModelTypes'

type LiveChordState = ChordDetectorState & {
  setListening: (v: boolean) => void
  setStatus: (s: ChordDetectorStatus) => void
  setCurrentChord: (d: ChordDetection) => void
  setError: (e: string | null) => void
  setLatency: (ms: number) => void
  setModelType: (t: 'tflite' | 'onnx' | null) => void
  reset: () => void
}

const INITIAL: ChordDetectorState = {
  isListening: false,
  status: 'idle',
  currentChord: null,
  history: [],
  latencyMs: 0,
  error: null,
  modelType: null,
}

export const useLiveChordStore = create<LiveChordState>((set) => ({
  ...INITIAL,

  setListening: (isListening) => set({ isListening }),

  setStatus: (status) => set({ status }),

  setCurrentChord: (d) =>
    set((state) => {
      // Dedupe history: only record a new entry when the chord label actually
      // changes, so the stream reads as a progression instead of N repeats.
      const prev = state.history[0]
      const isNewChord = !prev || prev.chord !== d.chord
      return {
        currentChord: d,
        history: isNewChord ? [d, ...state.history].slice(0, MAX_HISTORY) : state.history,
        latencyMs: d.latencyMs,
      }
    }),

  setError: (error) => set({ error }),

  setLatency: (latencyMs) => set({ latencyMs }),

  setModelType: (modelType) => set({ modelType }),

  reset: () => set(INITIAL),
}))
