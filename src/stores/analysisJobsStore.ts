import { create } from 'zustand'

import {
  ApiError,
  getJobStatus,
} from '@/src/api/analyze'
import {
  applyTrackedJobProgress,
  createTrackedAnalysisJob,
  isActiveTrackedJob,
  markTrackedJobFailed,
  parseTrackedAnalysisJobs,
  pruneTrackedAnalysisJobs,
  removeTrackedAnalysisJob,
  upsertTrackedAnalysisJob,
  type TrackAnalysisJobInput,
  type TrackedAnalysisJob,
} from '@/src/analysis/trackedAnalysisJobs'
import { getAppPref, setAppPref, upsertLessonFromAnalysis } from '@/src/db/client'
import { PREF_ANALYSIS_JOBS_JSON } from '@/src/db/schema'
import type { AnalyzeJob, LessonJSON } from '@/src/types'

export interface AnalysisJobsState {
  jobs: TrackedAnalysisJob[]
  hydrated: boolean
  hydrate: () => Promise<void>
  track: (input: TrackAnalysisJobInput) => Promise<void>
  applyStatus: (jobId: string, job: AnalyzeJob) => Promise<void>
  refresh: () => Promise<void>
  dismiss: (jobId: string) => Promise<void>
  clearAll: () => Promise<void>
}

let hydratePromise: Promise<void> | null = null
let refreshPromise: Promise<void> | null = null
let persistChain: Promise<void> = Promise.resolve()
const savePromises = new Map<string, Promise<void>>()
/** Jobs completed by the foreground Add Song flow, which already shows its own toast. */
const locallyCompleted = new Set<string>()

function persistJobs(jobs: readonly TrackedAnalysisJob[]): Promise<void> {
  const raw = JSON.stringify(jobs)
  persistChain = persistChain
    .catch(() => {})
    .then(() => setAppPref(PREF_ANALYSIS_JOBS_JSON, raw))
    .catch((error) => {
      console.log('[analysisJobs] could not persist tracked jobs', error)
    })
  return persistChain
}

function persistCompletedLesson(lesson: LessonJSON): Promise<void> {
  const jobId = typeof lesson.job_id === 'string' ? lesson.job_id.trim() : ''
  if (!jobId) throw new Error('Completed analysis is missing job_id')
  const existing = savePromises.get(jobId)
  if (existing) return existing
  const task = upsertLessonFromAnalysis(lesson).finally(() => {
    savePromises.delete(jobId)
  })
  savePromises.set(jobId, task)
  return task
}

function notifyReady(title: string): void {
  void import('@/components/ToastConfig')
    .then(({ toast }) => {
      toast.success(`${title} is ready.`)
    })
    .catch((error) => {
      console.log('[analysisJobs] ready toast failed', error)
    })
}

