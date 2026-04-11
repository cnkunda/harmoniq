/**
 * Contract between the Expo app and `assets/alphatab-harness/index.html`
 * (WebView on native) or `AlphaTabWeb.web.tsx` (DOM on Expo web).
 */

/** Parent → harness */
export type TabInboundMessage =
  | { type: 'setScore'; gp5Base64: string }
  | { type: 'setAudioSrc'; audioSrc: string }
  | { type: 'setPlaybackRate'; playbackRate: number }
  | { type: 'seekTo'; positionMs: number }
  | { type: 'getPosition' }
  | { type: 'setTranspose'; semitones: number }
  | { type: 'setTheme'; colors: Partial<TabThemeColors> }

export type NoteEventMessage = {
  type: 'noteEvent'
  midi: number
  beat: number
  fret?: number
  string?: number
}

/**
 * Subset of alphaTab display `RenderingResources` the app may override.
 * Keys match `@coderline/alphatab` JSON settings where applicable.
 */
export type TabThemeColors = {
  mainGlyphColor?: string
  secondaryGlyphColor?: string
  barSeparatorColor?: string
  scoreInfoColor?: string
  staffLineColor?: string
  barNumberColor?: string
}

/** Imperative API shared by `AlphaTabWebView` (native) and `AlphaTabWeb` (Expo web DOM). */
export type AlphaTabSurfaceRef = {
  setAudioSrc: (audioSrc: string) => void
  setPlaybackRate: (playbackRate: number) => void
  seekTo: (positionMs: number) => void
  getPosition: () => Promise<number | null>
  setTheme: (colors: Partial<TabThemeColors>) => void
  setTranspose: (semitones: number) => void
}

/** Harness → parent */
export type TabOutboundMessage =
  | { type: 'ready' }
  | { type: 'error'; message: string }
  | { type: 'position'; positionMs: number }
  | NoteEventMessage
  | { type: 'soundFontLoad'; status: 'loading' | 'loaded' | 'error'; message?: string }

export function encodeTabMessage(msg: TabInboundMessage): string {
  return JSON.stringify(msg)
}

export function decodeTabMessage(raw: string): TabOutboundMessage | null {
  try {
    const v: unknown = JSON.parse(raw)
    if (!v || typeof v !== 'object' || !('type' in v)) return null
    const o = v as { type: unknown; message?: unknown }
    if (o.type === 'ready') return { type: 'ready' }
    if (o.type === 'error' && typeof o.message === 'string') {
      return { type: 'error', message: o.message }
    }
    const maybePosition = o as { type: unknown; positionMs?: unknown }
    if (o.type === 'position' && typeof maybePosition.positionMs === 'number') {
      return { type: 'position', positionMs: maybePosition.positionMs }
    }
    const maybeSf = o as { type: unknown; status?: unknown; message?: unknown }
    if (
      o.type === 'soundFontLoad' &&
      (maybeSf.status === 'loading' || maybeSf.status === 'loaded' || maybeSf.status === 'error')
    ) {
      return {
        type: 'soundFontLoad',
        status: maybeSf.status,
        message: typeof maybeSf.message === 'string' ? maybeSf.message : undefined,
      }
    }
    const maybeNote = o as {
      type: unknown
      midi?: unknown
      beat?: unknown
      fret?: unknown
      string?: unknown
    }
    if (o.type === 'noteEvent' && typeof maybeNote.midi === 'number' && typeof maybeNote.beat === 'number') {
      return {
        type: 'noteEvent',
        midi: maybeNote.midi,
        beat: maybeNote.beat,
        fret: typeof maybeNote.fret === 'number' ? maybeNote.fret : undefined,
        string: typeof maybeNote.string === 'number' ? maybeNote.string : undefined,
      }
    }
  } catch {
    /* invalid */
  }
  return null
}
