import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/src/db/client', () => ({
  getAppPref: vi.fn(),
  setAppPref: vi.fn(),
}))

import { getAppPref, setAppPref } from '@/src/db/client'
import { PREF_EXPERIENCE_LEVEL, PREF_OUTPUT_TIER } from '@/src/db/schema'
import { useOutputTierStore } from '@/src/stores/outputTierStore'

function resetStore(): void {
  useOutputTierStore.setState({ tier: 'intermediate', hydrated: false })
}

describe('outputTierStore', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    resetStore()
  })

  it('keeps a stored output tier and ignores experience level', async () => {
    vi.mocked(getAppPref).mockImplementation(async (key: string) => {
      if (key === PREF_OUTPUT_TIER) return 'transcriber'
      if (key === PREF_EXPERIENCE_LEVEL) return 'beginner'
      return null
    })

    await useOutputTierStore.getState().hydrate()

    expect(useOutputTierStore.getState().tier).toBe('transcriber')
    expect(useOutputTierStore.getState().hydrated).toBe(true)
    expect(setAppPref).not.toHaveBeenCalled()
  })

  it('derives and persists a tier from experience level when unset', async () => {
    vi.mocked(getAppPref).mockImplementation(async (key: string) => {
      if (key === PREF_EXPERIENCE_LEVEL) return 'advanced'
      return null
    })

    await useOutputTierStore.getState().hydrate()

    expect(useOutputTierStore.getState().tier).toBe('transcriber')
    expect(setAppPref).toHaveBeenCalledWith(PREF_OUTPUT_TIER, 'transcriber')
  })

  it('defaults to Intermediate without persisting before onboarding', async () => {
    vi.mocked(getAppPref).mockResolvedValue(null)

    await useOutputTierStore.getState().hydrate()

    expect(useOutputTierStore.getState().tier).toBe('intermediate')
    expect(useOutputTierStore.getState().hydrated).toBe(true)
    expect(setAppPref).not.toHaveBeenCalled()
  })

  it('persists explicit tier changes', async () => {
    await useOutputTierStore.getState().setTier('learner')

    expect(setAppPref).toHaveBeenCalledWith(PREF_OUTPUT_TIER, 'learner')
    expect(useOutputTierStore.getState().tier).toBe('learner')
  })
})
