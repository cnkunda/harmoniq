import { usePathname, useRouter } from 'expo-router'
import { ArrowRight, X } from 'lucide-react-native'
import { useState } from 'react'
import { Text, View } from 'react-native'
import { AnimatedPressable } from '@/components/AnimatedPressable'
import { Button } from '@/components/Button'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { Pill } from '@/components/Pill'
import { toast } from '@/components/ToastConfig'

import { colors } from '@/src/constants/colors'
import { MANDATORY_SESSION_STEPS, SESSION_STEPS, sessionStepIndexFromPathname } from '@/src/constants/sessionFlow'
import { DEMO_LESSON_JOB_ID } from '@/src/demo/constants'
import { abandonActivePlan } from '@/src/session/activePlanPersistence'
import { completePracticePlanSlot } from '@/src/session/planProgress'
import { useLessonStore } from '@/src/stores/lessonStore'
import { usePlanStore } from '@/src/stores/planStore'
import { useSessionPrefsStore } from '@/src/stores/sessionPrefsStore'

const BRAND_MIN = 80
const ACTION_MIN = 80

/**
 * Session stack top bar: brand, step progress (active = wide pill, rest = dots), plan next action.
 * Replaces the old `SessionStepIndicator` + `SessionPlanBar` row for a single mock-aligned header.
 */
