import { Asset } from 'expo-asset'

export const CORPUS_NAMES = ['irregular-5-4', 'multi-voice-staff', 'nested-tuplets', 'syncopation'] as const
export type CorpusName = (typeof CORPUS_NAMES)[number]

const CORPUS_ASSETS: Record<CorpusName, number> = {
  'irregular-5-4': require('@/assets/musicxml-corpus/irregular-5-4.musicxml'),
  'multi-voice-staff': require('@/assets/musicxml-corpus/multi-voice-staff.musicxml'),
  'nested-tuplets': require('@/assets/musicxml-corpus/nested-tuplets.musicxml'),
  syncopation: require('@/assets/musicxml-corpus/syncopation.musicxml'),
}

export function isCorpusName(v: unknown): v is CorpusName {
  return typeof v === 'string' && (CORPUS_NAMES as readonly string[]).includes(v)
}

export async function loadCorpusMusicXml(name: CorpusName): Promise<string> {
  const asset = Asset.fromModule(CORPUS_ASSETS[name])
  await asset.downloadAsync()
  const uri = asset.localUri ?? asset.uri
  if (!uri) {
    throw new Error(`Corpus asset ${name} has no URI`)
  }
  const res = await fetch(uri)
  if (!res.ok) {
    throw new Error(`Failed to fetch corpus asset ${name}: HTTP ${res.status}`)
  }
  return res.text()
}