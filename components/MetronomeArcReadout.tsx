import { LinearGradient } from 'expo-linear-gradient'
import { memo, useEffect, useMemo, useRef } from 'react'
import { View, Text } from 'react-native'
import Animated, { useAnimatedStyle, useSharedValue, withSequence, withTiming } from 'react-native-reanimated'
import Svg, { Path } from 'react-native-svg'

import type { MetronomeSubdivision } from '@/src/audio/metronomeShared'
import colors from '@/src/constants/colors'

/** Reference: w-24 h-24 pendulum stage (96×96). */
const STAGE = 96
const PIVOT_BOTTOM = 24
const ARM_H = 56
const BOB = 16
const PEND_H = ARM_H + BOB * 0.5
const W_TICK = 3
const H_TICK = 10

const ARC_R = 38
const ARC_CX = STAGE / 2
const ARC_CY = STAGE - PIVOT_BOTTOM

function polar(cx: number, cy: number, r: number, angleRad: number) {
  return { x: cx + r * Math.cos(angleRad), y: cy - r * Math.sin(angleRad) }
}

function semicirclePathD(): string {
  const start = polar(ARC_CX, ARC_CY, ARC_R, Math.PI)
  const end = polar(ARC_CX, ARC_CY, ARC_R, 0)
  return `M ${start.x} ${start.y} A ${ARC_R} ${ARC_R} 0 0 1 ${end.x} ${end.y}`
}

export type MetronomeArcReadoutProps = {
  effectiveBpm: number
  baseTempoBpm: number
  flashTick: number
  lastDownbeat: boolean
  metronomeActive: boolean
  subdivision: MetronomeSubdivision
}

function MetronomeArcReadoutInner({
  effectiveBpm,
  flashTick,
  lastDownbeat,
  metronomeActive,
  subdivision,
}: MetronomeArcReadoutProps) {
  const d = useMemo(() => semicirclePathD(), [])
  const rotationDeg = useSharedValue(0)
  const swingRightNext = useRef(true)

  useEffect(() => {
    if (!metronomeActive) {
      swingRightNext.current = true
      rotationDeg.value = withTiming(0, { duration: 220 })
      return
    }
    if (flashTick <= 0) return

    const bpm = Math.max(1, effectiveBpm)
    const subdiv = Math.max(1, subdivision)
    const beatPeriodMs = 60000 / bpm / subdiv
    const strikeMs = Math.min(110, Math.max(36, beatPeriodMs * 0.11))
    const relaxMs = Math.max(80, beatPeriodMs - strikeMs)

    const mag = lastDownbeat ? 30 : 17
    const dir = swingRightNext.current ? 1 : -1
    swingRightNext.current = !swingRightNext.current
    rotationDeg.value = withSequence(
      withTiming(dir * mag, { duration: strikeMs }),
      withTiming(0, { duration: relaxMs }),
    )
  }, [effectiveBpm, flashTick, lastDownbeat, metronomeActive, rotationDeg, subdivision])

  const pendulumStyle = useAnimatedStyle(() => ({
    transform: [
      { translateX: 8 },
      { translateY: PEND_H },
      { rotate: `${rotationDeg.value}deg` },
      { translateX: -8 },
      { translateY: -PEND_H },
    ],
  }))

  const arcOpacity = metronomeActive ? 0.45 : 0.28
  const tickOpacity = metronomeActive ? 0.85 : 0.45

  return (
    <View className="items-center" accessibilityLabel={`Metronome, ${effectiveBpm} BPM`}>
      <View className="items-center justify-center py-2" style={{ width: STAGE, height: STAGE }}>
        <Svg width={STAGE} height={STAGE} style={{ position: 'absolute', left: 0, top: 0 }} pointerEvents="none">
          <Path
            d={d}
            fill="none"
            stroke={colors.wood[600]}
            strokeWidth={2}
            strokeOpacity={arcOpacity}
            strokeDasharray="6 5"
            strokeLinecap="round"
          />
        </Svg>

        <View
          pointerEvents="none"
          className="absolute rounded-full bg-wood-600"
          style={{
            width: W_TICK,
            height: H_TICK,
            left: ARC_CX - ARC_R - W_TICK * 0.25,
            bottom: PIVOT_BOTTOM - 2,
            transform: [{ rotate: '-32deg' }],
            opacity: tickOpacity,
          }}
        />
        <View
          pointerEvents="none"
          className="absolute rounded-full bg-wood-600"
          style={{
            width: W_TICK,
            height: H_TICK,
            left: ARC_CX + ARC_R - W_TICK * 0.75,
            bottom: PIVOT_BOTTOM - 2,
            transform: [{ rotate: '32deg' }],
            opacity: tickOpacity,
          }}
        />

        <View
          pointerEvents="none"
          className="absolute rounded-full bg-amber-accent"
          style={{
            width: W_TICK,
            height: H_TICK,
            left: STAGE / 2 - W_TICK / 2,
            bottom: PIVOT_BOTTOM + 10,
            opacity: metronomeActive ? 0.65 : 0.35,
          }}
        />

        <View style={{ position: 'absolute', left: STAGE / 2, bottom: PIVOT_BOTTOM, width: 0, height: 0 }}>
          <Animated.View
            style={[
              {
                position: 'absolute',
                bottom: 0,
                left: -8,
                width: 16,
                height: PEND_H,
                alignItems: 'center',
              },
              pendulumStyle,
            ]}
          >
            <LinearGradient
              colors={[colors.amber.accent, colors.amber.light]}
              start={{ x: 0.5, y: 0 }}
              end={{ x: 0.5, y: 1 }}
              style={{
                position: 'absolute',
                bottom: BOB - 2,
                width: 2,
                height: ARM_H,
                borderRadius: 1,
                marginLeft: -1,
                left: '50%',
                opacity: metronomeActive ? 1 : 0.55,
              }}
            />
            <View
              style={{
                position: 'absolute',
                bottom: 0,
                width: BOB,
                height: BOB,
                borderRadius: BOB / 2,
                backgroundColor: colors.amber.accent,
                borderWidth: 2,
                borderColor: 'rgba(232, 184, 109, 0.35)',
                opacity: metronomeActive ? 1 : 0.55,
              }}
            />
          </Animated.View>
        </View>

        <View
          pointerEvents="none"
          className="absolute rounded-full border border-wood-500 bg-wood-600"
          style={{
            width: 8,
            height: 8,
            left: STAGE / 2 - 4,
            bottom: PIVOT_BOTTOM - 4,
            zIndex: 4,
          }}
        />
      </View>

      <View className="mt-0.5 flex-row items-baseline justify-center gap-1 px-1">
        <Text className="font-mono text-2xl font-medium leading-none tabular-nums text-wood-900">
          {effectiveBpm}
        </Text>
        <Text className="pb-0.5 font-sans text-sm text-muted-brown">BPM</Text>
      </View>
    </View>
  )
}

export const MetronomeArcReadout = memo(MetronomeArcReadoutInner)
