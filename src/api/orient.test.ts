import { afterEach, describe, expect, it, vi } from 'vitest'

import { fetchOrientClip } from '@/src/api/orient'

vi.mock('@/src/config', () => ({ API_BASE_URL: 'http://api-test' }))

const CLIP = {
  wav_path: 'data/orient_clips/j1/orient_clip.wav',
  annotation: 'Listen for the bend',
  duration: 8,
  used_placeholder: false,
  placeholder_reason: null,
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('fetchOrientClip', () => {
  it('posts to /session/orient-clip and returns the parsed response', async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      status: 200,
      statusText: 'OK',
      json: async () => CLIP,
    }))
    vi.stubGlobal('fetch', fetchMock)

    const result = await fetchOrientClip({ job_id: 'j1', key: 'C major', bpm: 90 })

    expect(fetchMock).toHaveBeenCalledWith('http://api-test/session/orient-clip', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ job_id: 'j1', key: 'C major', bpm: 90 }),
    })
    expect(result).toEqual(CLIP)
  })

  it('throws ApiError with the FastAPI detail on a non-OK response', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        ok: false,
        status: 502,
        statusText: 'Bad Gateway',
        text: async () => '{"detail":"lyria unavailable"}',
      })),
    )

    await expect(fetchOrientClip({ job_id: 'j1' })).rejects.toMatchObject({
      name: 'ApiError',
      status: 502,
      message: 'lyria unavailable',
    })
  })
})
