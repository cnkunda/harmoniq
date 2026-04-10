import type { ScoreResult } from '@/src/types'

/** Parses persisted `sessions.review_snapshot` JSON into a usable ScoreResult (waveforms optional). */
export function parseScoreSnapshot(raw: string | null | undefined): ScoreResult | null {
  if (raw == null || raw.trim() === '') return null
  try {
    const o = JSON.parse(raw) as Partial<ScoreResult>
    if (typeof o.pitch_accuracy !== 'number' || !Number.isFinite(o.pitch_accuracy)) return null
    const wc = o.waveform_comparison
    const userB64 =
      wc && typeof wc === 'object' && typeof wc.user_wav_base64 === 'string' ? wc.user_wav_base64 : ''
    const refB64 =
      wc && typeof wc === 'object' && typeof wc.reference_wav_base64 === 'string' ? wc.reference_wav_base64 : ''
    return {
      pitch_accuracy: o.pitch_accuracy,
      note_duration_deltas: Array.isArray(o.note_duration_deltas)
        ? (o.note_duration_deltas as number[])
        : [],
      phrasing_score: typeof o.phrasing_score === 'number' && Number.isFinite(o.phrasing_score) ? o.phrasing_score : 0,
      bend_pitch_error_cents:
        typeof o.bend_pitch_error_cents === 'number' && Number.isFinite(o.bend_pitch_error_cents)
          ? o.bend_pitch_error_cents
          : 0,
      rushing_score: typeof o.rushing_score === 'number' && Number.isFinite(o.rushing_score) ? o.rushing_score : 0,
      node_scores:
        o.node_scores && typeof o.node_scores === 'object' && !Array.isArray(o.node_scores)
          ? (o.node_scores as Record<string, number>)
          : {},
      waveform_comparison: {
        user_wav_base64: userB64,
        reference_wav_base64: refB64,
      },
    }
  } catch {
    return null
  }
}
