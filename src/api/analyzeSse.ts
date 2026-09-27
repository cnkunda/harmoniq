/**
 * SSE client for `GET /analyze/{job_id}/stream` (Commit 151 — BUG-01 root-cause fix).
 *
 * Transport chain lives in `src/api/analyze.ts`: SSE first, then WebSocket /
 * polling. This module owns the SSE wire protocol only:
 *
 * - `createSseChunkParser` — incremental `event:`/`data:` frame parsing
 * - `createAnalyzeSseSession` — connect → events → terminal-close state machine
 * - `openAnalyzeSse` — web `EventSource` / native `expo/fetch` reader, or `null`
 *   when the environment has no SSE support (caller falls back to polling)
 *
 * Server event vocabulary: `connected`, `status`, `complete`, `failed`, `heartbeat`.
 * Terminal statuses (`complete`/`failed`) close the session before delivery, so
 * no callback can fire after settlement and no transport keeps reconnecting.
 */

import type { AnalyzeJob, AnalyzeJobStatus, LessonJSON } from '@/src/types'

// ---- Wire parsing -----------------------------------------------------------------------------

/** One dispatched SSE frame: `event` defaults to `message` when the server omits it. */
export interface SseEvent {
  event: string
  data: string
}

export interface SseChunkParser {
  /** Feed a decoded text chunk; returns every frame completed by this chunk. */
  push(chunk: string): SseEvent[]
}

/**
 * Incremental parser for the SSE text wire format.
 *
 * Handles frames split at arbitrary byte boundaries, CRLF/CR line endings
 * (a trailing lone `\r` is held back in case the next chunk completes it
 * to `\r\n`), multi-line `data:` fields, and `:` comment lines. `id:`/`retry:`
 * fields are ignored — there is no client-side event replay.
 */
export function createSseChunkParser(): SseChunkParser {
  let buffer = ''

  const parseBlock = (block: string): SseEvent | null => {
    let event = 'message'
    const dataLines: string[] = []
    for (const line of block.split('\n')) {
      if (!line || line.startsWith(':')) continue
      const colon = line.indexOf(':')
      const field = colon < 0 ? line : line.slice(0, colon)
      let value = colon < 0 ? '' : line.slice(colon + 1)
      if (value.startsWith(' ')) value = value.slice(1)
      if (field === 'event') event = value
      else if (field === 'data') dataLines.push(value)
    }
    if (dataLines.length === 0) return null
    return { event, data: dataLines.join('\n') }
  }

  return {
    push(chunk: string): SseEvent[] {
      buffer += chunk
      // Normalize line endings, but hold a trailing \r back — it may be the
      // first half of a \r\n split across two chunks.
      const deferredCr = buffer.endsWith('\r')
      const ready = deferredCr ? buffer.slice(0, -1) : buffer
      const normalized = ready.replace(/\r\n/g, '\n').replace(/\r/g, '\n')
      const boundary = normalized.lastIndexOf('\n\n')
      if (boundary < 0) {
        buffer = deferredCr ? `${ready}\r` : buffer
        return []
      }
      const complete = normalized.slice(0, boundary)
      buffer = normalized.slice(boundary + 2) + (deferredCr ? '\r' : '')
      const events: SseEvent[] = []
      for (const block of complete.split('\n\n')) {
        const parsed = parseBlock(block)
        if (parsed !== null) events.push(parsed)
      }
      return events
    },
  }
}

// ---- Event → job mapping ----------------------------------------------------------------------

const TERMINAL_STATUSES: ReadonlySet<string> = new Set(['complete', 'failed'])

function isAnalyzeJobStatus(value: unknown): value is AnalyzeJobStatus {
  return value === 'queued' || value === 'processing' || value === 'complete' || value === 'failed'
}

/**
 * Map a server `status`/`complete`/`failed` frame onto `AnalyzeJob`.
 * Returns `null` for frames that carry no job update (`connected`, `heartbeat`,
 * unknown event names). Throws on malformed payloads — the session converts
 * that into an unavailable stream (transparent polling fallback), never a
 * silent skip.
 */
