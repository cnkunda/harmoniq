import type { SongScoreMeta } from '@/types/tabMessage'

/** Read static metadata from an alphaTab `Score` model (any casing / optional fields). */
export function extractSongMetaFromScore(score: unknown): SongScoreMeta {
  const out: SongScoreMeta = {}
  if (!score || typeof score !== 'object') return out
  const s = score as Record<string, unknown>

  const str = (k: string): string | null => {
    const x = s[k]
    if (typeof x !== 'string' || !x.trim()) return null
    return x.trim()
  }

  const t = str('title')
  const a = str('artist')
  const al = str('album')
  const sub = str('subTitle')
  const words = str('words')
  const music = str('music')
  const tab = str('tab')
  const tempoRaw = s.tempo
  const tempoBpm =
    typeof tempoRaw === 'number' && Number.isFinite(tempoRaw) && tempoRaw > 0 ? tempoRaw : null

  if (t) out.title = t
  if (a) out.artist = a
  if (al) out.album = al
  if (sub) out.subTitle = sub
  if (words) out.words = words
  if (music) out.music = music
  if (tab) out.tab = tab
  if (tempoBpm != null) out.tempoBpm = tempoBpm

  const mbs = s.masterBars
  if (Array.isArray(mbs)) {
    const markers: NonNullable<SongScoreMeta['sectionMarkers']> = []
    for (let bi = 0; bi < mbs.length; bi++) {
      const mb = mbs[bi]
      if (!mb || typeof mb !== 'object') continue
      const sec = (mb as { section?: unknown }).section
      if (!sec || typeof sec !== 'object') continue
      const tx = (sec as { text?: unknown }).text
      if (typeof tx !== 'string' || !tx.trim()) continue
      markers.push({ startMasterBarIndex: bi, label: tx.trim() })
    }
    if (markers.length) out.sectionMarkers = markers
  }

  return out
}

export function sectionLabelAtMasterBar(score: unknown, idx: number): string | null {
  if (!score || typeof score !== 'object') return null
  const mbs = (score as { masterBars?: unknown }).masterBars
  if (!Array.isArray(mbs) || mbs.length === 0) return null
  const cap = Math.min(Math.max(0, idx), mbs.length - 1)
  let label: string | null = null
  for (let i = 0; i <= cap; i++) {
    const mb = mbs[i]
    if (!mb || typeof mb !== 'object') continue
    const sec = (mb as { section?: unknown }).section
    if (!sec || typeof sec !== 'object') continue
    const tx = (sec as { text?: unknown }).text
    if (typeof tx === 'string' && tx.trim()) label = tx.trim()
  }
  return label
}

export type TickLookupApi = {
  tickCache?: {
    findBeat?: (tick: number) => unknown
  } | null
  tickPosition?: number
}

export function resolveMasterBarIndexFromTick(api: TickLookupApi, tick: number): number | null {
  try {
    const tc = api.tickCache
    if (!tc || typeof tc.findBeat !== 'function') return null
    const beat = tc.findBeat(tick)
    if (!beat || typeof beat !== 'object') return null
    const voice = (beat as { voice?: unknown }).voice
    if (!voice || typeof voice !== 'object') return null
    const bar = (voice as { bar?: unknown }).bar
    if (!bar || typeof bar !== 'object') return null
    const mb = (bar as { masterBar?: unknown }).masterBar
    if (!mb || typeof mb !== 'object') return null
    const ix = (mb as { index?: unknown }).index
    return typeof ix === 'number' && Number.isFinite(ix) ? ix : null
  } catch {
    return null
  }
}
