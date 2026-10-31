/**
 * Commit 168: pure geometry helpers for left-handed diagram mirroring.
 *
 * Mirroring is a rendering concern only: logical string/fret values and pitch
 * resolution are unchanged. Right-handed output must remain byte-identical.
 */
import type { GuitarHand } from '@/src/preferences/guitarHand'

export type FretboardXLayout = {
  boardLeft: number
  boardRight: number
  nutWidth: number
  fretCount: number
}

export type FretCellSpan = {
  start: number
  end: number
}

/**
 * Horizontal span (in SVG user units) occupied by a fret cell, mirrored around
 * the board centre when `hand === 'left'`. Fret `0` is the nut slot.
 *
 * Fret values beyond `fretCount` intentionally keep their full offset so the
 * existing off-board behaviour (e.g. notated fret 15) is preserved.
 */
export function fretCellSpan(
  fret: number,
  hand: GuitarHand,
  layout: FretboardXLayout,
): FretCellSpan {
  const { boardLeft, boardRight, nutWidth, fretCount } = layout
  const boardWidth = boardRight - boardLeft
  const columnWidth = (boardWidth - nutWidth) / fretCount
  const safeFret = Number.isFinite(fret) ? Math.max(0, fret) : 0

  const localStart = safeFret === 0 ? 0 : nutWidth + (safeFret - 1) * columnWidth
  const localEnd = safeFret === 0 ? nutWidth : nutWidth + safeFret * columnWidth

  if (hand === 'right') {
    return { start: boardLeft + localStart, end: boardLeft + localEnd }
  }

  return {
    start: boardLeft + boardWidth - localEnd,
    end: boardLeft + boardWidth - localStart,
  }
}

/** Centre X of a fret cell for the requested hand. */
export function fretCellCenterX(
  fret: number,
  hand: GuitarHand,
  layout: FretboardXLayout,
): number {
  const span = fretCellSpan(fret, hand, layout)
  return (span.start + span.end) / 2
}

/**
 * X of the fret wire that closes a fret cell. Right-handed diagrams place it
 * on the cell's right edge; mirrored diagrams count frets leftwards, so it is
 * the cell's left edge.
 */
export function fretWireX(
  fret: number,
  hand: GuitarHand,
  layout: FretboardXLayout,
): number {
  const span = fretCellSpan(fret, hand, layout)
  return hand === 'right' ? span.end : span.start
}

/**
 * Map a logical chord-diagram string index (0 = first rendered column) to its
 * mirrored display column. Six strings are the norm, but the count is explicit
 * so the helper stays testable and self-documenting.
 */
export function chordStringDisplayIndex(
  stringIndex: number,
  hand: GuitarHand,
  stringCount = 6,
): number {
  const safeCount = Math.max(1, Math.round(stringCount))
  const safeIndex = Math.max(0, Math.min(safeCount - 1, Math.round(stringIndex)))
  return hand === 'left' ? safeCount - 1 - safeIndex : safeIndex
}
