import { API_BASE_URL } from '@/src/config'
import type { AnalyzeJob, JamResult, LessonJSON, ScoreResult } from '@/src/types'

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

export class AnalyzePollCancelledError extends Error {
  constructor() {
    super('Analyze polling was cancelled')
    this.name = 'AnalyzePollCancelledError'
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, init)
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new ApiError(res.status, body || res.statusText)
  }
  return res.json() as Promise<T>
}

/** YouTube or future multipart upload — `url` matches FastAPI `AnalyzeRequest`. */
export async function submitAnalyzeJob(input: {
  youtube_url?: string
  file?: Blob
  filename?: string
}): Promise<string> {
  if (input.file != null) {
    const form = new FormData()
    form.append('file', input.file, input.filename ?? 'upload.mp3')
    const { job_id } = await request<{ job_id: string }>('/analyze', { method: 'POST', body: form })
    return job_id
  }
  const url = input.youtube_url?.trim()
  if (!url) {
    throw new Error('Provide youtube_url or file')
  }
  const { job_id } = await request<{ job_id: string }>('/analyze', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url }),
  })
  return job_id
}

export async function getJobStatus(jobId: string): Promise<AnalyzeJob> {
  return request<AnalyzeJob>(`/analyze/${encodeURIComponent(jobId)}`)
}

export function pollAnalyzeJob(
  jobId: string,
  onStatus: (job: AnalyzeJob) => void,
  intervalMs = 3000,
): Promise<LessonJSON> {
  return pollAnalyzeJobCancelable(jobId, onStatus, intervalMs).promise
}

export function pollAnalyzeJobCancelable(
  jobId: string,
  onStatus: (job: AnalyzeJob) => void,
  intervalMs = 3000,
): { promise: Promise<LessonJSON>; cancel: () => void } {
  let settled = false
  let rejectRef: ((reason?: unknown) => void) | null = null
  let stopRef: (() => void) | null = null

  const promise = new Promise<LessonJSON>((resolve, reject) => {
    rejectRef = reject
    let intervalId: ReturnType<typeof setInterval> | undefined

    const stop = () => {
      if (intervalId !== undefined) {
        clearInterval(intervalId)
        intervalId = undefined
      }
    }
    stopRef = stop

    const tick = async () => {
      try {
        const job = await getJobStatus(jobId)
        onStatus(job)
        if (job.status === 'complete') {
          stop()
          settled = true
          if (job.result) resolve(job.result)
          else reject(new ApiError(500, 'Analysis complete but no result'))
          return
        }
        if (job.status === 'failed') {
          stop()
          settled = true
          reject(new ApiError(500, job.error ?? 'Analysis failed'))
        }
      } catch (e) {
        stop()
        settled = true
        reject(e)
      }
    }

    void tick()
    intervalId = setInterval(() => {
      void tick()
    }, intervalMs)
  })

  return {
    promise,
    cancel: () => {
      if (settled) return
      settled = true
      stopRef?.()
      rejectRef?.(new AnalyzePollCancelledError())
    },
  }
}

export async function submitScore(payload: {
  recording_wav_base64: string
  recording_mime_type?: string
  section: unknown
  skill_nodes: string[]
}): Promise<ScoreResult> {
  return request<ScoreResult>('/score', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export async function submitJamScore(payload: {
  recording_wav_base64?: string
  duration_seconds: number
  scale_position_map?: Record<string, number>
  inferred_scale_label?: string | null
}): Promise<JamResult> {
  return request<JamResult>('/jam-score', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      recording_wav_base64: payload.recording_wav_base64 ?? '',
      duration_seconds: payload.duration_seconds,
      scale_position_map: payload.scale_position_map ?? {},
      inferred_scale_label: payload.inferred_scale_label ?? null,
    }),
  })
}

export async function fetchOnboardingPlacementCoach(payload: {
  pitch_avg: number
  phrasing_avg: number
  timing_avg: number
  bend_error_cents_avg: number
}): Promise<{ coach_paragraph: string }> {
  return request<{ coach_paragraph: string }>('/onboarding-placement', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}
