import type { AnalyzeJob } from '@/src/types'

export type TrackedAnalysisStatus = 'queued' | 'processing' | 'failed'
export type TrackedAnalysisSource = 'youtube' | 'upload'

export interface TrackedAnalysisJob {
  jobId: string
  sourceKind: TrackedAnalysisSource
  sourceRef: string | null
  title: string
  artist: string | null
  submittedAt: string
  updatedAt: string
  status: TrackedAnalysisStatus
  progress: number | null
  stageLabel: string | null
  error: string | null
  errorCode: string | null
}

export interface TrackAnalysisJobInput {
  jobId: string
  sourceKind: TrackedAnalysisSource
  sourceRef: string | null
  title: string
  artist?: string | null
}

/** A job still being worked on by the server. */
export const TRACKED_ACTIVE_STATUSES: readonly TrackedAnalysisStatus[] = ['queued', 'processing']

/** Jobs still running after this long are treated as expired (backend job TTL is 24h). */
export const TRACKED_ACTIVE_MAX_MS = 24 * 60 * 60 * 1000

/** Failed jobs stay visible for a week so the user can review or dismiss them. */
export const TRACKED_FAILED_TTL_MS = 7 * 24 * 60 * 60 * 1000

export function isActiveTrackedJob(job: TrackedAnalysisJob): boolean {
  return job.status === 'queued' || job.status === 'processing'
}

export function trackedAnalysisStatusLabel(job: TrackedAnalysisJob): string {
  if (job.status === 'failed') return 'Analysis failed'
  if (job.status === 'queued') return 'Queued'
  return 'Analyzing…'
}

function asString(value: unknown): string | null {
  return typeof value === 'string' && value.trim().length > 0 ? value.trim() : null
}

function asProgress(value: unknown): number | null {
  if (typeof value !== 'number' || !Number.isFinite(value)) return null
  return Math.max(0, Math.min(1, value))
}

function parseStatus(value: unknown): TrackedAnalysisStatus | null {
  return value === 'queued' || value === 'processing' || value === 'failed' ? value : null
}

function parseSource(value: unknown): TrackedAnalysisSource | null {
  return value === 'youtube' || value === 'upload' ? value : null
}

function parseTimestamp(value: unknown, fallbackIso: string): string {
  const raw = asString(value)
  if (!raw) return fallbackIso
  return Number.isNaN(Date.parse(raw)) ? fallbackIso : raw
}

export function parseTrackedAnalysisJobs(raw: string | null, nowMs = Date.now()): TrackedAnalysisJob[] {
  if (!raw || !raw.trim()) return []
  let parsed: unknown
  try {
    parsed = JSON.parse(raw)
  } catch {
    return []
  }
  if (!Array.isArray(parsed)) return []

  const nowIso = new Date(nowMs).toISOString()
  const jobs: TrackedAnalysisJob[] = []
  for (const item of parsed) {
    if (!item || typeof item !== 'object' || Array.isArray(item)) continue
    const row = item as Record<string, unknown>
    const jobId = asString(row.jobId)
    const status = parseStatus(row.status)
    const sourceKind = parseSource(row.sourceKind)
    if (!jobId || !status || !sourceKind) continue
    const submittedAt = parseTimestamp(row.submittedAt, nowIso)
    const sourceRef = asString(row.sourceRef)
    jobs.push({
      jobId,
      sourceKind,
      sourceRef,
      title: asString(row.title) ?? sourceRef ?? 'Untitled analysis',
      artist: asString(row.artist),
      submittedAt,
      updatedAt: parseTimestamp(row.updatedAt, submittedAt),
      status,
      progress: asProgress(row.progress),
      stageLabel: asString(row.stageLabel),
      error: asString(row.error),
      errorCode: asString(row.errorCode),
    })
  }
  return pruneTrackedAnalysisJobs(jobs, nowMs)
}

export function upsertTrackedAnalysisJob(
  jobs: readonly TrackedAnalysisJob[],
  job: TrackedAnalysisJob,
): TrackedAnalysisJob[] {
  const next = jobs.filter((row) => row.jobId !== job.jobId)
  next.push(job)
  return next.sort((a, b) => Date.parse(b.submittedAt) - Date.parse(a.submittedAt))
}

export function removeTrackedAnalysisJob(
  jobs: readonly TrackedAnalysisJob[],
  jobId: string,
): TrackedAnalysisJob[] {
  return jobs.filter((row) => row.jobId !== jobId)
}

export function createTrackedAnalysisJob(input: TrackAnalysisJobInput, nowMs = Date.now()): TrackedAnalysisJob {
  const nowIso = new Date(nowMs).toISOString()
  return {
    jobId: input.jobId,
    sourceKind: input.sourceKind,
    sourceRef: input.sourceRef?.trim() ? input.sourceRef.trim() : null,
    title: input.title.trim() || input.sourceRef?.trim() || 'Untitled analysis',
    artist: input.artist?.trim() ? input.artist.trim() : null,
    submittedAt: nowIso,
    updatedAt: nowIso,
    status: 'queued',
    progress: null,
    stageLabel: 'Queued…',
    error: null,
    errorCode: null,
  }
}

export function applyTrackedJobProgress(
  job: TrackedAnalysisJob,
  status: AnalyzeJob,
  nowMs = Date.now(),
): TrackedAnalysisJob {
  if (status.status === 'complete') return job
  if (status.status === 'failed') {
    return markTrackedJobFailed(job, status.error ?? 'Analysis failed.', status.error_code, nowMs)
  }
  const progress = asProgress(status.progress) ?? job.progress
  const stage = asString(status.stage_label)
  return {
    ...job,
    status: status.status,
    progress,
    stageLabel: stage ?? job.stageLabel,
    updatedAt: new Date(nowMs).toISOString(),
  }
}

export function markTrackedJobFailed(
  job: TrackedAnalysisJob,
  error: string,
  errorCode: string | null | undefined,
  nowMs = Date.now(),
): TrackedAnalysisJob {
  return {
    ...job,
    status: 'failed',
    error: error.trim() || 'Analysis failed.',
    errorCode: asString(errorCode),
    updatedAt: new Date(nowMs).toISOString(),
  }
}

export function pruneTrackedAnalysisJobs(
  jobs: readonly TrackedAnalysisJob[],
  nowMs = Date.now(),
): TrackedAnalysisJob[] {
  const next: TrackedAnalysisJob[] = []
  for (const job of jobs) {
    if (isActiveTrackedJob(job)) {
      const startedMs = Date.parse(job.submittedAt)
      if (Number.isFinite(startedMs) && nowMs - startedMs > TRACKED_ACTIVE_MAX_MS) {
        next.push(
          markTrackedJobFailed(
            job,
            'This analysis expired. Try adding the song again.',
            'analysis_expired',
            nowMs,
          ),
        )
      } else {
        next.push(job)
      }
      continue
    }
    const updatedMs = Date.parse(job.updatedAt)
    if (Number.isFinite(updatedMs) && nowMs - updatedMs > TRACKED_FAILED_TTL_MS) continue
    next.push(job)
  }
  return next
}
