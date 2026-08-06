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

// ---------------------------------------------------------------------------
// Commit 111: Jam Mode Summary Agent
// ---------------------------------------------------------------------------

export type JamPhraseMetrics = {
  duration_ms: number
  notes_per_second: number
  unique_pitch_classes: number
  midi_span: number
  contour: 'rising' | 'falling' | 'arch' | 'static' | 'mixed'
  beat_offset_mean?: number
  beat_offset_std?: number
  home_pitch_class?: string | null
  transition_from?: string | null
  transition_gap_ms?: number
}

export type JamVocabularyPattern = {
  pattern_id: string
  pattern_type: 'motif' | 'sequence' | 'arpeggio' | 'scale_run' | 'bend_figure' | 'repeated_note'
  pitch_classes: string[]
  occurrence_count: number
  confidence: number
  description: string
}

export type JamSummaryBundle = {
  chord: string | null
  clarity: number
  intonation_cents: Record<string, number>
  timing_ms: number
  transition_from: string | null
  transition_gap_ms: number
  phrase_count: number
  total_notes: number
  avg_notes_per_second: number
  dominant_contour: string
  pitch_class_distribution: Record<string, number>
  vocabulary_patterns: JamVocabularyPattern[]
  vocabulary_diversity: number
  coach_summary: string
  coach_strengths: string[]
  coach_focus_areas: string[]
  coach_next_step: string
  persona: 'learner' | 'intermediate' | 'transcriber'
  duration_seconds: number
  inferred_scale_label: string | null
  inference_confidence: 'low' | 'medium' | 'high' | null
}

export type JamSummaryRequestBody = {
  duration_seconds: number
  pitch_class_weight_map?: Record<string, number>
  inferred_scale_label?: string | null
  inference_confidence?: 'low' | 'medium' | 'high' | null
  track_id?: string | null
  track_label?: string | null
  track_key?: string | null
  track_bpm?: number | null
  phrases?: JamPhraseMetrics[]
  player_level?: 'beginner' | 'intermediate' | 'advanced'
  persona?: 'learner' | 'intermediate' | 'transcriber' | null
  previous_jam_count?: number
  weak_areas?: string[]
}

export type JamSummaryResponseBody = {
  bundle: JamSummaryBundle
  coach_summary: string
}

export async function submitJamSummary(body: JamSummaryRequestBody): Promise<JamSummaryResponseBody> {
  const res = await fetch(`${API_BASE_URL}/jam/summary`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new ApiError(res.status, text || res.statusText)
  }
  return res.json() as Promise<JamSummaryResponseBody>
}
