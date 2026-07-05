import { Text, View } from 'react-native'
import Animated, {
  useAnimatedStyle,
  useSharedValue,
  withSequence,
  withTiming,
} from 'react-native-reanimated'
import { useEffect } from 'react'

import { AnimatedPressable } from '@/components/AnimatedPressable'
import { ConfidenceMeter } from '@/src/chord/ConfidenceMeter'
import { ChordHistoryStream } from '@/src/chord/ChordHistoryStream'
import { useChordDetector } from '@/src/chord/useChordDetector'
import { isNoChord } from '@/src/chord/chordVocab'
import colors from '@/src/constants/colors'

/**
 * Active Listener card for the Discover tab.
 * Shows live chord detection from microphone input.
 */
export function ActiveListenerCard() {
  const {
    isListening,
    currentChord,
    history,
    latencyMs,
    error,
    modelType,
    startListening,
    stopListening,
  } = useChordDetector()

  const chordFlash = useSharedValue(0)

  // Flash animation when chord changes
  useEffect(() => {
    if (!currentChord || isNoChord(currentChord.chord)) return
    chordFlash.value = 0
    chordFlash.value = withSequence(
      withTiming(0.3, { duration: 60 }),
      withTiming(0, { duration: 350 }),
    )
  }, [currentChord?.chord, currentChord?.timestamp, chordFlash])

  const flashStyle = useAnimatedStyle(() => ({
    opacity: chordFlash.value,
  }))

  const chordLabel = currentChord ? (isNoChord(currentChord.chord) ? '—' : formatChord(currentChord.chord)) : '—'

  return (
    <View className="rounded-xl border border-wood-600/50 bg-wood-800/80 p-4">
      <View className="flex-row items-center justify-between">
        <View>
          <Text className="font-sans-medium text-xs uppercase tracking-wide text-amber-light">
            Active Listener
          </Text>
          <Text className="mt-1 font-sans text-xs text-muted-brown">
            Real-time chord detection from your mic
          </Text>
        </View>
        {modelType && (
          <View className="rounded-md bg-wood-600/40 px-2 py-0.5">
            <Text className="font-mono text-[9px] uppercase text-muted-brown">
              {modelType}
            </Text>
          </View>
        )}
      </View>

      {/* Current Chord Display */}
      <View className="relative mt-4 items-center overflow-hidden rounded-lg border border-wood-700/40 bg-wood-900/60 py-6">
        <Animated.View
          pointerEvents="none"
          style={[
            {
              position: 'absolute',
              left: 0,
              right: 0,
              top: 0,
              bottom: 0,
              borderRadius: 8,
              backgroundColor: colors.amber.accent,
            },
            flashStyle,
          ]}
        />
        <Text className="font-serif text-4xl text-cream">{chordLabel}</Text>
        {currentChord && (
          <Text className="mt-1 font-sans text-xs text-muted-brown">
            confidence: {Math.round(currentChord.confidence * 100)}%
          </Text>
        )}
      </View>

      {/* Confidence Meter */}
      <ConfidenceMeter confidence={currentChord?.confidence ?? 0} />

      {/* Chord History */}
      <ChordHistoryStream history={history} />

      {/* Error Display */}
      {error && (
        <Text className="mt-2 text-center font-sans text-xs text-danger">{error}</Text>
      )}

      {/* Start / Stop Button */}
      <AnimatedPressable
        onPress={isListening ? () => void stopListening() : () => void startListening()}
        haptic="medium"
        className={`mt-4 rounded-lg px-4 py-3 ${
          isListening ? 'bg-danger/80' : 'bg-amber-accent/90'
        }`}
      >
        <Text
          className={`text-center font-sans-medium text-sm ${
            isListening ? 'text-cream' : 'text-wood-900'
          }`}
        >
          {isListening ? 'Stop Listening' : 'Start Listening'}
        </Text>
      </AnimatedPressable>

      {/* Latency Display */}
      {isListening && latencyMs > 0 && (
        <Text className="mt-2 text-center font-mono text-[10px] text-muted-brown">
          Latency: {latencyMs}ms
        </Text>
      )}
    </View>
  )
}

/** Format a chord label for display: "C:maj" → "C", "A:min" → "Am". */
function formatChord(chord: string): string {
  const [root, quality] = chord.split(':')
  if (!root) return chord
  if (quality === 'maj') return root
  if (quality === 'min') return `${root}m`
  return chord
}
