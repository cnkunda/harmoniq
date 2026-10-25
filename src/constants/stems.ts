/** Canonical Demucs stem keys, in UI/export order. */
export const STEM_KEYS = ['guitar', 'bass', 'drums', 'vocals', 'piano', 'other'] as const

export type StemKey = (typeof STEM_KEYS)[number]

export const STEM_LABELS: Record<StemKey, string> = {
  guitar: 'Guitar',
  bass: 'Bass',
  drums: 'Drums',
  vocals: 'Vocals',
  piano: 'Piano',
  other: 'Other',
}
