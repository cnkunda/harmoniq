function isApiLikeError(err: unknown): err is { status: number; message: string } {
  if (typeof err !== 'object' || err === null) return false
  const o = err as Record<string, unknown>
  return typeof o.status === 'number' && typeof o.message === 'string'
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
  lowTranscriptionConfidence:
    "Transcription confidence is limited here — use your ears and this tab as a helpful sketch.",
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
}

function networkishMessage(err: unknown): boolean {
  if (err instanceof TypeError) return true
  const msg = err instanceof Error ? err.message : String(err)
  return /network|fetch|failed to load|internet|offline/i.test(msg)
}

function bodyLooksShort(body: string): boolean {
  const b = body.toLowerCase()
  return b.includes('too short') || b.includes('30 sec') || b.includes('30s') || b.includes('duration')
}

function bodyLooksNoStem(body: string): boolean {
  const b = body.toLowerCase()
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
    if (bodyLooksShort(body)) {
      return {
        message: README_ERROR_COPY.audioTooShort,
        variant: 'warning',
        actionKind: 'dismiss',
        actionLabel: 'Dismiss',
      }
    }
    if (bodyLooksNoStem(body)) {
      return {
        message: README_ERROR_COPY.noGuitarStem,
        variant: 'warning',
        actionKind: 'retry',
        actionLabel: 'Try again',
      }
    }
    if (ctx.usedYoutubeUrl && err.status === 400) {
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
      }
    }
    if (err.status === 404) {
      return {
        message: README_ERROR_COPY.analysisJobFailed,
        variant: 'error',
        actionKind: 'retry',
        actionLabel: 'Retry',
      }
    }
    if (err.status >= 400) {
      return {
        message: README_ERROR_COPY.analysisJobFailed,
        variant: 'error',
        actionKind: 'retry',
        actionLabel: 'Retry',
      }
    }
  }

  return {
    message: README_ERROR_COPY.analysisJobFailed,
    variant: 'error',
    actionKind: 'retry',
    actionLabel: 'Retry',
  }
}

/** Review / POST /score failures. */
export function mapScoreFlowError(err: unknown): MappedUiError {
  if (networkishMessage(err)) {
    return {
      message: README_ERROR_COPY.noInternetAnalysis,
      variant: 'warning',
      actionKind: 'dismiss',
      actionLabel: 'Dismiss',
    }
  }
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
  return { message: m.message, variant: m.variant, action }
}
