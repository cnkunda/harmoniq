import { ActivityIndicator, Text, View } from 'react-native'
import Animated, { FadeInDown } from 'react-native-reanimated'

import { AnimatedPressable } from '@/components/AnimatedPressable'
import { LoadingSkeleton } from '@/components/LoadingSkeleton'
import type { DrillSlotPayload, PracticePlanPayload } from '@/src/types'

function stepLabel(slot: DrillSlotPayload): string {
  if (slot.slot_type === 'free_jam') return 'Free jam'
  if (slot.slot_type === 'warmup') return 'Warmup'
  if (slot.slot_type === 'technique') {
    const f = (slot.technique_focus ?? 'technique').replace(/_/g, ' ')
    const capitalized = f.charAt(0).toUpperCase() + f.slice(1)
    return capitalized.length > 14
      ? `${capitalized.slice(0, 12)}…`
      : `${capitalized}`
  }
  const t = slot.title.trim()
  if (t.length <= 20) return t
  return `${t.slice(0, 18)}…`
}

function sublabel(slot: DrillSlotPayload): string {
  if (slot.slot_type === 'warmup') return 'Finger warm-up'
  if (slot.slot_type === 'free_jam') return 'Open practice'
  if (slot.slot_type === 'technique') return slot.title.trim() || 'Technique practice'
  return slot.title.trim() || 'Section practice'
}

function formatDuration(seconds: number): string {
  const m = Math.round(seconds / 60)
  return `${m} min`
}

export function TodaysPlanCardLoading() {
  return (
    <View className="gap-4">
      <LoadingSkeleton height={28} width="70%" borderRadius={10} />
      <View className="gap-3">
        <LoadingSkeleton height={52} width="100%" borderRadius={10} />
        <LoadingSkeleton height={52} width="100%" borderRadius={10} />
        <LoadingSkeleton height={52} width="100%" borderRadius={10} />
      </View>
      <LoadingSkeleton height={44} width="55%" borderRadius={12} />
    </View>
  )
}

function StepRow({
  index,
  label,
  sub,
  duration,
  isCurrent,
}: {
  index: number
  label: string
  sub: string
  duration: string
  isCurrent: boolean
}) {
  return (
    <View
      className={`flex-row items-center gap-3 rounded-xl px-3 py-2.5 ${
        isCurrent ? 'bg-amber-dim border border-amber-accent/25' : ''
      }`}
    >
      <View
        className={`h-7 w-7 items-center justify-center rounded-full ${
          isCurrent ? 'bg-amber-accent' : 'border border-hairline'
        }`}
      >
        <Text className={`font-mono text-xs ${isCurrent ? 'text-wood-900' : 'text-muted-brown'}`}>
          {index + 1}
        </Text>
      </View>
      <View className="flex-1">
        <Text
          className={`font-sans-medium text-sm ${isCurrent ? 'text-amber-accent' : 'text-cream/80'}`}
          numberOfLines={1}
        >
          {label}
        </Text>
        <Text
          className={`font-sans text-xs ${isCurrent ? 'text-muted-brown' : 'text-muted2'}`}
          numberOfLines={1}
        >
          {sub}
        </Text>
      </View>
      <Text className="font-mono text-xs text-muted2">{duration}</Text>
    </View>
  )
}

export function TodaysPlanCard({
  plan,
  sessionMinutes,
  currentSlotIndex,
  onStart,
  busy,
  errorText,
}: {
  plan: PracticePlanPayload
  sessionMinutes: number
  currentSlotIndex: number
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
      </View>

      <View className="mb-4 gap-2">
        {plan.slots.map((slot, i) => (
          <StepRow
            key={`${slot.slot_type}-${i}`}
            index={i}
            label={stepLabel(slot)}
            sub={sublabel(slot)}
            duration={formatDuration(slot.duration_seconds)}
            isCurrent={i === currentSlotIndex}
          />
        ))}
      </View>

      {errorText ? <Text className="mb-3 font-sans text-sm text-danger">{errorText}</Text> : null}

      <AnimatedPressable
        onPress={onStart}
        disabled={busy}
        haptic="medium"
        className="flex-row items-center justify-center gap-2 self-stretch rounded-xl bg-amber-accent px-8 py-3.5 shadow-md disabled:opacity-50 sm:self-start"
        accessibilityRole="button"
        accessibilityLabel="Start today's practice session"
      >
        {busy ? <ActivityIndicator color="#1b120e" /> : null}
        <Text className="font-sans-medium text-base text-wood-900">{busy ? 'Starting…' : 'Start session'}</Text>
      </AnimatedPressable>
    </Animated.View>
  )
}
