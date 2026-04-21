import { getAppPref } from '@/src/db/client'
import { PREF_MOOD_CHECK_LAST_SHOWN_DAY, PREF_MOOD_CHECK_SKIP } from '@/src/db/schema'

/** Ordered session steps — matches `app/session/*.tsx` route segments (Commit 62 adds `tune`). */
export const SESSION_STEPS = ['tune', 'listen', 'study', 'slow', 'play', 'review'] as const
export type SessionStep = (typeof SESSION_STEPS)[number]

export function sessionStepIndexFromPathname(pathname: string): number {
  const normalized = pathname.replace(/\/+$/, '')
  const leaf = normalized.split(/[/\\]/).pop() ?? ''
  if (leaf === 'warmup') return SESSION_STEPS.indexOf('slow')
  const i = SESSION_STEPS.indexOf(leaf as SessionStep)
  return i >= 0 ? i : 0
}

export function sessionHref(step: SessionStep): `/session/${SessionStep}` {
  return `/session/${step}`
}

/** First session screen: pre-flight tuner (Commit 62) unless user chose to skip it. */
export function sessionEntryHref(skipTuneStep: boolean): `/session/${SessionStep}` {
  return skipTuneStep ? '/session/listen' : '/session/tune'
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
