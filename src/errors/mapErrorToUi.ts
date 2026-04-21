function isApiLikeError(err: unknown): err is { status: number; message: string } {
  if (typeof err !== 'object' || err === null) return false
  const o = err as Record<string, unknown>
  return typeof o.status === 'number' && typeof o.message === 'string'
}

function analyzeFlowErrorCode(err: unknown): string | undefined {
  if (typeof err !== 'object' || err === null) return undefined
  const o = err as Record<string, unknown>
  const fromApi = o.errorCode
  if (typeof fromApi === 'string' && fromApi.length > 0) return fromApi
  const snake = o.error_code
  if (typeof snake === 'string' && snake.length > 0) return snake
  return undefined
}

/** Matches README.md § Error States — do not show raw stacks; use these strings. */
export const README_ERROR_COPY = {
  micPermissionDenied:
    "Harmoniq needs to hear you play. Here's how to turn on mic access.",
  youtubeUrlInvalid: "That URL didn't work — make sure it's a full YouTube link and try again.",
  analysisJobFailed:
    'Something went wrong processing that song. Try a studio recording — live versions sometimes have unusual audio.',
  analysisJobTimeout:
    "This one's taking longer than usual. We'll notify you when it's ready.",
  noInternetAnalysis:
    'You need a connection to analyze a new song. Your existing library works offline.',
  audioTooShort: 'That clip is too short to analyze. Try a full song or a longer section.',
  scoreEndpointFailure: "Couldn't score that take — tap 'Do it again' to try once more.",
  noGuitarStem:
    "Couldn't isolate a clear guitar track from this recording. Try a different version of the song.",
  /** Must match `STEM_SEPARATION_FAILED_USER_MESSAGE` in `backend/app/jobs.py`. */
  stemSeparationFailed:
    'Something went wrong separating guitar stems. Try a studio recording — live versions sometimes have unusual audio.',
  /** Shown under primary copy when retry may need a different source, not the same file. */
  analyzeRetryHint:
    'Try another mix or studio recording, or use a different upload or YouTube version.',
  /** Must stay in sync with README.md § Error States — Low transcription confidence. */
  lowTranscriptionConfidence:
    'This part is a rough approximation — use it as a guide, not a rule.',
  browserMicBlocked:
    'Your browser is blocking mic access — click the lock icon to enable it.',
} as const

export type ErrorUiVariant = 'warning' | 'error' | 'info'

/** How the primary action button should behave (README “Action” column). */
export type UiErrorActionKind = 'retry' | 'dismiss' | 'open_settings' | 'continue' | null

export type MappedUiError = {
  message: string
  variant: ErrorUiVariant
  actionKind: UiErrorActionKind
  /** Button label; `null` when `actionKind` is null. */
  actionLabel: string | null
  /** Secondary line under the main message (e.g. retry hints for analyze). */
  detail?: string | null
}

function networkishMessage(err: unknown): boolean {
  if (err instanceof TypeError) return true
  const msg = err instanceof Error ? err.message : String(err)
  return /network|fetch|failed to load|internet|offline|connection|timed out/i.test(msg)
}

function bodyLooksShort(body: string): boolean {
  const b = body.toLowerCase()
  return b.includes('too short') || b.includes('30 sec') || b.includes('30s') || b.includes('duration')
}

function bodyLooksStemSeparationFailure(body: string): boolean {
  const b = body.toLowerCase()
  return b.includes('separating') && b.includes('guitar') && b.includes('stem')
}

function bodyLooksNoStem(body: string): boolean {
  const b = body.toLowerCase()
  if (bodyLooksStemSeparationFailure(body)) return false
  return b.includes('guitar') && (b.includes('stem') || b.includes('isolate') || b.includes('no clear'))
}

