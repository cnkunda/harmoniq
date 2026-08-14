import { API_BASE_URL } from '@/src/config'
import { getAppPref } from '@/src/db/client'
import { PREF_EXPERIENCE_LEVEL, PREF_STYLE_FOCUS } from '@/src/db/schema'
import type { SkillNodeRow } from '@/src/db/types'
import { parseTechniqueRollJson, rollingSessionsWeak } from '@/src/session/skillMutator'
import type {
  AnalyzeJob,
  CoachHydrationStatusPayload,
  CurriculumSuggestResponse,
  CurriculumSuggestion,
  JamResult,
  LearningContextPayload,
  LessonJSON,
  PlayerProfilePayload,
  PracticePlanPayload,
  QuizAnswersPayload,
  ScoreResult,
  SpotifyPlaybackStatePayload,
  SpotifyTasteProfile,
  TasteProfilePayload,
} from '@/src/types'

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    /** From `JobStatus.error_code` on failed analyze polls when present. */
    public readonly errorCode?: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

/** FastAPI `{ "detail": "..." | [...] }` → single-line message for banners. */
export function parseFastApiDetail(raw: string): string {
  const trimmed = raw.trim()
  if (!trimmed) return 'Request failed'
  try {
    const j = JSON.parse(trimmed) as { detail?: unknown }
    const d = j.detail
    if (typeof d === 'string') return d
    if (Array.isArray(d)) {
      return d
        .map((item) => {
          if (typeof item === 'string') return item
          if (item && typeof item === 'object' && 'msg' in item) {
            return String((item as { msg?: unknown }).msg ?? JSON.stringify(item))
          }
          return JSON.stringify(item)
        })
        .join('; ')
    }
  } catch {
    // not JSON
  }
  return trimmed
}

export type ExportFormat = 'midi' | 'musicxml' | 'pdf' | 'png'

/** POST /export/musicxml-from-json — MusicXML from Harmoniq JSON artifacts (Commit 80). */
export async function exportMusicXmlFromJson(payload: {
  beat_grid: unknown
  chord_timeline: unknown
  solo_notes: unknown
  title?: string | null
  artist?: string | null
}): Promise<string> {
  const body: Record<string, unknown> = {
    beat_grid: payload.beat_grid,
    chord_timeline: payload.chord_timeline,
    solo_notes: payload.solo_notes,
  }
  if (typeof payload.title === 'string' && payload.title.trim()) body.title = payload.title.trim()
  if (typeof payload.artist === 'string' && payload.artist.trim()) body.artist = payload.artist.trim()

  const res = await fetch(`${API_BASE_URL}/export/musicxml-from-json`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new ApiError(res.status, parseFastApiDetail(text))
  }
  const text = await res.text()
  return text
}

/** POST /export — returns blob + headers for filenames and MIME. */
export async function submitExportJob(payload: {
  gp5_base64: string
  format: ExportFormat
  title?: string | null
}): Promise<{ blob: Blob; mimeType: string; contentDisposition: string | null }> {
  const body: Record<string, unknown> = {
    gp5_base64: payload.gp5_base64,
    format: payload.format,
  }
  const t = typeof payload.title === 'string' ? payload.title.trim() : ''
  if (t) body.title = t

  const res = await fetch(`${API_BASE_URL}/export`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new ApiError(res.status, parseFastApiDetail(text))
  }
  const blob = await res.blob()
  return {
    blob,
    mimeType: res.headers.get('Content-Type') ?? 'application/octet-stream',
    contentDisposition: res.headers.get('Content-Disposition'),
  }
}

export class AnalyzePollCancelledError extends Error {
  constructor() {
    super('Analyze polling was cancelled')
    this.name = 'AnalyzePollCancelledError'
  }
}

/** Default timeout for JSON GET/POST (status polls, small payloads). */
const DEFAULT_REQUEST_TIMEOUT_MS = 45_000
/** Large multipart uploads to POST /analyze need a longer window than polling. */
const ANALYZE_UPLOAD_TIMEOUT_MS = 120_000

