export type FretboardOverlayMode = 'off' | 'note_names' | 'scale_degrees'

export type FretboardShareState = {
  version: 1
  overlay: FretboardOverlayMode
  selected?: { string: number; fret: number } | null
  scalePitchClasses?: number[] | null
  rootPitchClass?: number | null
}

export const FRETBOARD_SHARE_PARAM = 'fs'

function toBase64Url(input: string): string | null {
  if (typeof globalThis.btoa !== 'function') return null
  const b64 = globalThis.btoa(input)
  return b64.replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '')
}

function fromBase64Url(input: string): string | null {
  if (typeof globalThis.atob !== 'function') return null
  const padded = input.replace(/-/g, '+').replace(/_/g, '/').padEnd(Math.ceil(input.length / 4) * 4, '=')
  try {
    return globalThis.atob(padded)
  } catch {
    return null
  }
}

function normalizePitchClasses(input: unknown): number[] | null {
  if (!Array.isArray(input)) return null
  const pcs = Array.from(
    new Set(
      input
        .map((v) => (typeof v === 'number' && Number.isFinite(v) ? ((Math.round(v) % 12) + 12) % 12 : null))
        .filter((v): v is number => v != null),
    ),
  )
  return pcs.length > 0 ? pcs : null
}

function normalizeSelected(input: unknown): { string: number; fret: number } | null {
  if (!input || typeof input !== 'object') return null
  const row = input as Record<string, unknown>
  const s = typeof row.string === 'number' ? Math.round(row.string) : Number.NaN
  const f = typeof row.fret === 'number' ? Math.round(row.fret) : Number.NaN
  if (!Number.isFinite(s) || !Number.isFinite(f)) return null
  if (s < 1 || s > 6 || f < 0 || f > 24) return null
  return { string: s, fret: f }
}

function normalizeOverlay(input: unknown): FretboardOverlayMode {
  if (input === 'note_names' || input === 'scale_degrees' || input === 'off') return input
  return 'off'
}

function normalizeRootPitchClass(input: unknown): number | null {
  if (typeof input !== 'number' || !Number.isFinite(input)) return null
  return ((Math.round(input) % 12) + 12) % 12
}

export function encodeFretboardShareState(state: FretboardShareState): string | null {
  const payload: FretboardShareState = {
    version: 1,
    overlay: normalizeOverlay(state.overlay),
    selected: normalizeSelected(state.selected),
    scalePitchClasses: normalizePitchClasses(state.scalePitchClasses),
    rootPitchClass: normalizeRootPitchClass(state.rootPitchClass),
  }
  const encoded = toBase64Url(JSON.stringify(payload))
  return encoded ? `1.${encoded}` : null
}

export function decodeFretboardShareState(raw: string | null | undefined): FretboardShareState | null {
  if (!raw) return null
  const [version, encoded] = raw.split('.', 2)
  if (version !== '1' || !encoded) return null
  const json = fromBase64Url(encoded)
  if (!json) return null
  try {
    const parsed = JSON.parse(json) as Record<string, unknown>
    return {
      version: 1,
      overlay: normalizeOverlay(parsed.overlay),
      selected: normalizeSelected(parsed.selected),
      scalePitchClasses: normalizePitchClasses(parsed.scalePitchClasses),
      rootPitchClass: normalizeRootPitchClass(parsed.rootPitchClass),
    }
  } catch {
    return null
  }
}

export function readFretboardShareStateFromLocation(): FretboardShareState | null {
  if (typeof window === 'undefined') return null
  const raw = new URL(window.location.href).searchParams.get(FRETBOARD_SHARE_PARAM)
  return decodeFretboardShareState(raw)
}

export function buildFretboardShareUrl(state: FretboardShareState): string | null {
  if (typeof window === 'undefined') return null
  const encoded = encodeFretboardShareState(state)
  if (!encoded) return null
  const url = new URL(window.location.href)
  url.searchParams.set(FRETBOARD_SHARE_PARAM, encoded)
  return url.toString()
}