/** Analyze / add-song flow: submit + poll failures. */
export function mapAnalyzeFlowError(
  err: unknown,
  ctx: { usedYoutubeUrl?: boolean; elapsedMs?: number },
): MappedUiError {
  const timeoutMs = 5 * 60 * 1000
  if (typeof ctx.elapsedMs === 'number' && ctx.elapsedMs > timeoutMs) {
    return {
      message: README_ERROR_COPY.analysisJobTimeout,
      variant: 'info',
      actionKind: 'dismiss',
      actionLabel: 'Dismiss',
    }
  }

  if (typeof navigator !== 'undefined' && navigator.onLine === false) {
    return {
      message: README_ERROR_COPY.noInternetAnalysis,
      variant: 'warning',
      actionKind: 'dismiss',
      actionLabel: 'Dismiss',
    }
  }

  if (networkishMessage(err)) {
    return {
      message: README_ERROR_COPY.noInternetAnalysis,
      variant: 'warning',
      actionKind: 'dismiss',
      actionLabel: 'Dismiss',
    }
  }

  if (isApiLikeError(err)) {
    const body = err.message?.trim() ?? ''
    const code = analyzeFlowErrorCode(err)

    if (bodyLooksShort(body)) {
      return {
        message: README_ERROR_COPY.audioTooShort,
        variant: 'warning',
        actionKind: 'dismiss',
        actionLabel: 'Dismiss',
      }
    }

    if (code === 'youtube_invalid') {
      return {
        message: README_ERROR_COPY.youtubeUrlInvalid,
        variant: 'error',
        actionKind: 'retry',
        actionLabel: 'Retry',
      }
    }
    if (code === 'audio_too_short') {
      return {
        message: README_ERROR_COPY.audioTooShort,
        variant: 'warning',
        actionKind: 'dismiss',
        actionLabel: 'Dismiss',
      }
    }
    if (code === 'stem_separation_failed') {
      return {
        message: README_ERROR_COPY.stemSeparationFailed,
        variant: 'error',
        actionKind: 'retry',
        actionLabel: 'Retry',
        detail: README_ERROR_COPY.analyzeRetryHint,
      }
    }
    if (code === 'ingest_failed' || code === 'analysis_failed') {
      return {
        message: README_ERROR_COPY.analysisJobFailed,
        variant: 'error',
        actionKind: 'retry',
        actionLabel: 'Retry',
        detail: README_ERROR_COPY.analyzeRetryHint,
      }
    }
    if (code === 'no_usable_guitar_stem') {
      return {
        message: README_ERROR_COPY.noGuitarStem,
        variant: 'warning',
        actionKind: 'retry',
        actionLabel: 'Try again',
        detail: README_ERROR_COPY.analyzeRetryHint,
      }
    }

    if (bodyLooksStemSeparationFailure(body)) {
      return {
        message: README_ERROR_COPY.stemSeparationFailed,
        variant: 'error',
        actionKind: 'retry',
        actionLabel: 'Retry',
        detail: README_ERROR_COPY.analyzeRetryHint,
      }
    }

    if (bodyLooksNoStem(body)) {
      return {
        message: README_ERROR_COPY.noGuitarStem,
        variant: 'warning',
        actionKind: 'retry',
        actionLabel: 'Try again',
        detail: README_ERROR_COPY.analyzeRetryHint,
      }
    }
    // Async analyze: invalid YouTube URLs fail in the worker; poll surfaces ApiError(500, YOUTUBE_URL_INVALID_USER_MESSAGE).
    // Sync path: some deployments may return HTTP 400 on POST.
    if (
      body === README_ERROR_COPY.youtubeUrlInvalid ||
      (ctx.usedYoutubeUrl && err.status === 400)
    ) {
      return {
        message: README_ERROR_COPY.youtubeUrlInvalid,
        variant: 'error',
        actionKind: 'retry',
        actionLabel: 'Retry',
      }
    }
    if (err.status === 500 || err.status === 502 || err.status === 503) {
      return {
        message: README_ERROR_COPY.analysisJobFailed,
        variant: 'error',
        actionKind: 'retry',
        actionLabel: 'Retry',
        detail: README_ERROR_COPY.analyzeRetryHint,
      }
    }
    if (err.status === 404) {
      return {
        message: README_ERROR_COPY.analysisJobFailed,
        variant: 'error',
        actionKind: 'retry',
        actionLabel: 'Retry',
        detail: README_ERROR_COPY.analyzeRetryHint,
      }
    }
    if (err.status >= 400) {
      return {
        message: README_ERROR_COPY.analysisJobFailed,
        variant: 'error',
        actionKind: 'retry',
        actionLabel: 'Retry',
        detail: README_ERROR_COPY.analyzeRetryHint,
      }
    }
  }

  return {
    message: README_ERROR_COPY.analysisJobFailed,
    variant: 'error',
    actionKind: 'retry',
    actionLabel: 'Retry',
    detail: README_ERROR_COPY.analyzeRetryHint,
  }
}

/** Review / onboarding placement POST /score failures (MANUAL_QA: backend down or HTTP error → same copy). */
export function mapScoreFlowError(_err?: unknown): MappedUiError {
  return {
    message: README_ERROR_COPY.scoreEndpointFailure,
    variant: 'error',
    actionKind: 'retry',
    actionLabel: 'Do it again',
  }
}

/** Mic permission denied (Play / recorder). Pass `Platform.OS` from the app layer. */
export function mapMicPermissionDenied(platformOS: string): MappedUiError {
  const isWeb = platformOS === 'web'
  return {
    message: README_ERROR_COPY.micPermissionDenied,
    variant: 'error',
    actionKind: isWeb ? 'dismiss' : 'open_settings',
    actionLabel: isWeb ? 'Dismiss' : 'Open Settings',
  }
}

/** Web getUserMedia / pitch stream blocked (Jam). */
export function mapBrowserMicBlockedForJam(): MappedUiError {
  return {
    message: README_ERROR_COPY.browserMicBlocked,
    variant: 'error',
    actionKind: 'retry',
    actionLabel: 'Retry',
  }
}

/** Study step — lesson-level transcription confidence (README low confidence copy). */
export function mapLowTranscriptionConfidenceBanner(): MappedUiError {
  return {
    message: README_ERROR_COPY.lowTranscriptionConfidence,
    variant: 'warning',
    actionKind: 'continue',
    actionLabel: 'Continue',
  }
}

export type ErrorBannerActionFields = {
  message: string
  variant: ErrorUiVariant
  detail?: string
  action?: { label: string; onPress: () => void }
}

/** Map README-aligned error + handlers into `ErrorBanner` props (no raw stacks). */
export function toErrorBannerProps(
  m: MappedUiError,
  handlers: {
    onRetry: () => void
    onDismiss: () => void
    onOpenSettings: () => void
    onContinue: () => void
  },
): ErrorBannerActionFields {
  let action: ErrorBannerActionFields['action']
  if (m.actionKind != null && m.actionLabel) {
    const run =
      m.actionKind === 'retry'
        ? handlers.onRetry
        : m.actionKind === 'dismiss'
          ? handlers.onDismiss
          : m.actionKind === 'open_settings'
            ? handlers.onOpenSettings
            : handlers.onContinue
    action = { label: m.actionLabel, onPress: () => void run() }
  }
  const detail = m.detail?.trim() ? m.detail.trim() : undefined
  return { message: m.message, variant: m.variant, ...(detail ? { detail } : {}), action }
}
