import { describe, expect, it } from 'vitest'

import { ALPHA_TAB_NOTE_EVENT_MIN_INTERVAL_MS } from '@/src/constants/alphaTabBridge'

describe('alphaTabBridge', () => {
  it('note event throttle matches ~32 Hz cap (FEEL_REAL_QA B4)', () => {
    expect(ALPHA_TAB_NOTE_EVENT_MIN_INTERVAL_MS).toBe(31)
    const hz = 1000 / ALPHA_TAB_NOTE_EVENT_MIN_INTERVAL_MS
    expect(hz).toBeGreaterThan(32)
    expect(hz).toBeLessThan(33)
  })
})
