import { describe, it, expect, vi, beforeEach } from 'vitest'

const mockPrefs = new Map<string, string>()

vi.mock('@/src/db/client', () => ({
  getAppPref: vi.fn((key: string) => Promise.resolve(mockPrefs.get(key) ?? null)),
  setAppPref: vi.fn((key: string, value: string) => {
    mockPrefs.set(key, value)
    return Promise.resolve()
  }),
}))

import { getFavorites, addFavorite, removeFavorite, isFavorite } from './scaleFavorites'

describe('scaleFavorites', () => {
  beforeEach(() => {
    mockPrefs.clear()
  })

  it('returns empty array when no favorites saved', async () => {
    const favs = await getFavorites()
    expect(favs).toEqual([])
  })

  it('adds a favorite and retrieves it', async () => {
    await addFavorite({ scaleKey: 'ionian', rootPitchClass: 0 })
    const favs = await getFavorites()
    expect(favs).toHaveLength(1)
    expect(favs[0]).toEqual({ scaleKey: 'ionian', rootPitchClass: 0 })
  })

  it('does not duplicate identical favorites', async () => {
    await addFavorite({ scaleKey: 'ionian', rootPitchClass: 0 })
    await addFavorite({ scaleKey: 'ionian', rootPitchClass: 0 })
    const favs = await getFavorites()
    expect(favs).toHaveLength(1)
  })

  it('adds multiple distinct favorites', async () => {
    await addFavorite({ scaleKey: 'ionian', rootPitchClass: 0 })
    await addFavorite({ scaleKey: 'dorian', rootPitchClass: 2 })
    await addFavorite({ scaleKey: 'ionian', rootPitchClass: 5 })
    const favs = await getFavorites()
    expect(favs).toHaveLength(3)
  })

  it('removes a favorite by scaleKey and rootPitchClass', async () => {
    await addFavorite({ scaleKey: 'ionian', rootPitchClass: 0 })
    await addFavorite({ scaleKey: 'dorian', rootPitchClass: 2 })
    await removeFavorite('ionian', 0)
    const favs = await getFavorites()
    expect(favs).toHaveLength(1)
    expect(favs[0]).toEqual({ scaleKey: 'dorian', rootPitchClass: 2 })
  })

  it('isFavorite returns true for existing favorite', async () => {
    await addFavorite({ scaleKey: 'aeolian', rootPitchClass: 9 })
    expect(await isFavorite('aeolian', 9)).toBe(true)
  })

  it('isFavorite returns false for non-existing favorite', async () => {
    expect(await isFavorite('locrian', 5)).toBe(false)
  })

  it('handles invalid stored JSON gracefully', async () => {
    mockPrefs.set('scale_explorer_favorites', 'not valid json')
    const favs = await getFavorites()
    expect(favs).toEqual([])
  })

  it('stores cagedForm when provided', async () => {
    await addFavorite({ scaleKey: 'major_pentatonic', rootPitchClass: 0, cagedForm: 'E' })
    const favs = await getFavorites()
    expect(favs[0].cagedForm).toBe('E')
  })
})
