import { API_BASE_URL } from '@/src/config'

import { ApiError } from '@/src/api/analyze'

export type JamBackingRequestBody = {
  musical_key: string
  bpm?: number | null
  weak_areas?: string[]
  style_hint?: string | null
}

export type JamBackingResponseBody = {
  audio_base64: string
  mime_type: string
  format: string
  prompt_used: string
  duration_ms?: number | null
}

export async function requestJamBacking(body: JamBackingRequestBody): Promise<JamBackingResponseBody> {
  const res = await fetch(`${API_BASE_URL}/jam/backing`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      musical_key: body.musical_key,
      bpm: body.bpm ?? null,
      weak_areas: body.weak_areas ?? [],
      style_hint: body.style_hint ?? null,
    }),
  })
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new ApiError(res.status, text || res.statusText)
  }
  return res.json() as Promise<JamBackingResponseBody>
}