export function mapSseEventToJob(ev: SseEvent): AnalyzeJob | null {
  if (ev.event !== 'status' && ev.event !== 'complete' && ev.event !== 'failed') return null
  let parsed: unknown
  try {
    parsed = JSON.parse(ev.data)
  } catch {
    throw new Error(`malformed ${ev.event} payload: ${ev.data.slice(0, 120)}`)
  }
  if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error(`${ev.event} payload is not a JobStatus object`)
  }
  const rec = parsed as Record<string, unknown>
  if (!isAnalyzeJobStatus(rec.status)) {
    throw new Error(`${ev.event} payload has invalid status: ${String(rec.status)}`)
  }
  return {
    status: rec.status,
    result: (rec.result ?? null) as LessonJSON | null,
    error: typeof rec.error === 'string' ? rec.error : null,
    error_code: typeof rec.error_code === 'string' ? rec.error_code : null,
    progress: typeof rec.progress === 'number' ? rec.progress : null,
    stage_label: typeof rec.stage_label === 'string' ? rec.stage_label : null,
    processing_started_at: typeof rec.processing_started_at === 'number' ? rec.processing_started_at : null,
    analysis_stage: typeof rec.analysis_stage === 'string' ? rec.analysis_stage : null,
  }
}

// ---- Session state machine --------------------------------------------------------------------

export interface AnalyzeSseHandlers {
  /**
   * Every mapped job update, terminal ones included — the caller resolves or
   * rejects the job promise itself so polling and SSE share one code path.
   * Guaranteed not to fire after the session reports closed.
   */
  onJob: (job: AnalyzeJob) => void
  /** Stream failed before a terminal status. Fires at most once, only while open. */
  onUnavailable: (err: unknown) => void
}

export interface AnalyzeSseSession {
  /** Feed raw SSE text from a streaming reader. */
  push(text: string): 'open' | 'closed'
  /** Feed an already-named frame (EventSource delivers per-event-name, not raw text). */
  handleEvent(ev: SseEvent): 'open' | 'closed'
  /** The transport died before terminal. No-op once closed. */
  fail(err: unknown): void
  isClosed(): boolean
}

/**
 * Commit 151 state machine: connect → events → terminal close. Ignores
 * keep-alive frames, refuses every delivery after a terminal status, and
 * converts parse/mapping failures into `onUnavailable` so the caller can
 * fall back instead of hanging on a broken stream.
 */
export function createAnalyzeSseSession(handlers: AnalyzeSseHandlers): AnalyzeSseSession {
  const parser = createSseChunkParser()
  let closed = false

  const fail = (err: unknown): void => {
    if (closed) return
    closed = true
    handlers.onUnavailable(err)
  }

  const handleEvent = (ev: SseEvent): 'open' | 'closed' => {
    if (closed) return 'closed'
    let job: AnalyzeJob | null
    try {
      job = mapSseEventToJob(ev)
    } catch (err) {
      fail(err)
      return 'closed'
    }
    if (job === null) return 'open'
    const terminal = TERMINAL_STATUSES.has(job.status)
    if (terminal) closed = true // close before delivery: nothing may follow settlement
    handlers.onJob(job)
    return terminal ? 'closed' : 'open'
  }

  return {
    push(text: string): 'open' | 'closed' {
      if (closed) return 'closed'
      let events: SseEvent[]
      try {
        events = parser.push(text)
      } catch (err) {
        fail(err)
        return 'closed'
      }
      let state: 'open' | 'closed' = 'open'
      for (const ev of events) {
        state = handleEvent(ev)
        if (state === 'closed') break
      }
      return state
    },
    handleEvent,
    fail,
    isClosed(): boolean {
      return closed
    },
  }
}

// ---- Transports --------------------------------------------------------------------------------

export interface AnalyzeSseHandle {
  /** Tear down the connection. Safe to call more than once. */
  close(): void
}

const SSE_EVENT_NAMES = ['connected', 'status', 'complete', 'failed', 'heartbeat'] as const

function openEventSource(url: string, handlers: AnalyzeSseHandlers): AnalyzeSseHandle {
  const session = createAnalyzeSseSession(handlers)
  const source = new EventSource(url)

  const onNamed = (ev: Event): void => {
    const message = ev as MessageEvent<string>
    const state = session.handleEvent({ event: ev.type, data: String(message.data ?? '') })
    if (state === 'closed') source.close()
  }
  for (const name of SSE_EVENT_NAMES) source.addEventListener(name, onNamed)

  source.onerror = () => {
    // Transport-level failure only: server-sent `failed` frames arrive through
    // the named listener above and already closed the session. Closing first
    // stops EventSource's automatic reconnect, which would re-request the
    // stream after we decided to fall back.
    source.close()
    session.fail(new Error('SSE connection failed'))
  }

  return {
    close(): void {
      source.close()
    },
  }
}

/**
 * Incremental UTF-8 decoder for streaming readers.
 * Hermes has no `TextDecoder`, and stage labels contain multi-byte characters
 * (e.g. "Queued…") that can straddle chunk boundaries — bytes are carried
 * across `decode` calls until a sequence completes.
 */
