import type { Href } from 'expo-router'

import { BACKING_TRACKS, type BackingTrackDefinition } from '@/src/constants/backingTracks'

export type JamPracticeTrackInput = {
  trackId: string | null
  trackKey: string | null
  trackBpm: number | null
}

/**
 * Resolve a classic bundled loop for phrase practice.
 * Classic snapshots match by id; AI snapshots fall back to the same key/BPM when a loop exists.
 */
export function resolveJamPracticeTrack(input: JamPracticeTrackInput): BackingTrackDefinition | null {
  if (input.trackId) {
    const byId = BACKING_TRACKS.find((track) => track.id === input.trackId)
    if (byId) return byId
  }
  if (!input.trackKey) return null
  const sameKey = BACKING_TRACKS.filter((track) => track.key === input.trackKey)
  if (sameKey.length === 0) return null
  if (input.trackBpm != null) {
    const byTempo = sameKey.find((track) => track.bpm === input.trackBpm)
    if (byTempo) return byTempo
  }
  return sameKey.length === 1 ? sameKey[0]! : null
}

export function buildJamPracticeHref(input: {
  trackId: string
  startMs: number
  endMs: number
  phraseIndex: number
  source?: 'classic' | 'ai'
  key?: string | null
  bpm?: number | null
  progression?: string[] | null
  prompt?: string | null
}): Href {
  const params = [
    `trackId=${encodeURIComponent(input.trackId)}`,
    `startMs=${Math.max(0, Math.round(input.startMs))}`,
    `endMs=${Math.max(0, Math.round(input.endMs))}`,
    `phraseIndex=${input.phraseIndex}`,
  ]
  if (input.source) params.push(`source=${input.source}`)
  if (input.key) params.push(`key=${encodeURIComponent(input.key)}`)
  if (input.bpm != null) params.push(`bpm=${input.bpm}`)
  if (input.progression?.length) params.push(`progression=${encodeURIComponent(input.progression.join(','))}`)
  if (input.prompt) params.push(`prompt=${encodeURIComponent(input.prompt.slice(0, 400))}`)
  return `/jam-practice?${params.join('&')}` as Href
}
