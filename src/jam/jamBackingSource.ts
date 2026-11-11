/** Provenance resolution for generated jam backing audio (kept free of RN imports for unit tests). */

export type JamBackingProvenance = {
  prompt_used?: string | null
  provider?: string | null
  used_fallback?: boolean | null
  fallback_reason?: string | null
}

export type JamBackingSourceInfo = {
  provider: string
  usedFallback: boolean
  fallbackTrack: string | null
}

/**
 * Resolve what actually produced the backing audio. The legacy backend appends
 * `[fallback_track=<file>]` to `prompt_used` and returns HTTP 200, so the UI must
 * not label a bundled loop as AI output.
 */
export function resolveJamBackingSource(res: JamBackingProvenance): JamBackingSourceInfo {
  const match = /\[fallback_track=([^\]]+)\]/.exec(res.prompt_used ?? '')
  const fallbackTrack = match?.[1]?.trim() ?? null
  const usedFallback = res.used_fallback === true || fallbackTrack != null
  const provider = usedFallback ? (res.provider ?? 'bundled') : (res.provider ?? 'server')
  return { provider, usedFallback, fallbackTrack }
}
