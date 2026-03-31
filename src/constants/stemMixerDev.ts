import type { StemDefinition } from '@/src/audio/mixerTypes'

/** Dev-only bundled WAV stems (44.1 kHz mono) for multi-stem mixer smoke tests */
export const STEM_MIXER_DEV_STEMS: StemDefinition[] = [
  {
    id: 'guitar',
    label: 'Guitar (G4 sine)',
    source: require('../../assets/stem-mixer-dev/guitar.wav'),
  },
  {
    id: 'drums',
    label: 'Drums (C3 sine)',
    source: require('../../assets/stem-mixer-dev/drums.wav'),
  },
]
