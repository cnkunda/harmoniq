import { RefreshCw, RotateCcw } from 'lucide-react-native'
import { useState } from 'react'
import { Text, View } from 'react-native'
import Animated, { FadeInDown } from 'react-native-reanimated'

import { Button } from '@/components/Button'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { LoadingSkeleton } from '@/components/LoadingSkeleton'
import { colors } from '@/src/constants/colors'
import type { DrillSlotPayload, PracticePlanPayload } from '@/src/types'

function stepLabel(slot: DrillSlotPayload): string {
  if (slot.slot_type === 'free_jam') return 'Free jam'
  if (slot.slot_type === 'warmup') return 'Warm-up'
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
  const base =
    slot.slot_type === 'warmup'
      ? 'Finger warm-up'
      : slot.slot_type === 'free_jam'
        ? 'Open practice'
        : slot.title.trim() || (slot.slot_type === 'technique' ? 'Technique practice' : 'Section practice')
  if (slot.intent === 'remediation') return `Remediation · ${base}`
  if (slot.intent === 'review') return `Review · ${base.replace(/\s+review$/i, '')}`
  return base
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
  mode = 'preview',
  onRegenerate,
  regenerateBusy,
  onReset,
}: {
  plan: PracticePlanPayload
  sessionMinutes: number
  currentSlotIndex: number
  onStart: () => void
  busy?: boolean
  errorText?: string | null
  mode?: 'preview' | 'resume'
  onRegenerate?: () => void
  regenerateBusy?: boolean
  onReset?: () => Promise<void>
}) {
  const isResume = mode === 'resume'
  const [resetConfirmVisible, setResetConfirmVisible] = useState(false)
  const [resetBusy, setResetBusy] = useState(false)

  const handleConfirmReset = async () => {
    if (!onReset) return
    setResetBusy(true)
    try {
      await onReset()
    } finally {
      setResetBusy(false)
      setResetConfirmVisible(false)
    }
  }

  return (
    <Animated.View entering={FadeInDown.duration(380).delay(40)}>
      <View className="mb-4 flex-row items-start justify-between gap-3">
        <View className="min-w-0 flex-1">
          <Text className="mb-1 font-serif text-2xl text-cream">
            {isResume ? `Resume your ${sessionMinutes}-min session` : `Your ${sessionMinutes}-min session`}
          </Text>
          <Text className="font-sans text-sm text-amber-light/80">
            {isResume
              ? `Step ${currentSlotIndex + 1} of ${plan.slots.length} · pick up where you left off`
              : `${plan.slots.length} steps · guided path`}
          </Text>
        </View>
        {isResume && onReset ? (
          <Button
            label="Reset"
            variant="danger"
            size="sm"
            icon={<RotateCcw color={colors.danger} size={14} strokeWidth={2} />}
            onPress={() => setResetConfirmVisible(true)}
            accessibilityLabel="Reset this practice session"
          />
        ) : !isResume && onRegenerate ? (
          <Button
            label={regenerateBusy ? 'Updating…' : 'Regenerate'}
            variant="secondary"
            size="sm"
            loading={regenerateBusy}
            icon={<RefreshCw color={colors.cream} size={14} strokeWidth={2} />}
            onPress={onRegenerate}
            accessibilityLabel="Regenerate practice plan"
          />
        ) : null}
      </View>

      <View className="mb-4 gap-2">
        {plan.slots.map((slot, i) => (
          <StepRow
            key={slot.slot_id ?? `${slot.slot_type}-${i}`}
            index={i}
            label={stepLabel(slot)}
            sub={sublabel(slot)}
            duration={formatDuration(slot.duration_seconds)}
            isCurrent={i === currentSlotIndex}
          />
        ))}
      </View>

      {errorText ? <Text className="mb-3 font-sans text-sm text-danger">{errorText}</Text> : null}

      <Button
        label={busy ? (isResume ? 'Resuming…' : 'Starting…') : isResume ? 'Resume session' : 'Start session'}
        variant="primary"
        size="lg"
        loading={busy}
        onPress={onStart}
        accessibilityLabel={isResume ? "Resume today's practice session" : "Start today's practice session"}
        containerClassName="self-stretch sm:self-start"
      />

      <ConfirmDialog
        visible={resetConfirmVisible}
        title="Reset this session?"
        message="This clears the current plan progress and generates a fresh plan. This cannot be undone."
        confirmLabel="Reset session"
        destructive
        busy={resetBusy}
        onConfirm={() => void handleConfirmReset()}
        onCancel={() => setResetConfirmVisible(false)}
      />
    </Animated.View>
  )
}
