/**
 * Commit 152 — Progressive Analysis Reveal.
 *
 * Maps the backend `analysis_stage` (Commit 109 / archive Commit 109) onto the
 * add-song progressive-reveal UI phase. The stage sequence is NOT monotonic —
 * `mt3_inferring` (0.60) is emitted after `chords_inferring` (0.62) and
 * `chords_inferring` re-appears on the CRNN fallback path — so an explicit
 * rank map is required instead of a string/`>=` comparison.
 */

/** UI phase for the add-song analyzing container. */
export type RevealPhase = 'spinner' | 'preview' | 'refining' | 'done'

/**
 * Phase per known stage. Unknown future stages intentionally map to
 * `preview` so a new stage can never resurrect the removed monolithic spinner.
 */
const STAGE_PHASES: Readonly<Record<string, RevealPhase>> = {
  initializing: 'spinner',
  stems_separating: 'spinner',
  chords_inferring: 'preview',
  mt3_inferring: 'preview',
  solo_inferring: 'refining',
  building_musicxml: 'refining',
  complete: 'done',
}

/**
 * Derive the reveal phase from a job's `analysis_stage`.
 * Missing/unknown stages degrade safely: null → spinner (job just created),
 * unknown string → preview (progressive container, never the monolithic spinner).
 */
export function getRevealPhase(analysisStage: string | null | undefined): RevealPhase {
  if (analysisStage == null || analysisStage === '') return 'spinner'
  return STAGE_PHASES[analysisStage] ?? 'preview'
}

/**
 * Whether the chord-chart preview container should be rendered for a phase.
 * The spinner covers only the early `spinner` phase; everything later uses
 * the progressive preview + compact banner.
 */
export function shouldShowPreview(
  phase: RevealPhase,
  hasPartialResult: boolean,
): boolean {
  // `done` means the terminal frame arrived while the screen is still in its
  // analyzing state (min-wait before the swap) — keep the preview up rather
  // than flashing the spinner back.
  if (phase === 'done') return hasPartialResult
  if (phase === 'spinner') return hasPartialResult
  return true
}
