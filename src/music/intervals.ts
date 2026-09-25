export enum Interval {
  Unison = 0,
  m2 = 1,
  M2 = 2,
  m3 = 3,
  M3 = 4,
  P4 = 5,
  Tritone = 6,
  P5 = 7,
  m6 = 8,
  M6 = 9,
  m7 = 10,
  M7 = 11,
  Octave = 12,
}

const INTERVAL_NAMES: Record<Interval, string> = {
  [Interval.Unison]: 'unison',
  [Interval.m2]: 'minor 2nd',
  [Interval.M2]: 'major 2nd',
  [Interval.m3]: 'minor 3rd',
  [Interval.M3]: 'major 3rd',
  [Interval.P4]: 'perfect 4th',
  [Interval.Tritone]: 'tritone',
  [Interval.P5]: 'perfect 5th',
  [Interval.m6]: 'minor 6th',
  [Interval.M6]: 'major 6th',
  [Interval.m7]: 'minor 7th',
  [Interval.M7]: 'major 7th',
  [Interval.Octave]: 'octave',
}

const INTERVAL_ABBREVIATIONS: Record<Interval, string> = {
  [Interval.Unison]: 'P1',
  [Interval.m2]: 'm2',
  [Interval.M2]: 'M2',
  [Interval.m3]: 'm3',
  [Interval.M3]: 'M3',
  [Interval.P4]: 'P4',
  [Interval.Tritone]: 'TT',
  [Interval.P5]: 'P5',
  [Interval.m6]: 'm6',
  [Interval.M6]: 'M6',
  [Interval.m7]: 'm7',
  [Interval.M7]: 'M7',
  [Interval.Octave]: 'P8',
}

export function intervalSemitones(i: Interval): number {
  return i as number
}

export function intervalName(i: Interval): string {
  return INTERVAL_NAMES[i] ?? `unknown (${i})`
}

export function intervalAbbr(i: Interval): string {
  return INTERVAL_ABBREVIATIONS[i] ?? `?${i}`
}

const _SEMITONES_TO_INTERVAL: Record<number, Interval> = {
  0: Interval.Unison,
  1: Interval.m2,
  2: Interval.M2,
  3: Interval.m3,
  4: Interval.M3,
  5: Interval.P4,
  6: Interval.Tritone,
  7: Interval.P5,
  8: Interval.m6,
  9: Interval.M6,
  10: Interval.m7,
  11: Interval.M7,
  12: Interval.Octave,
}

export function semitonesToInterval(semitones: number): Interval | null {
  return _SEMITONES_TO_INTERVAL[semitones] ?? null
}