async function request<T>(path: string, init?: RequestInit, timeoutMs: number = DEFAULT_REQUEST_TIMEOUT_MS): Promise<T> {
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs)
  try {
    const res = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      signal: controller.signal,
    })
    if (!res.ok) {
      const body = await res.text().catch(() => '')
      throw new ApiError(res.status, parseFastApiDetail(body) || body || res.statusText)
    }
    return res.json() as Promise<T>
  } catch (e) {
    if (e instanceof ApiError) throw e
    const name = e instanceof Error ? e.name : ''
    const msg = e instanceof Error ? e.message : String(e)
    if (name === 'AbortError' || msg.toLowerCase().includes('aborted')) {
      throw new ApiError(408, 'Request timed out. Check your connection and try again.')
    }
    throw e
  } finally {
    clearTimeout(timeoutId)
  }
}

/** True when a status poll failed for a likely-transient reason — retry with backoff instead of failing the whole job. */
export function isRecoverableAnalyzePollError(e: unknown): boolean {
  if (e instanceof TypeError) return true
  if (e instanceof ApiError) {
    if (e.status === 408 || e.status === 429) return true
    if (e.status === 502 || e.status === 503 || e.status === 504) return true
    return false
  }
  if (e instanceof Error) {
    const m = e.message.toLowerCase()
    return m.includes('network') || m.includes('fetch') || m.includes('failed to load')
  }
  return false
}

/** Wall-clock cap for Add Song analyze polling — matches `mapAnalyzeFlowError` timeout branch. */
export const ANALYZE_MAX_PROCESSING_WALL_MS = 5 * 60 * 1000

export type PollAnalyzeOptions = {
  /** Called before scheduling a backoff retry after a transient poll failure. */
  onRecoverablePollError?: (info: { attempt: number; delayMs: number }) => void
  /** Client clock when the user started this analyze run (e.g. `Date.now()` at submit). */
  wallClockStartedAtMs?: number
  /** Notify if still `processing` after this many ms since `wallClockStartedAtMs`. Polling continues. */
  maxProcessingWallMs?: number
  /** Called once when maxProcessingWallMs is exceeded. Polling continues until completion. */
  onLongRunning?: () => void
}

const MAX_POLL_NETWORK_RETRIES = 12

function pollBackoffDelayMs(attempt: number): number {
  return Math.min(28_000, Math.round(600 * 1.65 ** Math.max(0, attempt - 1)))
}

const WEAK_AREA_BY_NODE_ID: Record<string, string> = {
  bend_accuracy: 'bending',
  pitch_accuracy: 'pitch',
  phrasing: 'phrasing',
  timing: 'timing',
  vibrato_control: 'vibrato',
}

/** Parse persisted `TasteProfile` JSON from `user_prefs` (commit 68). */
export function parseTasteProfileJson(raw: string | null): TasteProfilePayload | null {
  if (!raw || !raw.trim()) return null
  try {
    const o = JSON.parse(raw) as unknown
    if (!o || typeof o !== 'object' || Array.isArray(o)) return null
    const rec = o as Record<string, unknown>
    const style_label = typeof rec.style_label === 'string' ? rec.style_label.trim() : ''
    const technique_affinity = Array.isArray(rec.technique_affinity)
      ? rec.technique_affinity.filter((x): x is string => typeof x === 'string' && x.trim().length > 0)
      : []
    const bpm = rec.bpm_comfort_range
    let bpm_comfort_range: [number, number] = [80, 120]
    if (Array.isArray(bpm) && bpm.length === 2) {
      const a = Number(bpm[0])
      const b = Number(bpm[1])
      if (Number.isFinite(a) && Number.isFinite(b)) bpm_comfort_range = [Math.round(a), Math.round(b)]
    }
    const song_candidates = Array.isArray(rec.song_candidates)
      ? rec.song_candidates.filter((x): x is string => typeof x === 'string' && x.trim().length > 0)
      : []
    const src = rec.source
    const source: TasteProfilePayload['source'] =
      src === 'quiz' || src === 'manual' || src === 'spotify' ? src : 'spotify'
    if (!style_label) return null
    return {
      style_label,
      technique_affinity,
      bpm_comfort_range,
      song_candidates,
      source,
    }
  } catch {
    return null
  }
}

function parseExperienceLevel(raw: string | null): 'beginner' | 'intermediate' | 'advanced' | undefined {
  const v = raw?.trim().toLowerCase()
  if (v === 'beginner' || v === 'intermediate' || v === 'advanced') return v
  return undefined
}

