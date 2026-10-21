import { subscribeAnalyticsBackground } from '@/src/analytics/appLifecycle'
import type { AnalyticsEvent, NormalizedAnalyticsEvent } from '@/src/analytics/types'
import { getAppPref, insertAnalyticsEvents, setAppPref } from '@/src/db/client'
import { PREF_ANALYTICS_OPT_OUT, PREF_ANALYTICS_USER_ID } from '@/src/db/schema'
import type { AnalyticsEventRow } from '@/src/db/types'

export type { AnalyticsEvent, AnalyticsEventPayloads, AnalyticsEventType } from '@/src/analytics/types'

export const ANALYTICS_FLUSH_INTERVAL_MS = 30_000

type Subscriber = (event: NormalizedAnalyticsEvent) => void

let queue: NormalizedAnalyticsEvent[] = []
const subscribers = new Set<Subscriber>()
let enabled = true
let started = false
let flushTimer: ReturnType<typeof setInterval> | null = null
let unsubscribeBackground: (() => void) | null = null
let analyticsUserId: string | null = null
let flushChain: Promise<void> = Promise.resolve()

function createId(): string {
  return (
    globalThis.crypto?.randomUUID?.() ??
    `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`
  )
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

function ensureFlushTimer(): void {
  if (flushTimer != null || !enabled) return
  flushTimer = setInterval(() => {
    void flushAnalytics().catch(() => {
      /* flushAnalytics already logs and requeues */
    })
  }, ANALYTICS_FLUSH_INTERVAL_MS)
}

function stopFlushTimer(): void {
  if (flushTimer == null) return
  clearInterval(flushTimer)
  flushTimer = null
}

function ensureBackgroundListener(): void {
  if (unsubscribeBackground != null || !enabled) return
  unsubscribeBackground = subscribeAnalyticsBackground(() => {
    void flushAnalytics().catch(() => {
      /* flushAnalytics already logs and requeues */
    })
  })
}

function stopBackgroundListener(): void {
  if (unsubscribeBackground == null) return
  unsubscribeBackground()
  unsubscribeBackground = null
}

function teardown(): void {
  stopFlushTimer()
  stopBackgroundListener()
}

async function getOrCreateAnalyticsUserId(): Promise<string> {
  if (analyticsUserId) return analyticsUserId
  const existing = (await getAppPref(PREF_ANALYTICS_USER_ID))?.trim()
  if (existing) {
    analyticsUserId = existing
    return existing
  }
  const id = createId()
  await setAppPref(PREF_ANALYTICS_USER_ID, id)
  analyticsUserId = id
  return id
}

/**
 * Queue an analytics event locally. No-ops while analytics is disabled.
 * A UUID and ISO timestamp are assigned when the caller does not supply them.
 */
export function emit(event: AnalyticsEvent): void {
  if (!enabled) return
  const normalized: NormalizedAnalyticsEvent = {
    type: event.type,
    payload: event.payload,
    id: event.id ?? createId(),
    timestamp: event.timestamp ?? new Date().toISOString(),
  } as NormalizedAnalyticsEvent

  queue.push(normalized)
  for (const subscriber of [...subscribers]) {
    try {
      subscriber(normalized)
    } catch (e) {
      console.warn('[analytics] subscriber failed', errorMessage(e))
    }
  }
  if (started) ensureFlushTimer()
}

/** Observe accepted events (after opt-out checks). */
export function subscribe(handler: Subscriber): () => void {
  subscribers.add(handler)
  return () => {
    subscribers.delete(handler)
  }
}

/**
 * Persist queued events. Failed flushes re-queue the batch and reject so callers
 * can surface the failure; the 30s/background paths swallow after logging.
 */
export function flushAnalytics(): Promise<void> {
  const run = flushChain.then(async () => {
    if (!enabled || queue.length === 0) return
    const batch = queue.splice(0)
    try {
      const userId = await getOrCreateAnalyticsUserId()
      const rows: AnalyticsEventRow[] = batch.map((event) => ({
        id: event.id,
        user_id: userId,
        event_type: event.type,
        payload_json: JSON.stringify(event.payload),
        timestamp: event.timestamp,
      }))
      await insertAnalyticsEvents(rows)
    } catch (e) {
      queue = [...batch, ...queue]
      console.warn(`[analytics] flush failed; ${batch.length} event(s) re-queued: ${errorMessage(e)}`)
      throw e instanceof Error ? e : new Error(errorMessage(e))
    }
  })
  flushChain = run.catch(() => {
    /* keep the chain alive; the caller still sees the rejection */
  })
  return run
}

/** Start the 30s timer + background hook and load the opt-out pref. Idempotent. */
export async function startAnalytics(): Promise<void> {
  if (started) return
  started = true

  let optOut: string | null = null
  try {
    optOut = await getAppPref(PREF_ANALYTICS_OPT_OUT)
  } catch (e) {
    console.warn('[analytics] could not read opt-out pref; defaulting to enabled', errorMessage(e))
  }

  if (optOut === '1') {
    enabled = false
    queue = []
    teardown()
    return
  }

  enabled = true
  ensureFlushTimer()
  ensureBackgroundListener()
}

/** Stop the timer and background hook without changing the opt-out preference. */
export function stopAnalytics(): void {
  started = false
  teardown()
}

/**
 * Persist the opt-out pref before changing in-memory state. Throws if persistence
 * fails, leaving the bus state unchanged for the caller to report.
 */
export async function setAnalyticsEnabled(nextEnabled: boolean): Promise<void> {
  await setAppPref(PREF_ANALYTICS_OPT_OUT, nextEnabled ? '0' : '1')
  enabled = nextEnabled
  if (!nextEnabled) {
    queue = []
    started = false
    teardown()
    return
  }
  started = true
  ensureFlushTimer()
  ensureBackgroundListener()
}

/** Drop pending in-memory events without touching persisted rows. */
export function clearAnalyticsQueue(): void {
  queue = []
}
