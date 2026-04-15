/**
 * Decode standard base64 to bytes without calling global `atob`.
 * Expo / Metro web can error on bare `atob` (lazy window binding); GP5 payloads are binary-safe ASCII base64.
 */
export function base64ToUint8Array(base64: string): Uint8Array {
  const normalized = base64.replace(/\s/g, '').replace(/-/g, '+').replace(/_/g, '/')
  if (normalized.length === 0) return new Uint8Array(0)
  if (/[^A-Za-z0-9+/=]/.test(normalized)) {
    throw new Error('Invalid base64 data: unsupported character')
  }

  const firstEq = normalized.indexOf('=')
  if (firstEq >= 0) {
    if (firstEq < normalized.length - 2) {
      throw new Error('Invalid base64 data: "=" must be at the end')
    }
    if (!/^=+$/.test(normalized.slice(firstEq))) {
      throw new Error('Invalid base64 data: malformed padding')
    }
  }

  const remainder = normalized.length % 4
  if (remainder === 1) {
    throw new Error('Invalid base64 data: length mod 4 cannot equal 1')
  }
  if (firstEq >= 0 && remainder !== 0) {
    throw new Error('Invalid base64 data: padded input has invalid length')
  }

  const padded =
    remainder === 0
      ? normalized
      : `${normalized}${remainder === 2 ? '==' : '='}`

  const L = padded.length
  const paddingChars = padded.endsWith('==') ? 2 : padded.endsWith('=') ? 1 : 0
  const outLen = (L / 4) * 3 - paddingChars
  if (outLen < 0) {
    throw new Error('Invalid base64 data: negative output length')
  }
  const out = new Uint8Array(outLen)

  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'
  const dec = new Uint8Array(256)
  dec.fill(255)
  for (let i = 0; i < alphabet.length; i++) {
    dec[alphabet.charCodeAt(i)] = i
  }

  let o = 0
  for (let i = 0; i < L; i += 4) {
    const a = dec[padded.charCodeAt(i)]
    const b = dec[padded.charCodeAt(i + 1)]
    const cRaw = padded.charAt(i + 2)
    const dRaw = padded.charAt(i + 3)
    const c = cRaw === '=' ? 0 : dec[padded.charCodeAt(i + 2)]
    const d = dRaw === '=' ? 0 : dec[padded.charCodeAt(i + 3)]
    if (a === 255 || b === 255 || (cRaw !== '=' && c === 255) || (dRaw !== '=' && d === 255)) {
      throw new Error('Invalid base64 data')
    }
    const triple = (a << 18) | (b << 12) | (c << 6) | d
    if (o < outLen) out[o++] = (triple >> 16) & 0xff
    if (o < outLen && cRaw !== '=') out[o++] = (triple >> 8) & 0xff
    if (o < outLen && dRaw !== '=') out[o++] = triple & 0xff
  }

  return out
}
