import { useEffect } from 'react'
import { Text, View } from 'react-native'
import Svg, { Circle, G } from 'react-native-svg'
import Animated, { useAnimatedProps, useSharedValue, withTiming } from 'react-native-reanimated'

import colors from '@/src/constants/colors'

const AnimatedCircle = Animated.createAnimatedComponent(Circle)

const SIZE = 196
const STROKE = 10
const CX = SIZE / 2
const CY = SIZE / 2
const R = (SIZE - STROKE) / 2
/** Sits just inside the stroked ring so the disk covers stroke ends in the center. */
const INNER_FILL_R = R - STROKE / 2 - 6
const CIRC = 2 * Math.PI * R

export interface WarmupTimerRingProps {
  /** Seconds left in the whole warm-up (sum of remaining exercises). */
  totalRemainingSec: number
  /** Total planned duration; used for ring fill. */
  totalWarmupSec: number
  completed: boolean
  timeLabel: string
}

export function WarmupTimerRing({
  totalRemainingSec,
  totalWarmupSec,
  completed,
  timeLabel,
}: WarmupTimerRingProps) {
  const progress = (() => {
    if (completed) return 1
    if (totalWarmupSec <= 0) return 0
    const elapsed = totalWarmupSec - totalRemainingSec
    return Math.min(1, Math.max(0, elapsed / totalWarmupSec))
  })()

  const sv = useSharedValue(0)

  useEffect(() => {
    sv.value = withTiming(progress, { duration: 380 })
  }, [progress, sv])

  const animatedProps = useAnimatedProps(() => ({
    strokeDashoffset: CIRC * (1 - sv.value),
  }))

  return (
    <View className="items-center justify-center" style={{ width: SIZE, height: SIZE }}>
      <Svg width={SIZE} height={SIZE} viewBox={`0 0 ${SIZE} ${SIZE}`}>
        <Circle
          cx={CX}
          cy={CY}
          r={R}
          stroke={colors.wood[600]}
          strokeWidth={STROKE}
          fill="none"
          opacity={0.35}
        />
        <G transform={`rotate(-90 ${CX} ${CY})`}>
          <AnimatedCircle
            cx={CX}
            cy={CY}
            r={R}
            stroke={colors.amber.accent}
            strokeWidth={STROKE}
            fill="none"
            strokeDasharray={`${CIRC} ${CIRC}`}
            animatedProps={animatedProps}
            strokeLinecap="round"
          />
        </G>
        <Circle cx={CX} cy={CY} r={INNER_FILL_R} fill={colors.wood[900]} />
      </Svg>
      <View
        className="absolute items-center justify-center"
        style={{ width: INNER_FILL_R * 2, height: INNER_FILL_R * 2 }}
      >
        <Text className="font-serif text-4xl" style={{ color: colors.cream, includeFontPadding: false }}>
          {timeLabel}
        </Text>
        <Text className="mt-0.5 font-sans text-xs" style={{ color: colors.cream, opacity: 0.88 }}>
          remaining
        </Text>
      </View>
    </View>
  )
}
