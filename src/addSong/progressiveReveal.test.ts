import { describe, it, expect } from 'vitest'
import { getRevealPhase, shouldShowPreview } from './progressiveReveal'

describe('getRevealPhase', () => {
  it('maps early pipeline stages to the spinner phase', () => {
    expect(getRevealPhase('initializing')).toBe('spinner')
    expect(getRevealPhase('stems_separating')).toBe('spinner')
  })

  it('maps chord/transcription stages to the preview phase (incl. non-monotonic mt3_inferring)', () => {
    // Stage emission order is chords_inferring (0.62) → mt3_inferring (0.60):
    // mt3_inferring comes AFTER chords_inferring and must not fall back to spinner.
    expect(getRevealPhase('chords_inferring')).toBe('preview')
    expect(getRevealPhase('mt3_inferring')).toBe('preview')
  })

  it('maps solo/build stages to the refining phase', () => {
    expect(getRevealPhase('solo_inferring')).toBe('refining')
    expect(getRevealPhase('building_musicxml')).toBe('refining')
  })

  it('maps the terminal stage to done', () => {
    expect(getRevealPhase('complete')).toBe('done')
  })

  it('treats missing stages as spinner (job just created)', () => {
    expect(getRevealPhase(null)).toBe('spinner')
    expect(getRevealPhase(undefined)).toBe('spinner')
    expect(getRevealPhase('')).toBe('spinner')
  })

  it('degrades unknown future stages to preview, never back to the monolithic spinner', () => {
    expect(getRevealPhase('some_new_stage')).toBe('preview')
  })
})

describe('shouldShowPreview', () => {
  it('shows the preview for preview/refining phases regardless of partial data', () => {
    expect(shouldShowPreview('preview', false)).toBe(true)
    expect(shouldShowPreview('preview', true)).toBe(true)
    expect(shouldShowPreview('refining', false)).toBe(true)
    expect(shouldShowPreview('refining', true)).toBe(true)
  })

  it('keeps the spinner only when the phase is early and no partial data arrived', () => {
    expect(shouldShowPreview('spinner', false)).toBe(false)
    expect(shouldShowPreview('spinner', true)).toBe(true)
  })

  it('keeps the preview up when the terminal frame arrives during the analyzing min-wait', () => {
    expect(shouldShowPreview('done', true)).toBe(true)
    expect(shouldShowPreview('done', false)).toBe(false)
  })
})