export function createUtf8Decoder(): { decode(bytes: Uint8Array): string } {
  let pending: number[] = []

  const decodeOne = (bytes: Uint8Array, offset: number): { codePoint: number; length: number } | null => {
    const b0 = bytes[offset]
    if (b0 < 0x80) return { codePoint: b0, length: 1 }
    let codePoint: number
    let length: number
    if ((b0 & 0xe0) === 0xc0) {
      codePoint = b0 & 0x1f
      length = 2
    } else if ((b0 & 0xf0) === 0xe0) {
      codePoint = b0 & 0x0f
      length = 3
    } else if ((b0 & 0xf8) === 0xf0) {
      codePoint = b0 & 0x07
      length = 4
    } else {
      throw new Error(`invalid UTF-8 lead byte 0x${b0.toString(16)}`)
    }
    if (offset + length > bytes.length) return null // incomplete sequence at the tail
    for (let i = 1; i < length; i++) {
      const next = bytes[offset + i]
      if ((next & 0xc0) !== 0x80) {
        throw new Error('invalid UTF-8 continuation byte')
      }
      codePoint = (codePoint << 6) | (next & 0x3f)
    }
    return { codePoint, length }
  }

  const textEncoderFromCodePoint = (codePoint: number): string => {
    if (codePoint > 0xffff) {
      const shifted = codePoint - 0x10000
      return String.fromCharCode(0xd800 + (shifted >> 10), 0xdc00 + (shifted & 0x3ff))
    }
    return String.fromCharCode(codePoint)
  }

  return {
    decode(bytes: Uint8Array): string {
      const merged = pending.length > 0 ? Uint8Array.from([...pending, ...bytes]) : bytes
      pending = []
      let out = ''
      let i = 0
      while (i < merged.length) {
        const decoded = decodeOne(merged, i)
        if (decoded === null) {
          pending = Array.from(merged.slice(i))
          break
        }
        out += textEncoderFromCodePoint(decoded.codePoint)
        i += decoded.length
      }
      return out
    },
  }
}

/** `expo/fetch` is the only RN fetch whose `Response.body` is a ReadableStream. */
type ExpoFetchModule = { fetch: (input: string, init?: { signal?: AbortSignal }) => Promise<Response> }

async function readNativeStream(
  url: string,
  session: AnalyzeSseSession,
  signal: AbortSignal,
): Promise<void> {
  const { fetch: expoFetch } = require('expo/fetch') as ExpoFetchModule
  const res = await expoFetch(url, { signal })
  if (!res.ok || res.body == null) {
    throw new Error(`SSE HTTP ${res.status}${res.body == null ? ' without stream body' : ''}`)
  }
  const reader = res.body.getReader()
  const decoder = createUtf8Decoder()
  try {
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      if (value != null && session.push(decoder.decode(value)) === 'closed') break
    }
    if (!session.isClosed()) {
      throw new Error('SSE stream ended before a terminal status')
    }
  } finally {
    if (!signal.aborted) {
      void reader.cancel().catch((err: unknown) => {
        console.log('[analyzeSse] reader cancel failed:', err instanceof Error ? err.message : String(err))
      })
    }
  }
}

function openNativeFetchStream(url: string, handlers: AnalyzeSseHandlers): AnalyzeSseHandle {
  const session = createAnalyzeSseSession(handlers)
  const controller = new AbortController()
  void readNativeStream(url, session, controller.signal).catch((err: unknown) => {
    session.fail(err)
  })
  return {
    close(): void {
      controller.abort()
    },
  }
}

/**
 * Open `GET {baseUrl}/analyze/{job_id}/stream`. Returns `null` when the
 * environment supports neither `EventSource` (web) nor `expo/fetch` streaming
 * (native) — the caller must then fall back to its existing transport.
 *
 * Synchronous open failures return `null` (logged); failures after the stream
 * is open surface exactly once through `handlers.onUnavailable`.
 */
export function openAnalyzeSse(
  baseUrl: string,
  jobId: string,
  handlers: AnalyzeSseHandlers,
): AnalyzeSseHandle | null {
  const url = `${baseUrl}/analyze/${encodeURIComponent(jobId)}/stream`
  try {
    if (typeof EventSource !== 'undefined') return openEventSource(url, handlers)
    if (typeof navigator !== 'undefined' && navigator.product === 'ReactNative') {
      return openNativeFetchStream(url, handlers)
    }
  } catch (err) {
    console.log('[analyzeSse] open failed:', err instanceof Error ? err.message : String(err))
    return null
  }
  return null
}
