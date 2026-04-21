import { Platform } from 'react-native'

/** AlphaTab harness `<audio>` in WebView needs a proper URL scheme on native. */
export function normalizeExternalAudioSrcForTabHarness(uri: string): string {
  const t = uri.trim()
  if (!t) return t
  if (Platform.OS === 'web') return t
  if (/^(file:|blob:|content:|https?:)/i.test(t)) return t
  if (t.startsWith('/')) return `file://${t}`
  return `file:///${t.replace(/\\/g, '/')}`
}
