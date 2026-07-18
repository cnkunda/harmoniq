import { OPEN_MIDI_BY_ROW } from '@/src/music/fretboardCell'

export type CagedForm = 'E' | 'A' | 'D' | 'C' | 'G'

export type CagedPatternCell = {
  string: number
  fret: number
  interval: number
  finger?: 1 | 2 | 3 | 4
  variant: 'primary' | 'secondary'
}

type CagedPatternDef = {
  rootString: number
  rootFret: number
  cells: CagedPatternCell[]
}

const CAGED_PATTERN_DEFS: Record<CagedForm, CagedPatternDef> = {
  E: {
    rootString: 6,
    rootFret: 0,
    cells: [
      { string: 6, fret: 0, interval: 0, finger: 1, variant: 'primary' },
      { string: 5, fret: 2, interval: 7, finger: 3, variant: 'secondary' },
      { string: 4, fret: 2, interval: 0, finger: 4, variant: 'primary' },
      { string: 3, fret: 1, interval: 4, finger: 2, variant: 'secondary' },
      { string: 2, fret: 0, interval: 7, variant: 'secondary' },
      { string: 1, fret: 0, interval: 0, variant: 'primary' },
    ],
  },
  A: {
    rootString: 5,
    rootFret: 0,
    cells: [
      { string: 5, fret: 0, interval: 0, finger: 1, variant: 'primary' },
      { string: 4, fret: 2, interval: 7, finger: 3, variant: 'secondary' },
      { string: 3, fret: 2, interval: 0, finger: 2, variant: 'primary' },
      { string: 2, fret: 2, interval: 4, finger: 4, variant: 'secondary' },
      { string: 1, fret: 0, interval: 7, variant: 'secondary' },
    ],
  },
  D: {
    rootString: 4,
    rootFret: 0,
    cells: [
      { string: 4, fret: 0, interval: 0, finger: 1, variant: 'primary' },
      { string: 3, fret: 2, interval: 7, finger: 3, variant: 'secondary' },
      { string: 2, fret: 3, interval: 0, finger: 4, variant: 'primary' },
      { string: 1, fret: 2, interval: 4, finger: 2, variant: 'secondary' },
    ],
  },
  C: {
    rootString: 5,
    rootFret: 3,
    cells: [
      { string: 5, fret: 3, interval: 0, finger: 3, variant: 'primary' },
      { string: 4, fret: 2, interval: 4, finger: 2, variant: 'secondary' },
      { string: 3, fret: 0, interval: 7, finger: 1, variant: 'secondary' },
      { string: 2, fret: 1, interval: 0, finger: 4, variant: 'primary' },
      { string: 1, fret: 0, interval: 4, variant: 'secondary' },
    ],
  },
  G: {
    rootString: 6,
    rootFret: 3,
    cells: [
      { string: 6, fret: 3, interval: 0, finger: 2, variant: 'primary' },
      { string: 5, fret: 2, interval: 4, finger: 1, variant: 'secondary' },
      { string: 4, fret: 0, interval: 7, variant: 'secondary' },
      { string: 3, fret: 0, interval: 0, variant: 'primary' },
      { string: 2, fret: 0, interval: 4, finger: 3, variant: 'secondary' },
      { string: 1, fret: 3, interval: 0, finger: 4, variant: 'primary' },
    ],
  },
}

function fretForPitchClassOnString(pitchClass: number, stringNumber: number): number {
  const openMidi = OPEN_MIDI_BY_ROW[stringNumber - 1]
  const openPC = openMidi % 12
  return ((pitchClass - openPC) % 12 + 12) % 12
}

export function getCagedPattern(form: CagedForm): CagedPatternCell[] {
  return CAGED_PATTERN_DEFS[form].cells.map((c) => ({ ...c }))
}

export function getCagedPatternForScale(
  form: CagedForm,
  rootPitchClass: number,
  scaleIntervals: number[],
): CagedPatternCell[] {
  const def = CAGED_PATTERN_DEFS[form]
  const rootFretPos = fretForPitchClassOnString(rootPitchClass, def.rootString)
  const shapeBase = rootFretPos - def.rootFret

  const scaleSet = new Set(scaleIntervals)

  return def.cells
    .map((c) => ({
      ...c,
      fret: Math.max(0, Math.min(12, c.fret + shapeBase)),
    }))
    .filter((c) => {
      const intervalMod = c.interval % 12
      return scaleSet.has(intervalMod)
    })
}
