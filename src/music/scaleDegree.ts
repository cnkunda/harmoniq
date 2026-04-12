import { parseKey } from '@/src/music/capoSuggestion'

const NOTE_NAMES_SHARP = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'] as const

export function midiToNoteName(midi: number): string {
  const m = Math.round(midi)
  const pc = ((m % 12) + 12) % 12
  const oct = Math.floor(m / 12) - 1
  return `${NOTE_NAMES_SHARP[pc]}${oct}`
}

function intervalFromRoot(rootPc: number, midi: number): number {
  const pc = ((Math.round(midi) % 12) + 12) % 12
  return (pc - rootPc + 12) % 12
}

/** Scale-degree label relative to parsed key; includes blues b7 wording in minor. */
export function scaleDegreeLabel(keyLabel: string, midi: number): string {
  const parsed = parseKey(keyLabel)
  if (!parsed) {
    const pc = ((Math.round(midi) % 12) + 12) % 12
    return `${NOTE_NAMES_SHARP[pc]} (add a readable key like “A minor” for scale degree)`
  }

  const iv = intervalFromRoot(parsed.semitone, midi)

  if (parsed.mode === 'major') {
    const majorMap: Record<number, string> = {
      0: '1 — tonic',
      1: 'b2',
      2: '2 — major 2nd',
      3: 'b3',
      4: '3 — major 3rd',
      5: '4 — perfect 4th',
      6: 'b5 / #4 — tritone',
      7: '5 — perfect 5th',
      8: 'b6',
      9: '6 — major 6th',
      10: 'b7 — flat seventh (blues colour in major)',
      11: '7 — leading tone',
    }
    return majorMap[iv] ?? `chromatic alteration (${iv} semitones from tonic)`
  }

  const minorMap: Record<number, string> = {
    0: '1 — tonic',
    1: 'b2',
    2: '2',
    3: 'b3',
    4: '4',
    5: 'b5',
    6: 'b6 / #5 colour',
    7: '5 — perfect fifth',
    8: 'b6',
    9: '6 — major sixth (melodic / borrowed colour)',
    10: 'b7 — minor seventh / blues flat-seven colour',
    11: '7 — leading tone (harmonic minor colour)',
  }
  return minorMap[iv] ?? `chromatic alteration (${iv} semitones from tonic)`
}

export function buildStudyCoachLine(params: {
  noteName: string
  degreeLabel: string
  fingerLine: string
  keyLabel: string
}): string {
  const key = params.keyLabel.trim() || 'this piece'
  return `In ${key}, ${params.noteName} functions as ${params.degreeLabel}. ${params.fingerLine} Listen for intonation against the backing track and keep the motion small.`
}
