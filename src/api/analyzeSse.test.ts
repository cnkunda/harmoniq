import { describe, it, expect, vi } from 'vitest'

import {
  createSseChunkParser,
  createAnalyzeSseSession,
  createUtf8Decoder,
  mapSseEventToJob,
  openAnalyzeSse,
} from './analyzeSse'
import type { AnalyzeJob } from '@/src/types'

// ---- createSseChunkParser ----

describe('createSseChunkParser', () => {
  it('parses multiple frames from a single chunk', () => {
    const parser = createSseChunkParser()
    const events = parser.push('event: connected\ndata: {"job_id":"a"}\n\nevent: heartbeat\ndata: {"ts":1}\n\n')
    expect(events).toEqual([
      { event: 'connected', data: '{"job_id":"a"}' },
      { event: 'heartbeat', data: '{"ts":1}' },
    ])
  })

  it('buffers frames split across chunk boundaries mid-line', () => {
    const parser = createSseChunkParser()
    expect(parser.push('event: sta')).toEqual([])
    expect(parser.push('tus\ndata: {"status":"pro')).toEqual([])
    expect(parser.push('cessing"}\n\n')).toEqual([{ event: 'status', data: '{"status":"processing"}' }])
  })

  it('only emits a frame once the blank line arrives', () => {
    const parser = createSseChunkParser()
    expect(parser.push('event: status\ndata: {}\n')).toEqual([])
    expect(parser.push('\n')).toEqual([{ event: 'status', data: '{}' }])
  })

  it('handles CRLF line endings, including a CRLF split across chunks', () => {
    const parser = createSseChunkParser()
    expect(parser.push('event: status\r\ndata: {"status":"queued"}\r\n\r')).toEqual([])
    const events = parser.push('\n')
    expect(events).toEqual([{ event: 'status', data: '{"status":"queued"}' }])
  })

  it('joins multi-line data fields with newlines and skips comments', () => {
    const parser = createSseChunkParser()
    const events = parser.push(': keep-alive\n event: ignored-comment\nno-colon-line\nevent: status\ndata: line1\ndata: line2\n\n')
    expect(events).toEqual([{ event: 'status', data: 'line1\nline2' }])
  })

  it('defaults the event name to message and drops data-less frames', () => {
    const parser = createSseChunkParser()
    expect(parser.push('data: plain\n\n')).toEqual([{ event: 'message', data: 'plain' }])
    expect(parser.push('event: heartbeat\n\n')).toEqual([])
  })
})

// ---- mapSseEventToJob ----

describe('mapSseEventToJob', () => {
  const statusPayload = JSON.stringify({
    status: 'processing',
    progress: 0.62,
    stage_label: 'Transcribing (MT3)…',
    analysis_stage: 'chords_inferring',
    processing_started_at: 1700000000,
    result: null,
    error: null,
    error_code: null,
  })

  it('maps a status frame to AnalyzeJob, forwarding analysis_stage', () => {
    const job = mapSseEventToJob({ event: 'status', data: statusPayload })
    expect(job).not.toBeNull()
    expect(job).toMatchObject({
      status: 'processing',
      progress: 0.62,
      stage_label: 'Transcribing (MT3)…',
      analysis_stage: 'chords_inferring',
      processing_started_at: 1700000000,
    })
  })

  it('maps complete with a result and failed with an error code', () => {
    const complete = mapSseEventToJob({
      event: 'complete',
      data: JSON.stringify({ status: 'complete', result: { job_id: 'j1' } }),
    })
    expect(complete?.status).toBe('complete')
    expect(complete?.result).toEqual({ job_id: 'j1' })

    const failed = mapSseEventToJob({
      event: 'failed',
      data: JSON.stringify({ status: 'failed', error: 'Analysis failed.', error_code: 'analysis_failed' }),
    })
    expect(failed).toMatchObject({
      status: 'failed',
      error: 'Analysis failed.',
      error_code: 'analysis_failed',
    })
  })

  it('ignores keep-alive and unknown frames', () => {
    expect(mapSseEventToJob({ event: 'connected', data: '{"job_id":"a"}' })).toBeNull()
    expect(mapSseEventToJob({ event: 'heartbeat', data: '{"ts":1}' })).toBeNull()
    expect(mapSseEventToJob({ event: 'message', data: '{"status":"processing"}' })).toBeNull()
  })

  it('throws on malformed or invalid payloads instead of silently skipping', () => {
    expect(() => mapSseEventToJob({ event: 'status', data: '{oops' })).toThrow(/malformed status payload/)
    expect(() => mapSseEventToJob({ event: 'status', data: '"a string"' })).toThrow(/not a JobStatus object/)
    expect(() => mapSseEventToJob({ event: 'failed', data: JSON.stringify({ status: 'exploded' }) })).toThrow(
      /invalid status/,
    )
  })
})

// ---- createAnalyzeSseSession ----

function makeHandlers() {
  const onJob = vi.fn<(job: AnalyzeJob) => void>()
  const onUnavailable = vi.fn<(err: unknown) => void>()
  return { onJob, onUnavailable, handlers: { onJob, onUnavailable } }
}

const processingJob = JSON.stringify({ status: 'processing', progress: 0.4, analysis_stage: 'stems_separating' })
const completeJob = JSON.stringify({ status: 'complete', result: { job_id: 'j1' } })

