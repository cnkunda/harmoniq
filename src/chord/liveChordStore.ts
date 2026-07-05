import { create } from 'zustand'

import type { ChordDetection, ChordDetectorState } from '@/src/chord/chordModelTypes'
import { MAX_HISTORY } from '@/src/chord/chordModelTypes'

type LiveChordState = ChordDetectorState & {
  setListening: (v: boolean) => void
  setCurrentChord: (d: ChordDetection) => void
  setError: (e: string | null) => void
  setLatency: (ms: number) => void
  setModelType: (t: 'tflite' | 'onnx' | null) => void
  reset: () => void
}

const INITIAL: ChordDetectorState = {
  isListening: false,
  currentChord: null,
  history: [],
  latencyMs: 0,
  error: null,
  modelType: null,
}

export const useLiveChordStore = create<LiveChordState>((set) => ({
  ...INITIAL,

  setListening: (isListening) => set({ isListening }),

  setCurrentChord: (d) =>
    set((state) => ({
      currentChord: d,
      history: [d, ...state.history].slice(0, MAX_HISTORY),
      latencyMs: d.latencyMs,
    })),

  setError: (error) => set({ error }),

  setLatency: (latencyMs) => set({ latencyMs }),

  setModelType: (modelType) => set({ modelType }),

  reset: () => set(INITIAL),
}))
