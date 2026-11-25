import { afterEach, describe, expect, it, vi } from 'vitest'

const expoConstants = vi.hoisted(() => ({
  extra: undefined as Record<string, unknown> | undefined,
}))

vi.mock('expo-constants', () => ({
  default: {
    get expoConfig() {
      return { extra: expoConstants.extra }
    },
  },
}))

async function loadConfig(extra?: Record<string, unknown>) {
  expoConstants.extra = extra
  vi.resetModules()
  return await import('@/src/config')
}

afterEach(() => {
  vi.unstubAllEnvs()
})

describe('API_BASE_URL', () => {
  it('uses extra.apiBaseUrl when present', async () => {
    const config = await loadConfig({ apiBaseUrl: 'https://api.example.com' })
    expect(config.API_BASE_URL).toBe('https://api.example.com')
  })

  it('strips a trailing slash', async () => {
    const config = await loadConfig({ apiBaseUrl: 'https://api.example.com/' })
    expect(config.API_BASE_URL).toBe('https://api.example.com')
  })

  it('strips only the final slash', async () => {
    const config = await loadConfig({ apiBaseUrl: 'https://api.example.com//' })
    expect(config.API_BASE_URL).toBe('https://api.example.com/')
  })

  it('falls back to localhost when extra is missing', async () => {
    const config = await loadConfig(undefined)
    expect(config.API_BASE_URL).toBe('http://localhost:8000')
  })

  it('falls back to localhost when apiBaseUrl is empty', async () => {
    const config = await loadConfig({ apiBaseUrl: '' })
    expect(config.API_BASE_URL).toBe('http://localhost:8000')
  })

  it('falls back to localhost when apiBaseUrl is not a string', async () => {
    const config = await loadConfig({ apiBaseUrl: 8000 })
    expect(config.API_BASE_URL).toBe('http://localhost:8000')
  })
})

describe('isHarmoniqSkillMutationSkipped', () => {
  it('returns true when EXPO_PUBLIC_HARMONIQ_SKIP_SKILL_MUTATION=1', async () => {
    vi.stubEnv('EXPO_PUBLIC_HARMONIQ_SKIP_SKILL_MUTATION', '1')
    const config = await loadConfig()
    expect(config.isHarmoniqSkillMutationSkipped()).toBe(true)
  })

  it('returns true when HARMONIQ_SKIP_SKILL_MUTATION=1', async () => {
    vi.stubEnv('HARMONIQ_SKIP_SKILL_MUTATION', '1')
    const config = await loadConfig()
    expect(config.isHarmoniqSkillMutationSkipped()).toBe(true)
  })

  it('returns false when neither variable is set', async () => {
    vi.stubEnv('EXPO_PUBLIC_HARMONIQ_SKIP_SKILL_MUTATION', undefined)
    vi.stubEnv('HARMONIQ_SKIP_SKILL_MUTATION', undefined)
    const config = await loadConfig()
    expect(config.isHarmoniqSkillMutationSkipped()).toBe(false)
  })

  it('returns false when the value is not exactly 1', async () => {
    vi.stubEnv('EXPO_PUBLIC_HARMONIQ_SKIP_SKILL_MUTATION', 'true')
    const config = await loadConfig()
    expect(config.isHarmoniqSkillMutationSkipped()).toBe(false)
  })
})

describe('isPitchJsiEnabled', () => {
  it('returns true when EXPO_PUBLIC_HARMONIQ_PITCH_JSI=1', async () => {
    vi.stubEnv('EXPO_PUBLIC_HARMONIQ_PITCH_JSI', '1')
    const config = await loadConfig()
    expect(config.isPitchJsiEnabled()).toBe(true)
  })

  it('returns false when unset', async () => {
    vi.stubEnv('EXPO_PUBLIC_HARMONIQ_PITCH_JSI', undefined)
    const config = await loadConfig()
    expect(config.isPitchJsiEnabled()).toBe(false)
  })

  it('returns false for non-1 values', async () => {
    vi.stubEnv('EXPO_PUBLIC_HARMONIQ_PITCH_JSI', '0')
    const config = await loadConfig()
    expect(config.isPitchJsiEnabled()).toBe(false)
  })
})
