/**
 * Orient-clip API client.
 *
 * `POST /session/orient-clip` returns a backend-relative WAV path; callers
 * build the playable URL with `lessonFileUrl` (asset URLs are not API fetches).
 */

import { API_BASE_URL } from '@/src/config'

import { ApiError, parseFastApiDetail } from '@/src/api/analyze'

export type OrientClipRequest = {
  job_id: string
  style_label?: string | null
  technique?: string | null
  key?: string | null
  bpm?: number | null
}

export type OrientClipResponse = {
  wav_path: string
  annotation: string
  duration: number
  used_placeholder: boolean
  placeholder_reason: string | null
  annotation_source: 'template'
}

/** Generate or fetch the orient clip for a lesson job. */
export async function fetchOrientClip(request: OrientClipRequest): Promise<OrientClipResponse> {
  const response = await fetch(`${API_BASE_URL}/session/orient-clip`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  })

  if (!response.ok) {
    const body = await response.text().catch(() => '')
    throw new ApiError(response.status, parseFastApiDetail(body) || body || response.statusText)
  }

  return (await response.json()) as OrientClipResponse
}
