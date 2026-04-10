/**
 * Contract between the Expo app and `assets/alphatab-harness/index.html`
 * (WebView on native) or `AlphaTabWeb.web.tsx` (DOM on Expo web).
 */

/** Parent → harness */
export type TabInboundMessage =
  | { type: 'setScore'; gp5Base64: string }
  | { type: 'scrollToBar'; barIndex: number }
  | { type: 'setTranspose'; semitones: number }
  | { type: 'setTheme'; colors: Partial<TabThemeColors> }

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
  scrollToBar: (barIndex: number) => void
  setTheme: (colors: Partial<TabThemeColors>) => void
  setTranspose: (semitones: number) => void
}

/** Harness → parent */
export type TabOutboundMessage = { type: 'ready' } | { type: 'error'; message: string }

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
  } catch {
    /* invalid */
  }
  return null
}