/** Loads declared experience + Settings style focus for `PlayerProfilePayload.learning_context`. */
export async function loadLearningContextFromPrefs(): Promise<LearningContextPayload | undefined> {
  const [expRaw, styleRaw] = await Promise.all([
    getAppPref(PREF_EXPERIENCE_LEVEL),
    getAppPref(PREF_STYLE_FOCUS),
  ])
  const experience_level = parseExperienceLevel(expRaw)
  const solo_focus_notes = styleRaw?.trim() ? styleRaw.trim() : undefined
  if (experience_level == null && solo_focus_notes == null) return undefined
  const out: LearningContextPayload = {}
  if (experience_level != null) out.experience_level = experience_level
  if (solo_focus_notes != null) out.solo_focus_notes = solo_focus_notes
  return out
}

/**
 * Build optional player profile for analyze from persisted skill rows (commit 48).
 * After commit 63 session mutations, reload skill nodes (e.g. `loadFromDb`) before calling so
 * `weak_areas` reflects technique EMA and rolling three-session weak detection.
 */
export function buildPlayerProfileFromSkillNodes(
  nodes?: SkillNodeRow[] | null,
  tasteProfile?: TasteProfilePayload | null,
  learningContext?: LearningContextPayload | null,
): PlayerProfilePayload | undefined {
  const safeNodes = Array.isArray(nodes) ? nodes : []
  let base: PlayerProfilePayload | undefined
  if (safeNodes.length > 0) {
    const weakThreshold = 0.45
    const weakIds = new Set<string>()
    for (const n of safeNodes) {
      const byScore = Number.isFinite(n.score) && n.score < weakThreshold
      const roll = parseTechniqueRollJson(n.technique_roll_json)
      const byRoll = rollingSessionsWeak(roll)
      if (byScore || byRoll) weakIds.add(WEAK_AREA_BY_NODE_ID[n.id] ?? n.id)
    }
    const weak_areas = [...weakIds].sort()
    const skill_nodes = safeNodes.map((n) => {
      const rawScore = Number(n.score)
      const score = Number.isFinite(rawScore) ? Math.max(0, Math.min(1, rawScore)) : undefined
      return {
        id: n.id,
        label: n.label,
        ...(score != null ? { score } : {}),
      }
    })
    base = { weak_areas, skill_nodes }
  }
  let merged: PlayerProfilePayload | undefined = tasteProfile
    ? base
      ? { ...base, taste_profile: tasteProfile }
      : { taste_profile: tasteProfile }
    : base
  if (learningContext != null && Object.keys(learningContext).length > 0) {
    merged = merged
      ? { ...merged, learning_context: learningContext }
      : { learning_context: learningContext }
  }
  return merged
}

