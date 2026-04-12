import { useCallback } from 'react'
import { Text, View } from 'react-native'
import { Gesture, GestureDetector } from 'react-native-gesture-handler'
import Animated, { useAnimatedStyle, useSharedValue } from 'react-native-reanimated'

import { AnimatedPressable } from './AnimatedPressable'

export type NoteDetailCardProps = {
  noteName: string
  scaleDegree: string
  fingerLine: string
  /** Optional same-pitch fingerings on other strings (Study / AlphaTab). */
  alternateFingerLines?: string[]
  coachText: string
  onDismiss?: () => void
}

/**
 * Draggable pedagogy panel for Study (AlphaTab note selection).
 */
export function NoteDetailCard({
  noteName,
  scaleDegree,
  fingerLine,
  alternateFingerLines,
  coachText,
  onDismiss,
}: NoteDetailCardProps) {
  const translateX = useSharedValue(0)
  const translateY = useSharedValue(0)
  const startX = useSharedValue(0)
  const startY = useSharedValue(0)

  const pan = Gesture.Pan()
    .onStart(() => {
      startX.value = translateX.value
      startY.value = translateY.value
    })
    .onUpdate((e) => {
      translateX.value = startX.value + e.translationX
      translateY.value = startY.value + e.translationY
    })
    .onEnd(() => {
      startX.value = translateX.value
      startY.value = translateY.value
    })

  const cardStyle = useAnimatedStyle(() => ({
    transform: [{ translateX: translateX.value }, { translateY: translateY.value }],
  }))

  const handleDismiss = useCallback(() => {
    onDismiss?.()
  }, [onDismiss])

  return (
    <GestureDetector gesture={pan}>
      <Animated.View
        style={cardStyle}
        className="rounded-xl border border-amber-accent/50 bg-wood-900/92 p-3 shadow-lg"
        accessible
        accessibilityLabel={`Note ${noteName}. ${scaleDegree}. ${fingerLine}${
          alternateFingerLines?.length ? `. Alternates: ${alternateFingerLines.join(' ')}` : ''
        }`}
      >
        <View className="mb-2 flex-row items-center justify-between gap-2">
          <Text className="font-sans-medium text-[11px] uppercase tracking-wide text-amber-light">Selected note</Text>
          {onDismiss ? (
            <AnimatedPressable
              haptic="light"
              onPress={handleDismiss}
              className="rounded-md border border-wood-600/60 px-2 py-1"
              accessibilityRole="button"
              accessibilityLabel="Dismiss note detail"
            >
              <Text className="font-sans text-xs text-cream">Close</Text>
            </AnimatedPressable>
          ) : null}
        </View>
        <Text className="font-serif text-xl text-cream">{noteName}</Text>
        <Text className="mt-1 font-sans text-sm text-amber-light">{scaleDegree}</Text>
        <Text className="mt-2 font-sans text-xs leading-relaxed text-cream/90">{fingerLine}</Text>
        {alternateFingerLines && alternateFingerLines.length > 0 ? (
          <View className="mt-2">
            <Text className="font-sans-medium text-[10px] uppercase tracking-wide text-amber-light/90">
              Other positions (same pitch)
            </Text>
            {alternateFingerLines.map((line, i) => (
              <Text key={`alt-${i}-${line.slice(0, 24)}`} className="mt-1 font-sans text-[11px] leading-relaxed text-cream/75">
                · {line}
              </Text>
            ))}
          </View>
        ) : null}
        <Text className="mt-2 border-t border-wood-600/40 pt-2 font-sans text-xs leading-relaxed text-muted-brown">
          {coachText}
        </Text>
        <Text className="mt-2 font-sans text-[10px] text-muted-brown">Drag this card to reposition.</Text>
      </Animated.View>
    </GestureDetector>
  )
}