describe('createAnalyzeSseSession', () => {
  it('runs connect → events → terminal close', () => {
    const { onJob, onUnavailable, handlers } = makeHandlers()
    const session = createAnalyzeSseSession(handlers)

    expect(session.push('event: connected\ndata: {"job_id":"j1"}\n\n')).toBe('open')
    expect(session.push('event: heartbeat\ndata: {"ts":1}\n\n')).toBe('open')
    expect(onJob).not.toHaveBeenCalled() // keep-alives never reach consumers
    expect(onUnavailable).not.toHaveBeenCalled()

    expect(session.push(`event: status\ndata: ${processingJob}\n\n`)).toBe('open')
    expect(onJob).toHaveBeenCalledTimes(1)
    expect(onJob.mock.calls[0][0].analysis_stage).toBe('stems_separating')

    expect(session.push(`event: complete\ndata: ${completeJob}\n\n`)).toBe('closed')
    expect(session.isClosed()).toBe(true)
    expect(onJob).toHaveBeenCalledTimes(2)
    expect(onJob.mock.calls[1][0].status).toBe('complete')
    expect(onUnavailable).not.toHaveBeenCalled()
  })

  it('delivers nothing after a terminal status (BUG-01: no post-terminal work)', () => {
    const { onJob, onUnavailable, handlers } = makeHandlers()
    const session = createAnalyzeSseSession(handlers)

    session.push(`event: complete\ndata: ${completeJob}\n\n`)
    const callsAfterTerminal = onJob.mock.calls.length

    expect(session.push(`event: status\ndata: ${processingJob}\n\n`)).toBe('closed')
    expect(session.handleEvent({ event: 'failed', data: completeJob })).toBe('closed')
    session.fail(new Error('late transport error'))

    expect(onJob).toHaveBeenCalledTimes(callsAfterTerminal)
    expect(onUnavailable).not.toHaveBeenCalled() // a dead stream after terminal is not an error
  })

  it('reports an unavailable stream exactly once when the transport dies first', () => {
    const { onJob, onUnavailable, handlers } = makeHandlers()
    const session = createAnalyzeSseSession(handlers)

    session.push(`event: status\ndata: ${processingJob}\n\n`)
    session.fail(new Error('connection reset'))
    session.fail(new Error('second failure'))

    expect(onUnavailable).toHaveBeenCalledTimes(1)
    expect((onUnavailable.mock.calls[0][0] as Error).message).toBe('connection reset')
    expect(onJob).toHaveBeenCalledTimes(1)
    expect(session.isClosed()).toBe(true)
  })

  it('converts a malformed frame into an unavailable stream, never a silent skip', () => {
    const { onJob, onUnavailable, handlers } = makeHandlers()
    const session = createAnalyzeSseSession(handlers)

    expect(session.push('event: status\ndata: {broken\n\n')).toBe('closed')
    expect(onUnavailable).toHaveBeenCalledTimes(1)
    expect(onJob).not.toHaveBeenCalled()
    expect(session.isClosed()).toBe(true)
  })

  it('handles a terminal frame split across two raw chunks', () => {
    const { onJob, handlers } = makeHandlers()
    const session = createAnalyzeSseSession(handlers)

    expect(session.push('event: complete\ndata: {"status":"compl')).toBe('open')
    expect(onJob).not.toHaveBeenCalled()
    expect(session.push('ete","result":{"job_id":"j1"}}\n\n')).toBe('closed')
    expect(onJob).toHaveBeenCalledTimes(1)
    expect(onJob.mock.calls[0][0].status).toBe('complete')
  })
})

// ---- createUtf8Decoder ----

describe('createUtf8Decoder', () => {
  const encode = (text: string) => new TextEncoder().encode(text)

  it('decodes plain ASCII', () => {
    const decoder = createUtf8Decoder()
    expect(decoder.decode(encode('event: status'))).toBe('event: status')
  })

  it('carries a multi-byte sequence split across chunks (stage labels contain …)', () => {
    const decoder = createUtf8Decoder()
    const bytes = encode('Queued…')
    const splitAt = bytes.length - 2 // split inside the U+2026 sequence (E2 80 A6)
    expect(decoder.decode(bytes.slice(0, splitAt))).toBe('Queued')
    expect(decoder.decode(bytes.slice(splitAt))).toBe('…')
  })

  it('decodes 4-byte emoji code points as surrogate pairs', () => {
    const decoder = createUtf8Decoder()
    const bytes = encode('Ready 🎸') // 6 ASCII bytes + 4-byte F0 9F 8E B8
    expect(decoder.decode(bytes.slice(0, 8))).toBe('Ready ') // split inside the emoji sequence
    expect(decoder.decode(bytes.slice(8))).toBe('🎸')
  })

  it('throws loudly on an invalid lead byte', () => {
    const decoder = createUtf8Decoder()
    expect(() => decoder.decode(Uint8Array.from([0xff]))).toThrow(/invalid UTF-8 lead byte/)
  })
})

// ---- openAnalyzeSse availability ----

describe('openAnalyzeSse', () => {
  it('returns null in environments without EventSource or React Native streaming', () => {
    // vitest runs in node: no EventSource global, navigator.product is not ReactNative
    expect(typeof EventSource).toBe('undefined')
    expect(openAnalyzeSse('http://localhost:8000', 'job-1', { onJob: vi.fn(), onUnavailable: vi.fn() })).toBeNull()
  })
})
