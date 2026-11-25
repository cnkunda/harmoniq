/**
 * Level-gated logger honoring the repo's `[Module]` prefix convention
 * (AGENTS.md — "Logging"). Replaces raw `console.*` calls in app code so
 * release builds ship no debug-level noise while support diagnostics survive.
 */

/** Log levels exposed by {@link createLogger}. */
export interface Logger {
  /** Dev-only diagnostic — no-op outside `__DEV__`. */
  debug(...args: unknown[]): void
  /** Dev-only diagnostic — no-op outside `__DEV__`. */
  info(...args: unknown[]): void
  /** Always emitted — support diagnostic, kept in release builds. */
  warn(...args: unknown[]): void
  /** Always emitted — support diagnostic, kept in release builds. */
  error(...args: unknown[]): void
}

/**
 * Prefix the first argument with `prefix`, preserving the call-site shape
 * `console.warn('[Module] message', extra)` that existing assertions match
 * against (`stringContaining('...')` on the first argument).
 */
function format(prefix: string, args: unknown[]): unknown[] {
  if (args.length === 0) return [prefix]
  const [first, ...rest] = args
  if (typeof first === 'string') return [`${prefix} ${first}`, ...rest]
  return [prefix, first, ...rest]
}

/**
 * Create a logger bound to a `[Module]` prefix.
 *
 * `debug`/`info` emit only when `__DEV__` is true (the `typeof` guard matches
 * `src/session/listenTransportDebug.ts` and stays safe where `__DEV__` is not
 * declared at all, e.g. plain Node). Expo's production minification folds the
 * guard and babel strips the remaining `console.*` debug calls at build time.
 * `warn`/`error` always emit so support diagnostics are never lost.
 */
export function createLogger(prefix: string): Logger {
  const gated =
    (method: 'debug' | 'info') =>
    (...args: unknown[]): void => {
      if (typeof __DEV__ === 'undefined' || !__DEV__) return
      console[method](...format(prefix, args))
    }

  return {
    debug: gated('debug'),
    info: gated('info'),
    warn: (...args: unknown[]): void => {
      console.warn(...format(prefix, args))
    },
    error: (...args: unknown[]): void => {
      console.error(...format(prefix, args))
    },
  }
}
