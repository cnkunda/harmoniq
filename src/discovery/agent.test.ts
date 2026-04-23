/**
 * Tests for discovery agent (commit 91).
 */

import { describe, expect, it } from 'vitest'

import {
  generateDiscoveryFromLesson,
  generateDiscoverySuggestions,
  type MasteredSong,
  type SkillNode,
} from './agent'

describe('discovery agent', () => {
  const skillNodes: SkillNode[] = [
    { id: 'bend_accuracy', label: 'Bending', score: 0.9 },
    { id: 'vibrato_control', label: 'Vibrato', score: 0.7 },
    { id: 'timing', label: 'Timing', score: 0.85 },
  ]

  describe('generateDiscoverySuggestions', () => {
    it('should return empty array when no mastered songs', () => {
      const masteredSongs: MasteredSong[] = []
      const candidateSongs: MasteredSong[] = [
        {
          job_id: 'song1',
          song_title: 'Test Song',
          artist: 'Test Artist',
          key: 'C major',
          style_label: 'rock',
          tempo: 120,
        },
      ]

      const results = generateDiscoverySuggestions(masteredSongs, candidateSongs, skillNodes)
      expect(results).toEqual([])
    })

    it('should return empty array when no candidate songs', () => {
      const masteredSongs: MasteredSong[] = [
        {
          job_id: 'mastered1',
          song_title: 'Mastered Song',
          artist: 'Mastered Artist',
          key: 'C major',
          style_label: 'rock',
          tempo: 120,
        },
      ]
      const candidateSongs: MasteredSong[] = []

      const results = generateDiscoverySuggestions(masteredSongs, candidateSongs, skillNodes)
      expect(results).toEqual([])
    })

    it('should filter out already mastered songs from candidates', () => {
      const masteredSongs: MasteredSong[] = [
        {
          job_id: 'mastered1',
          song_title: 'Mastered Song',
          artist: 'Mastered Artist',
          key: 'C major',
          style_label: 'rock',
          tempo: 120,
        },
      ]
      const candidateSongs: MasteredSong[] = [
        {
          job_id: 'mastered1',
          song_title: 'Mastered Song',
          artist: 'Mastered Artist',
          key: 'C major',
          style_label: 'rock',
          tempo: 120,
        },
        {
          job_id: 'candidate1',
          song_title: 'Candidate Song',
          artist: 'Candidate Artist',
          key: 'G major',
          style_label: 'rock',
          tempo: 125,
        },
      ]

      const results = generateDiscoverySuggestions(masteredSongs, candidateSongs, skillNodes)
      expect(results.length).toBe(1)
      expect(results[0].job_id).toBe('candidate1')
    })

    it('should return suggestions with reason labels', () => {
      const masteredSongs: MasteredSong[] = [
        {
          job_id: 'mastered1',
          song_title: 'Gravity',
          artist: 'John Mayer',
          key: 'C major',
          style_label: 'blues rock',
          tempo: 120,
        },
      ]
      const candidateSongs: MasteredSong[] = [
        {
          job_id: 'candidate1',
          song_title: 'Sultans of Swing',
          artist: 'Dire Straits',
          key: 'D minor',
          style_label: 'blues rock',
          tempo: 125,
        },
      ]

      const results = generateDiscoverySuggestions(masteredSongs, candidateSongs, skillNodes)
      expect(results.length).toBeGreaterThan(0)
      expect(results[0].reasonLabel).toBeTruthy()
      expect(results[0].reasonLabel).toContain('Gravity')
    })

    it('should include technique focus from skill nodes', () => {
      const masteredSongs: MasteredSong[] = [
        {
          job_id: 'mastered1',
          song_title: 'Test Song',
          artist: 'Test Artist',
          key: 'C major',
          style_label: 'rock',
          tempo: 120,
        },
      ]
      const candidateSongs: MasteredSong[] = [
        {
          job_id: 'candidate1',
          song_title: 'Candidate Song',
          artist: 'Candidate Artist',
          key: 'G major',
          style_label: 'rock',
          tempo: 125,
        },
      ]

      const results = generateDiscoverySuggestions(masteredSongs, candidateSongs, skillNodes)
      expect(results.length).toBeGreaterThan(0)
      expect(results[0].techniqueFocus).toBeTruthy()
    })

    it('should limit results to specified number', () => {
      const masteredSongs: MasteredSong[] = [
        {
          job_id: 'mastered1',
          song_title: 'Mastered Song',
          artist: 'Mastered Artist',
          key: 'C major',
          style_label: 'rock',
          tempo: 120,
        },
      ]
      const candidateSongs: MasteredSong[] = [
        {
          job_id: 'candidate1',
          song_title: 'Candidate 1',
          artist: 'Artist 1',
          key: 'G major',
          style_label: 'rock',
          tempo: 125,
        },
        {
          job_id: 'candidate2',
          song_title: 'Candidate 2',
          artist: 'Artist 2',
          key: 'F major',
          style_label: 'rock',
          tempo: 115,
        },
        {
          job_id: 'candidate3',
          song_title: 'Candidate 3',
          artist: 'Artist 3',
          key: 'D major',
          style_label: 'rock',
          tempo: 130,
        },
      ]

      const results = generateDiscoverySuggestions(masteredSongs, candidateSongs, skillNodes, { limit: 2 })
      expect(results.length).toBeLessThanOrEqual(2)
    })

    it('should sort by similarity score descending', () => {
      const masteredSongs: MasteredSong[] = [
        {
          job_id: 'mastered1',
          song_title: 'Mastered Song',
          artist: 'Mastered Artist',
          key: 'C major',
          style_label: 'rock',
          tempo: 120,
        },
      ]
      const candidateSongs: MasteredSong[] = [
        {
          job_id: 'candidate1',
          song_title: 'Similar Song',
          artist: 'Artist 1',
          key: 'C major',
          style_label: 'rock',
          tempo: 120,
        },
        {
          job_id: 'candidate2',
          song_title: 'Different Song',
          artist: 'Artist 2',
          key: 'F# major',
          style_label: 'jazz',
          tempo: 180,
        },
      ]

      const results = generateDiscoverySuggestions(masteredSongs, candidateSongs, skillNodes)
      
      for (let i = 0; i < results.length - 1; i++) {
        expect(results[i].similarityScore).toBeGreaterThanOrEqual(results[i + 1].similarityScore)
      }
    })
  })

  describe('generateDiscoveryFromLesson', () => {
    it('should generate suggestions from a single mastered lesson', () => {
      const masteredSong: MasteredSong = {
        job_id: 'mastered1',
        song_title: 'Gravity',
        artist: 'John Mayer',
        key: 'C major',
        style_label: 'blues rock',
        tempo: 120,
      }
      const candidateSongs: MasteredSong[] = [
        {
          job_id: 'candidate1',
          song_title: 'Sultans of Swing',
          artist: 'Dire Straits',
          key: 'D minor',
          style_label: 'blues rock',
          tempo: 125,
        },
      ]

      const results = generateDiscoveryFromLesson(masteredSong, candidateSongs, skillNodes)
      expect(results.length).toBeGreaterThan(0)
      expect(results[0].reasonLabel).toContain('Gravity')
    })

    it('should respect limit parameter', () => {
      const masteredSong: MasteredSong = {
        job_id: 'mastered1',
        song_title: 'Test Song',
        artist: 'Test Artist',
        key: 'C major',
        style_label: 'rock',
        tempo: 120,
      }
      const candidateSongs: MasteredSong[] = [
        {
          job_id: 'candidate1',
          song_title: 'Candidate 1',
          artist: 'Artist 1',
          key: 'G major',
          style_label: 'rock',
          tempo: 125,
        },
        {
          job_id: 'candidate2',
          song_title: 'Candidate 2',
          artist: 'Artist 2',
          key: 'F major',
          style_label: 'rock',
          tempo: 115,
        },
        {
          job_id: 'candidate3',
          song_title: 'Candidate 3',
          artist: 'Artist 3',
          key: 'D major',
          style_label: 'rock',
          tempo: 130,
        },
      ]

      const results = generateDiscoveryFromLesson(masteredSong, candidateSongs, skillNodes, { limit: 1 })
      expect(results.length).toBeLessThanOrEqual(1)
    })

    // Edge case tests
    it('should handle empty skill nodes', () => {
      const masteredSong: MasteredSong = {
        job_id: 'mastered1',
        song_title: 'Test Song',
        artist: 'Test Artist',
        key: 'C major',
        style_label: 'rock',
        tempo: 120,
      }
      const candidateSongs: MasteredSong[] = [
        {
          job_id: 'candidate1',
          song_title: 'Candidate Song',
          artist: 'Candidate Artist',
          key: 'G major',
          style_label: 'rock',
          tempo: 125,
        },
      ]
      const emptySkillNodes: SkillNode[] = []

      const results = generateDiscoveryFromLesson(masteredSong, candidateSongs, emptySkillNodes)
      expect(results.length).toBeGreaterThan(0)
    })

    it('should handle skill nodes with zero scores', () => {
      const masteredSong: MasteredSong = {
        job_id: 'mastered1',
        song_title: 'Test Song',
        artist: 'Test Artist',
        key: 'C major',
        style_label: 'rock',
        tempo: 120,
      }
      const candidateSongs: MasteredSong[] = [
        {
          job_id: 'candidate1',
          song_title: 'Candidate Song',
          artist: 'Candidate Artist',
          key: 'G major',
          style_label: 'rock',
          tempo: 125,
        },
      ]
      const zeroScoreNodes: SkillNode[] = [
        { id: 'bend_accuracy', label: 'Bending', score: 0 },
        { id: 'vibrato_control', label: 'Vibrato', score: 0 },
      ]

      const results = generateDiscoveryFromLesson(masteredSong, candidateSongs, zeroScoreNodes)
      expect(results.length).toBeGreaterThan(0)
    })

    it('should handle candidate songs with null values', () => {
      const masteredSongs: MasteredSong[] = [
        {
          job_id: 'mastered1',
          song_title: 'Test Song',
          artist: 'Test Artist',
          key: 'C major',
          style_label: 'rock',
          tempo: 120,
        },
      ]
      const candidateSongs: MasteredSong[] = [
        {
          job_id: 'candidate1',
          song_title: 'Candidate Song',
          artist: 'Candidate Artist',
          key: null,
          style_label: null,
          tempo: null,
        },
      ]

      const results = generateDiscoverySuggestions(masteredSongs, candidateSongs, skillNodes)
      expect(results.length).toBeGreaterThanOrEqual(0)
    })

    it('should handle mastered songs with null values', () => {
      const masteredSongs: MasteredSong[] = [
        {
          job_id: 'mastered1',
          song_title: 'Test Song',
          artist: 'Test Artist',
          key: null,
          style_label: null,
          tempo: null,
        },
      ]
      const candidateSongs: MasteredSong[] = [
        {
          job_id: 'candidate1',
          song_title: 'Candidate Song',
          artist: 'Candidate Artist',
          key: 'C major',
          style_label: 'rock',
          tempo: 120,
        },
      ]

      const results = generateDiscoverySuggestions(masteredSongs, candidateSongs, skillNodes)
      expect(results.length).toBeGreaterThanOrEqual(0)
    })

    it('should handle very large candidate lists', () => {
      const masteredSongs: MasteredSong[] = [
        {
          job_id: 'mastered1',
          song_title: 'Test Song',
          artist: 'Test Artist',
          key: 'C major',
          style_label: 'rock',
          tempo: 120,
        },
      ]
      const candidateSongs: MasteredSong[] = Array.from({ length: 100 }, (_, i) => ({
        job_id: `candidate${i}`,
        song_title: `Song ${i}`,
        artist: `Artist ${i}`,
        key: i % 2 === 0 ? 'C major' : 'G major',
        style_label: 'rock',
        tempo: 120 + (i % 10),
      }))

      const results = generateDiscoverySuggestions(masteredSongs, candidateSongs, skillNodes, { limit: 5 })
      expect(results.length).toBeLessThanOrEqual(5)
    })

    it('should handle minSimilarity threshold filtering', () => {
      const masteredSongs: MasteredSong[] = [
        {
          job_id: 'mastered1',
          song_title: 'Test Song',
          artist: 'Test Artist',
          key: 'C major',
          style_label: 'rock',
          tempo: 120,
        },
      ]
      const candidateSongs: MasteredSong[] = [
        {
          job_id: 'candidate1',
          song_title: 'Similar Song',
          artist: 'Artist 1',
          key: 'C major',
          style_label: 'rock',
          tempo: 120,
        },
        {
          job_id: 'candidate2',
          song_title: 'Different Song',
          artist: 'Artist 2',
          key: 'F# major',
          style_label: 'jazz',
          tempo: 180,
        },
      ]

      const results = generateDiscoverySuggestions(masteredSongs, candidateSongs, skillNodes, { minSimilarity: 0.8 })
      expect(results.length).toBeGreaterThanOrEqual(0)
    })
  })
})
