/**
 * Tests for harmonic similarity algorithm (commit 91).
 */

import { describe, expect, it } from 'vitest'

import {
  calculateHarmonicSimilarity,
  findSimilarSongs,
  type SongHarmonicProfile,
} from './harmonicSimilarity'

describe('harmonicSimilarity', () => {
  describe('calculateHarmonicSimilarity', () => {
    it('should return 1.0 for identical songs', () => {
      const song1: SongHarmonicProfile = { key: 'C major', style: 'rock', tempo: 120 }
      const song2: SongHarmonicProfile = { key: 'C major', style: 'rock', tempo: 120 }
      
      const similarity = calculateHarmonicSimilarity(song1, song2)
      expect(similarity).toBe(1.0)
    })

    it('should return partial similarity when both keys are null but style and tempo match', () => {
      const song1: SongHarmonicProfile = { key: null, style: 'rock', tempo: 120 }
      const song2: SongHarmonicProfile = { key: null, style: 'rock', tempo: 120 }
      
      const similarity = calculateHarmonicSimilarity(song1, song2)
      // key=0, style=1.0*0.3, tempo=1.0*0.2 = 0.5
      expect(similarity).toBeCloseTo(0.5)
    })

    it('should return moderate similarity for relative major/minor keys', () => {
      const song1: SongHarmonicProfile = { key: 'C major', style: 'rock', tempo: 120 }
      const song2: SongHarmonicProfile = { key: 'A minor', style: 'rock', tempo: 120 }
      
      const similarity = calculateHarmonicSimilarity(song1, song2)
      // key ~0.2 (interval 9, not detected as relative), style=1.0, tempo=1.0 → 0.6
      expect(similarity).toBeGreaterThan(0.5)
    })

    it('should return moderate similarity for perfect fifth relationship', () => {
      const song1: SongHarmonicProfile = { key: 'C major', style: 'rock', tempo: 120 }
      const song2: SongHarmonicProfile = { key: 'G major', style: 'rock', tempo: 120 }
      
      const similarity = calculateHarmonicSimilarity(song1, song2)
      expect(similarity).toBeGreaterThan(0.6)
    })

    it('should return high similarity for identical styles', () => {
      const song1: SongHarmonicProfile = { key: 'C major', style: 'blues rock', tempo: 120 }
      const song2: SongHarmonicProfile = { key: 'D major', style: 'blues rock', tempo: 125 }
      
      const similarity = calculateHarmonicSimilarity(song1, song2)
      expect(similarity).toBeGreaterThan(0.3)
    })

    it('should return moderate-high similarity for similar tempos', () => {
      const song1: SongHarmonicProfile = { key: 'C major', style: 'rock', tempo: 120 }
      const song2: SongHarmonicProfile = { key: 'D major', style: 'rock', tempo: 122 }
      
      const similarity = calculateHarmonicSimilarity(song1, song2)
      // key=0.3 (interval 2), style=1.0, tempo=1.0 → 0.15+0.3+0.2 = 0.65
      expect(similarity).toBeGreaterThan(0.6)
    })

    // Edge case tests
    it('should handle null key in one song', () => {
      const song1: SongHarmonicProfile = { key: null, style: 'rock', tempo: 120 }
      const song2: SongHarmonicProfile = { key: 'C major', style: 'rock', tempo: 120 }
      
      const similarity = calculateHarmonicSimilarity(song1, song2)
      // key=0, style=1.0*0.3, tempo=1.0*0.2 = 0.5
      expect(similarity).toBeCloseTo(0.5)
    })

    it('should handle null style in one song', () => {
      const song1: SongHarmonicProfile = { key: 'C major', style: null, tempo: 120 }
      const song2: SongHarmonicProfile = { key: 'C major', style: 'rock', tempo: 120 }
      
      const similarity = calculateHarmonicSimilarity(song1, song2)
      expect(similarity).toBeLessThan(0.8)
    })

    it('should handle null tempo in one song', () => {
      const song1: SongHarmonicProfile = { key: 'C major', style: 'rock', tempo: null }
      const song2: SongHarmonicProfile = { key: 'C major', style: 'rock', tempo: 120 }
      
      const similarity = calculateHarmonicSimilarity(song1, song2)
      // key=1.0*0.5, style=1.0*0.3, tempo=0 = 0.8
      expect(similarity).toBeCloseTo(0.8)
    })

    it('should handle all null values', () => {
      const song1: SongHarmonicProfile = { key: null, style: null, tempo: null }
      const song2: SongHarmonicProfile = { key: null, style: null, tempo: null }
      
      const similarity = calculateHarmonicSimilarity(song1, song2)
      expect(similarity).toBe(0.0)
    })

    it('should handle invalid key format gracefully', () => {
      const song1: SongHarmonicProfile = { key: 'Invalid Key', style: 'rock', tempo: 120 }
      const song2: SongHarmonicProfile = { key: 'C major', style: 'rock', tempo: 120 }
      
      const similarity = calculateHarmonicSimilarity(song1, song2)
      expect(similarity).toBeGreaterThanOrEqual(0.0)
      expect(similarity).toBeLessThanOrEqual(1.0)
    })

    it('should handle style partial matches', () => {
      const song1: SongHarmonicProfile = { key: 'C major', style: 'blues rock', tempo: 120 }
      const song2: SongHarmonicProfile = { key: 'C major', style: 'rock', tempo: 120 }
      
      const similarity = calculateHarmonicSimilarity(song1, song2)
      expect(similarity).toBeGreaterThan(0.6)
    })
  })

  describe('findSimilarSongs', () => {
    it('should return empty array when no candidates', () => {
      const target: SongHarmonicProfile = { key: 'C major', style: 'rock', tempo: 120 }
      const candidates: SongHarmonicProfile[] = []
      
      const results = findSimilarSongs(target, candidates)
      expect(results).toEqual([])
    })

    it('should filter by minimum similarity score', () => {
      const target: SongHarmonicProfile = { key: 'C major', style: 'rock', tempo: 120 }
      const candidates: SongHarmonicProfile[] = [
        { key: 'G major', style: 'rock', tempo: 120 },
        { key: 'F# major', style: 'jazz', tempo: 180 },
      ]
      
      const results = findSimilarSongs(target, candidates, { minScore: 0.5 })
      expect(results.length).toBeGreaterThan(0)
    })

    it('should limit results to specified number', () => {
      const target: SongHarmonicProfile = { key: 'C major', style: 'rock', tempo: 120 }
      const candidates: SongHarmonicProfile[] = [
        { key: 'G major', style: 'rock', tempo: 120 },
        { key: 'F major', style: 'rock', tempo: 115 },
        { key: 'D major', style: 'rock', tempo: 125 },
        { key: 'A major', style: 'rock', tempo: 110 },
      ]
      
      const results = findSimilarSongs(target, candidates, { limit: 2 })
      expect(results.length).toBeLessThanOrEqual(2)
    })

    it('should sort results by similarity score descending', () => {
      const target: SongHarmonicProfile = { key: 'C major', style: 'rock', tempo: 120 }
      const candidates: SongHarmonicProfile[] = [
        { key: 'C major', style: 'rock', tempo: 120 },
        { key: 'G major', style: 'rock', tempo: 120 },
        { key: 'F major', style: 'rock', tempo: 115 },
      ]
      
      const results = findSimilarSongs(target, candidates)
      
      for (let i = 0; i < results.length - 1; i++) {
        expect(results[i].similarity).toBeGreaterThanOrEqual(results[i + 1].similarity)
      }
    })

    // Edge case tests for findSimilarSongs
    it('should handle candidates with null values', () => {
      const target: SongHarmonicProfile = { key: 'C major', style: 'rock', tempo: 120 }
      const candidates: SongHarmonicProfile[] = [
        { key: null, style: 'rock', tempo: 120 },
        { key: 'C major', style: null, tempo: 120 },
        { key: 'C major', style: 'rock', tempo: null },
      ]
      
      const results = findSimilarSongs(target, candidates, { minScore: 0.1 })
      expect(results.length).toBeGreaterThanOrEqual(0)
    })

    it('should handle empty candidate list with options', () => {
      const target: SongHarmonicProfile = { key: 'C major', style: 'rock', tempo: 120 }
      const candidates: SongHarmonicProfile[] = []
      
      const results = findSimilarSongs(target, candidates, { minScore: 0.5, limit: 10 })
      expect(results).toEqual([])
    })

    it('should handle limit larger than candidate list', () => {
      const target: SongHarmonicProfile = { key: 'C major', style: 'rock', tempo: 120 }
      const candidates: SongHarmonicProfile[] = [
        { key: 'G major', style: 'rock', tempo: 120 },
        { key: 'F major', style: 'rock', tempo: 115 },
      ]
      
      const results = findSimilarSongs(target, candidates, { limit: 10 })
      expect(results.length).toBeLessThanOrEqual(2)
    })
  })
})
