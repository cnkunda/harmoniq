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
