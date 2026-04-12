import { API_BASE_URL } from '@/src/config'
import type { AnalyzeJob, JamResult, LessonJSON, PlayerProfilePayload, ScoreResult } from '@/src/types'
import type { SkillNodeRow } from '@/src/db/types'

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

const WEAK_AREA_BY_NODE_ID: Record<string, string> = {
  bend_accuracy: 'bending',
  pitch_accuracy: 'pitch',
  phrasing: 'phrasing',
  timing: 'timing',
  vibrato_control: 'vibrato',
}

/** Build optional player profile for analyze from persisted skill rows (commit 48). */
export function buildPlayerProfileFromSkillNodes(nodes: SkillNodeRow[]): PlayerProfilePayload | undefined {
  if (nodes.length === 0) return undefined
  const weakThreshold = 0.45
  const weak_areas = nodes
    .filter((n) => n.score < weakThreshold)
    .map((n) => WEAK_AREA_BY_NODE_ID[n.id] ?? n.id)
  const skill_nodes = nodes.map((n) => ({
    id: n.id,
    label: n.label,
    score: n.score,
  }))
  return { weak_areas, skill_nodes }
}

/** YouTube or future multipart upload — `url` matches FastAPI `AnalyzeRequest`. */
export async function submitAnalyzeJob(input: {
  youtube_url?: string
  file?: Blob
  filename?: string
  player_profile?: PlayerProfilePayload
}): Promise<string> {
  if (input.file != null) {
    const form = new FormData()
    form.append('file', input.file, input.filename ?? 'upload.mp3')
    if (input.player_profile != null) {
      form.append('player_profile', JSON.stringify(input.player_profile))
    }
    const { job_id } = await request<{ job_id: string }>('/analyze', { method: 'POST', body: form })
    return job_id
  }
  const url = input.youtube_url?.trim()
  if (!url) {
    throw new Error('Provide youtube_url or file')
  }
  const body: { url: string; player_profile?: PlayerProfilePayload } = { url }
  if (input.player_profile != null) {
    body.player_profile = input.player_profile
  }
  const { job_id } = await request<{ job_id: string }>('/analyze', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
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

const QUICK_FEEDBACK_FALLBACK =
  'A few beats drifted — stay lighter on the pick and let each target note settle before you slide to the next.'

export async function submitQuickFeedback(
  payload: { accuracy_pattern: Array<'hit' | 'close' | 'miss'> },
  options?: { timeoutMs?: number },
): Promise<{ message: string }> {
  const timeoutMs = options?.timeoutMs ?? 3500
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), timeoutMs)
  try {
    const res = await fetch(`${API_BASE_URL}/quick-feedback`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal: ctrl.signal,
    })
    if (!res.ok) {
      return { message: QUICK_FEEDBACK_FALLBACK }
    }
    const data = (await res.json()) as { message?: string }
    const msg = typeof data.message === 'string' && data.message.trim() ? data.message.trim() : null
    return { message: msg ?? QUICK_FEEDBACK_FALLBACK }
  } catch {
    return { message: QUICK_FEEDBACK_FALLBACK }
  } finally {
    clearTimeout(timer)
  }
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
