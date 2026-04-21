import type { ScoreResult } from '@/src/types'

const MAX_LEN = 1200

function clampText(s: string): string {
  const t = s.trim()
  if (t.length <= MAX_LEN) return t
  return `${t.slice(0, MAX_LEN - 1)}…`
}

function collectFlags(result: ScoreResult): string[] {
  const rel = result.reliability?.reliability_flags ?? []
  const diag = result.diagnostics?.reliability_flags ?? []
  return [...new Set([...rel, ...diag])]
}

/** Client-side coach copy when `coach_paragraph` is missing (older backends). */
function heuristicCoachReview(result: ScoreResult): string {
  const p = result.pitch_accuracy
  const ph = result.phrasing_score
  const r = result.rushing_score
  const flags = collectFlags(result)
  const conf = result.reliability?.confidence ?? 'medium'

  const pitchPct = Math.round(p * 100)
  const phrasePct = Math.round(ph * 100)
  const timingPct = Math.round(r * 100)

  const parts: string[] = []
  if (p >= 0.85 && ph >= 0.8) {
    parts.push(`Solid take—pitch near ${pitchPct}% and phrasing near ${phrasePct}%.`)
  } else if (p < 0.55) {
    parts.push(`Pitch is the main gap today (${pitchPct}%); match the reference in smaller chunks.`)
  } else {
    parts.push(`Pitch ${pitchPct}%, phrasing ${phrasePct}%.`)
  }

  if (r < 0.55) {
    parts.push(`Timing wants more pocket (${timingPct}%); subdivide with the click or backing.`)
  } else if (r >= 0.85) {
    parts.push('Timing is locking in nicely.')
  }

  if (flags.includes('timing_unstable')) {
    parts.push('We saw uneven timing residuals—shorter phrases usually help.')
  }
  if (flags.some((f) => f === 'signal_low' || f === 'signal_near_silence' || f === 'voiced_sparse')) {
    parts.push('Signal was light—move closer to the mic on the next pass.')
  }
  if (conf === 'low') {
    parts.push('Confidence is low on this capture, so treat these numbers as directional.')
  }

  return parts.join(' ').trim()
}

/**
 * Text for `sessions.coach_review`: prefers server `coach_paragraph` when present, else a local summary.
 */
export function coachReviewFromScoreResult(result: ScoreResult): string | null {
  const fromApi =
    typeof result.coach_paragraph === 'string' && result.coach_paragraph.trim() ? result.coach_paragraph.trim() : ''
  const text = fromApi || heuristicCoachReview(result)
  const out = clampText(text)
  return out.length > 0 ? out : null
}
