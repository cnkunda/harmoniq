import { LinearGradient } from 'expo-linear-gradient'
import { memo, useEffect, useRef } from 'react'
import { View, Text } from 'react-native'
import Animated, {
  Easing,
  useAnimatedStyle,
  useSharedValue,
  withSequence,
  withTiming,
} from 'react-native-reanimated'
import Svg, { Path } from 'react-native-svg'

import type { MetronomeSubdivision } from '@/src/audio/metronomeShared'
import colors from '@/src/constants/colors'

/** Larger stage; all lengths scale from original 96px reference. */
const SCALE = 152 / 96
const STAGE = 152
const PIVOT_BOTTOM = Math.round(24 * SCALE)
const ARM_H = Math.round(56 * SCALE)
const BOB = Math.round(16 * SCALE)
/** Arm above fulcrum + bob below — fulcrum aligns with pivot cap center. */
const PEND_TOTAL_H = ARM_H + BOB
const PEND_ASSEMBLY_W = BOB
/** Rotation pivot: horizontal center of rod, vertical fulcrum = bob top = cap center (distance from assembly bottom). */
const PEND_PIVOT_X = PEND_ASSEMBLY_W / 2
const PEND_PIVOT_Y = BOB
/** Slight arm overlap into cap so the rod reads as emerging from the dark circle. */
const ARM_CAP_OVERLAP = Math.max(2, Math.round(2 * SCALE))

const W_TICK = Math.max(3, Math.round(3 * SCALE))
const H_TICK = Math.round(10 * SCALE)

const ARC_R = Math.round(38 * SCALE)
const ARC_CX = STAGE / 2
const ARC_CY = STAGE - PIVOT_BOTTOM
const ARC_STROKE = Math.max(2, 2 * SCALE)
const ARM_WIDTH = Math.max(3, Math.round(3 * SCALE))

const PIVOT_CAP = Math.round(8 * SCALE)

function polar(cx: number, cy: number, r: number, angleRad: number) {
  return { x: cx + r * Math.cos(angleRad), y: cy - r * Math.sin(angleRad) }
}

function semicirclePathD(cx: number, cy: number, r: number): string {
  const start = polar(cx, cy, r, Math.PI)
  const end = polar(cx, cy, r, 0)
  return `M ${start.x} ${start.y} A ${r} ${r} 0 0 1 ${end.x} ${end.y}`
}

const ARC_PATH_D = semicirclePathD(ARC_CX, ARC_CY, ARC_R)
const DASH_PATTERN = `${Math.round(6 * SCALE)} ${Math.round(5 * SCALE)}`

export type MetronomeArcReadoutProps = {
  effectiveBpm: number
  baseTempoBpm: number
  flashTick: number
  lastDownbeat: boolean
  metronomeActive: boolean
  subdivision: MetronomeSubdivision
  /** When false, only the pendulum stage is shown (e.g. BPM rendered in parent footer). Default true. */
  showBpm?: boolean
}

