import { memo, useEffect, useMemo } from 'react'
import { View, Text } from 'react-native'
import Animated, {
  useAnimatedProps,
  useAnimatedStyle,
  useSharedValue,
  withSequence,
  withTiming,
} from 'react-native-reanimated'
import Svg, { Circle, Path } from 'react-native-svg'

import colors from '@/src/constants/colors'

const AnimatedPath = Animated.createAnimatedComponent(Path)

const ARC_W = 152
const ARC_H = 78
const CX = ARC_W / 2
const CY = ARC_H - 2
const R = 60
const STROKE = 1.75
const KNOB_R = 6.5

/** Pivot at bottom center of the gauge so the beat reads as a “kick” from the base. */
const PIVOT_X = CX
const PIVOT_Y = ARC_H

/** Align readout to the half-circle base; nudge down from chord so it sits slightly below the cut line. */
const BPM_BASE_INSET = ARC_H - CY - 6

function polar(cx: number, cy: number, r: number, angleRad: number) {
  return { x: cx + r * Math.cos(angleRad), y: cy - r * Math.sin(angleRad) }
}

function arcPathD(): string {
  const start = polar(CX, CY, R, Math.PI)
  const end = polar(CX, CY, R, 0)
  return `M ${start.x} ${start.y} A ${R} ${R} 0 0 1 ${end.x} ${end.y}`
}

export type MetronomeArcReadoutProps = {
  effectiveBpm: number
  baseTempoBpm: number
  flashTick: number
  lastDownbeat: boolean
  metronomeActive: boolean
}

function MetronomeArcReadoutInner({
  effectiveBpm,
  baseTempoBpm,
  flashTick,
  lastDownbeat,
  metronomeActive,
}: MetronomeArcReadoutProps) {
  const d = useMemo(() => arcPathD(), [])

  const knobAngle = useMemo(() => {
    const base = baseTempoBpm > 0 ? baseTempoBpm : 120
    const lo = base * 0.5
    const hi = base * 1.25
    const span = Math.max(1e-6, hi - lo)
    const t = Math.min(1, Math.max(0, (effectiveBpm - lo) / span))
    return Math.PI - t * Math.PI
  }, [baseTempoBpm, effectiveBpm])

  const knob = polar(CX, CY, R - STROKE * 0.5, knobAngle)

  const pulse = useSharedValue(0)

  useEffect(() => {
    if (!metronomeActive) {
      pulse.value = 0
      return
    }
    if (flashTick <= 0) return
    pulse.value = 0
    const peak = lastDownbeat ? 1 : 0.55
    pulse.value = withSequence(withTiming(peak, { duration: 45 }), withTiming(0, { duration: 220 }))
  }, [flashTick, lastDownbeat, metronomeActive, pulse])

  const arcMotionStyle = useAnimatedStyle(() => {
    const s = 1 + pulse.value * 0.065
    return {
      transform: [
        { translateX: -PIVOT_X },
        { translateY: -PIVOT_Y },
        { scale: s },
        { translateX: PIVOT_X },
        { translateY: PIVOT_Y },
      ],
    }
  })

  const accentArcProps = useAnimatedProps(() => ({
    strokeOpacity: pulse.value * 0.88,
  }))

  return (
    <View className="items-center" style={{ width: ARC_W, height: ARC_H, alignSelf: 'center' }}>
      <Animated.View style={[{ position: 'absolute', left: 0, top: 0, width: ARC_W, height: ARC_H }, arcMotionStyle]}>
        <Svg width={ARC_W} height={ARC_H} accessibilityLabel={`Tempo gauge, ${effectiveBpm} BPM`}>
          <Path
            d={d}
            fill="none"
            stroke={colors.muted.brown}
            strokeWidth={STROKE}
            strokeOpacity={0.45}
            strokeDasharray="5 6"
            strokeLinecap="round"
          />
          <AnimatedPath
            animatedProps={accentArcProps}
            d={d}
            fill="none"
            stroke={colors.amber.accent}
            strokeWidth={STROKE + 1.25}
            strokeDasharray="5 6"
            strokeLinecap="round"
          />
          <Circle
            cx={knob.x}
            cy={knob.y}
            r={KNOB_R}
            fill={colors.ivory}
            stroke={metronomeActive ? colors.amber.accent : colors.wood[600]}
            strokeWidth={1.75}
          />
        </Svg>
      </Animated.View>

      <View
        pointerEvents="none"
        className="w-full flex-row items-baseline justify-center gap-1 px-1"
        style={{
          position: 'absolute',
          left: 0,
          right: 0,
          bottom: BPM_BASE_INSET,
        }}
      >
        <Text
          className="font-serif text-[26px] leading-none tabular-nums text-wood-900"
          style={{
            textShadowColor: `${colors.ivory}E6`,
            textShadowRadius: 3,
            textShadowOffset: { width: 0, height: 0 },
          }}
        >
          {effectiveBpm}
        </Text>
        <Text
          className="font-sans-medium pb-0.5 text-[10px] uppercase tracking-wider text-muted-brown"
          style={{
            textShadowColor: `${colors.ivory}E6`,
            textShadowRadius: 3,
            textShadowOffset: { width: 0, height: 0 },
          }}
        >
          BPM
        </Text>
      </View>
    </View>
  )
}

export const MetronomeArcReadout = memo(MetronomeArcReadoutInner)
