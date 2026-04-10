import { describe, expect, it } from 'vitest'

import { README_ERROR_COPY, mapAnalyzeFlowError, mapScoreFlowError } from '@/src/errors/mapErrorToUi'

function apiErr(status: number, message: string): Error & { status: number } {
  const e = new Error(message) as Error & { status: number }
  e.status = status
  return e
}

describe('mapScoreFlowError', () => {
  it('uses README score copy with retry action', () => {
    const m = mapScoreFlowError(apiErr(400, 'bad'))
    expect(m.message).toBe(README_ERROR_COPY.scoreEndpointFailure)
    expect(m.actionLabel).toBe('Do it again')
    expect(m.actionKind).toBe('retry')
  })
})

describe('mapAnalyzeFlowError', () => {
  it('maps short audio body', () => {
    const m = mapAnalyzeFlowError(apiErr(400, 'clip too short under 30 sec'), {})
    expect(m.message).toBe(README_ERROR_COPY.audioTooShort)
    expect(m.actionKind).toBe('dismiss')
  })

  it('maps youtube 400 when flag set', () => {
    const m = mapAnalyzeFlowError(apiErr(400, 'invalid'), { usedYoutubeUrl: true })
    expect(m.message).toBe(README_ERROR_COPY.youtubeUrlInvalid)
  })

  it('maps generic 400 without youtube flag to analysis failed', () => {
    const m = mapAnalyzeFlowError(apiErr(400, 'invalid'), { usedYoutubeUrl: false })
    expect(m.message).toBe(README_ERROR_COPY.analysisJobFailed)
  })
})
