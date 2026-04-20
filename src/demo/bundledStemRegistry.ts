/**
 * Maps `LessonJSON.stems[*]` paths with the `bundled://` scheme to Metro/Webpack assets.
 * Keeps demo lessons offline — no `/lesson-file` round trip.
 *
 * **Web:** `require()` often resolves to a **string URL**, not a numeric module id. We accept both
 * and pass strings through `StemDefinition.uri` so `Mixer.web` uses `fetch()` on a real asset URL.
 */

/** Normalize Metro (native) vs Webpack (web) `require()` shapes. */
function normalizeBundledRequire(m: unknown): number | string | null {
  if (typeof m === 'number') return m
  if (typeof m === 'string' && m.length > 0) return m
  if (m && typeof m === 'object' && 'default' in (m as object)) {
    const d = (m as { default: unknown }).default
    if (typeof d === 'number') return d
    if (typeof d === 'string' && d.length > 0) return d
  }
  return null
}

function reggaeDemoAsset(): unknown {
  return require('../../assets/demo-lesson/reggae_clean_30s.wav')
}

const BUNDLED_STEM_LOADERS: Record<string, () => unknown> = {
  /** 30s sample — see `assets/demo-lesson/SOURCES.md` */
  'bundled://demo/reggae': reggaeDemoAsset,
  /** Legacy path (same asset) — persisted lessons may still reference this key */
  'bundled://demo/am-blues-70': reggaeDemoAsset,
}

export function bundledStemRefOrNull(relPath: string): number | string | null {
  const trimmed = typeof relPath === 'string' ? relPath.trim() : ''
  if (!trimmed.startsWith('bundled://')) return null
  const loader = BUNDLED_STEM_LOADERS[trimmed]
  if (!loader) return null
  try {
    return normalizeBundledRequire(loader())
  } catch {
    return null
  }
}
