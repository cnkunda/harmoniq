import { getAppPref, setAppPref } from '@/src/db/client'
import type { CagedForm } from '@/src/music/cagedPatterns'

const FAVORITES_PREF_KEY = 'scale_explorer_favorites'

export type ScaleFavorite = {
  scaleKey: string
  rootPitchClass: number
  cagedForm?: CagedForm
}

export async function getFavorites(): Promise<ScaleFavorite[]> {
  try {
    const raw = await getAppPref(FAVORITES_PREF_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.filter(
      (f: unknown): f is ScaleFavorite =>
        typeof f === 'object' &&
        f != null &&
        typeof (f as ScaleFavorite).scaleKey === 'string' &&
        typeof (f as ScaleFavorite).rootPitchClass === 'number',
    )
  } catch {
    return []
  }
}

export async function addFavorite(fav: ScaleFavorite): Promise<void> {
  const favorites = await getFavorites()
  const exists = favorites.some(
    (f) => f.scaleKey === fav.scaleKey && f.rootPitchClass === fav.rootPitchClass,
  )
  if (exists) return
  favorites.push(fav)
  await setAppPref(FAVORITES_PREF_KEY, JSON.stringify(favorites))
}

export async function removeFavorite(scaleKey: string, rootPitchClass: number): Promise<void> {
  const favorites = await getFavorites()
  const filtered = favorites.filter(
    (f) => !(f.scaleKey === scaleKey && f.rootPitchClass === rootPitchClass),
  )
  await setAppPref(FAVORITES_PREF_KEY, JSON.stringify(filtered))
}

export async function isFavorite(scaleKey: string, rootPitchClass: number): Promise<boolean> {
  const favorites = await getFavorites()
  return favorites.some(
    (f) => f.scaleKey === scaleKey && f.rootPitchClass === rootPitchClass,
  )
}
