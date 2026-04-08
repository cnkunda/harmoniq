/** Ordered session steps (commit 19) — matches `app/session/*.tsx` route segments. */
export const SESSION_STEPS = ['listen', 'study', 'slow', 'play', 'review'] as const
export type SessionStep = (typeof SESSION_STEPS)[number]

export function sessionStepIndexFromPathname(pathname: string): number {
  const normalized = pathname.replace(/\/+$/, '')
  const leaf = normalized.split(/[/\\]/).pop() ?? ''
  const i = SESSION_STEPS.indexOf(leaf as SessionStep)
  return i >= 0 ? i : 0
}

export function sessionHref(step: SessionStep): `/session/${SessionStep}` {
  return `/session/${step}`
}
