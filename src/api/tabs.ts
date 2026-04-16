import { API_BASE_URL } from '@/src/config'

import { ApiError } from '@/src/api/analyze'

export type TabSearchHit = {
  id: string
  title: string
  artist: string | null
  source: string
}

export type TabSearchResponse = {
  hits: TabSearchHit[]
  provider: string
}

async function requestTabs<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`)
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new ApiError(res.status, body || res.statusText)
  }
  return res.json() as Promise<T>
}

/** Stub / future licensed catalog search. */
export async function searchTabs(query: string): Promise<TabSearchResponse> {
  const q = encodeURIComponent(query.trim())
  return requestTabs<TabSearchResponse>(`/tabs/search?q=${q}`)
}
