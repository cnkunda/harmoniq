import { describe, expect, it } from 'vitest'

import {
  chordStringDisplayIndex,
  fretCellCenterX,
  fretCellSpan,
  fretWireX,
  type FretboardXLayout,
} from './diagramMirror'

const LAYOUT: FretboardXLayout = {
  boardLeft: 44,
  boardRight: 888,
  nutWidth: 8,
  fretCount: 12,
}

const BOARD_CENTRE_SUM = LAYOUT.boardLeft + LAYOUT.boardRight

describe('fretCellSpan', () => {
  it('keeps the right-handed layout unchanged', () => {
    expect(fretCellSpan(0, 'right', LAYOUT)).toEqual({ start: 44, end: 52 })
    const first = fretCellSpan(1, 'right', LAYOUT)
    expect(first.start).toBe(52)
    expect(first.end).toBeGreaterThan(first.start)
  })

  it('mirrors the nut to the right edge for left-handed mode', () => {
    expect(fretCellSpan(0, 'left', LAYOUT)).toEqual({
      start: LAYOUT.boardRight - LAYOUT.nutWidth,
      end: LAYOUT.boardRight,
    })
  })

  it('mirrors every full cell around the board centre', () => {
    for (let fret = 0; fret <= LAYOUT.fretCount; fret += 1) {
      const right = fretCellCenterX(fret, 'right', LAYOUT)
      const left = fretCellCenterX(fret, 'left', LAYOUT)
      expect(right + left).toBeCloseTo(BOARD_CENTRE_SUM, 6)
    }
  })
})

describe('fretWireX', () => {
  it('uses opposite cell edges for each hand', () => {
    const span = fretCellSpan(3, 'left', LAYOUT)
    expect(fretWireX(3, 'right', LAYOUT)).toBeCloseTo(fretCellSpan(3, 'right', LAYOUT).end, 6)
    expect(fretWireX(3, 'left', LAYOUT)).toBeCloseTo(span.start, 6)
  })
})

describe('chordStringDisplayIndex', () => {
  it('leaves right-handed columns in place', () => {
    expect([0, 1, 5].map((i) => chordStringDisplayIndex(i, 'right'))).toEqual([0, 1, 5])
  })

  it('flips left-handed columns and is its own inverse', () => {
    expect([0, 1, 5].map((i) => chordStringDisplayIndex(i, 'left'))).toEqual([5, 4, 0])
    for (let i = 0; i < 6; i += 1) {
      expect(chordStringDisplayIndex(chordStringDisplayIndex(i, 'left'), 'left')).toBe(i)
    }
  })

  it('clamps out-of-range indexes instead of producing NaN geometry', () => {
    expect(chordStringDisplayIndex(-3, 'right')).toBe(0)
    expect(chordStringDisplayIndex(99, 'left')).toBe(0)
  })
})
