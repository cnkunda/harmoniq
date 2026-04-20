import { describe, expect, it } from 'vitest'

import { deriveSlowLoopRegion } from './slowLoopRegion'

describe('deriveSlowLoopRegion — lowest-confidence default', () => {
  it('picks bar index with minimum confidence_by_bar', () => {
    const section = {
      confidence_by_bar: [0.95, 0.15, 0.9],
    }
    const bars = [0, 1, 2, 3]
    const out = deriveSlowLoopRegion(section, [], bars, 120)
    expect(out).not.toBeNull()
    expect(out!.startBarIndex).toBe(1)
    expect(out!.endBarIndexExclusive).toBe(2)
    expect(out!.startSec).toBe(1)
    expect(out!.endSec).toBe(2)
  })

  it('prefers lowest-confidence bar over hardest_bar_index when both are present', () => {
    const section = {
      hardest_bar_index: 0,
      confidence_by_bar: [0.99, 0.2, 0.98],
    }
    const bars = [0, 1, 2, 3]
    const out = deriveSlowLoopRegion(section, [], bars, 120)
    expect(out).not.toBeNull()
    expect(out!.startBarIndex).toBe(1)
    expect(out!.endBarIndexExclusive).toBe(2)
    expect(out!.label).toContain('low confidence')
  })
})
