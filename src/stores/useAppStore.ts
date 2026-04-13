import { create } from 'zustand'

import type { NoteResultLabel } from '@/src/session/noteAccuracyBeats'
import { CENTS_TOLERANCE } from '@/src/utils/practiceConfig'

export type NoteContourSample = { hz: number; amp: number; t: number }

export type CurrentSessionState = {
  currentStreak: number
  bestStreak: number
  /** Best streak at the moment this capture started (for Review “new record” copy). */
  bestStreakAtSessionStart: number
  noteContours: NoteContourSample[][]
  /** Target MIDI per scored row (parallel to noteContours / noteResults). */
  noteTargetMidis: number[]
  noteResults: NoteResultLabel[]
  adaptedCentsTolerance: number
  /** Mean onset error in ms; positive = early vs grid (rushing). */
  bpmDrift: number
  /** Number of beats included in bpmDrift (for gating display). */
  bpmDriftSampleCount: number
}

type AppState = {
  currentSession: CurrentSessionState | null
  resetCurrentSession: () => void
  initSessionForCapture: () => void
  pushScoredBeat: (args: {
    result: NoteResultLabel
    contour: NoteContourSample[]
    targetMidi: number
    driftMsContribution?: number | null
  }) => void
  setAdaptedCentsTolerance: (cents: number) => void
  setBpmDrift: (ms: number, sampleCount: number) => void
  updateStreakAfterResult: (result: NoteResultLabel) => void
}

function emptySession(baseBest: number): CurrentSessionState {
  return {
    currentStreak: 0,
    bestStreak: baseBest,
    bestStreakAtSessionStart: baseBest,
    noteContours: [],
    noteTargetMidis: [],
    noteResults: [],
    adaptedCentsTolerance: CENTS_TOLERANCE,
    bpmDrift: 0,
    bpmDriftSampleCount: 0,
  }
}

export const useAppStore = create<AppState>((set, get) => ({
  currentSession: null,

  resetCurrentSession: () => set({ currentSession: null }),

  initSessionForCapture: () =>
    set((s) => {
      const prev = s.currentSession
      const baseBest = prev?.bestStreak ?? 0
      return { currentSession: emptySession(baseBest) }
    }),

  pushScoredBeat: ({ result, contour, targetMidi, driftMsContribution }) =>
    set((state) => {
      const cs = state.currentSession
      if (!cs) return state
      const nextContours = [...cs.noteContours, contour]
      const nextTargets = [...cs.noteTargetMidis, targetMidi]
      const nextResults = [...cs.noteResults, result]
      let nextDrift = cs.bpmDrift
      let nextCount = cs.bpmDriftSampleCount
      if (result !== 'ignored' && driftMsContribution != null && Number.isFinite(driftMsContribution)) {
        const prevN = cs.bpmDriftSampleCount
        nextCount = prevN + 1
        nextDrift = prevN <= 0 ? driftMsContribution : (cs.bpmDrift * prevN + driftMsContribution) / nextCount
      }
      return {
        currentSession: {
          ...cs,
          noteContours: nextContours,
          noteTargetMidis: nextTargets,
          noteResults: nextResults,
          bpmDrift: nextDrift,
          bpmDriftSampleCount: nextCount,
        },
      }
    }),

  setAdaptedCentsTolerance: (cents) =>
    set((state) => {
      const cs = state.currentSession
      if (!cs) return state
      return { currentSession: { ...cs, adaptedCentsTolerance: cents } }
    }),

  setBpmDrift: (ms, sampleCount) =>
    set((state) => {
      const cs = state.currentSession
      if (!cs) return state
      return { currentSession: { ...cs, bpmDrift: ms, bpmDriftSampleCount: sampleCount } }
    }),

  updateStreakAfterResult: (result) =>
    set((state) => {
      const cs = state.currentSession
      if (!cs) return state
      if (result === 'ignored') return state
      let currentStreak = cs.currentStreak
      let bestStreak = cs.bestStreak
      if (result === 'miss') {
        currentStreak = 0
      } else if (result === 'hit' || result === 'close' || result === 'vibrato') {
        currentStreak += 1
        if (currentStreak > bestStreak) bestStreak = currentStreak
      }
      return { currentSession: { ...cs, currentStreak, bestStreak } }
    }),
}))
