/**
 * Harmonic similarity analysis for song discovery (commit 91).
 * Calculates similarity between songs based on key, style, and harmonic relationships.
 */

import { parseKey } from './capoSuggestion';

export interface SongHarmonicProfile {
  key: string | null
  style: string | null
  tempo: number | null
}

/**
 * Parse a key label to extract root note and mode.
 */
function parseKeyLabel(keyLabel: string | null): { root: string | null; mode: 'major' | 'minor' | null } {
  if (!keyLabel) return { root: null, mode: null }
  
  const parsed = parseKey(keyLabel)
  if (!parsed) return { root: null, mode: null }
  
  return { root: parsed.tonic, mode: parsed.mode as 'major' | 'minor' }
}

/**
 * Calculate harmonic relationship between two keys.
 * Returns a score from 0.0 to 1.0 where 1.0 is identical key.
 */
function keySimilarity(key1: string | null, key2: string | null): number {
  if (!key1 || !key2) return 0.0
  if (key1 === key2) return 1.0
  
  const parsed1 = parseKeyLabel(key1)
  const parsed2 = parseKeyLabel(key2)
  
  if (!parsed1.root || !parsed2.root) return 0.0
  
  // Identical root and mode
  if (parsed1.root === parsed2.root && parsed1.mode === parsed2.mode) return 1.0
  
  // Relative major/minor relationship (e.g., C major ↔ A minor)
  if (parsed1.root === parsed2.root && parsed1.mode !== parsed2.mode) return 0.8
  
  // Parallel major/minor (same root, different mode) - already handled above
  
  // Perfect fourth/fifth relationships (strong harmonic connection)
  const NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
  const idx1 = NOTE_NAMES.indexOf(parsed1.root)
  const idx2 = NOTE_NAMES.indexOf(parsed2.root)
  
  if (idx1 === -1 || idx2 === -1) return 0.0
  
  const interval = Math.abs(idx2 - idx1)
  
  // Perfect fifth (7 semitones) or perfect fourth (5 semitones)
  if (interval === 7 || interval === 5) return 0.7
  
  // Third relationships (3 or 4 semitones)
  if (interval === 3 || interval === 4) return 0.5
  
  // Second relationships (1 or 2 semitones)
  if (interval === 1 || interval === 2) return 0.3
  
  return 0.2
}

/**
 * Calculate style similarity between two songs.
 * Returns a score from 0.0 to 1.0.
 */
function styleSimilarity(style1: string | null, style2: string | null): number {
  if (!style1 || !style2) return 0.0
  if (style1 === style2) return 1.0
  
  const s1 = style1.toLowerCase().trim()
  const s2 = style2.toLowerCase().trim()
  
  // Check for partial matches (e.g., "blues rock" vs "rock")
  if (s1.includes(s2) || s2.includes(s1)) return 0.7
  
  // Check for related styles
  const styleGroups: Record<string, string[]> = {
    rock: ['rock', 'blues rock', 'hard rock', 'classic rock'],
    blues: ['blues', 'blues rock', 'delta blues'],
    jazz: ['jazz', 'fusion', 'smooth jazz'],
    folk: ['folk', 'acoustic', 'singer-songwriter'],
    metal: ['metal', 'heavy metal', 'thrash'],
    pop: ['pop', 'indie pop'],
    country: ['country', 'country rock'],
  }
  
  for (const [base, variants] of Object.entries(styleGroups)) {
    if (variants.some(v => s1.includes(v)) && variants.some(v => s2.includes(v))) {
      return 0.6
    }
  }
  
  return 0.2
}

/**
 * Calculate tempo similarity between two songs.
 * Returns a score from 0.0 to 1.0 where 1.0 is identical tempo.
 */
function tempoSimilarity(tempo1: number | null, tempo2: number | null): number {
  if (!tempo1 || !tempo2) return 0.0
  
  const diff = Math.abs(tempo1 - tempo2)
  
  // Identical or very close (within 5 BPM)
  if (diff <= 5) return 1.0
  
  // Close (within 15 BPM)
  if (diff <= 15) return 0.8
  
  // Moderate difference (within 30 BPM)
  if (diff <= 30) return 0.5
  
  // Large difference
  return 0.2
}

/**
 * Calculate overall harmonic similarity between two songs.
 * Returns a score from 0.0 to 1.0.
 */
export function calculateHarmonicSimilarity(
  song1: SongHarmonicProfile,
  song2: SongHarmonicProfile
): number {
  const keyScore = keySimilarity(song1.key, song2.key)
  const styleScore = styleSimilarity(song1.style, song2.style)
  const tempoScore = tempoSimilarity(song1.tempo, song2.tempo)
  
  // Weighted average: key is most important for harmonic similarity
  return keyScore * 0.5 + styleScore * 0.3 + tempoScore * 0.2
}

/**
 * Find songs with high harmonic similarity to a target song.
 * Returns songs sorted by similarity score (descending).
 */
export function findSimilarSongs(
  target: SongHarmonicProfile,
  candidates: SongHarmonicProfile[],
  options?: { minScore?: number; limit?: number }
): Array<{ song: SongHarmonicProfile; similarity: number }> {
  const minScore = options?.minScore ?? 0.3
  const limit = options?.limit
  
  const scored = candidates.map(song => ({
    song,
    similarity: calculateHarmonicSimilarity(target, song),
  }))
  
  const filtered = scored.filter(s => s.similarity >= minScore)
  const sorted = filtered.sort((a, b) => b.similarity - a.similarity)
  
  return limit ? sorted.slice(0, limit) : sorted
}
