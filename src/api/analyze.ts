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
  return new Promise((resolve, reject) => {
    let intervalId: ReturnType<typeof setInterval> | undefined

    const stop = () => {
      if (intervalId !== undefined) {
        clearInterval(intervalId)
        intervalId = undefined
      }
    }

    const tick = async () => {
      try {
        const job = await getJobStatus(jobId)
        onStatus(job)
        if (job.status === 'complete') {
          stop()
          if (job.result) resolve(job.result)
          else reject(new ApiError(500, 'Analysis complete but no result'))
          return
        }
        if (job.status === 'failed') {
          stop()
          reject(new ApiError(500, job.error ?? 'Analysis failed'))
        }
      } catch (e) {
        stop()
        reject(e)
      }
    }

    void tick()
    intervalId = setInterval(() => {
      void tick()
    }, intervalMs)
  })
}

export async function submitScore(payload: {
  recording_wav_base64: string
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
  recording_wav_base64: string
  duration_seconds: number
}): Promise<JamResult> {
  return request<JamResult>('/jam-score', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}
