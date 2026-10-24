import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  getAppPref: vi.fn(),
}))

vi.mock('@/src/db/client', () => ({
  getAppPref: mocks.getAppPref,
}))

import {
  MANDATORY_SESSION_STEPS,
  OPTIONAL_SESSION_STEPS,
  SESSION_STEPS,
  isMandatoryStep,
  isOptionalStep,
  mandatoryStepIndex,
  sessionEntryHref,
  sessionHref,
  sessionStepIndexFromPathname,
} from '@/src/constants/sessionFlow'

describe('SESSION_STEPS', () => {
  it('contains all seven session routes in order', () => {
    expect(SESSION_STEPS).toEqual(['tune', 'musical-tolerance', 'listen', 'study', 'slow', 'play', 'review'])
  })
})

describe('MANDATORY_SESSION_STEPS', () => {
  it('excludes listen (Commit 163: listen is opt-in)', () => {
    expect(MANDATORY_SESSION_STEPS).not.toContain('listen')
  })

  it('contains six steps', () => {
    expect(MANDATORY_SESSION_STEPS).toHaveLength(6)
  })

  it('preserves the pedagogical order tune → musical-tolerance → study → slow → play → review', () => {
    expect(MANDATORY_SESSION_STEPS).toEqual(['tune', 'musical-tolerance', 'study', 'slow', 'play', 'review'])
  })
})

describe('OPTIONAL_SESSION_STEPS', () => {
  it('contains listen as the only optional step', () => {
    expect(OPTIONAL_SESSION_STEPS).toEqual(['listen'])
  })
})

describe('isMandatoryStep / isOptionalStep', () => {
  it('returns true for study (mandatory) and false for listen (optional)', () => {
    expect(isMandatoryStep('study')).toBe(true)
    expect(isMandatoryStep('listen')).toBe(false)
    expect(isOptionalStep('listen')).toBe(true)
    expect(isOptionalStep('study')).toBe(false)
  })
})

describe('mandatoryStepIndex', () => {
  it('returns correct indices for mandatory steps', () => {
    expect(mandatoryStepIndex('tune')).toBe(0)
    expect(mandatoryStepIndex('musical-tolerance')).toBe(1)
    expect(mandatoryStepIndex('study')).toBe(2)
    expect(mandatoryStepIndex('slow')).toBe(3)
    expect(mandatoryStepIndex('play')).toBe(4)
    expect(mandatoryStepIndex('review')).toBe(5)
  })

  it('returns -1 for listen (not in mandatory flow)', () => {
    expect(mandatoryStepIndex('listen')).toBe(-1)
  })
})

describe('sessionStepIndexFromPathname', () => {
  it('returns the SESSION_STEPS index for a valid path', () => {
    expect(sessionStepIndexFromPathname('/session/study')).toBe(3)
    expect(sessionStepIndexFromPathname('/session/listen')).toBe(2)
    expect(sessionStepIndexFromPathname('/session/review')).toBe(6)
  })

  it('handles trailing slashes', () => {
    expect(sessionStepIndexFromPathname('/session/study/')).toBe(3)
  })

  it('returns -1 for unknown paths', () => {
    expect(sessionStepIndexFromPathname('/session/unknown')).toBe(-1)
    expect(sessionStepIndexFromPathname('/home')).toBe(-1)
  })
})

describe('sessionHref', () => {
  it('builds the href for each step', () => {
    expect(sessionHref('study')).toBe('/session/study')
    expect(sessionHref('listen')).toBe('/session/listen')
    expect(sessionHref('review')).toBe('/session/review')
  })
})

describe('sessionEntryHref', () => {
  it('returns tune when skipTuneStep is false', () => {
    expect(sessionEntryHref(false)).toBe('/session/tune')
  })

  it('returns musical-tolerance when skipTuneStep is true', () => {
    expect(sessionEntryHref(true)).toBe('/session/musical-tolerance')
  })
})

describe('sessionEntryHrefWithMoodCheck', () => {
  beforeEach(() => {
    vi.resetModules()
    mocks.getAppPref.mockReset()
  })

  it('returns mood-check when neither skip flag nor lastShown day is set', async () => {
    mocks.getAppPref.mockResolvedValue(null)
    const { sessionEntryHrefWithMoodCheck } = await import('@/src/constants/sessionFlow')
    expect(await sessionEntryHrefWithMoodCheck(false)).toBe('/session/mood-check')
  })

  it('returns tune when mood check is auto-skipped', async () => {
    mocks.getAppPref.mockImplementation((key: string) => {
      if (key === 'mood_check_skip') return Promise.resolve('1')
      return Promise.resolve(null)
    })
    const { sessionEntryHrefWithMoodCheck } = await import('@/src/constants/sessionFlow')
    expect(await sessionEntryHrefWithMoodCheck(false)).toBe('/session/tune')
  })

  it('returns musical-tolerance when mood check is auto-skipped and tune is skipped', async () => {
    mocks.getAppPref.mockImplementation((key: string) => {
      if (key === 'mood_check_skip') return Promise.resolve('1')
      return Promise.resolve(null)
    })
    const { sessionEntryHrefWithMoodCheck } = await import('@/src/constants/sessionFlow')
    expect(await sessionEntryHrefWithMoodCheck(true)).toBe('/session/musical-tolerance')
  })
})