export const useAnalysisJobsStore = create<AnalysisJobsState>((set, get) => {
  const commitJobs = (jobs: TrackedAnalysisJob[]): Promise<void> => {
    set({ jobs })
    return persistJobs(jobs)
  }

  const ensureHydrated = async (): Promise<void> => {
    if (!get().hydrated) await get().hydrate()
  }

  return {
    jobs: [],
    hydrated: false,

    hydrate: async () => {
      if (get().hydrated) return
      if (!hydratePromise) {
        hydratePromise = (async () => {
          const raw = await getAppPref(PREF_ANALYSIS_JOBS_JSON)
          set({ jobs: parseTrackedAnalysisJobs(raw), hydrated: true })
        })().finally(() => {
          hydratePromise = null
        })
      }
      await hydratePromise
    },

    track: async (input) => {
      await ensureHydrated()
      const job = createTrackedAnalysisJob(input)
      await commitJobs(upsertTrackedAnalysisJob(get().jobs, job))
    },

    applyStatus: async (jobId, job) => {
      await ensureHydrated()
      const entry = get().jobs.find((row) => row.jobId === jobId)
      if (!entry) return

      if (job.status === 'complete') {
        if (!job.result) {
          await commitJobs(
            upsertTrackedAnalysisJob(
              get().jobs,
              markTrackedJobFailed(entry, 'Analysis finished without a result.', 'analysis_failed'),
            ),
          )
          return
        }
        try {
          await persistCompletedLesson(job.result)
          locallyCompleted.add(jobId)
          await commitJobs(removeTrackedAnalysisJob(get().jobs, jobId))
        } catch (error) {
          console.log('[analysisJobs] could not save completed lesson', error)
          await commitJobs(
            upsertTrackedAnalysisJob(
              get().jobs,
              markTrackedJobFailed(
                entry,
                'Analysis finished, but the song could not be saved. Try adding it again.',
                'save_failed',
              ),
            ),
          )
        }
        return
      }

      const updated = applyTrackedJobProgress(entry, job)
      const nextJobs = upsertTrackedAnalysisJob(get().jobs, updated)
      if (updated.status !== entry.status || updated.stageLabel !== entry.stageLabel) {
        await commitJobs(nextJobs)
      } else {
        set({ jobs: nextJobs })
      }
    },

    refresh: async () => {
      await ensureHydrated()
      if (refreshPromise) return refreshPromise

      refreshPromise = (async () => {
        const snapshot = get().jobs
        const active = snapshot.filter(isActiveTrackedJob)
        if (active.length === 0) {
          const pruned = pruneTrackedAnalysisJobs(snapshot)
          if (JSON.stringify(pruned) !== JSON.stringify(snapshot)) await commitJobs(pruned)
          return
        }

        const updates = new Map<string, TrackedAnalysisJob>()
        const completed: Array<{ jobId: string; title: string }> = []

        await Promise.all(
          active.map(async (entry) => {
            try {
              const job = await getJobStatus(entry.jobId)
              if (job.status === 'complete') {
                if (!job.result) {
                  updates.set(
                    entry.jobId,
                    markTrackedJobFailed(entry, 'Analysis finished without a result.', 'analysis_failed'),
                  )
                  return
                }
                try {
                  await persistCompletedLesson(job.result)
                  if (!locallyCompleted.has(entry.jobId)) {
                    completed.push({
                      jobId: entry.jobId,
                      title: job.result.song_title?.trim() || entry.title,
                    })
                  } else {
                    locallyCompleted.delete(entry.jobId)
                  }
                } catch (error) {
                  console.log('[analysisJobs] could not save completed lesson', error)
                  updates.set(
                    entry.jobId,
                    markTrackedJobFailed(
                      entry,
                      'Analysis finished, but the song could not be saved. Try adding it again.',
                      'save_failed',
                    ),
                  )
                }
                return
              }
              if (job.status === 'failed') {
                updates.set(
                  entry.jobId,
                  markTrackedJobFailed(
                    entry,
                    job.error ?? 'Analysis failed.',
                    job.error_code,
                  ),
                )
                return
              }
              updates.set(entry.jobId, applyTrackedJobProgress(entry, job))
            } catch (error) {
              if (error instanceof ApiError && error.status === 404) {
                updates.set(
                  entry.jobId,
                  markTrackedJobFailed(
                    entry,
                    'This analysis is no longer available. Try adding the song again.',
                    'job_not_found',
                  ),
                )
              } else {
                console.log('[analysisJobs] status refresh failed', entry.jobId, error)
              }
            }
          }),
        )

        let next = get().jobs
        for (const update of updates.values()) {
          next = upsertTrackedAnalysisJob(next, update)
        }
        for (const job of completed) {
          next = removeTrackedAnalysisJob(next, job.jobId)
        }
        next = pruneTrackedAnalysisJobs(next)
        await commitJobs(next)
        for (const job of completed) notifyReady(job.title)
      })().finally(() => {
        refreshPromise = null
      })

      return refreshPromise
    },

    dismiss: async (jobId) => {
      await ensureHydrated()
      await commitJobs(removeTrackedAnalysisJob(get().jobs, jobId))
    },

    clearAll: async () => {
      await commitJobs([])
    },
  }
})
