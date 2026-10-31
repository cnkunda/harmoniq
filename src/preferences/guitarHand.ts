/**
 * Commit 168: playing-hand preference for fretboard and chord-diagram mirroring.
 *
 * Right-handed diagrams are the non-regression default; a stored value only
 * changes the rendered orientation, never the underlying string/fret or pitch.
 */
export const GUITAR_HANDS = ['right', 'left'] as const

export type GuitarHand = (typeof GUITAR_HANDS)[number]

export const DEFAULT_GUITAR_HAND: GuitarHand = 'right'

/** Parse a stored `guitar_hand` value; unknown values are rejected. */
export function parseGuitarHand(raw: string | null | undefined): GuitarHand | null {
  if (raw == null) return null
  const normalized = raw.trim().toLowerCase()
  return (GUITAR_HANDS as readonly string[]).includes(normalized)
    ? (normalized as GuitarHand)
    : null
}
