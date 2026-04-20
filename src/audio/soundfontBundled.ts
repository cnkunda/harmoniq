/**
 * Resolve bundled SoundFont asset URIs for AlphaTab (Commit 60).
 */

import { Asset } from 'expo-asset'

import type { SoundFontProfileId } from '@/src/audio/soundfontProfiles'

const GENERAL_USER_ASSET = require('../../assets/soundfonts/guitar.sf2') as number
const FLUID_R3_MONO_ASSET = require('../../assets/soundfonts/fluid-r3-mono-gm.sf3') as number

/** Bundled file URL for Expo web / native (AlphaTab player must fetch this URL). */
export async function resolveBundledSoundFontUrlForProfile(profileId: SoundFontProfileId): Promise<string> {
  const mod = profileId === 'fluid_r3_mono' ? FLUID_R3_MONO_ASSET : GENERAL_USER_ASSET
  const asset = Asset.fromModule(mod)
  await asset.downloadAsync()
  const uri = asset.localUri ?? asset.uri
  if (!uri) throw new Error(`SoundFont asset has no URI (${profileId})`)
  return uri
}
