/**
 * Slonimsky-derived warmup pattern generator.
 *
 * Algorithmically produces fretboard positions for 4 pattern families —
 * interpolation, infrapolation, tritone_sequence, and compound —
 * derived from the principles in Slonimsky's "Thesaurus of Scales and
 * Melodic Patterns."
 *
 * All positions are deterministically computed from a seed value.
 */

import { Interval } from '@/src/music/intervals'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type SlonimskyFamily = 'interpolation' | 'infrapolation' | 'tritone_sequence' | 'compound'

export interface SlonimskyFretboardCell {
  string: number
  fret: number
  variant: 'primary' | 'secondary'
  finger?: 1 | 2 | 3 | 4
}

export interface SlonimskyPattern {
  id: string
  name: string
  description: string
  techniqueTags: string[]
  family: SlonimskyFamily
  fretboardCells: SlonimskyFretboardCell[]
  caption?: string
  defaultDurationSeconds: number
  difficulty: number
  isOpener: boolean
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

const STRING_BASE_MIDI: Record<number, number> = {
  1: 64,
  2: 59,
  3: 55,
  4: 50,
  5: 45,
  6: 40,
}

function _midi(s: number, fret: number): number {
  return (STRING_BASE_MIDI[s] ?? 64) + fret
}

function _findCell(targetMidi: number): { string: number; fret: number } | null {
  for (let s = 6; s >= 1; s -= 1) {
    const fret = targetMidi - (STRING_BASE_MIDI[s] ?? 64)
    if (fret >= 0 && fret <= 24) return { string: s, fret }
  }
  return null
}

function _cell(
  string: number,
  fret: number,
  variant: 'primary' | 'secondary',
  finger?: 1 | 2 | 3 | 4,
): SlonimskyFretboardCell {
  return { string, fret, variant, finger }
}

function _rng(seed: number): number {
  return Number((BigInt(seed) * 1103515245n + 12345n) & 0x7fffffffn)
}

function _pickIndex(seed: number, n: number): number {
  if (n <= 0) return 0
  return _rng(seed) % n
}

function _pickString(seed: number): number {
  return _pickIndex(seed, 6) + 1
}

function _pickFret(seed: number, maxStart: number): number {
  return _pickIndex(seed, maxStart) + 1
}

// ---------------------------------------------------------------------------
// Pattern descriptors with generate functions
// ---------------------------------------------------------------------------

interface PatternDescriptor {
  id: string
  name: string
  description: string
  techniqueTags: string[]
  family: SlonimskyFamily
  difficulty: number
  isOpener: boolean
  defaultDurationSeconds: number
  generate: (seed: number) => { cells: SlonimskyFretboardCell[]; caption: string }
}

function _interpCells(
  seed: number,
  order: number[],
  diff: number,
): { cells: SlonimskyFretboardCell[]; caption: string } {
  const s = _pickString(seed)
  const start = _pickFret(_rng(seed + 1), diff <= 1 ? 8 : 6)
  const cells: SlonimskyFretboardCell[] = []
  for (let i = 0; i < order.length; i += 1) {
    const offset = order[i]!
    cells.push(_cell(s, start + offset, 'primary', (offset + 1) as 1 | 2 | 3 | 4))
  }
  const fingerLabels = order.map((o) => ['Idx', 'Mid', 'Ring', 'Pinky'][o] ?? '?').join(' → ')
  return {
    cells,
    caption: `Play in finger order: ${fingerLabels}. Keep fingers close to the frets.`,
  }
}

const _NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

function _infraCells(
  seed: number,
  semitones: number,
  diff: number,
): { cells: SlonimskyFretboardCell[]; caption: string } {
  const s = _pickString(seed)
  const start = _pickFret(_rng(seed + 1), diff <= 2 ? 7 : 5)
  const rootCell = _cell(s, start, 'primary', 2)
  const b2Cell = _cell(s, start - 1, 'secondary', 1)
  const targetMidi = _midi(s, start) + semitones
  const target = _findCell(targetMidi) ?? { string: s, fret: start + semitones }
  const targetFinger: 3 | 4 = semitones >= 10 ? 4 : 3
  const targetCell = _cell(target.string, target.fret, 'primary', targetFinger)
  const rootNote = _NOTE_NAMES[_midi(s, start) % 12]
  return {
    cells: [b2Cell, rootCell, targetCell],
    caption: `${rootNote} Root on string ${s} fret ${start}. Approach from below (fret ${start - 1}), leap ${semitones} semitones.`,
  }
}

function _tritoneCells(
  seed: number,
  cellSize: number,
  repeatCount: number,
  descending: boolean,
): { cells: SlonimskyFretboardCell[]; caption: string } {
  const s = _pickString(seed)
  const start = _pickFret(_rng(seed + 1), 6)
  const cells: SlonimskyFretboardCell[] = []
  for (let r = 0; r < repeatCount; r += 1) {
    const shift = r * 6
    for (let i = 0; i < cellSize; i += 1) {
      const offset = descending ? cellSize - 1 - i : i
      const fret = start + shift + offset
      const variant: 'primary' | 'secondary' = r === 0 ? 'primary' : 'secondary'
      const finger = (offset + 1) as 1 | 2 | 3 | 4
      cells.push(_cell(s, fret, variant, finger))
    }
  }
  return {
    cells,
    caption: `${cellSize}-note ${descending ? 'descending' : 'ascending'} cell shifted by tritone (6 frets) ${repeatCount > 1 ? `${repeatCount} times` : ''}.`,
  }
}

const PATTERN_DESCRIPTORS: PatternDescriptor[] = [
  // ---- Interpolation (5) ----
  {
    id: 'slonimsky_interp_1324',
    name: 'Interpolation 1-3-2-4 (standard)',
    description: 'Play four consecutive frets in 1-3-2-4 finger order. Breaks the linear habit and builds finger independence.',
    techniqueTags: ['finger_independence', 'timing'],
    family: 'interpolation',
    difficulty: 1,
    isOpener: true,
    defaultDurationSeconds: 60,
    generate: (seed) => _interpCells(seed, [0, 2, 1, 3], 1),
  },
  {
    id: 'slonimsky_interp_1423',
    name: 'Interpolation 1-4-2-3 (wide)',
    description: 'Finger order 1-4-2-3 — index to pinky stretch challenges hand position awareness.',
    techniqueTags: ['finger_independence', 'shifting'],
    family: 'interpolation',
    difficulty: 2,
    isOpener: true,
    defaultDurationSeconds: 60,
    generate: (seed) => _interpCells(seed, [0, 3, 1, 2], 2),
  },
  {
    id: 'slonimsky_interp_1342',
    name: 'Interpolation 1-3-4-2 (ring-pinky)',
    description: 'Ring then pinky instead of middle — a subtle reordering that trips up automatic pilot.',
    techniqueTags: ['finger_independence', 'timing'],
    family: 'interpolation',
    difficulty: 1,
    isOpener: true,
    defaultDurationSeconds: 58,
    generate: (seed) => _interpCells(seed, [0, 2, 3, 1], 1),
  },
  {
    id: 'slonimsky_interp_2413',
    name: 'Interpolation 2-4-1-3 (shift start)',
    description: 'Starts with the middle finger — resets your hand frame and forces a deliberate shift.',
    techniqueTags: ['finger_independence', 'shifting'],
    family: 'interpolation',
    difficulty: 2,
    isOpener: false,
    defaultDurationSeconds: 62,
    generate: (seed) => _interpCells(seed, [1, 3, 0, 2], 2),
  },
  {
    id: 'slonimsky_interp_1243',
    name: 'Interpolation 1-2-4-3 (pinky close)',
    description: 'Pinky lands before ring — a close-interval challenge for the last two fingers.',
    techniqueTags: ['finger_independence', 'timing'],
    family: 'interpolation',
    difficulty: 1,
    isOpener: true,
    defaultDurationSeconds: 56,
    generate: (seed) => _interpCells(seed, [0, 1, 3, 2], 1),
  },

  // ---- Infrapolation (5) ----
  {
    id: 'slonimsky_infra_m3',
    name: 'Infrapolation — root → b2 → M3',
    description: 'Root, half-step below, then leap up a major third. A classic Slonimsky outside sound.',
    techniqueTags: ['pitch', 'shifting'],
    family: 'infrapolation',
    difficulty: 2,
    isOpener: false,
    defaultDurationSeconds: 60,
    generate: (seed) => _infraCells(seed, Interval.M3, 2),
  },
  {
    id: 'slonimsky_infra_p4',
    name: 'Infrapolation — root → b2 → P4',
    description: 'Approach from the half-step below, leap up a perfect fourth. Opens up the hand.',
    techniqueTags: ['pitch', 'shifting'],
    family: 'infrapolation',
    difficulty: 2,
    isOpener: false,
    defaultDurationSeconds: 58,
    generate: (seed) => _infraCells(seed, Interval.P4, 2),
  },
  {
    id: 'slonimsky_infra_p5',
    name: 'Infrapolation — root → b2 → P5',
    description: 'Half-step approach, perfect fifth leap. Wider interval demands left-hand relaxation.',
    techniqueTags: ['pitch', 'shifting'],
    family: 'infrapolation',
    difficulty: 2,
    isOpener: false,
    defaultDurationSeconds: 60,
    generate: (seed) => _infraCells(seed, Interval.P5, 2),
  },
  {
    id: 'slonimsky_infra_m7',
    name: 'Infrapolation — root → b2 → m7',
    description: 'Big stretch: half-step below root, then jump a minor seventh. Extreme finger spread.',
    techniqueTags: ['pitch', 'shifting'],
    family: 'infrapolation',
    difficulty: 3,
    isOpener: false,
    defaultDurationSeconds: 64,
    generate: (seed) => _infraCells(seed, Interval.m7, 3),
  },
  {
    id: 'slonimsky_infra_M7',
    name: 'Infrapolation — root → b2 → M7',
    description: 'Maximum infrapolation stretch — approach from below, leap a major seventh. Wide interval control.',
    techniqueTags: ['pitch', 'shifting'],
    family: 'infrapolation',
    difficulty: 3,
    isOpener: false,
    defaultDurationSeconds: 64,
    generate: (seed) => _infraCells(seed, Interval.M7, 3),
  },

  // ---- Tritone sequence (5) ----
  {
    id: 'slonimsky_tt_asc4',
    name: 'Tritone sequence — ascending 4-note',
    description: 'Play a 4-note ascending cell, then shift the whole shape up a tritone and repeat.',
    techniqueTags: ['shifting', 'timing'],
    family: 'tritone_sequence',
    difficulty: 2,
    isOpener: true,
    defaultDurationSeconds: 60,
    generate: (seed) => _tritoneCells(seed, 4, 2, false),
  },
  {
    id: 'slonimsky_tt_desc4',
    name: 'Tritone sequence — descending 4-note',
    description: 'Descending 4-note cell shifted by tritone. Landing clean is the goal.',
    techniqueTags: ['shifting', 'timing'],
    family: 'tritone_sequence',
    difficulty: 2,
    isOpener: true,
    defaultDurationSeconds: 60,
    generate: (seed) => _tritoneCells(seed, 4, 2, true),
  },
  {
    id: 'slonimsky_tt_3note_x2',
    name: 'Tritone sequence — 3-note × 3 shifts',
    description: 'Compact 3-note cell shifted by tritone three times. Rapid position changes.',
    techniqueTags: ['shifting', 'timing'],
    family: 'tritone_sequence',
    difficulty: 3,
    isOpener: false,
    defaultDurationSeconds: 62,
    generate: (seed) => _tritoneCells(seed, 3, 3, false),
  },
  {
    id: 'slonimsky_tt_4note_x3',
    name: 'Tritone sequence — 4-note × 3 shifts',
    description: 'Four-note cell shifted by tritone then again — covers a lot of the neck.',
    techniqueTags: ['shifting', 'timing'],
    family: 'tritone_sequence',
    difficulty: 3,
    isOpener: false,
    defaultDurationSeconds: 64,
    generate: (seed) => _tritoneCells(seed, 4, 3, false),
  },
  {
    id: 'slonimsky_tt_cross_string',
    name: 'Tritone sequence — cross-string',
    description: 'Ascending 4-note cell on one string, tritone shift to the next string. String change + shift.',
    techniqueTags: ['shifting', 'string_skipping'],
    family: 'tritone_sequence',
    difficulty: 3,
    isOpener: false,
    defaultDurationSeconds: 62,
    generate: (seed) => {
      const s = _pickString(seed)
      const start = _pickFret(_rng(seed + 1), 5)
      const s2 = Math.max(1, s - 1)
      const cells: SlonimskyFretboardCell[] = []
      for (let i = 0; i < 4; i += 1) {
        cells.push(_cell(s, start + i, 'primary', (i + 1) as 1 | 2 | 3 | 4))
      }
      const cell2Midi = _midi(s, start) + 6
      for (let i = 0; i < 4; i += 1) {
        const m = cell2Midi + i
        const found = _findCell(m)
        if (found) {
          cells.push(_cell(found.string, found.fret, 'secondary', (i + 1) as 1 | 2 | 3 | 4))
        }
      }
      return {
        cells,
        caption: `Cell on string ${s}, then tritone shift to string ${s2}. Watch the string change.`,
      }
    },
  },

  // ---- Compound (3) ----
  {
    id: 'slonimsky_cmp_interp_tt',
    name: 'Compound — interpolated tritone sequence',
    description: 'Interpolated 1-3-2-4 cell shifted by tritone. Combines finger independence with position shifting.',
    techniqueTags: ['finger_independence', 'shifting'],
    family: 'compound',
    difficulty: 3,
    isOpener: false,
    defaultDurationSeconds: 64,
    generate: (seed) => {
      const s = _pickString(seed)
      const start = _pickFret(_rng(seed + 1), 5)
      const order = [0, 2, 1, 3]
      const cells: SlonimskyFretboardCell[] = []
      for (let r = 0; r < 2; r += 1) {
        const shift = r * 6
        for (let i = 0; i < order.length; i += 1) {
          const offset = order[i]!
          const fret = start + shift + offset
          const variant: 'primary' | 'secondary' = r === 0 ? 'primary' : 'secondary'
          cells.push(_cell(s, fret, variant, (offset + 1) as 1 | 2 | 3 | 4))
        }
      }
      return {
        cells,
        caption: 'Interpolation 1-3-2-4 at fret ' + start + ', then tritone shift to ' + (start + 6) + '.',
      }
    },
  },
  {
    id: 'slonimsky_cmp_infra_desc',
    name: 'Compound — infrapolation with descending tail',
    description: 'Infrapolation leap followed by a descending chromatic tail. Pitch plus recovery.',
    techniqueTags: ['pitch', 'shifting'],
    family: 'compound',
    difficulty: 3,
    isOpener: false,
    defaultDurationSeconds: 62,
    generate: (seed) => {
      const s = _pickString(seed)
      const start = _pickFret(_rng(seed + 1), 5)
      const cells: SlonimskyFretboardCell[] = [
        _cell(s, start, 'primary', 2),
        _cell(s, start - 1, 'secondary', 1),
        _cell(s, start + 4, 'primary', 3),
      ]
      for (let i = 0; i < 3; i += 1) {
        cells.push(_cell(s, start + 4 - i - 1, 'secondary', (4 - i) as 2 | 3 | 4))
      }
      return {
        cells,
        caption: `Infrapolation (fret ${start - 1} → ${start} → ${start + 4}) then descend to ${start + 1}.`,
      }
    },
  },
  {
    id: 'slonimsky_cmp_two_string',
    name: 'Compound — two-string interpolated shift',
    description: 'Interpolated 1-3-2-4 on string 5, repeat on string 4 with tritone shift. Two-line voice leading.',
    techniqueTags: ['finger_independence', 'string_skipping'],
    family: 'compound',
    difficulty: 3,
    isOpener: false,
    defaultDurationSeconds: 64,
    generate: (seed) => {
      const s = _pickString(seed)
      const start = _pickFret(_rng(seed + 1), 4)
      const s2 = Math.max(1, s - 1)
      const order = [0, 2, 1, 3]
      const cells: SlonimskyFretboardCell[] = []
      for (let i = 0; i < order.length; i += 1) {
        const offset = order[i]!
        cells.push(_cell(s, start + offset, 'primary', (offset + 1) as 1 | 2 | 3 | 4))
      }
      for (let i = 0; i < order.length; i += 1) {
        const offset = order[i]!
        const targetMidi = _midi(s, start) + 6 + offset
        const found = _findCell(targetMidi) ?? { string: s2, fret: start + 6 + offset }
        cells.push(_cell(found.string, found.fret, 'secondary', (offset + 1) as 1 | 2 | 3 | 4))
      }
      return {
        cells,
        caption: `Interpolation on string ${s}, tritone shift to string ${s2}. Two-voice independence.`,
      }
    },
  },
]

// ---------------------------------------------------------------------------
// Exported API
// ---------------------------------------------------------------------------

/**
 * Generate a Slonimsky pattern for a given family with deterministic seeding.
 * Returns `null` when the family is invalid.
 */
export function generateSlonimskyPattern(
  family: string,
  seed?: number,
): SlonimskyPattern | null {
  const s = seed ?? Date.now()
  const descriptors = PATTERN_DESCRIPTORS.filter((d) => d.family === family)
  if (descriptors.length === 0) return null
  const idx = _pickIndex(s, descriptors.length)
  const desc = descriptors[idx]!
  const { cells, caption } = desc.generate(s)
  return {
    id: desc.id,
    name: desc.name,
    description: desc.description,
    techniqueTags: desc.techniqueTags,
    family: desc.family,
    fretboardCells: cells,
    caption,
    defaultDurationSeconds: desc.defaultDurationSeconds,
    difficulty: desc.difficulty,
    isOpener: desc.isOpener,
  }
}

/**
 * Deterministic daily warmup pick seeded by date integer (e.g., YYYYMMDD).
 * Returns the selected pattern wrapped in `{ id, pattern }`.
 */
export function generateDailyWarmup(seed?: number): {
  id: string
  pattern: SlonimskyPattern
} {
  const s = seed ?? _dailySeed()
  const idx = _pickIndex(s, PATTERN_DESCRIPTORS.length)
  const desc = PATTERN_DESCRIPTORS[idx]!
  const { cells, caption } = desc.generate(s)
  const pattern: SlonimskyPattern = {
    id: desc.id,
    name: desc.name,
    description: desc.description,
    techniqueTags: desc.techniqueTags,
    family: desc.family,
    fretboardCells: cells,
    caption,
    defaultDurationSeconds: desc.defaultDurationSeconds,
    difficulty: desc.difficulty,
    isOpener: desc.isOpener,
  }
  return { id: desc.id, pattern }
}

/**
 * Return all patterns whose difficulty <= the given level.
 * Uses seed 0 for deterministic fretboard positions.
 */
export function getSlonimskyPatternsByDifficulty(level: 1 | 2 | 3): SlonimskyPattern[] {
  return PATTERN_DESCRIPTORS
    .filter((d) => d.difficulty <= level)
    .map((desc) => {
      const { cells, caption } = desc.generate(0)
      return {
        id: desc.id,
        name: desc.name,
        description: desc.description,
        techniqueTags: desc.techniqueTags,
        family: desc.family,
        fretboardCells: cells,
        caption,
        defaultDurationSeconds: desc.defaultDurationSeconds,
        difficulty: desc.difficulty,
        isOpener: desc.isOpener,
      }
    })
}

/**
 * Return today's date as an integer seed (YYYYMMDD).
 * Matches Python backend's convention for deterministic daily picks.
 */
export function dailySeedFromDate(date: Date): number {
  return date.getFullYear() * 10000 + (date.getMonth() + 1) * 100 + date.getDate()
}

function _dailySeed(): number {
  return dailySeedFromDate(new Date())
}