/** YouTube or future multipart upload — `url` matches FastAPI `AnalyzeRequest`. */
export async function submitAnalyzeJob(input: {
  youtube_url?: string
  file?: Blob
  filename?: string
  player_profile?: PlayerProfilePayload
  focus_area?: 'timing' | 'vibrato' | 'dynamics' | 'phrasing' | 'bending' | 'rhythm' | 'expression'
}): Promise<string> {
  if (input.file != null) {
    const form = new FormData()
    form.append('file', input.file, input.filename ?? 'upload.mp3')
    if (input.player_profile != null) {
      form.append('player_profile', JSON.stringify(input.player_profile))
    }
    if (input.focus_area != null) {
      form.append('focus_area', input.focus_area)
    }
    const { job_id } = await request<{ job_id: string }>(
      '/analyze',
      { method: 'POST', body: form },
      ANALYZE_UPLOAD_TIMEOUT_MS,
    )
    return job_id
  }
  const url = input.youtube_url?.trim()
  if (!url) {
    throw new Error('Provide youtube_url or file')
  }
  const body: { url: string; player_profile?: PlayerProfilePayload; focus_area?: string } = { url }
  if (input.player_profile != null) {
    body.player_profile = input.player_profile
  }
  if (input.focus_area != null) {
    body.focus_area = input.focus_area
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
  options?: PollAnalyzeOptions,
): { promise: Promise<LessonJSON>; cancel: () => void } {
  /**
   * Polling strategy for long-running analyze jobs:
   * - Initial interval: 3000ms (reduced server load for expensive operations)
   * - Backoff: 1.3x per poll (less aggressive than 1.5x)
   * - Max backoff: 8000ms (cap to avoid excessive delays)
   * - Max exponent: 3 (reaches max backoff faster)
   * 
   * This reduces unnecessary polling for Demucs stem separation which can take
   * minutes on CPU, while still providing responsive updates for fast jobs.
   */
  let settled = false
  let rejectRef: ((reason?: unknown) => void) | null = null
  let stopRef: (() => void) | null = null
  let pollCount = 0
  let seenCompletedOrFailed = false  // BUG-01 guard: never re-poll after terminal status

  const promise = new Promise<LessonJSON>((resolve, reject) => {
    rejectRef = reject
    let timer: ReturnType<typeof setTimeout> | undefined
    let pollNetworkFailures = 0

    const stop = () => {
      if (timer !== undefined) {
        clearTimeout(timer)
        timer = undefined
      }
    }
    stopRef = stop

    const schedule = (delayMs: number) => {
      stop()
      timer = setTimeout(() => void tick(), delayMs)
    }

    const tick = async () => {
      if (settled || seenCompletedOrFailed) return  // BUG-01: never re-poll after terminal status
      try {
        const job = await getJobStatus(jobId)
        pollNetworkFailures = 0
        pollCount += 1

        // BUG-01: check terminal status BEFORE calling onStatus, so a throw from
        // the callback doesn't bypass the settled flag and trigger re-polling.
        if (job.status === 'complete') {
          stop(); settled = true; seenCompletedOrFailed = true
          if (job.result) resolve(job.result)
          else reject(new ApiError(500, 'Analysis complete but no result'))
          return
        }
        if (job.status === 'failed') {
          stop(); settled = true; seenCompletedOrFailed = true
          const code = typeof job.error_code === 'string' && job.error_code.length > 0 ? job.error_code : undefined
          reject(new ApiError(500, job.error ?? 'Analysis failed', code))
          return
        }

        onStatus(job)
        const wallStart = options?.wallClockStartedAtMs
        const maxWall = options?.maxProcessingWallMs
        if (
          wallStart != null &&
          maxWall != null &&
          maxWall > 0 &&
          job.status === 'processing' &&
          Date.now() - wallStart > maxWall
        ) {
          options?.onLongRunning?.()
        }
        const backoffMs = Math.min(8000, intervalMs * Math.pow(1.3, Math.min(pollCount - 1, 3)))
        schedule(backoffMs)
      } catch (e) {
        if (settled) return
        if (
          isRecoverableAnalyzePollError(e) &&
          pollNetworkFailures < MAX_POLL_NETWORK_RETRIES
        ) {
          pollNetworkFailures += 1
          const delayMs = pollBackoffDelayMs(pollNetworkFailures)
          options?.onRecoverablePollError?.({ attempt: pollNetworkFailures, delayMs })
          schedule(delayMs)
          return
        }
        stop()
        settled = true
        reject(e)
      }
    }

    void tick()
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

export function pollCoachHydration(
  jobId: string,
  onUpdate: (payload: CoachHydrationStatusPayload) => void,
  intervalMs = 2000,
): { promise: Promise<'complete' | 'fallback'>; cancel: () => void } {
  let settled = false
  let rejectRef: ((reason?: unknown) => void) | null = null
  let stopRef: (() => void) | null = null

  const promise = new Promise<'complete' | 'fallback'>((resolve, reject) => {
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
        const payload = await request<CoachHydrationStatusPayload>(`/analyze/${encodeURIComponent(jobId)}/coach`)
        onUpdate(payload)
        if (payload.status === 'complete' || payload.status === 'fallback') {
          stop()
          settled = true
          resolve(payload.status)
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
  musical_tolerance_mode?: 'expressive' | 'technique'
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
  /** Legacy alias: accepted for compatibility, mapped to pitch-class weights. */
  scale_position_map?: Record<string, number>
  pitch_class_weight_map?: Record<string, number>
  position_weight_map?: Record<string, number>
  inferred_scale_label?: string | null
  inference_confidence?: 'low' | 'medium' | 'high' | null
  track_id?: string | null
  track_label?: string | null
  track_key?: string | null
  track_bpm?: number | null
}): Promise<JamResult> {
  const pitchMap = payload.pitch_class_weight_map ?? payload.scale_position_map ?? {}
  return request<JamResult>('/jam-score', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      recording_wav_base64: payload.recording_wav_base64 ?? '',
      duration_seconds: payload.duration_seconds,
      scale_position_map: pitchMap,
      pitch_class_weight_map: pitchMap,
      position_weight_map: payload.position_weight_map ?? {},
      inferred_scale_label: payload.inferred_scale_label ?? null,
      inference_confidence: payload.inference_confidence ?? null,
      track_id: payload.track_id ?? null,
      track_label: payload.track_label ?? null,
      track_key: payload.track_key ?? null,
      track_bpm: payload.track_bpm ?? null,
    }),
  })
}

const QUICK_FEEDBACK_FALLBACK =
  'A few beats drifted — stay lighter on the pick and let each target note settle before you slide to the next.'

export async function submitQuickFeedback(
  payload: { accuracy_pattern: Array<'hit' | 'close' | 'miss' | 'vibrato'> },
  options?: { timeoutMs?: number },
): Promise<{ message: string }> {
  /** Server uses QUICK_FEEDBACK_TIMEOUT_SECONDS = 5; stay above that so we do not abort first. */
  const timeoutMs = options?.timeoutMs ?? 5500
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
  placement_confidence?: 'low' | 'medium' | 'high' | null
  reliability_flags?: string[]
}): Promise<{ coach_paragraph: string; confidence_note?: string | null }> {
  return request<{ coach_paragraph: string; confidence_note?: string | null }>('/onboarding-placement', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      ...payload,
      placement_confidence: payload.placement_confidence ?? null,
      reliability_flags: payload.reliability_flags ?? [],
    }),
  })
}

