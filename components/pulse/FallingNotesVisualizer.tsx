import { memo, useCallback, useState } from 'react'
import { Text, View } from 'react-native'
import Animated, { useAnimatedStyle, type SharedValue } from 'react-native-reanimated'

import { colors } from '@/src/constants/colors'
import type { PulseFallingNote } from '@/src/progress/pulseData'

const LEAD_SECONDS = 4.5
const HIT_LINE_OFFSET = 26
const LANE_GAP = 3

interface FallingNotesVisualizerProps {
  playhead: SharedValue<number>
  notes: readonly PulseFallingNote[]
  beats: readonly number[]
  downbeats: readonly number[]
  windowSec: number
  reducedMotion: boolean
}

interface LayoutSize {
  width: number
  height: number
}

const NoteBlock = memo(function NoteBlock({
  note,
  playhead,
  width,
  height,
  hitLineY,
  pxPerSec,
  reducedMotion,
}: {
  note: PulseFallingNote
  playhead: SharedValue<number>
  width: number
  height: number
  hitLineY: number
  pxPerSec: number
  reducedMotion: boolean
}) {
  const laneWidth = width / 12
  const noteHeight = Math.min(46, Math.max(7, note.durationSec * pxPerSec * 0.8))
  const left = note.pitchClass * laneWidth + LANE_GAP / 2
  const noteWidth = Math.max(4, laneWidth - LANE_GAP)

  const animatedStyle = useAnimatedStyle(() => {
    const t = reducedMotion ? note.startSec - 1.4 : playhead.value
    const secondsUntil = note.startSec - t
    const top = hitLineY - noteHeight - secondsUntil * pxPerSec
    const visible = top > -noteHeight * 2 && top < height + noteHeight
    return {
      transform: [{ translateY: top }],
      opacity: visible ? (note.isChordTone ? 0.95 : 0.5) : 0,
    }
  }, [note, hitLineY, pxPerSec, height, noteHeight, reducedMotion])

  return (
    <Animated.View
      pointerEvents="none"
      style={[
        {
          position: 'absolute',
          left,
          width: noteWidth,
          height: noteHeight,
          borderRadius: 3,
          backgroundColor: note.isChordTone ? colors.amber.accent : colors.muted.brown,
          borderWidth: note.isChordTone ? 1 : 0,
          borderColor: note.isChordTone ? colors.amber.light : 'transparent',
        },
        animatedStyle,
      ]}
    />
  )
})

const BeatGuide = memo(function BeatGuide({
  timeSec,
  playhead,
  width,
  height,
  hitLineY,
  pxPerSec,
  isDownbeat,
  reducedMotion,
}: {
  timeSec: number
  playhead: SharedValue<number>
  width: number
  height: number
  hitLineY: number
  pxPerSec: number
  isDownbeat: boolean
  reducedMotion: boolean
}) {
  const animatedStyle = useAnimatedStyle(() => {
    const t = reducedMotion ? timeSec - 1.4 : playhead.value
    const top = hitLineY - (timeSec - t) * pxPerSec
    const visible = top > -2 && top < height
    return {
      transform: [{ translateY: top }],
      opacity: visible ? (isDownbeat ? 0.45 : 0.18) : 0,
    }
  }, [timeSec, hitLineY, pxPerSec, height, isDownbeat, reducedMotion])

  return (
    <Animated.View
      pointerEvents="none"
      style={[
        {
          position: 'absolute',
          left: 0,
          width,
          height: isDownbeat ? 1.5 : 1,
          backgroundColor: isDownbeat ? colors.amber.accent : colors.muted.brown,
        },
        animatedStyle,
      ]}
    />
  )
})

