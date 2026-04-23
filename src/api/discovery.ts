/**
 * Discovery API client for song recommendations based on harmonic similarity (commit 91).
 */

import type { DiscoveryRequest, DiscoveryResponse } from '@/src/types'

const API_BASE = process.env.EXPO_PUBLIC_API_BASE_URL || 'http://localhost:8000'

/**
 * Get discovery recommendations based on user's mastered songs and skill progress.
 */
export async function getDiscoveryRecommendations(request: DiscoveryRequest): Promise<DiscoveryResponse> {
  const response = await fetch(`${API_BASE}/discovery/recommendations`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(request),
  })

  if (!response.ok) {
    throw new Error(`Discovery request failed: ${response.status} ${response.statusText}`)
  }

  const data: DiscoveryResponse = await response.json()
  return data
}