function MetronomeArcReadoutInner({
  effectiveBpm,
  flashTick,
  lastDownbeat,
  metronomeActive,
  subdivision,
  showBpm = true,
}: MetronomeArcReadoutProps) {
  const rotationDeg = useSharedValue(0)
  const swingRightNext = useRef(true)

  useEffect(() => {
    if (!metronomeActive) {
      swingRightNext.current = true
      rotationDeg.value = withTiming(0, {
        duration: 420,
        easing: Easing.out(Easing.cubic),
      })
      return
    }
    if (flashTick <= 0) return

    const bpm = Math.max(1, effectiveBpm)
    const subdiv = Math.max(1, subdivision)
    const beatPeriodMs = 60000 / bpm / subdiv
    /** One full swing per click, fits in beat window; ease-out to apex, smooth return (sin in-out ≈ harmonic). */
    let outwardMs = Math.round(beatPeriodMs * 0.46)
    let inwardMs = beatPeriodMs - outwardMs
    const minLeg = 32
    outwardMs = Math.max(minLeg, outwardMs)
    inwardMs = Math.max(minLeg, inwardMs)
    const sum = outwardMs + inwardMs
    if (sum > beatPeriodMs && beatPeriodMs > 0) {
      const s = beatPeriodMs / sum
      outwardMs = Math.max(26, Math.round(outwardMs * s))
      inwardMs = Math.max(26, beatPeriodMs - outwardMs)
    }

    const mag = lastDownbeat ? 30 : 17
    const dir = swingRightNext.current ? 1 : -1
    swingRightNext.current = !swingRightNext.current
    rotationDeg.value = withSequence(
      withTiming(dir * mag, {
        duration: outwardMs,
        easing: Easing.out(Easing.cubic),
      }),
      withTiming(0, {
        duration: inwardMs,
        easing: Easing.inOut(Easing.sin),
      }),
    )
  }, [effectiveBpm, flashTick, lastDownbeat, metronomeActive, rotationDeg, subdivision])

  const pendulumStyle = useAnimatedStyle(() => ({
    transform: [
      { translateX: PEND_PIVOT_X },
      { translateY: PEND_PIVOT_Y },
      { rotate: `${rotationDeg.value}deg` },
      { translateX: -PEND_PIVOT_X },
      { translateY: -PEND_PIVOT_Y },
    ],
  }))

  const arcOpacity = metronomeActive ? 0.5 : 0.32
  const tickOpacity = metronomeActive ? 0.88 : 0.48
  const arcStroke = colors.wood[500]

  const stage = (
    <View className="items-center justify-center" style={{ width: STAGE, height: STAGE }}>
      <Svg width={STAGE} height={STAGE} style={{ position: 'absolute', left: 0, top: 0 }} pointerEvents="none">
        <Path
          d={ARC_PATH_D}
          fill="none"
          stroke={arcStroke}
          strokeWidth={ARC_STROKE}
          strokeOpacity={arcOpacity}
          strokeDasharray={DASH_PATTERN}
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
          bottom: PIVOT_BOTTOM - Math.round(2 * SCALE),
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
          bottom: PIVOT_BOTTOM - Math.round(2 * SCALE),
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
          bottom: PIVOT_BOTTOM + Math.round(10 * SCALE),
          opacity: metronomeActive ? 0.7 : 0.38,
        }}
      />

      <Animated.View
        style={[
          {
            position: 'absolute',
            left: STAGE / 2 - PEND_ASSEMBLY_W / 2,
            bottom: PIVOT_BOTTOM - BOB,
            width: PEND_ASSEMBLY_W,
            height: PEND_TOTAL_H,
            alignItems: 'center',
            zIndex: 2,
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
            bottom: BOB - ARM_CAP_OVERLAP,
            width: ARM_WIDTH,
            height: ARM_H + ARM_CAP_OVERLAP,
            borderRadius: ARM_WIDTH / 2,
            marginLeft: -ARM_WIDTH / 2,
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
            borderWidth: Math.max(2, Math.round(2 * SCALE)),
            borderColor: 'rgba(232, 184, 109, 0.4)',
            opacity: metronomeActive ? 1 : 0.55,
          }}
        />
      </Animated.View>

      <View
        pointerEvents="none"
        className="absolute rounded-full border-2 border-wood-500 bg-wood-700"
        style={{
          width: PIVOT_CAP,
          height: PIVOT_CAP,
          left: STAGE / 2 - PIVOT_CAP / 2,
          bottom: PIVOT_BOTTOM - PIVOT_CAP / 2,
          zIndex: 4,
        }}
      />
    </View>
  )

  return (
    <View className="items-center" accessibilityLabel={`Metronome, ${effectiveBpm} BPM`}>
      {stage}
      {showBpm ? (
        <View className="mt-0.5 flex-row items-baseline justify-center gap-1 px-1">
          <Text className="font-mono text-2xl font-medium leading-none tabular-nums text-wood-900">
            {effectiveBpm}
          </Text>
          <Text className="pb-0.5 font-sans text-sm text-muted-light">BPM</Text>
        </View>
      ) : null}
    </View>
  )
}

export const MetronomeArcReadout = memo(MetronomeArcReadoutInner)
