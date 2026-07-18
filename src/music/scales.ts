import { parseKey } from '@/src/music/capoSuggestion'

export type ScaleFamily =
  | 'diatonic'
  | 'harmonic_minor'
  | 'melodic_minor'
  | 'pentatonic'
  | 'blues'
  | 'symmetrical'
  | 'other'

export interface ScaleEntry {
  name: string
  family: ScaleFamily
  intervals: number[]
  pitchClasses: number[]
  aliases: string[]
}

function buildEntry(
  name: string,
  family: ScaleFamily,
  intervals: number[],
  aliases: string[],
): ScaleEntry {
  return {
    name,
    family,
    intervals,
    pitchClasses: intervals,
    aliases,
  }
}

export const SCALE_DB: Record<string, ScaleEntry> = {
  // ---- Diatonic modes ----
  ionian: buildEntry('Ionian', 'diatonic', [0, 2, 4, 5, 7, 9, 11], ['Major', 'Major scale']),
  dorian: buildEntry('Dorian', 'diatonic', [0, 2, 3, 5, 7, 9, 10], []),
  phrygian: buildEntry('Phrygian', 'diatonic', [0, 1, 3, 5, 7, 8, 10], []),
  lydian: buildEntry('Lydian', 'diatonic', [0, 2, 4, 6, 7, 9, 11], []),
  mixolydian: buildEntry('Mixolydian', 'diatonic', [0, 2, 4, 5, 7, 9, 10], []),
  aeolian: buildEntry('Aeolian', 'diatonic', [0, 2, 3, 5, 7, 8, 10], ['Natural minor', 'Minor']),
  locrian: buildEntry('Locrian', 'diatonic', [0, 1, 3, 5, 6, 8, 10], []),

  // ---- Harmonic minor modes ----
  harmonic_minor: buildEntry('Harmonic Minor', 'harmonic_minor', [0, 2, 3, 5, 7, 8, 11], []),
  locrian_natural_6: buildEntry('Locrian ♮6', 'harmonic_minor', [0, 1, 3, 5, 6, 9, 10], ['Locrian ♮6']),
  ionian_sharp_5: buildEntry('Ionian ♯5', 'harmonic_minor', [0, 2, 4, 5, 8, 9, 11], ['Ionian #5']),
  dorian_sharp_4: buildEntry('Dorian ♯4', 'harmonic_minor', [0, 2, 3, 6, 7, 9, 10], ['Dorian #4']),
  phrygian_dominant: buildEntry('Phrygian Dominant', 'harmonic_minor', [0, 1, 4, 5, 7, 8, 10], ['Phrygian major']),
  lydian_sharp_2: buildEntry('Lydian ♯2', 'harmonic_minor', [0, 3, 4, 6, 7, 9, 11], ['Lydian #2']),
  super_locrian_bb7: buildEntry('Super Locrian ♭♭7', 'harmonic_minor', [0, 1, 3, 4, 6, 8, 10], ['Ultralocrian', 'Super Locrian bb7']),

  // ---- Melodic minor modes ----
  melodic_minor: buildEntry('Melodic Minor', 'melodic_minor', [0, 2, 3, 5, 7, 9, 11], ['Jazz minor']),
  dorian_b2: buildEntry('Dorian ♭2', 'melodic_minor', [0, 1, 3, 5, 7, 9, 10], ['Dorian b2']),
  lydian_augmented: buildEntry('Lydian Augmented', 'melodic_minor', [0, 2, 4, 6, 8, 9, 11], ['Lydian #5']),
  lydian_dominant: buildEntry('Lydian Dominant', 'melodic_minor', [0, 2, 4, 6, 7, 9, 10], ['Lydian b7']),
  mixolydian_b6: buildEntry('Mixolydian ♭6', 'melodic_minor', [0, 2, 4, 5, 7, 8, 10], ['Mixolydian b6']),
  aeolian_b5: buildEntry('Aeolian ♭5', 'melodic_minor', [0, 2, 3, 5, 6, 8, 10], ['Locrian #2', 'Aeolian b5']),
  altered: buildEntry('Altered', 'melodic_minor', [0, 1, 3, 4, 6, 8, 10], ['Super Locrian', 'Altered scale']),

  // ---- Pentatonic ----
  major_pentatonic: buildEntry('Major Pentatonic', 'pentatonic', [0, 2, 4, 7, 9], []),
  minor_pentatonic: buildEntry('Minor Pentatonic', 'pentatonic', [0, 3, 5, 7, 10], []),

  // ---- Blues ----
  blues_major: buildEntry('Blues (Major)', 'blues', [0, 2, 3, 4, 7, 9], ['Major blues']),
  blues_minor: buildEntry('Blues (Minor)', 'blues', [0, 3, 5, 6, 7, 10], ['Minor blues']),
  egyptian: buildEntry('Egyptian', 'pentatonic', [0, 2, 5, 7, 9], ['Suspended pentatonic']),

  // ---- Symmetrical ----
  whole_tone: buildEntry('Whole Tone', 'symmetrical', [0, 2, 4, 6, 8, 10], []),
  diminished_half_whole: buildEntry('Diminished (Half-Whole)', 'symmetrical', [0, 1, 3, 4, 6, 7, 9, 10], ['Half-whole diminished']),
  diminished_whole_half: buildEntry('Diminished (Whole-Half)', 'symmetrical', [0, 2, 3, 5, 6, 8, 9, 11], ['Whole-half diminished']),
  augmented_scale: buildEntry('Augmented', 'symmetrical', [0, 3, 4, 7, 8, 11], []),

  // ---- Other ----
  chromatic: buildEntry('Chromatic', 'other', [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11], []),
  bebop_dominant: buildEntry('Bebop Dominant', 'other', [0, 2, 4, 5, 7, 9, 10, 11], []),
  bebop_major: buildEntry('Bebop Major', 'other', [0, 2, 4, 5, 7, 8, 9, 11], []),
}