export function SessionChromeBar() {
  const pathname = usePathname()
  const router = useRouter()
  const storePlan = usePlanStore((s) => s.currentPlan)
  const homePracticeMode = useSessionPrefsStore((s) => s.homePracticeMode)
  const plan = homePracticeMode === 'plan' ? storePlan : null
  const idx = usePlanStore((s) => s.currentSlotIndex)
  const saveLesson = useLessonStore((s) => s.saveLesson)
  const setLessonSectionIndex = useLessonStore((s) => s.setLessonSectionIndex)
  const lessonJobId = useLessonStore((s) => s.lesson?.job_id)
  const isDemoLesson = lessonJobId === DEMO_LESSON_JOB_ID
  const [confirmAction, setConfirmAction] = useState<'leave' | 'end' | null>(null)

  if (!pathname.includes('/session/')) return null

  const active = sessionStepIndexFromPathname(pathname)
  const showStepDots = active >= 0
  const currentStep = pathname.replace(/\/+$/, '').split('/').pop()
  const onTuneScreen = currentStep === 'tune'
  const onReviewScreen = currentStep === 'review'
  // Commit 163: progress bar uses the mandatory flow (listen is opt-in, not counted).
  const mandatoryIdx = MANDATORY_SESSION_STEPS.indexOf(currentStep as (typeof MANDATORY_SESSION_STEPS)[number])
  const progressDenom = MANDATORY_SESSION_STEPS.length
  const progressNumer = mandatoryIdx >= 0 ? mandatoryIdx + 1 : 1

  const closeSessionOrHome = () => {
    router.replace('/(tabs)')
  }

  const handleClose = () => {
    if (active >= 2) {
      setConfirmAction('leave')
    } else {
      closeSessionOrHome()
    }
  }

  const handleConfirmAction = () => {
    if (confirmAction === 'leave') {
      closeSessionOrHome()
    } else if (confirmAction === 'end' && plan) {
      void abandonActivePlan(plan.plan_id).then(closeSessionOrHome)
    }
    setConfirmAction(null)
  }
  const slot = plan?.slots?.[idx]
  const slots = plan?.slots
  const hasPlan = Boolean(slots?.length)
  const hasNext = hasPlan && slots != null && idx < slots.length - 1

  const goNextSection = () => {
    void completePracticePlanSlot({
      router,
      deps: { saveLesson, setLessonSectionIndex },
      slotIndex: idx,
      performance: null,
    }).catch((e: unknown) => {
      toast.error(e instanceof Error ? e.message : 'Could not continue the practice plan.')
    })
  }

  return (
    <View className="border-b border-wood-600/20 bg-wood-800/40">
      <View className="flex-row items-center px-4 py-3">
        <View style={{ minWidth: BRAND_MIN }}>
          <View className="flex-row flex-wrap items-center gap-2">
            <AnimatedPressable
              haptic="light"
              onPress={() => router.push('/(tabs)')}
              accessibilityRole="button"
              accessibilityLabel="Home"
            >
              <Text className="font-serif text-lg text-cream">Harmoniq</Text>
            </AnimatedPressable>
            {isDemoLesson ? (
              <Pill variant="accent" size="xs" textClassName="uppercase tracking-wider">
                Demo
              </Pill>
            ) : null}
          </View>
        </View>

        {showStepDots ? (
          <View
            className="flex-1 flex-row items-center justify-center px-1"
            accessibilityLabel={active >= 0 ? `Step ${progressNumer} of ${progressDenom}` : undefined}
            accessibilityRole="progressbar"
          >
            <View className="h-1.5 w-full max-w-[160px] overflow-hidden rounded-full bg-wood-700/60">
              <View
                className="h-full rounded-full bg-amber-accent"
                style={{ width: `${Math.max(0, Math.min(100, (progressNumer / progressDenom) * 100))}%` }}
              />
            </View>
          </View>
        ) : (
          <View className="flex-1" />
        )}

        <View style={{ minWidth: ACTION_MIN, alignItems: 'flex-end' }}>
          {onTuneScreen ? (
            <View className="items-end gap-1">
              <AnimatedPressable
                haptic="light"
                onPress={handleClose}
                accessibilityRole="button"
                accessibilityLabel="Close session"
                hitSlop={10}
                className="h-10 w-10 items-center justify-center rounded-full bg-wood-700/40 active:bg-wood-600/40"
              >
                <X color={colors.cream} size={20} strokeWidth={2} />
              </AnimatedPressable>
              {hasPlan && hasNext && !onReviewScreen ? (
                <Button
                  label="Next section"
                  variant="ghost"
                  size="sm"
                  haptic="light"
                  onPress={goNextSection}
                  accessibilityLabel="Go to next section in practice plan"
                  icon={<ArrowRight color={colors.cream} size={14} strokeWidth={2} />}
                  className="px-2"
                />
              ) : null}
            </View>
          ) : (
            <View className="flex-row items-center gap-2">
              {hasPlan ? (
                onReviewScreen ? null : hasNext ? (
                  <Button
                    label="Next section"
                    variant="ghost"
                    size="sm"
                    haptic="light"
                    onPress={goNextSection}
                    accessibilityLabel="Go to next section in practice plan"
                    icon={<ArrowRight color={colors.cream} size={14} strokeWidth={2} />}
                    className="px-2"
                  />
                ) : (
                  <Button
                    label="End plan"
                    variant="ghost"
                    size="sm"
                    haptic="light"
                    onPress={() => setConfirmAction('end')}
                    accessibilityLabel="End practice plan"
                    labelProps={{ className: 'text-danger' }}
                    className="px-2"
                  />
                )
              ) : null}
               <AnimatedPressable
                 haptic="light"
                 onPress={handleClose}
                 accessibilityRole="button"
                 accessibilityLabel="Close session"
                 hitSlop={10}
                 className="h-10 w-10 items-center justify-center rounded-full bg-wood-700/40 active:bg-wood-600/40"
               >
                 <X color={colors.cream} size={20} strokeWidth={2} />
               </AnimatedPressable>
            </View>
          )}
        </View>
      </View>

      {hasPlan && slots != null ? (
        <Text className="border-t border-wood-600/20 px-4 py-2 font-sans text-xs text-muted-brown" numberOfLines={1}>
          Plan · {idx + 1}/{slots.length}: {slot?.title ?? '—'}
        </Text>
      ) : null}

      <ConfirmDialog
        visible={confirmAction != null}
        title={confirmAction === 'end' ? 'End this practice plan?' : 'Leave this lesson?'}
        message={
          confirmAction === 'end'
            ? 'The active plan will be cleared and you will return home. Completed results stay in your history.'
            : 'Your progress in this lesson is saved.'
        }
        confirmLabel={confirmAction === 'end' ? 'End plan' : 'Leave'}
        destructive
        onConfirm={handleConfirmAction}
        onCancel={() => setConfirmAction(null)}
      />
    </View>
  )
}
