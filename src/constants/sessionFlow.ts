import { getAppPref } from '@/src/db/client'
import { PREF_MOOD_CHECK_LAST_SHOWN_DAY, PREF_MOOD_CHECK_SKIP } from '@/src/db/schema'

/**
 * Session flow — Commit 163 rewrite: Orient-as-Hint (de-gate Listen).
 *
 * Every route under `app/session/` is a session step. Steps fall into two sets:
 *
 * - `SESSION_STEPS` — every session route, in order. Used for route recognition,
 *   progress-bar length, and analytics. `listen` lives here as an *optional* step.
 * - `MANDATORY_SESSION_STEPS` — the default flow a learner walks. `listen` is
 *   excluded: it is opt-in via Settings ("Include Listen at session start") and
 *   reachable from the Study/Play header.
 *
 * Phase pre-flight steps (`tune`, `musical-tolerance`, `mood-check`) are not part
 * of the pedagogical phases (see `sessionPhases.ts`).
 */
export const SESSION_STEPS = ['tune', 'musical-tolerance', 'listen', 'study', 'slow', 'play', 'review'] as const
export type SessionStep = (typeof SESSION_STEPS)[number]

/** Steps a learner walks by default. `listen` is optional, not mandatory. */
export const MANDATORY_SESSION_STEPS: readonly SessionStep[] = [
  'tune',
  'musical-tolerance',
  'study',
  'slow',
  'play',
  'review',
] as const

/** Steps that are opt-in rather than part of the default flow. */
export const OPTIONAL_SESSION_STEPS: readonly SessionStep[] = ['listen'] as const

/** True when `step` is part of the default flow (not an opt-in extra). */
export function isMandatoryStep(step: SessionStep): boolean {
  return MANDATORY_SESSION_STEPS.includes(step)
}

/** True when `step` is opt-in (e.g. `listen`). */
export function isOptionalStep(step: SessionStep): boolean {
  return OPTIONAL_SESSION_STEPS.includes(step)
}

/** Ordered position of a step within the *default* flow (0-based). -1 = not in flow. */
export function mandatoryStepIndex(step: SessionStep): number {
  return MANDATORY_SESSION_STEPS.indexOf(step)
}

export function sessionStepIndexFromPathname(pathname: string): number {
  const normalized = pathname.replace(/\/+$/, '')
  const leaf = normalized.split(/[/\\]/).pop() ?? ''
  const i = SESSION_STEPS.indexOf(leaf as SessionStep)
  return i >= 0 ? i : -1
}

export function sessionHref(step: SessionStep): `/session/${SessionStep}` {
  return `/session/${step}`
}

/** First session screen: pre-flight tuner (Commit 62) unless user chose to skip it. */
export function sessionEntryHref(skipTuneStep: boolean): `/session/${SessionStep}` {
  return skipTuneStep ? '/session/musical-tolerance' : '/session/tune'
}

function currentLocalDayKey(): string {
  const d = new Date()
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

/** Commit 76: gate first daily session through mood check unless user enabled auto-skip. */
export async function sessionEntryHrefWithMoodCheck(
  skipTuneStep: boolean,
): Promise<`/session/${SessionStep}` | '/session/mood-check'> {
  const [skipMoodCheck, lastShown] = await Promise.all([
    getAppPref(PREF_MOOD_CHECK_SKIP),
    getAppPref(PREF_MOOD_CHECK_LAST_SHOWN_DAY),
  ])
  if (skipMoodCheck === '1') return sessionEntryHref(skipTuneStep)
  if ((lastShown ?? '').trim() === currentLocalDayKey()) return sessionEntryHref(skipTuneStep)
  return '/session/mood-check'
}