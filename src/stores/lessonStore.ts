import { create } from 'zustand'

import { ApiError, getJobStatus, pollAnalyzeJob, pollCoachHydration, submitAnalyzeJob } from '@/src/api/analyze'
import { clearCachedLessonIfWeb, persistCachedLessonIfWeb } from '@/src/db/persistCachedLesson'
import { getNextFocusArea } from '@/src/session'
import { createScoreRefetchScheduler, type ScoreRefetchScheduler } from '@/src/session/scoreRefetch'
import type { AnalyzeJob, AnalyzeJobStatus, LessonJSON } from '@/src/types'
import { applyCorrectionsToLesson } from '@/src/utils/applyCorrections'
import { useCorrectionStore } from '@/src/stores/correctionStore'

/** Idle / in-flight UI states plus server-reported job status from `AnalyzeJob`. */
export type LessonStoreStatus = 'idle' | 'submitting' | AnalyzeJobStatus

export interface LessonStoreState {
  jobId: string | null
  status: LessonStoreStatus
  lesson: LessonJSON | null
  error: string | null
  /** Index into `lesson.sections` for the current practice target (session flow / `?section=` deep link). */
  lessonSectionIndex: number
  setLessonSectionIndex: (index: number) => void
  /** Starts URL analyze; cancels any in-flight poll from a previous call. */
  analyzeFromUrl: (url: string) => Promise<void>
  /** Starts file upload analyze; cancels any in-flight poll from a previous call. */
  analyzeFromFile: (file: Blob, filename?: string) => Promise<void>
  /** Persist a resolved lesson payload in store for downstream session screens. */
  saveLesson: (lesson: LessonJSON) => Promise<void>
  /** Schedule a debounced MusicXML/lesson refetch after a correction mutation (Commit 153). */
  requestScoreRefetch: (jobId: string) => void
  /** True while a correction-triggered score refetch is pending or in flight. */
  scoreUpdating: boolean
  clearError: () => void
  /** Clears in-memory lesson (e.g. after “clear all practice data”). */
  resetLesson: () => void
}

let pollGeneration = 0

/**
 * Commit 153: debounced score refetch after correction mutations.
 * Singleton so rapid corrections across screens coalesce into one GET.
 */
let scoreRefetchScheduler: ScoreRefetchScheduler | null = null

function getScoreRefetchScheduler(): ScoreRefetchScheduler {
  if (!scoreRefetchScheduler) {
    scoreRefetchScheduler = createScoreRefetchScheduler<AnalyzeJob>({
      fetchJob: getJobStatus,
      applyResult: async (job) => {
        if (job.status !== 'complete' || !job.result) {
          console.log('[LessonStore] score refetch skipped — job not complete', job.status)
          return
        }
        // Drop stale refetches that land after the user switched or cleared the lesson.
        const activeJobId = useLessonStore.getState().lesson?.job_id
        if (!activeJobId || activeJobId !== job.result.job_id) {
          console.log('[LessonStore] score refetch dropped — lesson changed', activeJobId, job.result.job_id)
          return
        }
        await useLessonStore.getState().saveLesson(job.result)
      },
      onError: (jobId, error) => {
        console.log('[LessonStore] score refetch failed', jobId, error)
        void import('@/components/ToastConfig').then(({ toast }) => {
          toast.error(
            'Score refresh failed: ' + (error instanceof Error ? error.message : 'unknown error'),
          )
        })
      },
      onStateChange: (updating) => {
        if (useLessonStore.getState().scoreUpdating !== updating) {
          useLessonStore.setState({ scoreUpdating: updating })
        }
      },
    })
  }
  return scoreRefetchScheduler
}

function formatAnalyzeError(e: unknown): string {
  if (e instanceof ApiError) {
    const body = e.message?.trim() ?? ''
    if (e.status >= 500) return 'Analysis failed on the server. Try again later.'
    if (e.status === 404) return 'Analysis job was not found.'
    if (e.status >= 400) return body || 'Invalid request.'
    return body || `Request failed (${e.status})`
  }
  if (e instanceof Error) return e.message
  return 'Something went wrong.'
}