export function FallingNotesVisualizer({
  playhead,
  notes,
  beats,
  downbeats,
  windowSec,
  reducedMotion,
}: FallingNotesVisualizerProps) {
  const [size, setSize] = useState<LayoutSize>({ width: 0, height: 0 })
  const onLayout = useCallback((event: { nativeEvent: { layout: LayoutSize } }) => {
    const { width, height } = event.nativeEvent.layout
    setSize((previous) =>
      Math.abs(previous.width - width) < 1 && Math.abs(previous.height - height) < 1
        ? previous
        : { width, height },
    )
  }, [])

  const hitLineY = Math.max(20, size.height - HIT_LINE_OFFSET)
  const pxPerSec = Math.max(1, (hitLineY - 6) / LEAD_SECONDS)
  const downbeatSet = new Set(downbeats.map((value) => value.toFixed(3)))
  const visibleBeats = beats.filter((beat) => beat <= windowSec + LEAD_SECONDS)

  return (
    <View
      className="overflow-hidden rounded-xl border border-wood-600/40"
      style={{ backgroundColor: `${colors.wood[900]}B8`, height: 264 }}
      onLayout={onLayout}
    >
      <View className="absolute inset-0">
        {size.width > 0
          ? Array.from({ length: 11 }, (_, index) => (
              <View
                key={`lane-${index}`}
                pointerEvents="none"
                style={{
                  position: 'absolute',
                  left: ((index + 1) / 12) * size.width,
                  top: 0,
                  bottom: 0,
                  width: 1,
                  backgroundColor: `${colors.wood[600]}40`,
                }}
              />
            ))
          : null}

        {size.width > 0 && reducedMotion
          ? Array.from({ length: 6 }, (_, index) => (
              <View
                key={`static-guide-${index}`}
                pointerEvents="none"
                style={{
                  position: 'absolute',
                  left: 0,
                  right: 0,
                  top: 28 + index * 36,
                  height: index === 3 ? 1.5 : 1,
                  backgroundColor: index === 3 ? `${colors.amber.accent}70` : `${colors.muted.brown}45`,
                }}
              />
            ))
          : null}

        {size.width > 0 && !reducedMotion
          ? visibleBeats.map((beat) => (
              <BeatGuide
                key={`beat-${beat}`}
                timeSec={beat}
                playhead={playhead}
                width={size.width}
                height={size.height}
                hitLineY={hitLineY}
                pxPerSec={pxPerSec}
                isDownbeat={downbeatSet.has(beat.toFixed(3))}
                reducedMotion={reducedMotion}
              />
            ))
          : null}

        {size.width > 0
          ? notes.map((note) => (
              <NoteBlock
                key={note.id}
                note={note}
                playhead={playhead}
                width={size.width}
                height={size.height}
                hitLineY={hitLineY}
                pxPerSec={pxPerSec}
                reducedMotion={reducedMotion}
              />
            ))
          : null}
      </View>

      <View
        pointerEvents="none"
        style={{ position: 'absolute', left: 0, right: 0, top: 0, height: 34, backgroundColor: `${colors.wood[900]}E6` }}
      />
      <View
        pointerEvents="none"
        style={{ position: 'absolute', left: 0, right: 0, top: 34, height: 14, backgroundColor: `${colors.wood[900]}80` }}
      />

      <View
        pointerEvents="none"
        className="absolute left-3 top-2 flex-row items-center gap-3"
      >
        <View className="flex-row items-center gap-1.5">
          <View className="h-2 w-2 rounded-full" style={{ backgroundColor: colors.amber.accent }} />
          <Text className="font-sans text-[10px] text-cream/75">Chord tone</Text>
        </View>
        <View className="flex-row items-center gap-1.5">
          <View className="h-2 w-2 rounded-full" style={{ backgroundColor: colors.muted.brown }} />
          <Text className="font-sans text-[10px] text-cream/55">Passing tone</Text>
        </View>
      </View>

      <View
        pointerEvents="none"
        style={{
          position: 'absolute',
          left: 0,
          right: 0,
          top: hitLineY,
          height: 2,
          backgroundColor: colors.amber.light,
          shadowColor: colors.amber.light,
          shadowOpacity: 0.8,
          shadowRadius: 8,
          shadowOffset: { width: 0, height: 0 },
        }}
      />

      {notes.length === 0 ? (
        <View className="absolute inset-0 items-center justify-center px-6">
          <Text className="text-center font-sans text-xs text-cream/55">
            No solo notes in this excerpt. The chord-tone grid will fill in as analysis completes.
          </Text>
        </View>
      ) : null}
    </View>
  )
}
