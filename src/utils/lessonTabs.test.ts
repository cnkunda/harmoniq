import { describe, expect, it } from 'vitest'

import { TRANSCRIPTION_CONFIDENCE_UNCERTAIN_MAX } from '@/src/db/schema'
import { pickTabVariant, type SectionTabPayloads } from '@/src/utils/lessonTabs'

const TABS: SectionTabPayloads = { full: 'F', skeleton: 'S', alt: 'A' }

describe('pickTabVariant', () => {
  it('keeps the full tab at high confidence', () => {
    expect(pickTabVariant(0.95, TABS, false)).toBe('full')
  })

  it('falls back to skeleton when confidence is uncertain', () => {
    expect(pickTabVariant(TRANSCRIPTION_CONFIDENCE_UNCERTAIN_MAX - 0.01, TABS, false)).toBe('skeleton')
  })

  it('uses alt when skeleton is missing', () => {
    expect(pickTabVariant(0.5, { full: 'F', alt: 'A' }, false)).toBe('alt')
  })

  it('keeps full when no degraded variant exists', () => {
    expect(pickTabVariant(0.5, { full: 'F' }, false)).toBe('full')
  })

  it('preferFullTabs overrides the auto fallback', () => {
    expect(pickTabVariant(0.1, TABS, true)).toBe('full')
  })

  it('treats exactly the uncertain threshold as certain', () => {
    expect(pickTabVariant(TRANSCRIPTION_CONFIDENCE_UNCERTAIN_MAX, TABS, false)).toBe('full')
  })

  it('treats missing confidence as certain (no silent degradation)', () => {
    expect(pickTabVariant(undefined, TABS, false)).toBe('full')
    expect(pickTabVariant(null, TABS, false)).toBe('full')
  })

  it('prefers full over skeleton at high confidence', () => {
    expect(pickTabVariant(0.9, { skeleton: 'S', full: 'F' }, false)).toBe('full')
  })

  it('never throws when no tab payload exists', () => {
    expect(pickTabVariant(0.3, {}, false)).toMatch(/^(full|skeleton|alt)$/)
  })
})