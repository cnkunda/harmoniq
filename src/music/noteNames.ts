/**12 pitch classes, MIDI order (C = 0). */
export const CHROMATIC_NOTE_NAMES = [
  'C',
  'C#',
  'D',
  'D#',
  'E',
  'F',
  'F#',
  'G',
  'G#',
  'A',
  'A#',
  'B',
] as const

/** Letter name for MIDI note’s pitch class (ignores octave). */
export function pitchClassLabelFromMidi(midi: number): string {
  const pc = ((Math.round(midi) % 12) + 12) % 12
  return CHROMATIC_NOTE_NAMES[pc] ?? 'C'
}
