export interface ProgressionPattern {
  name: string
  description: string
  romanPattern: string[]
  minLength: number
  style: string
}

export interface ProgressionLabel {
  startBar: number
  endBar: number
  name: string
  description: string
}

export interface ProgressionMatch {
  startBar: number
  endBar: number
  pattern: ProgressionPattern
  matchedNumerals: string[]
}

export const COMMON_PROGRESSIONS: ProgressionPattern[] = [
  {
    name: 'ii-V-I',
    description: 'The most fundamental jazz progression — pre-dominant to dominant to tonic',
    romanPattern: ['ii', 'V', 'I'],
    minLength: 3,
    style: 'jazz',
  },
  {
    name: 'I-IV-V',
    description: 'The classic blues and rock foundation — tonic to subdominant to dominant',
    romanPattern: ['I', 'IV', 'V'],
    minLength: 3,
    style: 'blues',
  },
  {
    name: 'I-V-vi-IV',
    description: 'The pop-punk staple — four chords that drive countless hits',
    romanPattern: ['I', 'V', 'vi', 'IV'],
    minLength: 4,
    style: 'pop',
  },
  {
    name: 'vi-IV-I-V',
    description: 'The inverted pop progression — a minor start landing on the dominant',
    romanPattern: ['vi', 'IV', 'I', 'V'],
    minLength: 4,
    style: 'pop',
  },
  {
    name: 'I-vi-IV-V',
    description: 'The 50s progression / doo-wop — timeless romantic harmony',
    romanPattern: ['I', 'vi', 'IV', 'V'],
    minLength: 4,
    style: 'pop',
  },
  {
    name: 'ii°-V-i',
    description: 'The minor-key jazz progression — diminished supertonic to dominant to tonic',
    romanPattern: ['ii°', 'V', 'i'],
    minLength: 3,
    style: 'jazz',
  },
  {
    name: 'ii°-V7-i',
    description: 'The minor-key jazz progression with dominant seventh',
    romanPattern: ['ii°', 'V7', 'i'],
    minLength: 3,
    style: 'jazz',
  },
  {
    name: 'I-IV-I-V',
    description: 'The blues turnaround — short loop back to the dominant',
    romanPattern: ['I', 'IV', 'I', 'V'],
    minLength: 4,
    style: 'blues',
  },
  {
    name: 'iii-vi-ii-V',
    description: 'The jazz turnaround — cycle of descending thirds leading to the dominant',
    romanPattern: ['iii', 'vi', 'ii', 'V'],
    minLength: 4,
    style: 'jazz',
  },
  {
    name: 'I-IV-ii-V',
    description: 'A smooth harmonic descent — tonic through subdominant variants to dominant',
    romanPattern: ['I', 'IV', 'ii', 'V'],
    minLength: 4,
    style: 'jazz',
  },
]

function normalizeRoman(roman: string): string {
  return roman.toLowerCase().replace(/[0-9]/g, '')
}

function romanMatches(patternRoman: string, dataRoman: string): boolean {
  return normalizeRoman(patternRoman) === normalizeRoman(dataRoman)
}

export function findProgressions(
  romanNumerals: string[],
  patterns: ProgressionPattern[] = COMMON_PROGRESSIONS,
): ProgressionMatch[] {
  if (romanNumerals.length === 0) return []

  const matches: ProgressionMatch[] = []

  for (let pos = 0; pos < romanNumerals.length; pos++) {
    for (const pattern of patterns) {
      if (pos + pattern.minLength > romanNumerals.length) continue

      const slice = romanNumerals.slice(pos, pos + pattern.minLength)
      let matched = true
      for (let i = 0; i < pattern.minLength; i++) {
        if (!romanMatches(pattern.romanPattern[i], slice[i])) {
          matched = false
          break
        }
      }

      if (matched) {
        matches.push({
          startBar: pos,
          endBar: pos + pattern.minLength - 1,
          pattern,
          matchedNumerals: slice,
        })
      }
    }
  }

  return matches
}
