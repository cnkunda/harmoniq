import { BACKING_TRACKS, type BackingTrackId } from '@/src/constants/backingTracks'

/** Pick a bundled loop whose key/tempo fits weak-area practice focus (Jam suggestions). */
export function pickSuggestedClassicFromWeakAreas(weakAreas: readonly string[]): BackingTrackId {
  const s = new Set(weakAreas.map((w) => w.toLowerCase()))
  if (s.has('timing')) return 'em-vamp-90'
  if (s.has('pitch') || s.has('bending')) return 'am-blues-70'
  if (s.has('phrasing') || s.has('vibrato')) return 'g-ballad-65'
  return BACKING_TRACKS[0]?.id ?? 'am-blues-70'
}
