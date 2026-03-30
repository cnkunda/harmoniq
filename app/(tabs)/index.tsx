import Slider from '@react-native-community/slider'
import { Audio, type AVPlaybackStatus } from 'expo-av'
import { useEffect, useMemo, useState } from 'react'
import { Platform, Pressable, Text, View } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'

const TEST_TRACK = require('../../assets/backing-tracks/am-blues-70bpm.mp3')
const MIN_RATE = 0.5
const MAX_RATE = 1

export default function HomeScreen() {
  const [sound, setSound] = useState<Audio.Sound | null>(null)
  const [isPlaying, setIsPlaying] = useState(false)
  const [isLooping, setIsLooping] = useState(true)
  const [rate, setRate] = useState(0.75)

  const rateLabel = useMemo(() => `${Math.round(rate * 100)}%`, [rate])

  useEffect(() => {
    let mounted = true
    let loaded: Audio.Sound | null = null

    const prepare = async () => {
      const { sound: loadedSound } = await Audio.Sound.createAsync(
        TEST_TRACK,
        {
          shouldPlay: false,
          isLooping: true,
          rate: 0.75,
          shouldCorrectPitch: true,
          progressUpdateIntervalMillis: 250,
        },
      )

      loadedSound.setOnPlaybackStatusUpdate((status: AVPlaybackStatus) => {
        if (!mounted || !status.isLoaded) return
        setIsPlaying(status.isPlaying)
        setIsLooping(status.isLooping)
        setRate(status.rate)
      })

      if (mounted) {
        loaded = loadedSound
        setSound(loadedSound)
      } else {
        await loadedSound.unloadAsync()
      }
    }

    prepare().catch((error) => {
      console.error('Failed to initialize playback test track', error)
    })

    return () => {
      mounted = false
      if (loaded) {
        loaded.unloadAsync().catch((error) => {
          console.error('Failed to unload playback test track', error)
        })
      }
    }
  }, [])

  const togglePlayPause = async () => {
    if (!sound) return
    if (isPlaying) {
      await sound.pauseAsync()
      return
    }
    await sound.playAsync()
  }

  const toggleLoop = async () => {
    if (!sound) return
    await sound.setIsLoopingAsync(!isLooping)
  }

  const setPlaybackRate = async (nextRate: number) => {
    if (!sound) return
    await sound.setStatusAsync({
      rate: nextRate,
      shouldCorrectPitch: true,
    })
  }

  return (
    <SafeAreaView className="flex-1 bg-wood-900">
      <View className="flex-1 px-6 py-8">
        <Text className="text-3xl font-serif text-amber-accent">Audio Playback Smoke Test</Text>
        <Text className="mt-2 text-sm font-sans text-cream">
          API: expo-av Audio.Sound. Control parity target: iOS, Android, and web.
        </Text>
        <Text className="mt-1 text-xs font-sans text-muted-brown">
          Bundled asset: assets/backing-tracks/am-blues-70bpm.mp3
        </Text>

        <View className="mt-8 rounded-xl border border-wood-700 bg-wood-800 p-4">
          <Text className="font-sans-medium text-cream">Rate: {rateLabel}</Text>
          <Slider
            value={rate}
            minimumValue={MIN_RATE}
            maximumValue={MAX_RATE}
            step={0.05}
            minimumTrackTintColor="#D4860A"
            maximumTrackTintColor="#7A5A3B"
            thumbTintColor="#F0DEB4"
            onSlidingComplete={setPlaybackRate}
            className="mt-3"
          />
          <Text className="mt-1 text-xs font-sans text-muted-brown">50% to 100% speed, pitch correction on</Text>
        </View>

        <View className="mt-6 flex-row gap-3">
          <Pressable
            onPress={togglePlayPause}
            className="rounded-lg bg-amber-accent px-4 py-3"
            accessibilityRole="button"
          >
            <Text className="font-sans-medium text-wood-900">{isPlaying ? 'Pause' : 'Play'}</Text>
          </Pressable>

          <Pressable
            onPress={toggleLoop}
            className="rounded-lg border border-amber-accent px-4 py-3"
            accessibilityRole="button"
          >
            <Text className="font-sans-medium text-amber-light">{isLooping ? 'Loop: ON' : 'Loop: OFF'}</Text>
          </Pressable>
        </View>

        {Platform.OS === 'web' ? (
          <Text className="mt-4 text-xs font-sans text-muted-brown">
            Web note: pitch correction quality depends on browser media implementation; expect slight degradation.
          </Text>
        ) : null}
      </View>
    </SafeAreaView>
  )
}
