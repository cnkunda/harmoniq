import { create } from 'zustand'

import { ApiError, pollAnalyzeJob, submitAnalyzeJob } from '@/src/api/analyze'
import { clearCachedLessonIfWeb, persistCachedLessonIfWeb } from '@/src/db/persistCachedLesson'
import type { AnalyzeJobStatus, LessonJSON } from '@/src/types'

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
  saveLesson: (lesson: LessonJSON) => void
  clearError: () => void
  /** Clears in-memory lesson (e.g. after “clear all practice data”). */
  resetLesson: () => void
}

let pollGeneration = 0

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

  setLessonSectionIndex: (index: number) =>
    set({ lessonSectionIndex: Math.max(0, Math.floor(index)) }),

  clearError: () => set({ error: null }),
  resetLesson: () => {
    set({ lesson: null, jobId: null, status: 'idle', error: null, lessonSectionIndex: 0 })
    void clearCachedLessonIfWeb().catch(() => {})
  },
  saveLesson: (lesson: LessonJSON) => {
    set({ lesson, status: 'complete', error: null })
    void persistCachedLessonIfWeb(lesson).catch(() => {})
  },

  analyzeFromUrl: async (url: string) => {
    const gen = ++pollGeneration
    set({ error: null, status: 'submitting', lesson: null })
    try {
      const jobId = await submitAnalyzeJob({ youtube_url: url })
      if (gen !== pollGeneration) return
      set({ jobId, status: 'processing' })
      const lesson = await pollAnalyzeJob(jobId, (job) => {
        if (gen !== pollGeneration) return
        set({ status: job.status })
      })
      if (gen !== pollGeneration) return
      set({ lesson, status: 'complete', error: null })
    } catch (e) {
      if (gen !== pollGeneration) return
      set({ status: 'failed', error: formatAnalyzeError(e) })
    }
  },

  analyzeFromFile: async (file: Blob, filename?: string) => {
    const gen = ++pollGeneration
    set({ error: null, status: 'submitting', lesson: null })
    try {
      const jobId = await submitAnalyzeJob({ file, filename })
      if (gen !== pollGeneration) return
      set({ jobId, status: 'processing' })
      const lesson = await pollAnalyzeJob(jobId, (job) => {
        if (gen !== pollGeneration) return
        set({ status: job.status })
      })
      if (gen !== pollGeneration) return
      set({ lesson, status: 'complete', error: null })
    } catch (e) {
      if (gen !== pollGeneration) return
      set({ status: 'failed', error: formatAnalyzeError(e) })
    }
  },
}))
