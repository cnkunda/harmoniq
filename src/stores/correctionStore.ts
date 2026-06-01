import { create } from 'zustand'

import { getAppPref, setAppPref } from '@/src/db/client'
import type {
  ChordCorrection,
  CorrectionSet,
  NoteCorrection,
  VoicingOverride,
} from '@/src/types'

// ---- Pref key pattern: correction_{jobId} ----

function prefKey(jobId: string): string {
  return `correction_${jobId}`
}

function parseCorrectionSet(raw: string | null): CorrectionSet | null {
  if (!raw?.trim()) return null
  try {
    const o = JSON.parse(raw) as unknown
    if (!o || typeof o !== 'object' || Array.isArray(o)) return null
    const s = o as Record<string, unknown>
    return {
      chordCorrections: Array.isArray(s.chordCorrections) ? (s.chordCorrections as ChordCorrection[]) : [],
      noteCorrections: Array.isArray(s.noteCorrections) ? (s.noteCorrections as NoteCorrection[]) : [],
      voicingOverrides: Array.isArray(s.voicingOverrides) ? (s.voicingOverrides as VoicingOverride[]) : [],
    }
  } catch {
    return null
  }
}

function generateId(): string {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 8)
}

// ---- Store ----

export interface CorrectionStoreState {
  /** Corrections keyed by job_id. */
  corrections: Record<string, CorrectionSet>
  /** Whether hydration has completed for the active job. */
  hydrated: boolean

  /** Load corrections from DB for a given job. */
  hydrate: (jobId: string) => Promise<void>
  /** Clear in-memory corrections (e.g., on lesson change). */
  reset: () => void

  /** Apply a chord correction. */
  applyChordCorrection: (jobId: string, eventIndex: number, originalChord: string, correctedChord: string) => Promise<void>
  /** Apply a note correction. */
  applyNoteCorrection: (
    jobId: string,
    noteIndex: number,
    original: { pitch: number; duration: number; start_time: number },
    corrected: { pitch?: number; duration?: number; start_time?: number; string?: number; fret?: number },
  ) => Promise<void>
  /** Apply a voicing override. */
  applyVoicingOverride: (jobId: string, chordTimestamp: number, originalShape: string, correctedShape: string) => Promise<void>
  /** Revert a specific correction by ID. */
  revertCorrection: (jobId: string, correctionId: string) => Promise<void>
  /** Get the correction set for a job (returns empty set if none). */
  getCorrections: (jobId: string) => CorrectionSet
}

export const useCorrectionStore = create<CorrectionStoreState>((set, get) => ({
  corrections: {},
  hydrated: false,

  hydrate: async (jobId: string) => {
    const raw = await getAppPref(prefKey(jobId))
    const parsed = parseCorrectionSet(raw)
    set((s) => ({
      corrections: { ...s.corrections, [jobId]: parsed ?? { chordCorrections: [], noteCorrections: [], voicingOverrides: [] } },
      hydrated: true,
    }))
  },

  reset: () => set({ corrections: {}, hydrated: false }),

  applyChordCorrection: async (jobId, eventIndex, originalChord, correctedChord) => {
    const current = get().corrections[jobId] ?? { chordCorrections: [], noteCorrections: [], voicingOverrides: [] }
    const correction: ChordCorrection = {
      id: generateId(),
      eventIndex,
      originalChord,
      correctedChord,
      timestamp: Date.now(),
    }
    // Replace existing correction for the same eventIndex if present
    const filtered = current.chordCorrections.filter((c) => c.eventIndex !== eventIndex)
    const next: CorrectionSet = {
      ...current,
      chordCorrections: [...filtered, correction],
    }
    set((s) => ({ corrections: { ...s.corrections, [jobId]: next } }))
    await setAppPref(prefKey(jobId), JSON.stringify(next))
  },

  applyNoteCorrection: async (jobId, noteIndex, original, corrected) => {
    const current = get().corrections[jobId] ?? { chordCorrections: [], noteCorrections: [], voicingOverrides: [] }
    const correction: NoteCorrection = {
      id: generateId(),
      noteIndex,
      originalPitch: original.pitch,
      originalDuration: original.duration,
      originalStartTime: original.start_time,
      correctedPitch: corrected.pitch,
      correctedDuration: corrected.duration,
      correctedStartTime: corrected.start_time,
      correctedString: corrected.string,
      correctedFret: corrected.fret,
      timestamp: Date.now(),
    }
    const filtered = current.noteCorrections.filter((c) => c.noteIndex !== noteIndex)
    const next: CorrectionSet = {
      ...current,
      noteCorrections: [...filtered, correction],
    }
    set((s) => ({ corrections: { ...s.corrections, [jobId]: next } }))
    await setAppPref(prefKey(jobId), JSON.stringify(next))
  },

  applyVoicingOverride: async (jobId, chordTimestamp, originalShape, correctedShape) => {
    const current = get().corrections[jobId] ?? { chordCorrections: [], noteCorrections: [], voicingOverrides: [] }
    const override: VoicingOverride = {
      id: generateId(),
      chordTimestamp,
      originalShape,
      correctedShape,
      timestamp: Date.now(),
    }
    const filtered = current.voicingOverrides.filter((v) => v.chordTimestamp !== chordTimestamp)
    const next: CorrectionSet = {
      ...current,
      voicingOverrides: [...filtered, override],
    }
    set((s) => ({ corrections: { ...s.corrections, [jobId]: next } }))
    await setAppPref(prefKey(jobId), JSON.stringify(next))
  },

  revertCorrection: async (jobId, correctionId) => {
    const current = get().corrections[jobId]
    if (!current) return
    const next: CorrectionSet = {
      chordCorrections: current.chordCorrections.filter((c) => c.id !== correctionId),
      noteCorrections: current.noteCorrections.filter((c) => c.id !== correctionId),
      voicingOverrides: current.voicingOverrides.filter((v) => v.id !== correctionId),
    }
    set((s) => ({ corrections: { ...s.corrections, [jobId]: next } }))
    await setAppPref(prefKey(jobId), JSON.stringify(next))
  },

  getCorrections: (jobId: string) => {
    return get().corrections[jobId] ?? { chordCorrections: [], noteCorrections: [], voicingOverrides: [] }
  },
}))