/** Commit 70: ordered practice plan from profile + analyzed library job ids. */
export async function generatePracticePlan(payload: {
  player_profile?: PlayerProfilePayload
  job_ids: string[]
  duration_minutes?: number
  mood?: 'focused' | 'loose' | 'tired' | 'on_fire'
  /** Device-persisted lessons when the API job store has no in-memory results. */
  library_lessons?: LessonJSON[]
}): Promise<PracticePlanPayload> {
  return request<PracticePlanPayload>('/practice/plan', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      player_profile: payload.player_profile ?? null,
      job_ids: payload.job_ids,
      duration_minutes: payload.duration_minutes ?? 25,
      mood: payload.mood ?? null,
      library_lessons: payload.library_lessons ?? [],
    }),
  })
}

/** Commit 65: backend-ranked next lesson suggestion from profile + library job ids. */
export async function fetchCurriculumSuggestion(payload: {
  player_profile?: PlayerProfilePayload
  job_ids: string[]
}): Promise<CurriculumSuggestion | null> {
  const body = {
    player_profile: payload.player_profile ?? null,
    job_ids: payload.job_ids,
  }
  const res = await request<CurriculumSuggestResponse>('/curriculum/suggest', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const ranked = Array.isArray(res.ranked) ? res.ranked : []
  return ranked.length > 0 ? ranked[0]! : null
}

/** Commit 68: deterministic taste profile (no network on server). */
export async function deriveTasteProfile(payload: {
  spotify_profile?: SpotifyTasteProfile
  quiz_answers?: QuizAnswersPayload
  taste_source?: 'spotify' | 'manual'
}): Promise<TasteProfilePayload> {
  return request<TasteProfilePayload>('/taste/derive', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

/** Commit 67: JSON `authorize_url` for in-app browser / manual redirect. */
export async function initiateSpotifyAuth(
  clientSession: string,
  platform: 'native' | 'web',
): Promise<string> {
  const res = await fetch(
    `${API_BASE_URL}/auth/spotify?client_session=${encodeURIComponent(clientSession)}&format=json&platform=${platform}`,
  )
  const text = await res.text().catch(() => '')
  if (!res.ok) {
    throw new ApiError(res.status, parseFastApiDetail(text))
  }
  let data: { authorize_url?: string }
  try {
    data = JSON.parse(text) as { authorize_url?: string }
  } catch {
    throw new ApiError(502, 'Invalid Spotify start response')
  }
  const url = typeof data.authorize_url === 'string' ? data.authorize_url.trim() : ''
  if (!url) {
    throw new ApiError(502, 'Missing authorize_url from server')
  }
  return url
}

export async function fetchSpotifyTasteProfile(clientSession: string): Promise<SpotifyTasteProfile> {
  return request<SpotifyTasteProfile>(
    `/taste/spotify?client_session=${encodeURIComponent(clientSession)}`,
  )
}

export async function fetchSpotifyPlaybackState(clientSession: string): Promise<SpotifyPlaybackStatePayload> {
  return request<SpotifyPlaybackStatePayload>(
    `/spotify/playback?client_session=${encodeURIComponent(clientSession)}`,
  )
}

export async function disconnectSpotifyServer(clientSession: string): Promise<void> {
  const res = await fetch(
    `${API_BASE_URL}/auth/spotify?client_session=${encodeURIComponent(clientSession)}`,
    { method: 'DELETE' },
  )
  if (!res.ok && res.status !== 204) {
    const text = await res.text().catch(() => '')
    throw new ApiError(res.status, parseFastApiDetail(text))
  }
}

/** Commit 85: plain-language theory rationale for a chord in a key context. */
export async function fetchTheoryAnnotation(payload: {
  key: string
  chord: string
  chord_function: string
}): Promise<{ rationale: string }> {
  return request<{ rationale: string }>('/theory/annotation', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

// ---------------------------------------------------------------------------
// Commit 108: Beat Grid Recompute API
// ---------------------------------------------------------------------------

export interface BeatGridRecomputeRequest {
  time_signature?: string | null
  bpm_override?: number | null
  reset_to_auto?: boolean
}

export interface BeatGridRecomputeResponse {
  job_id: string
  beat_grid: {
    bpm: number
    pulse_bpm: number
    beats: number[]
    downbeats: number[]
    time_signature: { numerator: number; denominator: number }
    tick_value: number
  }
  chord_timeline: { events: Array<{ timestamp: number; chord: string; confidence: number }> }
  solo_notes: { notes: Array<{ start_time: number; duration: number; pitch: number; velocity: number }> }
  musicxml: string
  recompute_stage: string
  invalidated_artifacts: string[]
}

export async function recomputeBeatGrid(
  jobId: string,
  payload: BeatGridRecomputeRequest,
): Promise<BeatGridRecomputeResponse> {
  return request<BeatGridRecomputeResponse>(`/analyze/${jobId}/beat-grid/recompute`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

// ---------------------------------------------------------------------------
// Commit 109: Analysis Correction APIs
// ---------------------------------------------------------------------------

import type { CorrectionHistory, CorrectionRecord } from '@/src/types'

export type { CorrectionRecord, CorrectionHistory } from '@/src/types'

export async function correctChord(
  jobId: string,
  beatIndex: number,
  payload: { chord: string; reason?: string },
): Promise<CorrectionRecord> {
  return request<CorrectionRecord>(`/analyze/${jobId}/chord/${beatIndex}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export async function correctSoloNote(
  jobId: string,
  noteIndex: number,
  payload: {
    pitch?: number
    start_time?: number
    duration?: number
    velocity?: number
    string?: number
    fret?: number
    reason?: string
  },
): Promise<CorrectionRecord> {
  return request<CorrectionRecord>(`/analyze/${jobId}/solo-note/${noteIndex}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export async function overrideVoicing(
  jobId: string,
  beatIndex: number,
  payload: { voicing_shape: string; reason?: string },
): Promise<CorrectionRecord> {
  return request<CorrectionRecord>(`/analyze/${jobId}/chord/${beatIndex}/voicing`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export async function getCorrectionHistory(jobId: string): Promise<CorrectionHistory> {
  return request<CorrectionHistory>(`/analyze/${jobId}/corrections`)
}

export async function revertCorrection(
  jobId: string,
  correctionIndex: number,
): Promise<CorrectionRecord> {
  return request<CorrectionRecord>(`/analyze/${jobId}/corrections/revert`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ correction_index: correctionIndex }),
  })
}

export async function exportCorrections(
  jobId: string,
  payload: { include_solo_notes?: boolean; include_voicings?: boolean; format?: 'json' | 'csv' },
): Promise<{ format: string; data: unknown; count: number }> {
  return request(`/analyze/${jobId}/corrections/export`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}
