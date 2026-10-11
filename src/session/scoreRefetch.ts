// Commit 153: debounced score refetch after correction mutations

/**
 * Trailing-debounce window for coalescing rapid successive corrections into a
 * single refetch (chord taps in quick succession must not storm the API).
 */
export const SCORE_REFETCH_DEBOUNCE_MS = 300

export interface ScoreRefetchSchedulerOptions<T> {
  /** Fetch the current job payload (e.g. `GET /analyze/{job_id}`). */
  fetchJob: (jobId: string) => Promise<T>
  /** Apply a successfully fetched payload (e.g. persist the lesson). May be async. */
  applyResult: (result: T) => void | Promise<void>
  /** Called when a refetch run fails — surface loudly (toast), never swallow. */
  onError: (jobId: string, error: unknown) => void
  /**
   * Emits after every state transition: true while a debounced run is pending
   * or a fetch is in flight, false when idle. Drives the "Updating score…" UI.
   */
  onStateChange?: (updating: boolean) => void
  debounceMs?: number
}

export interface ScoreRefetchScheduler {
  /** Schedule a debounced refetch for `jobId`, replacing any pending schedule. */
  request: (jobId: string) => void
  /** Cancel any pending debounced run (an in-flight fetch still settles). */
  cancel: () => void
}

/**
 * Create a debounced refetch scheduler (Commit 153).
 *
 * Guarantees:
 * - Rapid `request()` calls within the window coalesce into ONE fetch.
 * - At most one fetch is in flight; a `request()` landing mid-flight is
 *   re-scheduled after the in-flight run settles (with a fresh debounce window).
 * - `onError` fires per failed run; the scheduler never rejects unhandled.
 */
export function createScoreRefetchScheduler<T>(options: ScoreRefetchSchedulerOptions<T>): ScoreRefetchScheduler {
  const { fetchJob, applyResult, onError, onStateChange, debounceMs = SCORE_REFETCH_DEBOUNCE_MS } = options

  let timer: ReturnType<typeof setTimeout> | null = null
  let inFlight = false
  let queuedJobId: string | null = null

  const emit = (): void => {
    onStateChange?.(timer !== null || inFlight)
  }

  const clearTimer = (): void => {
    if (timer !== null) {
      clearTimeout(timer)
      timer = null
    }
  }

  const run = async (jobId: string): Promise<void> => {
    if (inFlight) {
      queuedJobId = jobId
      return
    }
    inFlight = true
    emit()
    try {
      const result = await fetchJob(jobId)
      await applyResult(result)
    } catch (e) {
      onError(jobId, e)
    } finally {
      inFlight = false
      if (queuedJobId !== null) {
        const next = queuedJobId
        queuedJobId = null
        schedule(next)
      } else {
        emit()
      }
    }
  }

  const schedule = (jobId: string): void => {
    clearTimer()
    timer = setTimeout(() => {
      timer = null
      void run(jobId)
    }, debounceMs)
    emit()
  }

  return {
    request: schedule,
    cancel: () => {
      clearTimer()
      queuedJobId = null
      emit()
    },
  }
}
