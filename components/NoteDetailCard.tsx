import { useCallback } from 'react'
import { Text, View } from 'react-native'
import { Gesture, GestureDetector } from 'react-native-gesture-handler'
import Animated, { useAnimatedStyle, useSharedValue } from 'react-native-reanimated'

import { AnimatedPressable } from './AnimatedPressable'
import type { ChordToneStatus } from '@/src/music/noteSelectionDetail'
import { colors } from '@/src/constants/colors'

export type NoteDetailCardProps = {
  noteName: string
  scaleDegree: string
  fingerLine: string
  alternateFingerLines?: string[]
  coachText: string
  onDismiss?: () => void
  /** Commit 159: report the displayed note as incorrectly transcribed. */
  onReportIncorrect?: () => void
  /** Commit 159: open the existing note correction controls for this note. */
  onCorrectNote?: () => void
  chordToneStatus?: ChordToneStatus | null
  /** Commit 157: backend scale-degree label ("R", "b3", …) when harmonized analysis exists. */
  harmonicDegree?: string | null
  confidence?: number | null
}

const STATUS_META: Record<ChordToneStatus, { label: string; color: string; dot: string }> = {
  chord_tone: { label: 'Chord tone', color: colors.success, dot: colors.success },
  tension: { label: 'Tension', color: colors.amber.accent, dot: colors.amber.light },
  chromatic: { label: 'Chromatic / Outside', color: colors.danger, dot: colors.danger },
  pedal: { label: 'Pedal', color: colors.muted.light, dot: colors.muted.light },
}

function ChordToneBadge({ status }: { status: ChordToneStatus }) {
  const meta = STATUS_META[status]
  return (
    <View className="flex-row items-center gap-1.5 rounded-full border px-2.5 py-1" style={{ borderColor: meta.color + '60' }}>
      <View className="h-2 w-2 rounded-full" style={{ backgroundColor: meta.dot }} />
      <Text className="font-sans-medium text-[10px]" style={{ color: meta.color }}>{meta.label}</Text>
    </View>
  )
}

function ConfidenceBadge({ confidence }: { confidence: number }) {
  const pct = Math.round(confidence * 100)
  const color = pct >= 85 ? colors.success : pct >= 60 ? colors.amber.accent : colors.danger
  return (
    <View className="flex-row items-center gap-1 rounded-full border px-2 py-1" style={{ borderColor: color + '50' }}>
      <Text className="font-mono text-[10px]" style={{ color }}>Confidence: {pct}%</Text>
    </View>
  )
}

export function NoteDetailCard({
  noteName,
  scaleDegree,
  fingerLine,
  alternateFingerLines,
  coachText,
  onDismiss,
  onReportIncorrect,
  onCorrectNote,
  chordToneStatus,
  harmonicDegree,
  confidence,
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
        className="rounded-3xl border border-wood-600 bg-wood-800 p-5 shadow-soft-wood"
        accessible
        accessibilityLabel={`Note ${noteName}. ${scaleDegree}. ${fingerLine}${
          alternateFingerLines?.length ? `. Alternates: ${alternateFingerLines.join(' ')}` : ''
        }`}
      >
        <View className="mb-4 items-center">
          <View className="h-1 w-12 rounded-full bg-wood-600/70" />
        </View>

        <View className="mb-4 flex-row items-center justify-between gap-2">
          <View className="flex-row items-center gap-2">
            <View className="h-2 w-2 rounded-full bg-amber-light" />
            <Text className="font-sans-medium text-[11px] uppercase tracking-wide text-amber-light">Selected note</Text>
          </View>
          {onDismiss ? (
            <AnimatedPressable
              haptic="light"
              onPress={handleDismiss}
              className="rounded-lg border border-wood-600 bg-wood-900 px-2.5 py-1.5"
              accessibilityRole="button"
              accessibilityLabel="Dismiss note detail"
            >
              <Text className="font-sans text-xs text-cream">Done</Text>
            </AnimatedPressable>
          ) : null}
        </View>

        <View className="mb-4 flex-row items-center justify-between gap-3">
          <Text className="font-serif text-2xl text-cream">{noteName}</Text>
          <View className="rounded-full border border-amber-accent bg-wood-900 px-3 py-1">
            <Text className="font-sans-medium text-xs text-amber-light">{scaleDegree}</Text>
          </View>
        </View>

        {chordToneStatus || harmonicDegree || (confidence != null && confidence >= 0) ? (
          <View className="mb-4 flex-row flex-wrap items-center gap-2">
            {chordToneStatus ? <ChordToneBadge status={chordToneStatus} /> : null}
            {harmonicDegree ? (
              <View className="rounded-full border border-wood-600/50 bg-wood-900 px-2 py-1">
                <Text className="font-mono text-[10px] text-amber-light">{harmonicDegree}</Text>
              </View>
            ) : null}
            {confidence != null && confidence >= 0 ? <ConfidenceBadge confidence={confidence} /> : null}
          </View>
        ) : null}

        <View className="rounded-2xl border border-wood-600 bg-wood-900 p-4">
          <Text className="font-sans-medium text-[10px] uppercase tracking-wide text-amber-light">Suggested fingering</Text>
          <Text className="mt-1 font-sans text-sm leading-relaxed text-cream">{fingerLine}</Text>
        </View>

        {alternateFingerLines && alternateFingerLines.length > 0 ? (
          <View className="mt-4 rounded-2xl border border-wood-600 bg-wood-900 p-4">
            <Text className="font-sans-medium text-[10px] uppercase tracking-wide text-amber-light">
              Other positions (same pitch)
            </Text>
            {alternateFingerLines.map((line, i) => (
              <Text key={`alt-${i}-${line.slice(0, 24)}`} className="mt-1 font-sans text-xs leading-relaxed text-cream">
                · {line}
              </Text>
            ))}
          </View>
        ) : null}

        <View className="mt-4 rounded-2xl border border-wood-600 bg-wood-700 p-4">
          <Text className="font-sans text-xs leading-relaxed text-cream">{coachText}</Text>
        </View>

        {onReportIncorrect || onCorrectNote ? (
          <View className="mt-4 flex-row flex-wrap gap-2">
            {onCorrectNote ? (
              <AnimatedPressable
                haptic="light"
                onPress={onCorrectNote}
                className="rounded-full border border-amber-accent/60 bg-amber-accent/10 px-3 py-2"
                accessibilityRole="button"
                accessibilityLabel="Correct this note"
              >
                <Text className="font-sans-medium text-xs text-amber-light">Correct note</Text>
              </AnimatedPressable>
            ) : null}
            {onReportIncorrect ? (
              <AnimatedPressable
                haptic="light"
                onPress={onReportIncorrect}
                className="rounded-full border border-danger/45 bg-danger/10 px-3 py-2"
                accessibilityRole="button"
                accessibilityLabel="Report this note as incorrect"
              >
                <Text className="font-sans-medium text-xs text-danger">Report incorrect</Text>
              </AnimatedPressable>
            ) : null}
          </View>
        ) : null}

        <Text className="mt-4 font-sans text-[10px] text-muted-light">
          Drag to reposition. Tap another note in score or fretboard to compare.
        </Text>
      </Animated.View>
    </GestureDetector>
  )
}
