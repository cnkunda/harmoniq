import { describe, expect, it } from 'vitest'

import {
  README_ERROR_COPY,
  mapAnalyzeFlowError,
  mapBrowserMicBlockedForJam,
  mapLowTranscriptionConfidenceBanner,
  mapScoreFlowError,
} from '@/src/errors/mapErrorToUi'

function apiErr(
  status: number,
  message: string,
  errorCode?: string,
): Error & { status: number; errorCode?: string } {
  const e = new Error(message) as Error & { status: number; errorCode?: string }
  e.status = status
  if (errorCode) e.errorCode = errorCode
  return e
}

describe('README-aligned banners (MANUAL_QA §31–39)', () => {
  it('low transcription confidence uses README Error States copy', () => {
    const m = mapLowTranscriptionConfidenceBanner()
    expect(m.message).toBe(README_ERROR_COPY.lowTranscriptionConfidence)
    expect(m.actionKind).toBe('continue')
    expect(m.actionLabel).toBe('Continue')
  })

  it('browser mic blocked (Jam) uses README Error States copy', () => {
    const m = mapBrowserMicBlockedForJam()
    expect(m.message).toBe(README_ERROR_COPY.browserMicBlocked)
    expect(m.actionKind).toBe('retry')
    expect(m.actionLabel).toBe('Retry')
  })
})

describe('mapScoreFlowError', () => {
  it('uses README score copy with Do it again for HTTP /score errors', () => {
    const m = mapScoreFlowError(apiErr(400, 'bad'))
    expect(m.message).toBe(README_ERROR_COPY.scoreEndpointFailure)
    expect(m.actionLabel).toBe('Do it again')
    expect(m.actionKind).toBe('retry')
  })

  it('uses same README score copy when backend is unreachable (MANUAL_QA)', () => {
    const m = mapScoreFlowError(new TypeError('Failed to fetch'))
    expect(m.message).toBe(README_ERROR_COPY.scoreEndpointFailure)
    expect(m.actionLabel).toBe('Do it again')
    expect(m.actionKind).toBe('retry')
  })
})

describe('mapAnalyzeFlowError', () => {
  it('maps elapsed wall time over 5 min to analysis job timeout (Dismiss)', () => {
    const m = mapAnalyzeFlowError(apiErr(408, 'Analysis still running'), {
      elapsedMs: 5 * 60 * 1000 + 1,
    })
    expect(m.message).toBe(README_ERROR_COPY.analysisJobTimeout)
    expect(m.actionKind).toBe('dismiss')
    expect(m.actionLabel).toBe('Dismiss')
  })

  it('maps short audio body', () => {
    const m = mapAnalyzeFlowError(apiErr(400, 'clip too short under 30 sec'), {})
    expect(m.message).toBe(README_ERROR_COPY.audioTooShort)
    expect(m.actionKind).toBe('dismiss')
  })

  it('maps backend AUDIO_TOO_SHORT_USER_MESSAGE on 400 and on failed-job poll (500)', () => {
    const detail = README_ERROR_COPY.audioTooShort
    const post = mapAnalyzeFlowError(apiErr(400, detail), { usedYoutubeUrl: false })
    expect(post.message).toBe(detail)
    expect(post.actionKind).toBe('dismiss')
    const polled = mapAnalyzeFlowError(apiErr(500, detail), { usedYoutubeUrl: true })
    expect(polled.message).toBe(detail)
    expect(polled.actionKind).toBe('dismiss')
  })

  it('maps youtube 400 when flag set', () => {
    const m = mapAnalyzeFlowError(apiErr(400, 'invalid'), { usedYoutubeUrl: true })
    expect(m.message).toBe(README_ERROR_COPY.youtubeUrlInvalid)
  })

  it('maps youtube invalid worker message at 500 (poll failure)', () => {
    const m = mapAnalyzeFlowError(apiErr(500, README_ERROR_COPY.youtubeUrlInvalid), {})
    expect(m.message).toBe(README_ERROR_COPY.youtubeUrlInvalid)
    expect(m.actionKind).toBe('retry')
    expect(m.actionLabel).toBe('Retry')
  })

  it('maps generic 400 without youtube flag to analysis failed', () => {
    const m = mapAnalyzeFlowError(apiErr(400, 'invalid'), { usedYoutubeUrl: false })
    expect(m.message).toBe(README_ERROR_COPY.analysisJobFailed)
    expect(m.detail).toBe(README_ERROR_COPY.analyzeRetryHint)
  })

  it('maps poll/job failure 500 to analysis failed copy with Retry', () => {
    const m = mapAnalyzeFlowError(apiErr(500, README_ERROR_COPY.analysisJobFailed), {})
    expect(m.message).toBe(README_ERROR_COPY.analysisJobFailed)
    expect(m.actionKind).toBe('retry')
    expect(m.actionLabel).toBe('Retry')
    expect(m.detail).toBe(README_ERROR_COPY.analyzeRetryHint)
  })

  it('maps stem_separation_failed error_code to README stem separation copy (not no-guitar)', () => {
    const m = mapAnalyzeFlowError(
      apiErr(500, README_ERROR_COPY.stemSeparationFailed, 'stem_separation_failed'),
      {},
    )
    expect(m.message).toBe(README_ERROR_COPY.stemSeparationFailed)
    expect(m.detail).toBe(README_ERROR_COPY.analyzeRetryHint)
  })

  it('maps legacy separation failure body without error_code to stem separation copy', () => {
    const m = mapAnalyzeFlowError(apiErr(500, README_ERROR_COPY.stemSeparationFailed), {})
    expect(m.message).toBe(README_ERROR_COPY.stemSeparationFailed)
    expect(m.detail).toBe(README_ERROR_COPY.analyzeRetryHint)
  })

  it('maps no_usable_guitar_stem error_code to no-guitar README copy', () => {
    const m = mapAnalyzeFlowError(apiErr(500, 'unused', 'no_usable_guitar_stem'), {})
    expect(m.message).toBe(README_ERROR_COPY.noGuitarStem)
    expect(m.actionLabel).toBe('Try again')
    expect(m.detail).toBe(README_ERROR_COPY.analyzeRetryHint)
  })

  it('maps 502 to analysis failed', () => {
    const m = mapAnalyzeFlowError(apiErr(502, 'Bad Gateway'), {})
    expect(m.message).toBe(README_ERROR_COPY.analysisJobFailed)
    expect(m.detail).toBe(README_ERROR_COPY.analyzeRetryHint)
  })

  it('maps fetch TypeError to no-internet copy (unreachable backend)', () => {
    const m = mapAnalyzeFlowError(new TypeError('Failed to fetch'), {})
    expect(m.message).toBe(README_ERROR_COPY.noInternetAnalysis)
    expect(m.actionKind).toBe('dismiss')
  })

  it('maps client request timeout (connection copy) to no-internet README message', () => {
    const m = mapAnalyzeFlowError(
      apiErr(408, 'Request timed out. Check your connection and try again.'),
      {},
    )
    expect(m.message).toBe(README_ERROR_COPY.noInternetAnalysis)
    expect(m.actionKind).toBe('dismiss')
    expect(m.actionLabel).toBe('Dismiss')
  })
})
