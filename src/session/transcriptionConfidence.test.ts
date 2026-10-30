import { describe, expect, it } from 'vitest'

import {
  CHECK_BY_EAR_CUE,
  confidenceBandFromScore,
  confidenceBandLabel,
  confusionBarWidth,
  confusionLevel,
  confusionLevelLabel,
  sectionNeedsCheckByEar,
} from '@/src/session/transcriptionConfidence'

describe('confidenceBandFromScore', () => {
  it('mirrors the backend band cutoffs', () => {
    expect(confidenceBandFromScore(0.4999)).toBe('low')
    expect(confidenceBandFromScore(0.5)).toBe('medium')
    expect(confidenceBandFromScore(0.7499)).toBe('medium')
    expect(confidenceBandFromScore(0.75)).toBe('high')
    expect(confidenceBandFromScore(1)).toBe('high')
  })

  it('treats missing and non-finite values as unknown', () => {
    expect(confidenceBandFromScore(null)).toBeNull()
    expect(confidenceBandFromScore(undefined)).toBeNull()
    expect(confidenceBandFromScore(Number.NaN)).toBeNull()
  })
})

describe('confidenceBandLabel', () => {
  it('returns plain-language wording per band', () => {
    expect(confidenceBandLabel('low')).toBe('Rough transcription')
    expect(confidenceBandLabel('medium')).toBe('Some fuzziness')
    expect(confidenceBandLabel('high')).toBe('Good match')
  })

  it('renders nothing for an unknown band', () => {
    expect(confidenceBandLabel(null)).toBeNull()
    expect(confidenceBandLabel(undefined)).toBeNull()
  })
})

describe('confusionLevel', () => {
  it('mirrors the backend hedge tiers', () => {
    expect(confusionLevel(0)).toBe('low')
    expect(confusionLevel(0.2999)).toBe('low')
    expect(confusionLevel(0.3)).toBe('moderate')
    expect(confusionLevel(0.5999)).toBe('moderate')
    expect(confusionLevel(0.6)).toBe('high')
    expect(confusionLevel(1)).toBe('high')
  })

  it('clamps out-of-range values and treats missing as unknown', () => {
    expect(confusionLevel(-1)).toBe('low')
    expect(confusionLevel(1.5)).toBe('high')
    expect(confusionLevel(null)).toBeNull()
    expect(confusionLevel(undefined)).toBeNull()
    expect(confusionLevel(Number.NaN)).toBeNull()
  })
})

describe('confusion labels and bar widths', () => {
  it('returns learner-facing labels', () => {
    expect(confusionLevelLabel('low')).toBe('Low')
    expect(confusionLevelLabel('moderate')).toBe('Moderate')
    expect(confusionLevelLabel('high')).toBe('High')
    expect(confusionLevelLabel(null)).toBeNull()
  })

  it('uses coarse bar widths', () => {
    expect(confusionBarWidth('low')).toBe('33%')
    expect(confusionBarWidth('moderate')).toBe('66%')
    expect(confusionBarWidth('high')).toBe('100%')
    expect(confusionBarWidth(null)).toBeNull()
  })
})

describe('sectionNeedsCheckByEar', () => {
  it('cues low chord confidence', () => {
    expect(sectionNeedsCheckByEar({ chord_confidence: 0.4999 })).toBe(true)
    expect(sectionNeedsCheckByEar({ chord_confidence: 0.5 })).toBe(false)
  })

  it('cues moderate or high confusion', () => {
    expect(sectionNeedsCheckByEar({ instrument_confusion: 0.2999 })).toBe(false)
    expect(sectionNeedsCheckByEar({ instrument_confusion: 0.3 })).toBe(true)
    expect(sectionNeedsCheckByEar({ instrument_confusion: 0.6 })).toBe(true)
  })

  it('does not cue when data is missing', () => {
    expect(sectionNeedsCheckByEar(null)).toBe(false)
    expect(sectionNeedsCheckByEar(undefined)).toBe(false)
    expect(sectionNeedsCheckByEar({})).toBe(false)
    expect(sectionNeedsCheckByEar({ chord_confidence: null, instrument_confusion: null })).toBe(
      false,
    )
  })

  it('keeps the coach hedge action in the copy', () => {
    expect(CHECK_BY_EAR_CUE).toContain('check this part by ear')
  })
})
