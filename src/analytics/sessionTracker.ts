import { emit } from '@/src/analytics/eventBus'
import { SESSION_STEPS, sessionStepIndexFromPathname } from '@/src/constants/sessionFlow'

type ActiveSession = {
  startedAtMs: number
  startedAtIso: string
  entryStep: string
  lastStep: string
  songTitle: string | null
}

export type SessionTrackerContext = {
  songTitle?: string | null
}

/**
 * Grace period before reporting an abandon. React StrictMode mounts effects twice
 * (cleanup immediately followed by re-mount), and this lets the re-mount cancel it.
 */
export const SESSION_LEAVE_GRACE_MS = 300

let activeSession: ActiveSession | null = null
let pendingAbandon: ReturnType<typeof setTimeout> | null = null

function cancelPendingAbandon(): void {
  if (pendingAbandon == null) return
  clearTimeout(pendingAbandon)
  pendingAbandon = null
}

function secondsBetween(startMs: number, endMs: number): number {
  return Math.max(0, Math.round((endMs - startMs) / 1000))
}

function resolvedStep(pathname: string): string | null {
  const index = sessionStepIndexFromPathname(pathname)
  return index >= 0 ? (SESSION_STEPS[index] ?? null) : null
}

/**
 * Feed session pathname changes here. Starts exactly one session on the first
 * recognized step and emits progress only when the step actually changes.
 */
export function trackSessionPathname(pathname: string, context: SessionTrackerContext = {}): void {
  const step = resolvedStep(pathname)
  if (!step) return

  cancelPendingAbandon()
  const songTitle = typeof context.songTitle === 'string' ? context.songTitle.trim() || null : null

  if (!activeSession) {
    const now = new Date()
    activeSession = {
      startedAtMs: now.getTime(),
      startedAtIso: now.toISOString(),
      entryStep: step,
      lastStep: step,
      songTitle,
    }
    emit({
      type: 'session_start',
      payload: { song_title: songTitle, step },
    })
    return
  }

  if (songTitle && !activeSession.songTitle) activeSession.songTitle = songTitle
  if (step === activeSession.lastStep) return

  const fromStep = activeSession.lastStep
  activeSession.lastStep = step
  emit({
    type: 'session_step_progress',
    payload: {
      from_step: fromStep,
      to_step: step,
      elapsed_sec: secondsBetween(activeSession.startedAtMs, Date.now()),
    },
  })
}

/**
 * Mark the active session complete and clear it. Idempotent: later layout unmounts
 * cannot emit a second complete or an abandon.
 */
export function completeSession(endedAt: Date = new Date()): void {
  if (!activeSession) return
  const session = activeSession
  activeSession = null
  cancelPendingAbandon()
  emit({
    type: 'session_complete',
    payload: {
      song_title: session.songTitle,
      duration_sec: secondsBetween(session.startedAtMs, endedAt.getTime()),
      final_step: session.lastStep,
      started_at: session.startedAtIso,
    },
  })
}

/** Report the active session as abandoned, if one is still open. */
export function abandonActiveSession(endedAt: Date = new Date()): void {
  if (!activeSession) return
  const session = activeSession
  activeSession = null
  cancelPendingAbandon()
  emit({
    type: 'session_abandon',
    payload: {
      song_title: session.songTitle,
      duration_sec: secondsBetween(session.startedAtMs, endedAt.getTime()),
      last_step: session.lastStep,
    },
  })
}

/**
 * Call from the session layout cleanup. Delayed so StrictMode re-mounts can cancel it.
 */
export function handleSessionLayoutUnmount(): void {
  if (!activeSession) return
  cancelPendingAbandon()
  pendingAbandon = setTimeout(() => {
    pendingAbandon = null
    abandonActiveSession()
  }, SESSION_LEAVE_GRACE_MS)
}
