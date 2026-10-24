import { useFocusEffect } from '@react-navigation/native'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Text, View } from 'react-native'
import {
  runOnJS,
  useAnimatedReaction,
  useFrameCallback,
  useReducedMotion,
  useSharedValue,
} from 'react-native-reanimated'

import { AnimatedPressable } from '@/components/AnimatedPressable'
import { FallingNotesVisualizer } from '@/components/pulse/FallingNotesVisualizer'
import { PulseChordTimeline } from '@/components/pulse/PulseChordTimeline'
import { PulseRing } from '@/components/pulse/PulseRing'
import { colors } from '@/src/constants/colors'
import type { PulseStageData } from '@/src/progress/pulseData'

export interface PulseStageProps {
  stage: PulseStageData
  trackTitle: string | null
  isDemoPreview?: boolean
  onPreviewDemo?: () => void
}

export function PulseStage({ stage, trackTitle, isDemoPreview = false, onPreviewDemo }: PulseStageProps) {
  const reducedMotion = useReducedMotion()
  const playhead = useSharedValue(0)
  const windowSecValue = useSharedValue(stage.windowSec)
  const lastChordIndex = useSharedValue(-2)
  const lastBarIndex = useSharedValue(-2)

  const [activeChordIndex, setActiveChordIndex] = useState(-1)
  const [activeBarIndex, setActiveBarIndex] = useState(-1)

  const eventStarts = useMemo(() => stage.events.map((event) => event.timestamp), [stage.events])
  const confidences = useMemo(() => stage.events.map((event) => event.confidence), [stage.events])
  const barStarts = useMemo(() => stage.bars.map((bar) => bar.startSec), [stage.bars])

  useEffect(() => {
    windowSecValue.value = stage.windowSec
    playhead.value = 0
    lastChordIndex.value = -2
    lastBarIndex.value = -2
    if (reducedMotion) {
      setActiveChordIndex(stage.events.length > 0 ? 0 : -1)
      setActiveBarIndex(stage.bars.length > 0 ? 0 : -1)
    } else {
      setActiveChordIndex(-1)
      setActiveBarIndex(-1)
    }
  }, [stage, reducedMotion, playhead, windowSecValue, lastChordIndex, lastBarIndex])

  const frameCallback = useFrameCallback((info) => {
    if (windowSecValue.value <= 0) return
    const delta = Math.min(0.1, (info.timeSincePreviousFrame ?? 16) / 1000)
    const next = playhead.value + delta
    playhead.value = next >= windowSecValue.value ? 0 : next
  }, false)

  useFocusEffect(
    useCallback(() => {
      if (reducedMotion || stage.windowSec <= 0) return
      frameCallback.setActive(true)
      return () => frameCallback.setActive(false)
    }, [frameCallback, reducedMotion, stage.windowSec]),
  )

  useAnimatedReaction(
    () => playhead.value,
    (timeSec) => {
      let chordIndex = -1
      for (let i = 0; i < eventStarts.length; i += 1) {
        if (eventStarts[i]! <= timeSec) chordIndex = i
        else break
      }
      if (chordIndex !== lastChordIndex.value) {
        lastChordIndex.value = chordIndex
        runOnJS(setActiveChordIndex)(chordIndex)
      }

      let barIndex = -1
      for (let i = 0; i < barStarts.length; i += 1) {
        if (barStarts[i]! <= timeSec) barIndex = i
        else break
      }
      if (barIndex !== lastBarIndex.value) {
        lastBarIndex.value = barIndex
        runOnJS(setActiveBarIndex)(barIndex)
      }
    },
    [eventStarts, barStarts],
  )

  const activeEvent = activeChordIndex >= 0 ? stage.events[activeChordIndex] : null
  const activeBar = activeBarIndex >= 0 ? stage.bars[activeBarIndex] : null
  const display = activeEvent?.display ?? activeBar?.display ?? '—'
  const roman = activeEvent?.roman ?? activeBar?.roman ?? null
  const confidence = activeEvent?.confidence ?? activeBar?.confidence ?? 0

  if (stage.events.length === 0 || stage.windowSec <= 0) {
    return (
      <View className="rounded-2xl border border-wood-600/45 bg-wood-800/40 px-6 py-8">
        <Text className="font-serif text-xl text-cream">No chord data yet</Text>
        <Text className="mt-2 font-sans text-sm leading-6 text-muted-light">
          Analyze a song to populate the pulse stage. Once a lesson has a chord timeline, the falling
          notes and ring animate from that real transcript.
        </Text>
        {onPreviewDemo ? (
          <AnimatedPressable
            onPress={onPreviewDemo}
            haptic="light"
            accessibilityRole="button"
            accessibilityLabel="Preview Chord Pulse with the demo lesson"
            className="mt-5 self-start rounded-full border border-amber-accent/50 bg-amber-accent/15 px-4 py-2 active:bg-amber-accent/25"
          >
            <Text className="font-sans-medium text-sm text-amber-light">Preview with demo</Text>
          </AnimatedPressable>
        ) : null}
      </View>
    )
  }

  return (
    <View className="rounded-2xl border border-wood-600/45 bg-wood-800/40 p-4">
      <View className="mb-3 flex-row items-baseline justify-between gap-3">
        <View className="flex-1 flex-row items-center gap-2">
          <Text
            className="font-sans-medium text-[11px] uppercase tracking-wider text-muted-light"
            numberOfLines={1}
          >
            {trackTitle?.trim() || 'Latest practice'}
          </Text>
          {isDemoPreview ? (
            <Text className="rounded-full bg-amber-accent/15 px-2 py-0.5 font-mono text-[9px] uppercase tracking-wider text-amber-light">
              Demo
            </Text>
          ) : null}
        </View>
        <Text className="font-mono text-[10px] text-muted-light/70">
          {Math.round(stage.windowSec)}s loop
        </Text>
      </View>

      <View className="flex-col gap-4 md:flex-row md:items-center">
        <View className="items-center md:w-[220px]">
          <PulseRing
            playhead={playhead}
            chordStarts={eventStarts}
            confidences={confidences}
            downbeats={stage.beatGrid.downbeats}
            pulseBpm={stage.beatGrid.pulseBpm}
            activeConfidence={confidence}
          >
            <Text className="font-serif text-4xl text-cream" numberOfLines={1}>
              {display}
            </Text>
            <Text className="mt-0.5 font-mono text-[10px] uppercase tracking-[1.5px] text-amber-light/80">
              {roman ?? 'Chord'}
            </Text>
          </PulseRing>

          <View className="mt-1 w-44">
            <View className="mb-1 flex-row items-center justify-between">
              <Text className="font-sans text-[10px] uppercase tracking-wider text-muted-light/75">
                Confidence
              </Text>
              <Text className="font-mono text-[10px] text-cream/80">
                {Math.round(confidence * 100)}%
              </Text>
            </View>
            <View className="h-1.5 overflow-hidden rounded-full" style={{ backgroundColor: `${colors.wood[600]}70` }}>
              <View
                className="h-1.5 rounded-full"
                style={{
                  width: `${Math.round(confidence * 100)}%`,
                  backgroundColor: confidence >= 0.85 ? colors.success : colors.amber.accent,
                }}
              />
            </View>
          </View>
        </View>

        <View className="md:flex-1">
          <FallingNotesVisualizer
            playhead={playhead}
            notes={stage.notes}
            beats={stage.beatGrid.beats}
            downbeats={stage.beatGrid.downbeats}
            windowSec={stage.windowSec}
            reducedMotion={reducedMotion}
          />
        </View>
      </View>

      <PulseChordTimeline bars={stage.bars} activeIndex={activeBarIndex} />
    </View>
  )
}