export function getScale(name: string): ScaleEntry | undefined {
  return SCALE_DB[name]
}

export function getScalesByFamily(family: ScaleFamily): ScaleEntry[] {
  return Object.values(SCALE_DB).filter((s) => s.family === family)
}

export function getScalePitchClasses(root: number, scaleName: string): number[] | null {
  const entry = SCALE_DB[scaleName]
  if (!entry) return null
  return entry.intervals.map((i) => (root + i) % 12)
}

export function getScalePitchClassesFromKey(keyLabel: string): number[] | null {
  const parsed = parseKey(keyLabel)
  if (!parsed) return null
  const scaleName = parsed.mode === 'major' ? 'ionian' : 'aeolian'
  return getScalePitchClasses(parsed.semitone, scaleName)
}

export function matchScaleToPitchClasses(
  observed: number[],
  rootPitchClass?: number,
): Array<{ name: string; score: number }> {
  if (observed.length === 0) return []

  const observedSet = new Set(observed.filter((pc) => pc >= 0 && pc <= 11))
  if (observedSet.size === 0) return []

  const candidates: Array<{ name: string; score: number }> = []

  for (const [key, entry] of Object.entries(SCALE_DB)) {
    // Transpose scale intervals to rootPitchClass when provided; otherwise use raw pitchClasses
    const scalePCs = rootPitchClass != null
      ? entry.intervals.map((i) => (rootPitchClass + i) % 12)
      : entry.pitchClasses
    const scalePcSet = new Set(scalePCs)

    // Overlap: count of observed PCs that are in the (transposed) scale
    let overlap = 0
    for (const pc of observedSet) {
      if (scalePcSet.has(pc)) overlap += 1
    }
    const overlapScore = overlap / Math.max(scalePCs.length, observedSet.size)

    // Root alignment: 1.0 if observed set contains the scale root, else 0.0
    const root = rootPitchClass != null ? rootPitchClass : scalePCs[0]
    const rootAlignment = observedSet.has(root) ? 1.0 : 0.0

    // Pentatonic skeleton match: overlap with the 5 core notes of the scale
    const third = entry.intervals[2]
    const pentIntervals: number[] = third <= 3 ? [0, 3, 5, 7, 10] : [0, 2, 4, 7, 9]
    const pentSet = new Set(pentIntervals)
    const pentSkeletonPCs = scalePCs.filter((_, i) => pentSet.has(entry.intervals[i]))
    const pentOverlap = [...observedSet].filter((pc) => pentSkeletonPCs.includes(pc)).length
    const pentatonicScore = pentSkeletonPCs.length > 0 ? pentOverlap / pentSkeletonPCs.length : 0

    const score = 0.5 * overlapScore + 0.3 * rootAlignment + 0.2 * pentatonicScore

    candidates.push({ name: key, score })
  }

  candidates.sort((a, b) => b.score - a.score)
  return candidates.slice(0, 3)
}