export const useLessonStore = create<LessonStoreState>((set) => ({
  jobId: null,
  status: 'idle',
  lesson: null,
  error: null,
  lessonSectionIndex: 0,
  scoreUpdating: false,

  setLessonSectionIndex: (index: number) =>
    set({ lessonSectionIndex: Math.max(0, Math.floor(index)) }),

  clearError: () => set({ error: null }),
  resetLesson: () => {
    getScoreRefetchScheduler().cancel()
    set({ lesson: null, jobId: null, status: 'idle', error: null, lessonSectionIndex: 0, scoreUpdating: false })
    void clearCachedLessonIfWeb().catch(() => {})
  },
  requestScoreRefetch: (jobId: string) => {
    getScoreRefetchScheduler().request(jobId)
  },
  saveLesson: async (lesson: LessonJSON) => {
    // Commit 110: hydrate corrections from DB then apply before persisting
    const jobId = lesson.job_id
    let finalLesson = lesson
    if (jobId) {
      await useCorrectionStore.getState().hydrate(jobId)
      const corrections = useCorrectionStore.getState().getCorrections(jobId)
      if (corrections.chordCorrections.length > 0 || corrections.noteCorrections.length > 0) {
        finalLesson = applyCorrectionsToLesson(lesson, corrections)
      }
    }
    set({ lesson: finalLesson, status: 'complete', error: null })
    void persistCachedLessonIfWeb(finalLesson).catch(() => {})
    void import('@/src/db/client')
      .then(({ upsertLessonFromAnalysis }) => upsertLessonFromAnalysis(finalLesson))
      .catch(() => {})
  },

  // commit 66: coach hydration starts after lesson is available.

  analyzeFromUrl: async (url: string) => {
    const gen = ++pollGeneration
    set({ error: null, status: 'submitting', lesson: null })
    try {
      const focus_area = await getNextFocusArea()
      const jobId = await submitAnalyzeJob({ youtube_url: url, focus_area })
      if (gen !== pollGeneration) return
      set({ jobId, status: 'processing' })
      const lesson = await pollAnalyzeJob(jobId, (job) => {
        if (gen !== pollGeneration) return
        set({ status: job.status })
      })
      if (gen !== pollGeneration) return
      set({ lesson, status: 'complete', error: null })
      void (async () => {
        const { promise } = pollCoachHydration(
          jobId,
          (payload) => {
            if (gen !== pollGeneration) return
            const current = useLessonStore.getState().lesson
            if (!current || !Array.isArray(current.sections) || current.sections.length === 0) return
            const nextSections = current.sections.map((sec, idx) => {
              const upd = payload.sections.find((s) => s.index === idx)
              if (!upd) return sec
              return {
                ...(sec as Record<string, unknown>),
                coach_note: upd.coach_note,
                coach_explanation: upd.coach_explanation,
              }
            })
            const patched = { ...current, sections: nextSections }
            set({ lesson: patched })
            void persistCachedLessonIfWeb(patched).catch(() => {})
            void import('@/src/db/client')
              .then(({ upsertLessonFromAnalysis }) => upsertLessonFromAnalysis(patched))
              .catch(() => {})
          },
          1800,
        )
        await promise.catch(() => {
          void import('@/components/ToastConfig').then(({ toast }) => {
            toast.info('Coach tips could not refresh. Your session is still ready.')
          })
        })
      })()
    } catch (e) {
      if (gen !== pollGeneration) return
      set({ status: 'failed', error: formatAnalyzeError(e) })
    }
  },

  analyzeFromFile: async (file: Blob, filename?: string) => {
    const gen = ++pollGeneration
    set({ error: null, status: 'submitting', lesson: null })
    try {
      const focus_area = await getNextFocusArea()
      const jobId = await submitAnalyzeJob({ file, filename, focus_area })
      if (gen !== pollGeneration) return
      set({ jobId, status: 'processing' })
      const lesson = await pollAnalyzeJob(jobId, (job) => {
        if (gen !== pollGeneration) return
        set({ status: job.status })
      })
      if (gen !== pollGeneration) return
      set({ lesson, status: 'complete', error: null })
      void (async () => {
        const { promise } = pollCoachHydration(
          jobId,
          (payload) => {
            if (gen !== pollGeneration) return
            const current = useLessonStore.getState().lesson
            if (!current || !Array.isArray(current.sections) || current.sections.length === 0) return
            const nextSections = current.sections.map((sec, idx) => {
              const upd = payload.sections.find((s) => s.index === idx)
              if (!upd) return sec
              return {
                ...(sec as Record<string, unknown>),
                coach_note: upd.coach_note,
                coach_explanation: upd.coach_explanation,
              }
            })
            const patched = { ...current, sections: nextSections }
            set({ lesson: patched })
            void persistCachedLessonIfWeb(patched).catch(() => {})
            void import('@/src/db/client')
              .then(({ upsertLessonFromAnalysis }) => upsertLessonFromAnalysis(patched))
              .catch(() => {})
          },
          1800,
        )
        await promise.catch(() => {
          void import('@/components/ToastConfig').then(({ toast }) => {
            toast.info('Coach tips could not refresh. Your session is still ready.')
          })
        })
      })()
    } catch (e) {
      if (gen !== pollGeneration) return
      set({ status: 'failed', error: formatAnalyzeError(e) })
    }
  },
}))
