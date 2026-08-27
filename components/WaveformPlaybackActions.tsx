import { Audio } from 'expo-av'
import * as FileSystem from 'expo-file-system/legacy'
import { useCallback, useRef, useState } from 'react'
import { Platform, Text, View } from 'react-native'
import { AnimatedPressable } from '@/components/AnimatedPressable'

type Props = {
  userWavBase64: string
  referenceWavBase64: string
  userFileUri?: string | null
  referenceFileUri?: string | null
}

/** Plays stored WAV from file URI (preferred) or base64 data URI. */
export function WaveformPlaybackActions({ userWavBase64, referenceWavBase64, userFileUri, referenceFileUri }: Props) {
  const soundRef = useRef<Audio.Sound | null>(null)
  const [label, setLabel] = useState<string | null>(null)

  const stop = useCallback(async () => {
    const s = soundRef.current
    if (s) {
      await s.unloadAsync()
      soundRef.current = null
    }
  }, [])

  const playUri = useCallback(
    async (uri: string, name: string) => {
      try {
        await stop()
        await Audio.setAudioModeAsync({ playsInSilentModeIOS: true })
        const { sound } = await Audio.Sound.createAsync({ uri })
        soundRef.current = sound
        setLabel(`Playing ${name}…`)
        sound.setOnPlaybackStatusUpdate((st) => {
          if (st.isLoaded && st.didJustFinish) {
            void stop()
            setLabel(null)
          }
        })
        await sound.playAsync()
      } catch (e) {
        setLabel(e instanceof Error ? e.message : 'Playback failed')
      }
    },
    [stop],
  )

  const play = useCallback(
    async (which: 'user' | 'ref') => {
      const path = which === 'user' ? userFileUri : referenceFileUri
      const b64 = which === 'user' ? userWavBase64 : referenceWavBase64
      const name = which === 'user' ? 'your take' : 'reference'
      if (path && path.length > 0) {
        await playUri(path, name)
        return
      }
      if (!b64 || b64.length === 0) {
        setLabel(`No ${name} audio stored for this session.`)
        return
      }
      if (Platform.OS === 'web') {
        await playUri(`data:audio/wav;base64,${b64}`, name)
        return
      }
      const dir = FileSystem.cacheDirectory ?? FileSystem.documentDirectory
      if (!dir) {
        setLabel('No writable directory for temp audio.')
        return
      }
      const filePath = `${dir}harmoniq-${which}-${Date.now()}.wav`
      await FileSystem.writeAsStringAsync(filePath, b64, { encoding: FileSystem.EncodingType.Base64 })
      await playUri(filePath, name)
    },
    [playUri, referenceFileUri, referenceWavBase64, userFileUri, userWavBase64],
  )

  return (
    <View className="mt-3 rounded-lg border border-wood-600/45 bg-cream-dark/35 px-3 py-3">
      <Text className="font-sans-medium text-xs uppercase tracking-wide text-amber-accent">Waveforms</Text>
      <View className="mt-2 flex-row flex-wrap gap-2">
        <AnimatedPressable
          haptic="light"
          onPress={() => void play('user')}
          className="rounded-lg border border-wood-600/50 bg-ivory px-3 py-2"
          accessibilityRole="button"
          accessibilityLabel="Play your take"
        >
          <Text className="font-sans-medium text-sm text-wood-900">Play your take</Text>
        </AnimatedPressable>
        <AnimatedPressable
          haptic="light"
          onPress={() => void play('ref')}
          className="rounded-lg border border-wood-600/50 bg-ivory px-3 py-2"
          accessibilityRole="button"
          accessibilityLabel="Play reference"
        >
          <Text className="font-sans-medium text-sm text-wood-900">Play reference</Text>
        </AnimatedPressable>
      </View>
      {label ? <Text className="mt-2 font-sans text-[11px] text-muted-light">{label}</Text> : null}
    </View>
  )
}
