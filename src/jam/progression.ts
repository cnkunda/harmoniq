/** Jam progression input parsing (J4) — keeps free-text entry safe to send to the generator. */

const CHORD_RE = /^[A-Ga-g][#b]?(?:maj|min|m|dim|aug|sus2|sus4|add9|maj7|min7|m7|7|6|9|11|13)?$/
export const MAX_PROGRESSION_CHORDS = 16

export const PROGRESSION_PRESETS: ReadonlyArray<{ label: string; text: string }> = [
  { label: 'Minor vamp', text: 'Am F C G' },
  { label: '12-bar blues', text: 'A7 D7 A7 A7 D7 D7 A7 A7 E7 D7 A7 E7' },
  { label: 'ii–V–I', text: 'Dm7 G7 Cmaj7' },
  { label: 'Pop loop', text: 'C G Am F' },
  { label: 'Dorian rock', text: 'Am7 D7 Am7 D7' },
] as const

/** Normalize a token to `Root` + lowercase quality, e.g. `AM7` -> `Am7`. */
export function normalizeChordSymbol(token: string): string {
  return token.charAt(0).toUpperCase() + token.slice(1).toLowerCase()
}

/** Split on whitespace, commas, pipes, or slashes; keep only valid chord symbols. */
export function parseProgressionInput(input: string, maxChords = MAX_PROGRESSION_CHORDS): string[] {
  const out: string[] = []
  for (const raw of input.split(/[\s,|/]+/)) {
    const token = raw.trim()
    if (!token || out.length >= maxChords) continue
    if (!CHORD_RE.test(token)) continue
    out.push(normalizeChordSymbol(token))
  }
  return out
}
