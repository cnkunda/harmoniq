import { useEffect } from 'react'
import { ActivityIndicator, Text, View } from 'react-native'
import Svg, { Circle, G } from 'react-native-svg'
import Animated, {
  FadeInDown,
  useAnimatedProps,
  useSharedValue,
  withTiming,
} from 'react-native-reanimated'

import { AnimatedPressable } from '@/components/AnimatedPressable'
import { LoadingSkeleton } from '@/components/LoadingSkeleton'
import colors from '@/src/constants/colors'
import type { DrillSlotPayload, PracticePlanPayload } from '@/src/types'

const AnimatedCircle = Animated.createAnimatedComponent(Circle)

function chipLabel(slot: DrillSlotPayload): string {
  if (slot.slot_type === 'free_jam') return 'Free jam'
  if (slot.slot_type === 'warmup') return 'Warmup'
  if (slot.slot_type === 'technique') {
    const f = (slot.technique_focus ?? 'technique').replace(/_/g, ' ')
    const capitalized = f.charAt(0).toUpperCase() + f.slice(1)

    return capitalized.length > 14
      ? `${capitalized.slice(0, 12)}…`
      : `${capitalized} drill`
  }
  const t = slot.title.trim()
  if (t.length <= 20) return t
  return `${t.slice(0, 18)}…`
}

export function TodaysPlanCardLoading() {
  return (
    <View className="gap-4">
      <LoadingSkeleton height={28} width="70%" borderRadius={10} />
      <View className="flex-row flex-wrap gap-2">
        <LoadingSkeleton height={32} width={88} borderRadius={999} />
        <LoadingSkeleton height={32} width={96} borderRadius={999} />
        <LoadingSkeleton height={32} width={104} borderRadius={999} />
        <LoadingSkeleton height={32} width={80} borderRadius={999} />
      </View>
      <LoadingSkeleton height={44} width="55%" borderRadius={12} />
    </View>
  )
}

function PlanProgressRing({ progress }: { progress: number }) {
  const size = 56
  const stroke = 4
  const r = (size - stroke) / 2
  const cx = size / 2
  const cy = size / 2
  const circumference = 2 * Math.PI * r
  const sv = useSharedValue(0)

  useEffect(() => {
    sv.value = withTiming(Math.min(1, Math.max(0, progress)), { duration: 420 })
  }, [progress, sv])

  const animatedProps = useAnimatedProps(() => ({
    strokeDashoffset: circumference * (1 - sv.value),
  }))

  const pct = Math.round(Math.min(1, Math.max(0, progress)) * 100)

  return (
    <View style={{ width: size, height: size }}>
      <Svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <Circle
          cx={cx}
          cy={cy}
          r={r}
          stroke={colors.wood[600]}
          strokeWidth={stroke}
          fill="none"
          opacity={0.45}
        />
        <G transform={`rotate(-90 ${cx} ${cy})`}>
          <AnimatedCircle
            cx={cx}
            cy={cy}
            r={r}
            stroke={colors.amber.accent}
            strokeWidth={stroke}
            fill="none"
            strokeDasharray={`${circumference} ${circumference}`}
            animatedProps={animatedProps}
            strokeLinecap="round"
          />
        </G>
      </Svg>
      <View className="absolute inset-0 items-center justify-center">
        <Text className="font-sans-medium text-xs text-cream">{pct}%</Text>
      </View>
    </View>
  )
}

export function TodaysPlanCard({
  plan,
  sessionMinutes,
  progressFraction,
  onStart,
  busy,
  errorText,
}: {
  plan: PracticePlanPayload
  sessionMinutes: number
  progressFraction: number
  onStart: () => void
  busy?: boolean
  errorText?: string | null
}) {
  return (
    <Animated.View entering={FadeInDown.duration(380).delay(40)}>
      <View className="mb-4 flex-row items-start justify-between gap-3">
        <View className="min-w-0 flex-1">
          <Text className="mb-1 font-serif text-2xl text-cream">Your {sessionMinutes}-min session</Text>
          <Text className="font-sans text-sm text-amber-light/80">{plan.slots.length} steps · guided path</Text>
        </View>
        <PlanProgressRing progress={progressFraction} />
      </View>

      <View className="mb-4 flex-row flex-wrap gap-2">
        {plan.slots.map((slot, i) => (
          <AnimatedPressable
            key={`${slot.slot_type}-${i}`}
            haptic="none"
            onPress={() => {}}
            accessibilityRole="text"
            accessibilityLabel={`Slot ${i + 1}: ${chipLabel(slot)}`}
            className="rounded-full border border-amber-accent/35 bg-wood-800/55 px-3 py-1.5"
          >
            <Text className="font-sans-medium text-xs text-cream">{chipLabel(slot)}</Text>
          </AnimatedPressable>
        ))}
      </View>

      {errorText ? <Text className="mb-3 font-sans text-sm text-danger">{errorText}</Text> : null}

      <AnimatedPressable
        onPress={onStart}
        disabled={busy}
        haptic="medium"
        className="flex-row items-center justify-center gap-2 self-stretch rounded-xl bg-amber-accent px-8 py-3.5 shadow-md disabled:opacity-50 sm:self-start"
        accessibilityRole="button"
        accessibilityLabel="Start today’s practice session"
      >
        {busy ? <ActivityIndicator color="#2C1810" /> : null}
        <Text className="font-sans-medium text-base text-wood-900">{busy ? 'Starting…' : 'Start'}</Text>
      </AnimatedPressable>
    </Animated.View>
  )
}
