import { useLocalSearchParams } from 'expo-router'
import { useCallback, useEffect, useState } from 'react'
import { Text, View } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'

import { TabViewport } from '@/components/TabViewport'
import { WoodGradient } from '@/components/WoodGradient'
import colors from '@/src/constants/colors'
import { CORPUS_NAMES, isCorpusName, loadCorpusMusicXml, type CorpusName } from '@/src/lib/corpusAssets'

const LABELS: Record<CorpusName, string> = {
  'irregular-5-4': 'Irregular 5/4 meter',
  'multi-voice-staff': 'Multi-voice staff',
  'nested-tuplets': 'Nested tuplets',
  syncopation: 'Heavy syncopation',
}

/**
 * Hidden MusicXML corpus render surface (Commit 107).
 * Reachable via /musicxml-render-test?file=<corpus-name> — used by the
 * Playwright web suite and the Detox native scaffold to assert the
 * AlphaTab importer renders every corpus file without crashing.
 */
export default function MusicXmlRenderTestScreen() {
  const params = useLocalSearchParams<{ file?: string | string[] }>()
  const raw = Array.isArray(params.file) ? params.file[0] : params.file
  const name: CorpusName = isCorpusName(raw) ? raw : CORPUS_NAMES[0]

  const [xml, setXml] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setXml(null)
    setError(null)
    loadCorpusMusicXml(name)
      .then((text) => {
        if (!cancelled) setXml(text)
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e))
      })
    return () => {
      cancelled = true
    }
  }, [name])

  const handleRenderError = useCallback((msg: string) => {
    setError(msg)
  }, [])

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.wood[900] }} edges={['top']}>
      <WoodGradient />
      <View style={{ flex: 1 }}>
        <View style={{ paddingHorizontal: 16, paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: 'rgba(163,123,76,0.4)' }}>
          <Text
            style={{ color: colors.cream, fontFamily: 'monospace', fontSize: 12 }}
            accessibilityLabel={`corpus-title:${name}`}
          >
            MusicXML corpus: {name} — {LABELS[name]}
          </Text>
        </View>
        <View style={{ flex: 1 }}>
          {error ? (
            <Text style={{ color: colors.danger, fontFamily: 'monospace', fontSize: 12, padding: 16 }} accessibilityLabel="corpus-error">
              {error}
            </Text>
          ) : xml ? (
            <TabViewport musicXml={xml} songTitle={name} songArtist="Corpus" onError={handleRenderError} />
          ) : (
            <View />
          )}
        </View>
      </View>
    </SafeAreaView>
  )
}