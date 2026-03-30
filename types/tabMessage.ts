/**
 * Contract between the Expo app and `assets/alphatab-harness/index.html`
 * (WebView on native, iframe or direct `postMessage` on web).
 */

/** Parent → harness */
export type TabInboundMessage =
  | { type: 'setScore'; gp5Base64: string }
  | { type: 'scrollToBar'; barIndex: number }
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
