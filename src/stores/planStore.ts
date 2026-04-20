import { create } from 'zustand'

import type { PracticePlanPayload } from '@/src/types'

const DAY_MS = 24 * 60 * 60 * 1000

export interface PlanStoreState {
  /** Active session plan (after Start); drives SessionPlanBar navigation. */
  currentPlan: PracticePlanPayload | null
  currentSlotIndex: number
  planGeneratedAt: number | null
  /** Cached home preview; refreshed when stale (>24h) or profile/library changes (handled by Home). */
  homePreviewPlan: PracticePlanPayload | null
  homePreviewGeneratedAt: number | null
  setPlan: (plan: PracticePlanPayload) => void
  setCurrentSlotIndex: (index: number) => void
  clearPlan: () => void
  setHomePreviewPlan: (plan: PracticePlanPayload | null, generatedAt?: number) => void
  isHomePreviewStale: () => boolean
}

export const usePlanStore = create<PlanStoreState>((set, get) => ({
  currentPlan: null,
  currentSlotIndex: 0,
  planGeneratedAt: null,
  homePreviewPlan: null,
  homePreviewGeneratedAt: null,

  setPlan: (plan) => set({ currentPlan: plan, currentSlotIndex: 0, planGeneratedAt: Date.now() }),

  setCurrentSlotIndex: (index) => set({ currentSlotIndex: Math.max(0, Math.floor(index)) }),

  clearPlan: () => set({ currentPlan: null, currentSlotIndex: 0, planGeneratedAt: null }),

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
