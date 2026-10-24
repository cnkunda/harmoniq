import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/src/db/client', () => ({
  getAppPref: vi.fn(),
  setAppPref: vi.fn(),
}))

import { getAppPref, setAppPref } from '@/src/db/client'
import { PREF_HOME_PRACTICE_MODE } from '@/src/db/schema'
import { useSessionPrefsStore } from '@/src/stores/sessionPrefsStore'

describe('sessionPrefsStore.homePracticeMode', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useSessionPrefsStore.setState({ homePracticeMode: 'plan', hydrated: false })
  })

  it('defaults to plan when no pref is stored', async () => {
    vi.mocked(getAppPref).mockResolvedValue(null)
    await useSessionPrefsStore.getState().hydrate()
    expect(useSessionPrefsStore.getState().homePracticeMode).toBe('plan')
  })

  it('hydrates single and persists changes', async () => {
    vi.mocked(getAppPref).mockImplementation(async (key: string) =>
      key === PREF_HOME_PRACTICE_MODE ? 'single' : null,
    )
    await useSessionPrefsStore.getState().hydrate()
    expect(useSessionPrefsStore.getState().homePracticeMode).toBe('single')

    await useSessionPrefsStore.getState().setHomePracticeMode('plan')
    expect(setAppPref).toHaveBeenCalledWith(PREF_HOME_PRACTICE_MODE, 'plan')
    expect(useSessionPrefsStore.getState().homePracticeMode).toBe('plan')
  })
})
