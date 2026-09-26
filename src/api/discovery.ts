/**
 * Discovery API client for song recommendations based on harmonic similarity (commit 91).
 */

import type { DiscoveryRequest, DiscoveryResponse } from '@/src/types'
import { API_BASE_URL } from '@/src/config'

/**
 * Get discovery recommendations based on user's mastered songs and skill progress.
 */
export async function getDiscoveryRecommendations(request: DiscoveryRequest): Promise<DiscoveryResponse> {
  const response = await fetch(`${API_BASE_URL}/discovery/recommendations`, {
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
