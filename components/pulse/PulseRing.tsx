import type { ReactNode } from 'react'
import { useAnimatedStyle, useDerivedValue, useReducedMotion, interpolateColor, type SharedValue } from 'react-native-reanimated'
import Animated from 'react-native-reanimated'
import { View } from 'react-native'

import { colors } from '@/src/constants/colors'

export interface PulseRingProps {
  playhead: SharedValue<number>
  chordStarts: readonly number[]
  confidences: readonly number[]
  downbeats: readonly number[]
  pulseBpm: number
  /** JS-side fallback used when reduced motion is enabled. */
  activeConfidence: number
  size?: number
  children?: ReactNode
}

function currentIndex(starts: readonly number[], timeSec: number): number {
  'worklet'
  let index = -1
  for (let i = 0; i < starts.length; i += 1) {
    if (starts[i]! <= timeSec) index = i
    else break
  }
  return index
}

export function PulseRing({
  playhead,
  chordStarts,
  confidences,
  downbeats,
  pulseBpm,
  activeConfidence,
  size = 176,
  children,
}: PulseRingProps) {
  const reducedMotion = useReducedMotion()
  const beatSec = 60 / Math.max(20, pulseBpm)

  const confidence = useDerivedValue(() => {
    const index = currentIndex(chordStarts, playhead.value)
    return index >= 0 ? (confidences[index] ?? 0) : 0
  }, [chordStarts, confidences, playhead])

  const ringStyle = useAnimatedStyle(() => {
    if (reducedMotion) {
      return {
        transform: [{ scale: 1 }],
        borderColor: interpolateColor(
          activeConfidence,
          [0.3, 0.9],
          [colors.muted.brown, colors.amber.light],
        ),
      }
    }
    const t = playhead.value
    let lastDownbeat = 0
    let isDownbeat = false
    for (const downbeat of downbeats) {
      if (downbeat <= t) {
        lastDownbeat = downbeat
        isDownbeat = true
      } else {
        break
      }
    }
    const sinceBeat = Math.max(0, t - lastDownbeat)
    const phase = (sinceBeat % beatSec) / beatSec
    const amplitude = isDownbeat ? 0.075 : 0.03
    return {
      transform: [{ scale: 1 + amplitude * Math.exp(-phase * 5) }],
      borderColor: interpolateColor(
        confidence.value,
        [0.3, 0.9],
        [colors.muted.brown, colors.amber.light],
      ),
    }
  }, [reducedMotion, activeConfidence, downbeats, beatSec])

  const haloStyle = useAnimatedStyle(() => {
    if (reducedMotion) return { opacity: 0, transform: [{ scale: 1 }] }
    const t = playhead.value
    let lastDownbeat = 0
    let isDownbeat = false
    for (const downbeat of downbeats) {
      if (downbeat <= t) {
        lastDownbeat = downbeat
        isDownbeat = true
      } else {
        break
      }
    }
    const sinceBeat = Math.max(0, t - lastDownbeat)
    const phase = (sinceBeat % beatSec) / beatSec
    return {
      opacity: (isDownbeat ? 0.28 : 0.1) * (1 - phase),
      transform: [{ scale: 1 + (isDownbeat ? 0.34 : 0.16) * phase }],
    }
  }, [reducedMotion, downbeats, beatSec])

  return (
    <View className="items-center justify-center" style={{ width: size + 44, height: size + 44 }}>
      <Animated.View
        pointerEvents="none"
        style={[
          {
            position: 'absolute',
            width: size,
            height: size,
            borderRadius: size / 2,
            borderWidth: 2,
            borderColor: colors.amber.accent,
          },
          haloStyle,
        ]}
      />
      <Animated.View
        style={[
          {
            width: size,
            height: size,
            borderRadius: size / 2,
            borderWidth: 4,
            backgroundColor: `${colors.wood[900]}B0`,
          },
          ringStyle,
        ]}
      >
        <View
          className="flex-1 items-center justify-center rounded-full"
          style={{ backgroundColor: `${colors.wood[800]}55` }}
        >
          {children}
        </View>
      </Animated.View>
    </View>
  )
}
