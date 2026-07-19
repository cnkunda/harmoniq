import { ActivityIndicator, Text, View } from 'react-native'
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
import { formatChordDisplay } from '@/src/music/chordVoicing'
import colors from '@/src/constants/colors'

/** Map internal error codes/messages to user-friendly copy. */
function friendlyError(error: string): string {
  if (error === 'MIC_PERMISSION_DENIED' || /NotAllowedError|permission/i.test(error)) {
    return 'Microphone access denied. Enable mic permission in your browser or OS settings, then try again.'
  }
  if (/HTTPS|secure context/i.test(error)) {
    return 'Live listening needs a secure connection (HTTPS or localhost).'
  }
  if (/getUserMedia|unavailable/i.test(error)) {
    return 'No microphone is available in this browser.'
  }
  if (/Failed to load chord model|ONNX|runtime/i.test(error)) {
    return 'Could not load the chord model. Check your connection and try again.'
  }
  return error
}

/**
 * Active Listener card for the Discover tab.
 * Shows live chord detection from microphone input.
 */
export function ActiveListenerCard() {
  const {
    isListening,
    status,
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

  const chordLabel = currentChord ? (isNoChord(currentChord.chord) ? '—' : formatChordDisplay(currentChord.chord)) : '—'

  const isInitializing = status === 'initializing'
  const isWarming = status === 'warming'

  return (
    <View className="rounded-xl border border-wood-600/50 bg-wood-800/80 p-4">
      <View className="flex-row items-center justify-between">
        <View className="flex-1">
          <View className="flex-row items-center gap-2">
            <Text className="font-sans-medium text-xs uppercase tracking-wide text-amber-light">
              Active Listener
            </Text>
            <View className="rounded bg-amber-accent/20 px-1.5 py-0.5">
              <Text className="font-mono text-[8px] uppercase tracking-wider text-amber-light">Beta</Text>
            </View>
          </View>
          <Text className="mt-1 font-sans text-xs text-muted-brown">
            Experimental real-time chord detection from your mic
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
        {currentChord && !isWarming && (
          <Text className="mt-1 font-sans text-xs text-muted-brown">
            confidence: {Math.round(currentChord.confidence * 100)}%
          </Text>
        )}
        {(isInitializing || isWarming) && (
          <View className="mt-2 flex-row items-center gap-2">
            <ActivityIndicator color={colors.amber.accent} size="small" />
            <Text className="font-sans text-xs text-muted-brown">
              {isInitializing ? 'Loading model…' : 'Warming up…'}
            </Text>
          </View>
        )}
      </View>

      {/* Confidence Meter */}
      <ConfidenceMeter confidence={currentChord?.confidence ?? 0} />

      {/* Chord History */}
      <ChordHistoryStream history={history} />

      {/* Error Display */}
      {error && (
        <Text className="mt-2 text-center font-sans text-xs text-danger">{friendlyError(error)}</Text>
      )}

      {/* Start / Stop Button */}
      <AnimatedPressable
        onPress={isListening ? () => void stopListening() : () => void startListening()}
        haptic="medium"
        disabled={isInitializing}
        className={`mt-4 rounded-lg px-4 py-3 ${
          isListening ? 'bg-danger/80' : 'bg-amber-accent/90'
        } ${isInitializing ? 'opacity-60' : ''}`}
      >
        <Text
          className={`text-center font-sans-medium text-sm ${
            isListening ? 'text-cream' : 'text-wood-900'
          }`}
        >
          {isInitializing ? 'Starting…' : isListening ? 'Stop Listening' : 'Start Listening'}
        </Text>
      </AnimatedPressable>

      {/* Latency Display */}
      {isListening && status === 'listening' && latencyMs > 0 && (
        <Text className="mt-2 text-center font-mono text-[10px] text-muted-brown">
          Latency: {latencyMs}ms
        </Text>
      )}
    </View>
  )
}


