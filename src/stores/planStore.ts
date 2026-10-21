import { create } from 'zustand'

import type {
  PlanAdaptationPayload,
  PlanSlotResultPayload,
  PracticePlanPayload,
} from '@/src/types'

const DAY_MS = 24 * 60 * 60 * 1000

export interface PlanStoreState {
  /** Active session plan (after Start); drives SessionPlanBar navigation. */
  currentPlan: PracticePlanPayload | null
  currentSlotIndex: number
  planGeneratedAt: number | null
  /** Commit 162: completed slot results for the active plan. */
  slotResults: PlanSlotResultPayload[]
  /** Commit 162: applied adaptations for the active plan. */
  adaptationLog: PlanAdaptationPayload[]
  /** Epoch ms when the active plan was first started. */
  activePlanStartedAt: number | null
  /** Cached home preview; refreshed when stale (>24h) or profile/library changes (handled by Home). */
  homePreviewPlan: PracticePlanPayload | null
  homePreviewGeneratedAt: number | null
  setPlan: (plan: PracticePlanPayload) => void
  /** Restore a persisted active plan without resetting its progress. */
  restorePlan: (
    plan: PracticePlanPayload,
    currentSlotIndex: number,
    slotResults: PlanSlotResultPayload[],
    adaptationLog: PlanAdaptationPayload[],
    startedAt: number | null,
  ) => void
  setCurrentSlotIndex: (index: number) => void
  appendSlotResult: (result: PlanSlotResultPayload) => void
  appendAdaptation: (adaptation: PlanAdaptationPayload) => void
  clearPlan: () => void
  setHomePreviewPlan: (plan: PracticePlanPayload | null, generatedAt?: number) => void
  isHomePreviewStale: () => boolean
}

export const usePlanStore = create<PlanStoreState>((set, get) => ({
  currentPlan: null,
  currentSlotIndex: 0,
  planGeneratedAt: null,
  slotResults: [],
  adaptationLog: [],
  activePlanStartedAt: null,
  homePreviewPlan: null,
  homePreviewGeneratedAt: null,

  setPlan: (plan) =>
    set({
      currentPlan: plan,
      currentSlotIndex: 0,
      planGeneratedAt: Date.now(),
      slotResults: [],
      adaptationLog: [],
      activePlanStartedAt: Date.now(),
    }),

  restorePlan: (plan, currentSlotIndex, slotResults, adaptationLog, startedAt) =>
    set({
      currentPlan: plan,
      currentSlotIndex: Math.max(0, Math.floor(currentSlotIndex)),
      planGeneratedAt: Date.now(),
      slotResults,
      adaptationLog,
      activePlanStartedAt: startedAt,
    }),

  setCurrentSlotIndex: (index) => set({ currentSlotIndex: Math.max(0, Math.floor(index)) }),

  appendSlotResult: (result) =>
    set((state) => {
      const existing = state.slotResults.findIndex((item) => item.slot_id === result.slot_id)
      if (existing < 0) return { slotResults: [...state.slotResults, result] }
      const next = [...state.slotResults]
      next[existing] = result
      return { slotResults: next }
    }),

  appendAdaptation: (adaptation) =>
    set((state) => ({ adaptationLog: [...state.adaptationLog, adaptation] })),

  clearPlan: () =>
    set({
      currentPlan: null,
      currentSlotIndex: 0,
      planGeneratedAt: null,
      slotResults: [],
      adaptationLog: [],
      activePlanStartedAt: null,
    }),

  setHomePreviewPlan: (plan, generatedAt) =>
    set({
      homePreviewPlan: plan,
      homePreviewGeneratedAt: plan ? (generatedAt ?? Date.now()) : null,
    }),

  isHomePreviewStale: () => {
    const at = get().homePreviewGeneratedAt
    if (at == null) return true
    return Date.now() - at > DAY_MS
  },
}))
