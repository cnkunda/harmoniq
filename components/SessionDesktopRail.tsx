import { Text, View } from 'react-native'

import { SESSION_STEPS, type SessionStep } from '@/src/constants/sessionFlow'
import { PHASE_FOR_STEP } from '@/src/constants/sessionPhases'

const STEP_LABELS: Record<SessionStep, string> = {
  tune: 'Tune',
  'musical-tolerance': 'Feel',
  listen: 'Listen',
  study: 'Study',
  slow: 'Slow',
  play: 'Play',
  review: 'Review',
}

export interface SessionDesktopRailProps {
  activeStep: SessionStep
}

export function SessionDesktopRail({ activeStep }: SessionDesktopRailProps) {
  const activeIndex = SESSION_STEPS.indexOf(activeStep)
  return (
    <View className="hidden w-56 shrink-0 gap-0 border-r border-wood-600/20 bg-wood-900/40 px-4 py-6 md:flex">
      <Text className="mb-4 font-sans-medium text-[11px] uppercase tracking-widest text-cream/60">Session</Text>
      {SESSION_STEPS.map((step, i) => {
        const isActive = step === activeStep
        const isPast = i < activeIndex
        const isFuture = i > activeIndex
        return (
          <View key={step} className="flex-row gap-3">
            <View className="items-center">
              <View
                className={`h-7 w-7 items-center justify-center rounded-full border ${
                  isActive
                    ? 'border-amber-accent bg-amber-accent'
                    : isPast
                      ? 'border-amber-accent/50 bg-amber-accent/20'
                      : 'border-wood-600 bg-wood-800'
                }`}
              >
                <Text
                  className={`font-mono text-xs ${
                    isActive ? 'text-wood-900' : isPast ? 'text-amber-light' : 'text-muted-light'
                  }`}
                >
                  {isPast ? '✓' : i + 1}
                </Text>
              </View>
              {i < SESSION_STEPS.length - 1 ? (
                <View className={`mt-1 h-8 w-px ${isPast ? 'bg-amber-accent/40' : 'bg-wood-600/40'}`} />
              ) : null}
            </View>
            <View className="flex-1 pb-6 pt-1">
              <Text
                className={`font-sans-medium text-sm ${isActive ? 'text-cream' : isPast ? 'text-cream/70' : 'text-muted-light'}`}
              >
                {STEP_LABELS[step]}
              </Text>
              {PHASE_FOR_STEP[step] ? (
                <Text className="font-sans text-[11px] capitalize text-cream/40">{PHASE_FOR_STEP[step]}</Text>
              ) : (
                <Text className="font-sans text-[11px] text-cream/40">prep</Text>
              )}
            </View>
          </View>
        )
      })}
    </View>
  )
}
